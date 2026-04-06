from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import polymarket_mcp.server as server
from polymarket_mcp.models import BetDecision, BetSide, ExecutedAction

from ._helpers import make_settings


def test_server_context_status_and_close(monkeypatch) -> None:
    settings = make_settings()

    class _Signal:
        def __init__(self, _s):
            self.closed = False

        def close(self):
            self.closed = True

    class _Market:
        def __init__(self, _s):
            self.closed = False

        def close(self):
            self.closed = True

    class _Strategy:
        def __init__(self, _s):
            pass

    class _Execution:
        def __init__(self, _s):
            pass

    class _Auth:
        def __init__(self, _s):
            pass

        def get_or_create_api_credentials(self):
            return None

    class _RL:
        def __init__(self):
            pass

    monkeypatch.setattr(server, "SignalClient", _Signal)
    monkeypatch.setattr(server, "MarketClient", _Market)
    monkeypatch.setattr(server, "Strategy", _Strategy)
    monkeypatch.setattr(server, "ExecutionEngine", _Execution)
    monkeypatch.setattr(server, "PolymarketAuthClient", _Auth)
    monkeypatch.setattr(server, "RateLimiter", _RL)

    ctx = server.create_server_context(settings)

    status = ctx.status()
    assert status["authenticated"] is False
    assert status["mode"] == "read-only"

    server.close_server_context(ctx)
    assert cast(Any, ctx.signal_client).closed is True
    assert cast(Any, ctx.market_client).closed is True


def test_run_cycle_once_counts_and_action_shape() -> None:
    class _RL:
        def acquire(self, _cat):
            return 0.25

    class _Sig:
        def fetch_all(self):
            return [object(), object()]

    class _Mkt:
        def list_candidate_markets(self, _k):
            return [object()]

    class _Strat:
        def decide(self, _inp):
            return [object()]

    class _Exec:
        def execute(self, _decisions):
            return [ExecutedAction(status="dry_run_order", details={"market_id": "m1"})]

    class _Ctx:
        settings = make_settings(signal_keywords=["trump"])
        rate_limiter = _RL()
        signal_client = _Sig()
        market_client = _Mkt()
        strategy = _Strat()
        execution = _Exec()

    out = server.run_cycle_once(cast(Any, _Ctx()))

    assert out["wait_time_ms"] == 250.0
    assert out["signal_count"] == 2
    assert out["market_count"] == 1
    assert out["decision_count"] == 1
    assert out["action_count"] == 1
    actions = cast(list[dict[str, object]], out["actions"])
    assert actions[0]["status"] == "dry_run_order"


def test_submit_order_confirmation_and_direct_execute_paths() -> None:
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.5,
        usd_size=600.0,
        confidence=0.9,
        reason="r",
    )

    class _LimitsConfirm:
        def validate_order(self, *_args):
            return True, None

        def should_require_confirmation(self, *_args, **_kwargs) -> bool:
            return True

    class _Exec:
        def execute(self, _d):
            return [ExecutedAction(status="live_order_submitted", details={"order_id": "oid"})]

    class _Ctx:
        settings = make_settings(require_confirmation_above_usd=500.0, min_liquidity_required=10.0)
        safety_limits = _LimitsConfirm()
        pending_confirmations = {}
        execution = _Exec()

    out = server.submit_order_with_confirmation(cast(Any, _Ctx()), decision)
    assert out["ok"] is True
    assert out["requires_confirmation"] is True
    assert "confirmation_id" in out

    class _LimitsDirect(_LimitsConfirm):
        def should_require_confirmation(self, *_args, **_kwargs) -> bool:
            return False

    class _Ctx2(_Ctx):
        safety_limits = _LimitsDirect()

    out2 = server.submit_order_with_confirmation(cast(Any, _Ctx2()), decision)
    assert out2["ok"] is True
    assert out2["requires_confirmation"] is False
    actions2 = cast(list[dict[str, object]], out2["actions"])
    assert actions2[0]["status"] == "live_order_submitted"


def test_submit_order_rejects_safety_validation() -> None:
    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.5,
        usd_size=10.0,
        confidence=0.8,
        reason="r",
    )

    class _Limits:
        def validate_order(self, *_args):
            return False, "bad spread"

        def should_require_confirmation(self, *_args, **_kwargs):
            return False

    class _Ctx:
        settings = make_settings(min_liquidity_required=10.0)
        safety_limits = _Limits()
        pending_confirmations = {}
        execution = object()

    out = server.submit_order_with_confirmation(cast(Any, _Ctx()), decision)
    assert out["ok"] is False
    assert out["error_category"] == "safety"


def test_confirm_order_not_found_expired_and_success() -> None:
    class _Exec:
        def execute(self, _d):
            return [ExecutedAction(status="dry_run_order", details={"x": 1})]

    class _Ctx:
        pending_confirmations = {}
        execution = _Exec()

    ctx = _Ctx()

    missing = server.confirm_order(cast(Any, ctx), "none")
    assert missing["ok"] is False
    assert missing["error_category"] == "not_found"

    decision = BetDecision(
        market_id="m1",
        token_id="tok1",
        side=BetSide.BUY,
        price=0.5,
        usd_size=10.0,
        confidence=0.8,
        reason="r",
    )
    expired_id = "confirm_expired"
    ctx.pending_confirmations[expired_id] = server.PendingConfirmation(
        confirmation_id=expired_id,
        decision=decision,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    expired = server.confirm_order(cast(Any, ctx), expired_id)
    assert expired["ok"] is False
    assert expired["error_category"] == "expired"
    assert expired_id not in ctx.pending_confirmations

    ok_id = "confirm_ok"
    ctx.pending_confirmations[ok_id] = server.PendingConfirmation(
        confirmation_id=ok_id,
        decision=decision,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    ok = server.confirm_order(cast(Any, ctx), ok_id)
    assert ok["ok"] is True
    assert ok["confirmation_id"] == ok_id
    assert ok_id not in ctx.pending_confirmations


def test_demo_decision_and_runtime_bot(monkeypatch) -> None:
    class _Ctx:
        settings = make_settings(max_usd_per_bet=300.0, require_confirmation_above_usd=250.0)

    decision = server.demo_decision(cast(Any, _Ctx()))
    assert decision.market_id == "demo-market"
    assert decision.side == BetSide.BUY
    assert decision.usd_size == 260.0

    class _Bot:
        def __init__(self, settings):
            self.settings = settings

    monkeypatch.setattr(server, "PolymarketBot", _Bot)
    bot = server.create_runtime_bot(cast(Any, _Ctx()))
    assert bot.settings is _Ctx.settings
