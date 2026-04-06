from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .auth.client import PolymarketAuthClient
from .bot import PolymarketBot
from .config import Settings, load_settings
from .execution import ExecutionEngine
from .models import BetDecision, BetSide
from .polymarket_client import MarketClient
from .sources import SignalClient
from .strategy import Strategy, StrategyInput
from .utils.rate_limiter import EndpointCategory, RateLimiter
from .utils.safety_limits import MarketData, OrderRequest, Position, SafetyLimits


@dataclass
class PendingConfirmation:
    confirmation_id: str
    decision: BetDecision
    created_at: datetime
    expires_at: datetime


@dataclass
class ServerContext:
    settings: Settings
    signal_client: SignalClient
    market_client: MarketClient
    strategy: Strategy
    execution: ExecutionEngine
    auth_client: PolymarketAuthClient
    rate_limiter: RateLimiter
    safety_limits: SafetyLimits
    pending_confirmations: dict[str, PendingConfirmation]
    positions: dict[str, Position]

    @property
    def is_authenticated(self) -> bool:
        creds = self.auth_client.get_or_create_api_credentials()
        return creds is not None

    def status(self) -> dict[str, object]:
        return {
            "authenticated": self.is_authenticated,
            "mode": "full" if self.is_authenticated else "read-only",
            "pending_confirmations": len(self.pending_confirmations),
            "positions": len(self.positions),
            "signal_services": self.settings.signal_services,
            "market_services": self.settings.market_services,
        }

    def positions_list(self) -> list[Position]:
        return list(self.positions.values())


def create_server_context(settings: Settings | None = None) -> ServerContext:
    resolved = settings or load_settings()
    safety_limits = SafetyLimits(
        max_order_size_usd=resolved.max_order_size_usd,
        max_total_exposure_usd=resolved.max_total_exposure_usd,
        max_position_size_per_market=resolved.max_position_size_per_market,
        min_liquidity_required=resolved.min_liquidity_required,
        max_spread_tolerance=resolved.max_spread_tolerance,
        require_confirmation_above_usd=resolved.require_confirmation_above_usd,
    )
    return ServerContext(
        settings=resolved,
        signal_client=SignalClient(resolved),
        market_client=MarketClient(resolved),
        strategy=Strategy(resolved),
        execution=ExecutionEngine(resolved),
        auth_client=PolymarketAuthClient(resolved),
        rate_limiter=RateLimiter(),
        safety_limits=safety_limits,
        pending_confirmations={},
        positions={},
    )


def close_server_context(context: ServerContext) -> None:
    context.signal_client.close()
    context.market_client.close()


def run_cycle_once(context: ServerContext) -> dict[str, object]:
    wait = context.rate_limiter.acquire(EndpointCategory.MARKET_DATA)
    signals = context.signal_client.fetch_all()
    markets = context.market_client.list_candidate_markets(context.settings.signal_keywords)
    decisions = context.strategy.decide(StrategyInput(signals=signals, markets=markets))
    actions = context.execution.execute(decisions)
    return {
        "wait_time_ms": wait * 1000.0,
        "signal_count": len(signals),
        "market_count": len(markets),
        "decision_count": len(decisions),
        "action_count": len(actions),
        "actions": [action.details | {"status": action.status} for action in actions],
    }


def submit_order_with_confirmation(context: ServerContext, decision: BetDecision) -> dict[str, object]:
    market_data = MarketData(
        market_id=decision.market_id,
        token_id=decision.token_id,
        best_bid=max(0.01, decision.price - 0.01),
        best_ask=min(0.99, decision.price + 0.01),
        bid_liquidity=context.settings.min_liquidity_required,
        ask_liquidity=context.settings.min_liquidity_required,
    )
    order = OrderRequest(
        token_id=decision.token_id,
        market_id=decision.market_id,
        side=decision.side.value,
        price=decision.price,
        size=max(1.0, decision.usd_size / max(decision.price, 0.01)),
    )
    current_positions = _context_positions(context)
    valid, reason = context.safety_limits.validate_order(order, current_positions, market_data)
    if not valid:
        return {
            "ok": False,
            "error": reason or "validation failed",
            "error_category": "safety",
        }

    requires_confirmation = context.safety_limits.should_require_confirmation(
        order,
        autonomous_trading_enabled=context.settings.enable_autonomous_trading,
    )
    if requires_confirmation:
        confirmation_id = f"confirm_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        context.pending_confirmations[confirmation_id] = PendingConfirmation(
            confirmation_id=confirmation_id,
            decision=decision,
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        return {
            "ok": True,
            "requires_confirmation": True,
            "confirmation_id": confirmation_id,
            "order_value_usd": decision.usd_size,
            "threshold_usd": context.settings.require_confirmation_above_usd,
        }

    result = context.execution.execute([decision])
    _apply_position_update(context, decision)
    return {
        "ok": True,
        "requires_confirmation": False,
        "actions": [action.details | {"status": action.status} for action in result],
    }


def confirm_order(context: ServerContext, confirmation_id: str) -> dict[str, object]:
    pending = context.pending_confirmations.get(confirmation_id)
    if pending is None:
        return {
            "ok": False,
            "error": "confirmation id not found",
            "error_category": "not_found",
        }

    now = datetime.now(timezone.utc)
    if pending.expires_at < now:
        del context.pending_confirmations[confirmation_id]
        return {
            "ok": False,
            "error": "confirmation expired",
            "error_category": "expired",
        }

    result = context.execution.execute([pending.decision])
    _apply_position_update(context, pending.decision)
    del context.pending_confirmations[confirmation_id]
    return {
        "ok": True,
        "confirmation_id": confirmation_id,
        "actions": [action.details | {"status": action.status} for action in result],
    }


def _apply_position_update(context: ServerContext, decision: BetDecision) -> None:
    value = round(decision.usd_size, 8)
    positions = _context_positions_map(context)
    existing = positions.get(decision.token_id)
    if existing is None:
        signed = value if decision.side == BetSide.BUY else -value
        positions[decision.token_id] = Position(
            token_id=decision.token_id,
            market_id=decision.market_id,
            size=signed,
            value_usd=signed,
        )
        return

    if decision.side == BetSide.BUY:
        new_size = existing.size + value
    else:
        new_size = existing.size - value

    if abs(new_size) < 1e-9:
        del positions[decision.token_id]
        return

    positions[decision.token_id] = Position(
        token_id=existing.token_id,
        market_id=existing.market_id,
        size=new_size,
        value_usd=new_size,
    )


def _context_positions(context: ServerContext) -> list[Position]:
    positions_attr = getattr(context, "positions", None)
    if isinstance(positions_attr, dict):
        return list(positions_attr.values())
    if hasattr(context, "positions_list"):
        result = context.positions_list()
        if isinstance(result, list):
            return [item for item in result if isinstance(item, Position)]
    return []


def _context_positions_map(context: ServerContext) -> dict[str, Position]:
    positions_attr = getattr(context, "positions", None)
    if isinstance(positions_attr, dict):
        return positions_attr
    positions: dict[str, Position] = {}
    setattr(context, "positions", positions)
    return positions


def demo_decision(context: ServerContext) -> BetDecision:
    return BetDecision(
        market_id="demo-market",
        token_id="demo-token",
        side=BetSide.BUY,
        price=0.55,
        usd_size=min(context.settings.max_usd_per_bet, context.settings.require_confirmation_above_usd + 10),
        confidence=0.8,
        reason="demo-decision",
    )


def create_runtime_bot(context: ServerContext) -> PolymarketBot:
    return PolymarketBot(context.settings)
