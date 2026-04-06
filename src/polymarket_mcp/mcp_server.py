from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

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


def _safe_offset(cursor: str | None, total_count: int) -> int:
    if cursor is None or cursor.strip() == "":
        return 0
    try:
        parsed = int(cursor)
    except ValueError:
        return 0
    if parsed < 0:
        return 0
    return min(parsed, total_count)


def _pagination_meta(total_count: int, limit: int, offset: int) -> dict[str, object]:
    remaining = max(total_count - offset, 0)
    returned = min(remaining, limit)
    next_offset = offset + returned
    next_cursor = str(next_offset) if total_count > next_offset else None
    return {
        "limit": limit,
        "cursor": str(offset),
        "returned_count": returned,
        "total_count": total_count,
        "next_cursor": next_cursor,
    }


def _request_context(settings_mode: str):
    if settings_mode == "request":
        ctx = create_server_context()
        return ctx, True
    return _CTX, False


def _close_if_request_context(ctx, is_request: bool) -> None:
    if is_request:
        close_server_context(ctx)


@mcp.tool(description="Return service health, config mode, and MCP limit defaults.")
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
        "mcp_context_mode": settings.mcp_context_mode,
    }


@mcp.tool(description="Run one end-to-end polling cycle and return counts/actions.")
def run_cycle_once() -> dict[str, object]:
    settings = load_settings()
    ctx, is_request = _request_context(settings.mcp_context_mode)
    try:
        result = server_run_cycle_once(ctx)
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
    finally:
        _close_if_request_context(ctx, is_request)


@mcp.tool(description="Fetch signal items with MCP pagination and provider warnings.")
def fetch_signals(limit: int | None = None, cursor: str | None = None) -> dict[str, object]:
    settings = load_settings()
    capped_limit = _safe_limit(limit, settings.mcp_default_limit, settings.mcp_max_limit)
    client = SignalClient(settings)
    try:
        items, provider_errors = client.fetch_all_with_meta()
        offset = _safe_offset(cursor, len(items))
        paged = items[offset : offset + capped_limit]
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
        "pagination": _pagination_meta(len(items), capped_limit, offset),
        "count": len(paged),
        "warnings": provider_errors,
        "items": [
            {
                "source": item.source.value,
                "source_id": item.source_id,
                "author": item.author,
                "url": item.url,
                "text": item.text,
                "published_at": item.published_at.isoformat(),
            }
            for item in paged
        ],
    }


@mcp.tool(description="List candidate markets with MCP pagination and provider warnings.")
def list_markets(limit: int | None = None, cursor: str | None = None) -> dict[str, object]:
    settings = load_settings()
    capped_limit = _safe_limit(limit, settings.mcp_default_limit, settings.mcp_max_limit)
    client = MarketClient(settings)
    try:
        markets, provider_errors = client.list_candidate_markets_with_meta(settings.signal_keywords)
        offset = _safe_offset(cursor, len(markets))
        paged = markets[offset : offset + capped_limit]
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
        "pagination": _pagination_meta(len(markets), capped_limit, offset),
        "count": len(paged),
        "warnings": provider_errors,
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
            for item in paged
        ],
    }


@mcp.tool(description="Search markets by text query with pagination and warnings.")
def search_markets(query: str, limit: int | None = None, cursor: str | None = None) -> dict[str, object]:
    settings = load_settings()
    capped_limit = _safe_limit(limit, settings.mcp_default_limit, settings.mcp_max_limit)
    client = MarketClient(settings)
    try:
        markets, provider_errors = client.search_markets_with_meta(query, settings.mcp_max_limit)
        if provider_errors.get("search") == "empty_query":
            return {
                "ok": False,
                "tool": "search_markets",
                "error": "empty_query",
                "error_category": "invalid_input",
            }
        offset = _safe_offset(cursor, len(markets))
        paged = markets[offset : offset + capped_limit]
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "search_markets",
            "error": str(exc),
            "error_category": "provider",
            "count": 0,
            "items": [],
        }
    finally:
        client.close()

    return {
        "ok": True,
        "tool": "search_markets",
        "query": query,
        "pagination": _pagination_meta(len(markets), capped_limit, offset),
        "count": len(paged),
        "warnings": provider_errors,
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
            for item in paged
        ],
    }


