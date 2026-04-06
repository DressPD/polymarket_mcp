from __future__ import annotations

from dataclasses import replace

from polymarket_mcp.config import Settings


def make_settings(**overrides: object) -> Settings:
    base = Settings(
        poll_interval_seconds=20,
        dry_run=True,
        enable_live_trading=False,
        max_usd_per_bet=5.0,
        max_bets_per_hour=4,
        market_limit=50,
        min_confidence=0.65,
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
        truth_social_rss_url="https://www.presidency.ucsb.edu/taxonomy/term/428/all/feed/feed?items_per_page=20",
        official_rss_url="https://www.presidency.ucsb.edu/documents/app-categories/press-office/press-releases?items_per_page=60",
        mcp_default_limit=10,
        mcp_max_limit=50,
        mcp_context_mode="shared",
        max_order_size_usd=1000.0,
        max_total_exposure_usd=5000.0,
        max_position_size_per_market=2000.0,
        min_liquidity_required=10000.0,
        max_spread_tolerance=0.05,
        require_confirmation_above_usd=500.0,
        enable_autonomous_trading=False,
    )
    return replace(base, **overrides)
