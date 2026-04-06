from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .polymarket_client import MarketClient
from .server import close_server_context, confirm_order, create_server_context, demo_decision, run_cycle_once as server_run_cycle_once, submit_order_with_confirmation
from .sources import SignalClient

mcp = FastMCP("polymarket-mcp")
_CTX = create_server_context()


def _safe_limit(value: int | None, settings_default: int, settings_max: int) -> int:
    if value is None:
        return settings_default
    if value < 0:
        return 0
    return min(value, settings_max)


@mcp.tool()
def health() -> dict[str, object]:
    settings = load_settings()
    return {
        "ok": True,
        "tool": "health",
        "status": "ok",
        "service": "polymarket-mcp",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "signal_services": settings.signal_services,
        "market_services": settings.market_services,
        "dry_run": settings.dry_run,
        "live_trading": settings.enable_live_trading,
        "mcp_default_limit": settings.mcp_default_limit,
        "mcp_max_limit": settings.mcp_max_limit,
    }


@mcp.tool()
def run_cycle_once() -> dict[str, object]:
    try:
        result = server_run_cycle_once(_CTX)
        return {
            "ok": True,
            "tool": "run_cycle_once",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "run_cycle_once",
            "error": str(exc),
            "error_category": "internal",
        }


@mcp.tool()
def fetch_signals(limit: int | None = None) -> dict[str, object]:
    settings = load_settings()
    capped_limit = _safe_limit(limit, settings.mcp_default_limit, settings.mcp_max_limit)
    client = SignalClient(settings)
    try:
        items = client.fetch_all()[:capped_limit]
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "fetch_signals",
            "error": str(exc),
            "error_category": "provider",
            "count": 0,
            "items": [],
        }
    finally:
        client.close()

    return {
        "ok": True,
        "tool": "fetch_signals",
        "limit": capped_limit,
        "count": len(items),
        "items": [
            {
                "source": item.source.value,
                "source_id": item.source_id,
                "author": item.author,
                "url": item.url,
                "text": item.text,
                "published_at": item.published_at.isoformat(),
            }
            for item in items
        ],
    }


@mcp.tool()
def list_markets(limit: int | None = None) -> dict[str, object]:
    settings = load_settings()
    capped_limit = _safe_limit(limit, settings.mcp_default_limit, settings.mcp_max_limit)
    client = MarketClient(settings)
    try:
        markets = client.list_candidate_markets(settings.signal_keywords)[:capped_limit]
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "list_markets",
            "error": str(exc),
            "error_category": "provider",
            "count": 0,
            "items": [],
        }
    finally:
        client.close()

    return {
        "ok": True,
        "tool": "list_markets",
        "limit": capped_limit,
        "count": len(markets),
        "items": [
            {
                "market_id": item.market_id,
                "question": item.question,
                "slug": item.slug,
                "yes_token_id": item.yes_token_id,
                "best_ask": item.best_ask,
                "best_bid": item.best_bid,
                "volume_24h": item.volume_24h,
                "liquidity": item.liquidity,
                "min_tick_size": item.min_tick_size,
                "neg_risk": item.neg_risk,
            }
            for item in markets
        ],
    }


@mcp.tool()
def submit_demo_order() -> dict[str, object]:
    try:
        result = submit_order_with_confirmation(_CTX, demo_decision(_CTX))
        return {
            "ok": True,
            "tool": "submit_demo_order",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "submit_demo_order",
            "error": str(exc),
            "error_category": "internal",
        }


@mcp.tool()
def confirm_demo_order(confirmation_id: str) -> dict[str, object]:
    try:
        result = confirm_order(_CTX, confirmation_id)
        return {
            "ok": result.get("ok", False),
            "tool": "confirm_demo_order",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "confirm_demo_order",
            "error": str(exc),
            "error_category": "internal",
        }


def main() -> None:
    try:
        mcp.run()
    finally:
        close_server_context(_CTX)


if __name__ == "__main__":
    main()
