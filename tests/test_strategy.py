from __future__ import annotations

from datetime import timedelta

from polymarket_mcp.config import Settings
from polymarket_mcp.models import CandidateMarket, SignalItem, SignalSource, utc_now
from polymarket_mcp.strategy import Strategy, StrategyInput


def _settings(min_confidence: float = 0.65) -> Settings:
    return Settings(
        poll_interval_seconds=20,
        dry_run=True,
        enable_live_trading=False,
        max_usd_per_bet=5.0,
        max_bets_per_hour=4,
        market_limit=50,
        min_confidence=min_confidence,
        signal_keywords=["trump", "donald"],
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
        news_api_key=None,
        signal_services=["x", "official_rss"],
        market_services=["gamma"],
        custom_rss_urls=[],
        mcp_default_limit=10,
        mcp_max_limit=50,
    )


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
