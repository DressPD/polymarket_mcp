from __future__ import annotations

from datetime import timedelta

from polymarket_mcp.models import CandidateMarket, SignalItem, SignalSource, utc_now
from polymarket_mcp.strategy import Strategy, StrategyInput

from ._helpers import make_settings


def _settings(min_confidence: float = 0.65):
    return make_settings(min_confidence=min_confidence)


def test_strategy_creates_buy_decision_for_matching_signal() -> None:
    now = utc_now()
    strategy = Strategy(_settings())
    signals = [
        SignalItem(
            source=SignalSource.X,
            source_id="1",
            url="https://x.com/i/web/status/1",
            author="a",
            text="Trump campaign update",
            published_at=now - timedelta(minutes=2),
            fetched_at=now,
        )
    ]
    markets = [
        CandidateMarket(
            market_id="m1",
            question="Will Trump win election?",
            slug="trump-win-election",
            yes_token_id="tok1",
            best_ask=0.55,
            best_bid=0.54,
            volume_24h=10000,
            liquidity=5000,
            min_tick_size=0.01,
            neg_risk=False,
            enable_order_book=True,
        )
    ]

    decisions = strategy.decide(StrategyInput(signals=signals, markets=markets))

    assert len(decisions) == 1
    assert decisions[0].token_id == "tok1"
    assert decisions[0].price == 0.55


def test_strategy_respects_min_confidence() -> None:
    now = utc_now()
    strategy = Strategy(_settings(min_confidence=0.95))
    signals = [
        SignalItem(
            source=SignalSource.OFFICIAL_RSS,
            source_id="2",
            url="https://example.com",
            author="b",
            text="single weak mention",
            published_at=now - timedelta(minutes=3),
            fetched_at=now,
        )
    ]
    markets = [
        CandidateMarket(
            market_id="m2",
            question="Trump event?",
            slug="trump-event",
            yes_token_id="tok2",
            best_ask=0.40,
            best_bid=0.39,
            volume_24h=2000,
            liquidity=1500,
            min_tick_size=0.01,
            neg_risk=False,
            enable_order_book=True,
        )
    ]

    decisions = strategy.decide(StrategyInput(signals=signals, markets=markets))

    assert decisions == []
