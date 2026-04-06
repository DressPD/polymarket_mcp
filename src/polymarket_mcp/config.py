from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class Settings:
    poll_interval_seconds: int
    dry_run: bool
    enable_live_trading: bool
    max_usd_per_bet: float
    max_bets_per_hour: int
    market_limit: int
    min_confidence: float
    signal_keywords: list[str]
    signal_lookback_minutes: int
    x_bearer_token: str | None
    gamma_base_url: str
    clob_host: str
    chain_id: int
    private_key: str | None
    funder_address: str | None
    signature_type: int
    poly_api_key: str | None
    poly_api_secret: str | None
    poly_api_passphrase: str | None
    news_api_key: str | None
    signal_services: list[str]
    market_services: list[str]
    custom_rss_urls: list[str]
    mcp_default_limit: int
    mcp_max_limit: int


def load_settings() -> Settings:
    _ = load_dotenv()

    poll_interval = _clamp_int(_parse_int(os.getenv("BOT_POLL_INTERVAL_SECONDS"), 20), 5, 3600)
    max_usd_per_bet = _clamp_float(_parse_float(os.getenv("BOT_MAX_USD_PER_BET"), 5.0), 0.1, 1000.0)
    max_bets_per_hour = _clamp_int(_parse_int(os.getenv("BOT_MAX_BETS_PER_HOUR"), 4), 1, 240)
    market_limit = _clamp_int(_parse_int(os.getenv("BOT_MARKET_LIMIT"), 50), 1, 500)
    min_confidence = _clamp_float(_parse_float(os.getenv("BOT_MIN_CONFIDENCE"), 0.65), 0.0, 1.0)
    lookback = _clamp_int(_parse_int(os.getenv("SIGNAL_LOOKBACK_MINUTES"), 60), 1, 24 * 60)
    chain_id = _parse_int(os.getenv("POLYMARKET_CHAIN_ID"), 137)
    signature_type = _parse_int(os.getenv("POLYMARKET_SIGNATURE_TYPE"), 1)
    if signature_type not in {0, 1, 2}:
        signature_type = 1
    mcp_default_limit = _clamp_int(_parse_int(os.getenv("MCP_DEFAULT_LIMIT"), 10), 1, 100)
    mcp_max_limit = _clamp_int(_parse_int(os.getenv("MCP_MAX_LIMIT"), 50), 1, 500)
    if mcp_default_limit > mcp_max_limit:
        mcp_default_limit = mcp_max_limit

    return Settings(
        poll_interval_seconds=poll_interval,
        dry_run=_parse_bool(os.getenv("BOT_DRY_RUN"), True),
        enable_live_trading=_parse_bool(os.getenv("BOT_ENABLE_LIVE_TRADING"), False),
        max_usd_per_bet=max_usd_per_bet,
        max_bets_per_hour=max_bets_per_hour,
        market_limit=market_limit,
        min_confidence=min_confidence,
        signal_keywords=_parse_csv(
            os.getenv("SIGNAL_KEYWORDS"),
            ["trump", "donald", "truth social", "white house"],
        ),
        signal_lookback_minutes=lookback,
        x_bearer_token=os.getenv("X_BEARER_TOKEN") or None,
        gamma_base_url=os.getenv("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com"),
        clob_host=os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com"),
        chain_id=chain_id,
        private_key=os.getenv("POLYMARKET_PRIVATE_KEY") or None,
        funder_address=os.getenv("POLYMARKET_FUNDER_ADDRESS") or None,
        signature_type=signature_type,
        poly_api_key=os.getenv("POLYMARKET_API_KEY") or None,
        poly_api_secret=os.getenv("POLYMARKET_API_SECRET") or None,
        poly_api_passphrase=os.getenv("POLYMARKET_API_PASSPHRASE") or None,
        news_api_key=os.getenv("NEWS_API_KEY") or None,
        signal_services=_parse_csv(
            os.getenv("SIGNAL_SERVICES"),
            ["x", "truth_rss", "official_rss"],
        ),
        market_services=_parse_csv(
            os.getenv("MARKET_SERVICES"),
            ["gamma"],
        ),
        custom_rss_urls=_parse_csv(
            os.getenv("CUSTOM_RSS_URLS"),
            [],
        ),
        mcp_default_limit=mcp_default_limit,
        mcp_max_limit=mcp_max_limit,
    )