@mcp.tool(description="Get current best bid/ask and midpoint for a token.")
def get_current_price(token_id: str) -> dict[str, object]:
    settings = load_settings()
    client = MarketClient(settings)
    try:
        payload, provider_errors = client.get_current_price_with_meta(token_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "get_current_price",
            "error": str(exc),
            "error_category": "provider",
        }
    finally:
        client.close()

    if payload is None:
        if provider_errors.get("price") == "empty_token_id":
            return {
                "ok": False,
                "tool": "get_current_price",
                "error": "empty_token_id",
                "error_category": "invalid_input",
                "warnings": provider_errors,
            }
        return {
            "ok": False,
            "tool": "get_current_price",
            "error": "price_unavailable",
            "error_category": "not_found",
            "warnings": provider_errors,
        }

    return {
        "ok": True,
        "tool": "get_current_price",
        "warnings": provider_errors,
        "result": payload,
    }


@mcp.tool(description="Get token orderbook levels with optional depth cap.")
def get_orderbook(token_id: str, depth: int = 20) -> dict[str, object]:
    settings = load_settings()
    client = MarketClient(settings)
    try:
        payload, provider_errors = client.get_orderbook_with_meta(token_id, depth)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "get_orderbook",
            "error": str(exc),
            "error_category": "provider",
        }
    finally:
        client.close()

    if payload is None:
        if provider_errors.get("orderbook") == "empty_token_id":
            return {
                "ok": False,
                "tool": "get_orderbook",
                "error": "empty_token_id",
                "error_category": "invalid_input",
                "warnings": provider_errors,
            }
        return {
            "ok": False,
            "tool": "get_orderbook",
            "error": "orderbook_unavailable",
            "error_category": "not_found",
            "warnings": provider_errors,
        }

    return {
        "ok": True,
        "tool": "get_orderbook",
        "warnings": provider_errors,
        "result": payload,
    }


@mcp.tool(description="Submit demo decision, with confirmation flow when required.")
def submit_demo_order() -> dict[str, object]:
    settings = load_settings()
    ctx, is_request = _request_context(settings.mcp_context_mode)
    try:
        result = submit_order_with_confirmation(ctx, demo_decision(ctx))
        return {
            "ok": True,
            "tool": "submit_demo_order",
            "idempotency_key": f"demo-{uuid4().hex[:12]}",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool": "submit_demo_order",
            "error": str(exc),
            "error_category": "internal",
        }
    finally:
        _close_if_request_context(ctx, is_request)


@mcp.tool(description="Confirm previously staged demo order by confirmation id.")
def confirm_demo_order(confirmation_id: str) -> dict[str, object]:
    settings = load_settings()
    ctx, is_request = _request_context(settings.mcp_context_mode)
    try:
        result = confirm_order(ctx, confirmation_id)
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
    finally:
        _close_if_request_context(ctx, is_request)


@mcp.tool(description="List tracked in-memory demo positions from server context.")
def list_positions() -> dict[str, object]:
    settings = load_settings()
    ctx, is_request = _request_context(settings.mcp_context_mode)
    try:
        positions = ctx.positions_list()
        return {
            "ok": True,
            "tool": "list_positions",
            "count": len(positions),
            "items": [
                {
                    "token_id": p.token_id,
                    "market_id": p.market_id,
                    "size": p.size,
                    "value_usd": p.value_usd,
                }
                for p in positions
            ],
        }
    finally:
        _close_if_request_context(ctx, is_request)


@mcp.tool(description="List pending confirmation items awaiting user confirmation.")
def list_pending_confirmations() -> dict[str, object]:
    settings = load_settings()
    ctx, is_request = _request_context(settings.mcp_context_mode)
    try:
        pending = list(ctx.pending_confirmations.values())
        return {
            "ok": True,
            "tool": "list_pending_confirmations",
            "count": len(pending),
            "items": [
                {
                    "confirmation_id": item.confirmation_id,
                    "market_id": item.decision.market_id,
                    "token_id": item.decision.token_id,
                    "side": item.decision.side.value,
                    "usd_size": item.decision.usd_size,
                    "created_at": item.created_at.isoformat(),
                    "expires_at": item.expires_at.isoformat(),
                }
                for item in pending
            ],
        }
    finally:
        _close_if_request_context(ctx, is_request)


def main() -> None:
    try:
        mcp.run()
    finally:
        close_server_context(_CTX)


if __name__ == "__main__":
    main()
