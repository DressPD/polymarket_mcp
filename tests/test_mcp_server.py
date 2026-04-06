from __future__ import annotations

import polymarket_mcp.mcp_server as mcp_server
from polymarket_mcp.config import Settings


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
        news_api_key=None,
        signal_services=["x"],
        market_services=["gamma"],
        custom_rss_urls=[],
        mcp_default_limit=3,
        mcp_max_limit=5,
    )


def test_safe_limit_bounds() -> None:
    assert mcp_server._safe_limit(None, 3, 5) == 3
    assert mcp_server._safe_limit(-1, 3, 5) == 0
    assert mcp_server._safe_limit(99, 3, 5) == 5


def test_health_contains_limits(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)
    payload = mcp_server.health()
    assert payload["ok"] is True
    assert payload["tool"] == "health"
    assert payload["status"] == "ok"
    assert payload["service"] == "polymarket-mcp"
    assert payload["mcp_default_limit"] == 3
    assert payload["mcp_max_limit"] == 5
