from __future__ import annotations

import pytest

from polymarket_mcp.utils.safety_limits import ExposureCalculator, MarketData, OrderRequest, Position, SafetyLimits


def _limits() -> SafetyLimits:
    return SafetyLimits(
        max_order_size_usd=1000.0,
        max_total_exposure_usd=5000.0,
        max_position_size_per_market=2000.0,
        min_liquidity_required=10000.0,
        max_spread_tolerance=0.05,
        require_confirmation_above_usd=500.0,
    )


def _market() -> MarketData:
    return MarketData(
        market_id="m1",
        token_id="t1",
        best_bid=0.49,
        best_ask=0.50,
        bid_liquidity=6000.0,
        ask_liquidity=7000.0,
    )


@pytest.mark.parametrize(
    "positions,side,size,price,expected_delta",
    [
        ([], "BUY", 100.0, 1.0, 100.0),
        ([Position(token_id="t1", market_id="m1", size=100, value_usd=100.0)], "SELL", 50.0, 1.0, -50.0),
        ([Position(token_id="t1", market_id="m1", size=-50, value_usd=-50.0)], "SELL", 100.0, 1.0, 100.0),
        ([], "SELL", 100.0, 1.0, 100.0),
    ],
)
def test_exposure_calculation_scenarios(
    positions: list[Position],
    side: str,
    size: float,
    price: float,
    expected_delta: float,
) -> None:
    impact = ExposureCalculator.calculate_order_impact(
        current_exposure=500.0,
        order=OrderRequest(token_id="t1", market_id="m1", side=side, price=price, size=size),
        current_positions=positions,
    )
    assert impact.delta_usd == pytest.approx(expected_delta)
    assert impact.is_increase == (expected_delta > 0)


def test_gate_order_size_limit() -> None:
    valid, message = _limits().validate_order(
        OrderRequest(token_id="t1", market_id="m1", side="BUY", price=0.5, size=2100.0),
        [],
        _market(),
    )
    assert valid is False
    assert message is not None and "max order" in message


def test_gate_total_exposure_limit() -> None:
    valid, message = _limits().validate_order(
        OrderRequest(token_id="t1", market_id="m1", side="BUY", price=1.0, size=500.0),
        [Position(token_id="x", market_id="x", size=1.0, value_usd=4900.0)],
        _market(),
    )
    assert valid is False
    assert message is not None and "total exposure" in message


def test_gate_market_exposure_limit() -> None:
    valid, message = _limits().validate_order(
        OrderRequest(token_id="t1", market_id="m1", side="BUY", price=1.0, size=100.0),
        [Position(token_id="t1", market_id="m1", size=1.0, value_usd=1950.0)],
        _market(),
    )
    assert valid is False
    assert message is not None and "market exposure" in message


def test_gate_liquidity_limit() -> None:
    bad_market = MarketData(
        market_id="m1",
        token_id="t1",
        best_bid=0.49,
        best_ask=0.50,
        bid_liquidity=100.0,
        ask_liquidity=100.0,
    )
    valid, message = _limits().validate_order(
        OrderRequest(token_id="t1", market_id="m1", side="BUY", price=1.0, size=10.0),
        [],
        bad_market,
    )
    assert valid is False
    assert message is not None and "liquidity" in message


def test_gate_spread_limit() -> None:
    wide_spread_market = MarketData(
        market_id="m1",
        token_id="t1",
        best_bid=0.40,
        best_ask=0.50,
        bid_liquidity=10000.0,
        ask_liquidity=10000.0,
    )
    valid, message = _limits().validate_order(
        OrderRequest(token_id="t1", market_id="m1", side="BUY", price=0.5, size=10.0),
        [],
        wide_spread_market,
    )
    assert valid is False
    assert message is not None and "spread" in message


def test_confirmation_threshold_respected() -> None:
    limits = _limits()
    order = OrderRequest(token_id="t1", market_id="m1", side="BUY", price=1.0, size=600.0)
    assert limits.should_require_confirmation(order, autonomous_trading_enabled=False) is True
    assert limits.should_require_confirmation(order, autonomous_trading_enabled=True) is False
