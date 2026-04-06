from __future__ import annotations

from polymarket_mcp.utils.safety_limits import ExposureCalculator, MarketData, OrderRequest, Position, SafetyLimits


def _limits(**overrides):
    base = SafetyLimits(
        max_order_size_usd=1000.0,
        max_total_exposure_usd=5000.0,
        max_position_size_per_market=2000.0,
        min_liquidity_required=100.0,
        max_spread_tolerance=0.1,
        require_confirmation_above_usd=500.0,
        auto_cancel_on_large_spread=True,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _order(price: float = 0.5, size: float = 100.0, side: str = "BUY") -> OrderRequest:
    return OrderRequest(token_id="tok", market_id="m1", side=side, price=price, size=size)


def _market(best_bid: float = 0.5, best_ask: float = 0.52, liq: float = 1000.0) -> MarketData:
    return MarketData(market_id="m1", token_id="tok", best_bid=best_bid, best_ask=best_ask, bid_liquidity=liq / 2, ask_liquidity=liq / 2)


def test_confirmation_requirement_switches_on_autonomous_mode() -> None:
    limits = _limits()
    order = _order(price=1.0, size=600.0)

    assert limits.should_require_confirmation(order, autonomous_trading_enabled=False) is True
    assert limits.should_require_confirmation(order, autonomous_trading_enabled=True) is False


def test_validate_order_rejects_each_limit_type() -> None:
    limits = _limits()

    ok, reason = limits.validate_order(_order(price=1.0, size=2000.0), [], _market())
    assert ok is False
    assert reason is not None and "max order" in reason

    positions = [Position(token_id="x", market_id="m2", size=1.0, value_usd=4900.0)]
    ok, reason = limits.validate_order(_order(price=1.0, size=200.0), positions, _market())
    assert ok is False
    assert reason is not None and "total exposure" in reason

    positions = [Position(token_id="x", market_id="m1", size=1.0, value_usd=1950.0)]
    ok, reason = limits.validate_order(_order(price=1.0, size=100.0), positions, _market())
    assert ok is False
    assert reason is not None and "market exposure" in reason

    ok, reason = limits.validate_order(_order(price=1.0, size=10.0), [], _market(liq=10.0))
    assert ok is False
    assert reason is not None and "insufficient liquidity" in reason

    ok, reason = limits.validate_order(_order(price=1.0, size=10.0), [], _market(best_bid=0.5, best_ask=1.0))
    assert ok is False
    assert reason is not None and "spread" in reason


def test_validate_order_success_and_exposure_calculator_paths() -> None:
    limits = _limits()
    ok, reason = limits.validate_order(_order(price=0.5, size=10.0), [], _market())
    assert ok is True
    assert reason is None

    buy = ExposureCalculator.calculate_order_impact(100.0, _order(price=0.5, size=10.0, side="BUY"), [])
    assert buy.after_usd > buy.before_usd
    assert buy.is_increase is True

    sell_open_short = ExposureCalculator.calculate_order_impact(100.0, _order(price=0.5, size=10.0, side="SELL"), [])
    assert sell_open_short.after_usd > sell_open_short.before_usd

    positions = [Position(token_id="tok", market_id="m1", size=1.0, value_usd=200.0)]
    sell_close_long = ExposureCalculator.calculate_order_impact(300.0, _order(price=0.5, size=100.0, side="SELL"), positions)
    assert sell_close_long.after_usd < sell_close_long.before_usd

    assert SafetyLimits._calculate_total_exposure([
        Position(token_id="a", market_id="m1", size=1.0, value_usd=10.0),
        Position(token_id="b", market_id="m2", size=1.0, value_usd=-20.0),
    ]) == 30.0
