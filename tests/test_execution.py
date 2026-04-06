from __future__ import annotations

from datetime import timedelta

from polymarket_mcp.config import Settings
from polymarket_mcp.execution import ExecutionEngine
from polymarket_mcp.models import BetDecision, BetSide, utc_now

from ._helpers import make_settings


def _settings() -> Settings:
    return make_settings(max_bets_per_hour=1, signal_keywords=["trump"])


def test_execution_applies_rate_limit() -> None:
    engine = ExecutionEngine(_settings())
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.45,
        usd_size=5.0,
        confidence=0.8,
        reason="test",
    )

    actions1 = engine.execute([decision])
    actions2 = engine.execute([decision])

    assert actions1[0].status == "dry_run_order"
    assert actions2[0].status == "skipped_rate_limit"


def test_execution_rejects_invalid_decision_payload() -> None:
    engine = ExecutionEngine(_settings())
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=1.2,
        usd_size=5.0,
        confidence=0.8,
        reason="bad-price",
    )

    actions = engine.execute([decision])

    assert actions[0].status == "skipped_invalid_decision"


def test_execution_live_order_success(monkeypatch) -> None:
    settings = make_settings(dry_run=False, enable_live_trading=True)
    engine = ExecutionEngine(settings)
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.5,
        usd_size=5.0,
        confidence=0.8,
        reason="live",
    )

    monkeypatch.setattr(engine, "_live_order", lambda _d: "oid-123")
    actions = engine.execute([decision])

    assert actions[0].status == "live_order_submitted"
    assert actions[0].details["order_id"] == "oid-123"


def test_execution_live_order_failure(monkeypatch) -> None:
    settings = make_settings(dry_run=False, enable_live_trading=True)
    engine = ExecutionEngine(settings)
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.5,
        usd_size=5.0,
        confidence=0.8,
        reason="live",
    )

    def _raise(_decision: BetDecision) -> str:
        raise RuntimeError("submission failed")

    monkeypatch.setattr(engine, "_live_order", _raise)
    actions = engine.execute([decision])

    assert actions[0].status == "live_order_failed"
    assert "submission failed" in str(actions[0].details["reason"])


def test_execution_rate_limit_evicts_old_timestamps() -> None:
    engine = ExecutionEngine(_settings())
    engine.executed_timestamps.append(utc_now() - timedelta(hours=2))

    assert engine._allow_by_rate_limit() is True
    assert len(engine.executed_timestamps) == 0


def test_execution_skips_risk_limit_when_usd_size_too_large() -> None:
    engine = ExecutionEngine(_settings())
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.45,
        usd_size=999.0,
        confidence=0.8,
        reason="risk",
    )

    actions = engine.execute([decision])
    assert actions[0].status == "skipped_risk_limit"


def test_execution_validate_decision_all_error_branches() -> None:
    engine = ExecutionEngine(_settings())

    bad_market = BetDecision("", "tok", BetSide.BUY, 0.5, 1.0, 0.5, "r")
    assert engine._validate_decision(bad_market) == "missing market_id"

    bad_token = BetDecision("m", "", BetSide.BUY, 0.5, 1.0, 0.5, "r")
    assert engine._validate_decision(bad_token) == "missing token_id"

    bad_price = BetDecision("m", "t", BetSide.BUY, 0.0, 1.0, 0.5, "r")
    assert engine._validate_decision(bad_price) == "price must be between 0 and 1"

    bad_size = BetDecision("m", "t", BetSide.BUY, 0.5, 0.0, 0.5, "r")
    assert engine._validate_decision(bad_size) == "usd_size must be positive"

    bad_conf = BetDecision("m", "t", BetSide.BUY, 0.5, 1.0, 2.0, "r")
    assert engine._validate_decision(bad_conf) == "confidence must be between 0 and 1"


def test_execution_live_order_import_error(monkeypatch) -> None:
    settings = make_settings(
        dry_run=False,
        enable_live_trading=True,
        private_key="pk",
        funder_address="fa",
    )
    engine = ExecutionEngine(settings)
    decision = BetDecision("m1", "tok1", BetSide.BUY, 0.5, 5.0, 0.8, "live")

    def _import_fail(_name: str):
        raise ImportError("missing")

    monkeypatch.setattr("polymarket_mcp.execution.import_module", _import_fail)
    actions = engine.execute([decision])
    assert actions[0].status == "live_order_failed"
    assert "py-clob-client is not installed" in str(actions[0].details["reason"])


def test_execution_live_order_missing_required_keys(monkeypatch) -> None:
    settings = make_settings(dry_run=False, enable_live_trading=True, private_key=None, funder_address=None)
    engine = ExecutionEngine(settings)
    decision = BetDecision("m1", "tok1", BetSide.BUY, 0.5, 5.0, 0.8, "live")

    class _Dummy:
        class ClobClient:
            pass

        class ApiCreds:
            pass

        class OrderArgs:
            pass

        class OrderType:
            GTC = "GTC"

        BUY = "BUY"

    def _import_ok(name: str):
        if name.endswith(".client"):
            return type("X", (), {"ClobClient": _Dummy.ClobClient})
        if name.endswith(".clob_types"):
            return type("Y", (), {"ApiCreds": _Dummy.ApiCreds, "OrderArgs": _Dummy.OrderArgs, "OrderType": _Dummy.OrderType})
        return type("Z", (), {"BUY": _Dummy.BUY})

    monkeypatch.setattr("polymarket_mcp.execution.import_module", _import_ok)
    actions = engine.execute([decision])
    assert actions[0].status == "live_order_failed"
    assert "Missing POLYMARKET_PRIVATE_KEY" in str(actions[0].details["reason"])
