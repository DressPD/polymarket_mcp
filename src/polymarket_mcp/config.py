from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

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


class ChainID(int, Enum):
    POLYGON_MAINNET = 137
    POLYGON_AMOY_TESTNET = 80002


class MCPContextMode(str, Enum):
    SHARED = "shared"
    REQUEST = "request"


class RiskLimitDefaults:
    MAX_ORDER_SIZE_USD = 1000.0
    MAX_TOTAL_EXPOSURE_USD = 5000.0
    MAX_POSITION_SIZE_PER_MARKET = 2000.0
    MIN_LIQUIDITY_REQUIRED = 10000.0
    MAX_SPREAD_TOLERANCE = 0.05
    REQUIRE_CONFIRMATION_ABOVE_USD = 500.0


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
    truth_social_rss_url: str
    official_rss_url: str
    mcp_default_limit: int
    mcp_max_limit: int
    mcp_context_mode: str
    max_order_size_usd: float
    max_total_exposure_usd: float
    max_position_size_per_market: float
    min_liquidity_required: float
    max_spread_tolerance: float
    require_confirmation_above_usd: float
    enable_autonomous_trading: bool


def load_settings() -> Settings:
    _ = load_dotenv()

    poll_interval = _clamp_int(_parse_int(os.getenv("BOT_POLL_INTERVAL_SECONDS"), 20), 5, 3600)
    max_usd_per_bet = _clamp_float(_parse_float(os.getenv("BOT_MAX_USD_PER_BET"), 5.0), 0.1, 1000.0)
    max_bets_per_hour = _clamp_int(_parse_int(os.getenv("BOT_MAX_BETS_PER_HOUR"), 4), 1, 240)
    market_limit = _clamp_int(_parse_int(os.getenv("BOT_MARKET_LIMIT"), 50), 1, 500)
    min_confidence = _clamp_float(_parse_float(os.getenv("BOT_MIN_CONFIDENCE"), 0.65), 0.0, 1.0)
    lookback = _clamp_int(_parse_int(os.getenv("SIGNAL_LOOKBACK_MINUTES"), 60), 1, 24 * 60)
    chain_id = _parse_int(os.getenv("POLYMARKET_CHAIN_ID"), ChainID.POLYGON_MAINNET.value)
    if chain_id not in {ChainID.POLYGON_MAINNET.value, ChainID.POLYGON_AMOY_TESTNET.value}:
        chain_id = ChainID.POLYGON_MAINNET.value
    signature_type = _parse_int(os.getenv("POLYMARKET_SIGNATURE_TYPE"), 1)
    if signature_type not in {0, 1, 2}:
        signature_type = 1
    mcp_default_limit = _clamp_int(_parse_int(os.getenv("MCP_DEFAULT_LIMIT"), 10), 1, 100)
    mcp_max_limit = _clamp_int(_parse_int(os.getenv("MCP_MAX_LIMIT"), 50), 1, 500)
    if mcp_default_limit > mcp_max_limit:
        mcp_default_limit = mcp_max_limit
    mcp_context_mode = (os.getenv("MCP_CONTEXT_MODE") or MCPContextMode.SHARED.value).strip().lower()
    if mcp_context_mode not in {MCPContextMode.SHARED.value, MCPContextMode.REQUEST.value}:
        mcp_context_mode = MCPContextMode.SHARED.value

    truth_social_rss_url = os.getenv(
        "TRUTH_SOCIAL_RSS_URL",
        "https://www.presidency.ucsb.edu/taxonomy/term/428/all/feed/feed?items_per_page=20",
    )
    official_rss_url = os.getenv(
        "OFFICIAL_RSS_URL",
        "https://www.presidency.ucsb.edu/documents/app-categories/press-office/press-releases?items_per_page=60",
    )

    custom_rss_urls = [url for url in _parse_csv(os.getenv("CUSTOM_RSS_URLS"), []) if _is_http_url(url)]

    max_order_size_usd = _clamp_float(
        _parse_float(os.getenv("MAX_ORDER_SIZE_USD"), RiskLimitDefaults.MAX_ORDER_SIZE_USD),
        1.0,
        50000.0,
    )
    max_total_exposure_usd = _clamp_float(
        _parse_float(os.getenv("MAX_TOTAL_EXPOSURE_USD"), RiskLimitDefaults.MAX_TOTAL_EXPOSURE_USD),
        max_order_size_usd,
        1_000_000.0,
    )
    max_position_size_per_market = _clamp_float(
        _parse_float(os.getenv("MAX_POSITION_SIZE_PER_MARKET"), RiskLimitDefaults.MAX_POSITION_SIZE_PER_MARKET),
        1.0,
        max_total_exposure_usd,
    )
    min_liquidity_required = _clamp_float(
        _parse_float(os.getenv("MIN_LIQUIDITY_REQUIRED"), RiskLimitDefaults.MIN_LIQUIDITY_REQUIRED),
        0.0,
        10_000_000.0,
    )
    max_spread_tolerance = _clamp_float(
        _parse_float(os.getenv("MAX_SPREAD_TOLERANCE"), RiskLimitDefaults.MAX_SPREAD_TOLERANCE),
        0.0,
        1.0,
    )
    require_confirmation_above_usd = _clamp_float(
        _parse_float(
            os.getenv("REQUIRE_CONFIRMATION_ABOVE_USD"),
            RiskLimitDefaults.REQUIRE_CONFIRMATION_ABOVE_USD,
        ),
        1.0,
        max_order_size_usd,
    )

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
        custom_rss_urls=custom_rss_urls,
        truth_social_rss_url=truth_social_rss_url,
        official_rss_url=official_rss_url,
        mcp_default_limit=mcp_default_limit,
        mcp_max_limit=mcp_max_limit,
        mcp_context_mode=mcp_context_mode,
        max_order_size_usd=max_order_size_usd,
        max_total_exposure_usd=max_total_exposure_usd,
        max_position_size_per_market=max_position_size_per_market,
        min_liquidity_required=min_liquidity_required,
        max_spread_tolerance=max_spread_tolerance,
        require_confirmation_above_usd=require_confirmation_above_usd,
        enable_autonomous_trading=_parse_bool(os.getenv("ENABLE_AUTONOMOUS_TRADING"), False),
    )


def _is_http_url(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")
