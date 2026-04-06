from __future__ import annotations

from polymarket_bot.config import Settings
from polymarket_bot.execution import ExecutionEngine
from polymarket_bot.models import BetDecision, BetSide


def _settings() -> Settings:
    return Settings(
        poll_interval_seconds=20,
        dry_run=True,
        enable_live_trading=False,
        max_usd_per_bet=5.0,
        max_bets_per_hour=1,
        market_limit=50,
        min_confidence=0.65,
        signal_keywords=["trump"],
        signal_lookback_minutes=60,
        x_bearer_token=None,
        gamma_base_url="https://gamma-api.polymarket.com",
        clob_host="https://clob.polymarket.com",
        chain_id=137,
        private_key=None,
        funder_address=None,
        signature_type=1,
        poly_api_key=None,
        poly_api_secret=None,
        poly_api_passphrase=None,
    )


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
