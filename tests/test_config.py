from __future__ import annotations

from polymarket_mcp.config import load_settings


def test_load_settings_clamps_and_normalizes(monkeypatch) -> None:
    monkeypatch.setenv("BOT_POLL_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("BOT_MAX_USD_PER_BET", "5000")
    monkeypatch.setenv("BOT_MAX_BETS_PER_HOUR", "999")
    monkeypatch.setenv("BOT_MARKET_LIMIT", "0")
    monkeypatch.setenv("BOT_MIN_CONFIDENCE", "9")
    monkeypatch.setenv("SIGNAL_LOOKBACK_MINUTES", "0")
    monkeypatch.setenv("MCP_DEFAULT_LIMIT", "200")
    monkeypatch.setenv("MCP_MAX_LIMIT", "3")
    monkeypatch.setenv("MCP_CONTEXT_MODE", "request")
    monkeypatch.setenv("POLYMARKET_SIGNATURE_TYPE", "99")
    monkeypatch.setenv("BOT_DRY_RUN", "false")
    monkeypatch.setenv("BOT_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("SIGNAL_SERVICES", "x,official_rss")
    monkeypatch.setenv("MARKET_SERVICES", "gamma")
    monkeypatch.setenv("CUSTOM_RSS_URLS", "https://a.example/rss, https://b.example/rss")
    monkeypatch.setenv("TRUTH_SOCIAL_RSS_URL", "https://example.com/truth.xml")
    monkeypatch.setenv("OFFICIAL_RSS_URL", "https://example.com/official.xml")

    settings = load_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.max_usd_per_bet == 1000.0
    assert settings.max_bets_per_hour == 240
    assert settings.market_limit == 1
    assert settings.min_confidence == 1.0
    assert settings.signal_lookback_minutes == 1
    assert settings.mcp_max_limit == 3
    assert settings.mcp_default_limit == 3
    assert settings.mcp_context_mode == "request"
    assert settings.signature_type == 1
    assert settings.dry_run is False
    assert settings.enable_live_trading is True
    assert settings.signal_services == ["x", "official_rss"]
    assert settings.market_services == ["gamma"]
    assert settings.custom_rss_urls == ["https://a.example/rss", "https://b.example/rss"]
    assert settings.truth_social_rss_url == "https://example.com/truth.xml"
    assert settings.official_rss_url == "https://example.com/official.xml"


def test_load_settings_rejects_invalid_context_mode_and_non_http_custom_urls(monkeypatch) -> None:
    monkeypatch.setenv("MCP_CONTEXT_MODE", "invalid")
    monkeypatch.setenv("CUSTOM_RSS_URLS", "https://ok.example/rss, ftp://bad.example/rss, javascript:alert(1)")

    settings = load_settings()

    assert settings.mcp_context_mode == "shared"
    assert settings.custom_rss_urls == ["https://ok.example/rss"]
