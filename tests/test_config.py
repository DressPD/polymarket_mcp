from __future__ import annotations

from polymarket_mcp.config import (
    _clamp_float,
    _clamp_int,
    _is_http_url,
    _parse_bool,
    _parse_csv,
    _parse_float,
    _parse_int,
    load_settings,
)


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


def test_parse_bool() -> None:
    assert _parse_bool("true", False) is True
    assert _parse_bool("FALSE", True) is False
    assert _parse_bool(None, True) is True
    assert _parse_bool("1", False) is True


def test_parse_int() -> None:
    assert _parse_int("42", 0) == 42
    assert _parse_int("", 10) == 10
    assert _parse_int(None, 5) == 5
    assert _parse_int("invalid", 7) == 7


def test_parse_float() -> None:
    assert _parse_float("3.14", 0.0) == 3.14
    assert _parse_float("", 1.0) == 1.0
    assert _parse_float(None, 2.0) == 2.0
    assert _parse_float("bad", 4.0) == 4.0


def test_parse_csv() -> None:
    assert _parse_csv("a,b,c", []) == ["a", "b", "c"]
    assert _parse_csv("", ["d"]) == ["d"]
    assert _parse_csv(None, ["e"]) == ["e"]
    assert _parse_csv(" a , b ", []) == ["a", "b"]


def test_clamp_float() -> None:
    assert _clamp_float(5.0, 0.0, 10.0) == 5.0
    assert _clamp_float(-1.0, 0.0, 10.0) == 0.0
    assert _clamp_float(15.0, 0.0, 10.0) == 10.0


def test_clamp_int() -> None:
    assert _clamp_int(5, 0, 10) == 5
    assert _clamp_int(-1, 0, 10) == 0
    assert _clamp_int(15, 0, 10) == 10


def test_is_http_url() -> None:
    assert _is_http_url("https://example.com") is True
    assert _is_http_url("http://test.org") is True
    assert _is_http_url("ftp://bad.com") is False
    assert _is_http_url("noturl") is False
