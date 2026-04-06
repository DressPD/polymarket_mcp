from __future__ import annotations

import polymarket_mcp.mcp_server as mcp_server
from polymarket_mcp.config import Settings

from ._helpers import make_settings


def _settings() -> Settings:
    return make_settings(
        signal_keywords=["trump"],
        signal_services=["x"],
        mcp_default_limit=3,
        mcp_max_limit=5,
        mcp_context_mode="shared",
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
    assert payload["mcp_context_mode"] == "shared"


def test_confirm_demo_order_not_found() -> None:
    payload = mcp_server.confirm_demo_order("missing")
    assert payload["ok"] is False
    assert payload["tool"] == "confirm_demo_order"
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["error_category"] == "not_found"


def test_run_cycle_once_internal_error_envelope(monkeypatch) -> None:
    def _boom(_ctx):
        raise RuntimeError("cycle failed")

    monkeypatch.setattr(mcp_server, "server_run_cycle_once", _boom)

    payload = mcp_server.run_cycle_once()

    assert payload["ok"] is False
    assert payload["tool"] == "run_cycle_once"
    assert payload["error_category"] == "internal"


def test_list_markets_provider_error_envelope(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def list_candidate_markets_with_meta(self, _keywords):
            raise RuntimeError("market provider failure")

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    payload = mcp_server.list_markets(limit=4)

    assert payload["ok"] is False
    assert payload["tool"] == "list_markets"
    assert payload["error_category"] == "provider"
    assert payload["count"] == 0
    assert payload["items"] == []


def test_submit_and_confirm_demo_order_internal_error(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "demo_decision", lambda _ctx: object())

    def _submit_boom(_ctx, _decision):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(mcp_server, "submit_order_with_confirmation", _submit_boom)
    payload = mcp_server.submit_demo_order()
    assert payload["ok"] is False
    assert payload["tool"] == "submit_demo_order"
    assert payload["error_category"] == "internal"

    def _confirm_boom(_ctx, _cid):
        raise RuntimeError("confirm failed")

    monkeypatch.setattr(mcp_server, "confirm_order", _confirm_boom)
    payload2 = mcp_server.confirm_demo_order("cid")
    assert payload2["ok"] is False
    assert payload2["tool"] == "confirm_demo_order"
    assert payload2["error_category"] == "internal"


def test_fetch_signals_provider_error_envelope(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_all_with_meta(self):
            raise RuntimeError("source failure")

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "SignalClient", _Client)

    payload = mcp_server.fetch_signals(limit=99)

    assert payload["ok"] is False
    assert payload["tool"] == "fetch_signals"
    assert payload["error_category"] == "provider"
    assert payload["count"] == 0
    assert payload["items"] == []


def test_list_markets_applies_limit_and_success_shape(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Market:
        def __init__(self, idx: int) -> None:
            self.market_id = f"m{idx}"
            self.question = "q"
            self.slug = "s"
            self.yes_token_id = f"tok{idx}"
            self.best_ask = 0.5
            self.best_bid = 0.4
            self.volume_24h = 10.0
            self.liquidity = 20.0
            self.min_tick_size = 0.01
            self.neg_risk = False

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def list_candidate_markets_with_meta(self, _keywords):
            return ([_Market(1), _Market(2), _Market(3), _Market(4), _Market(5), _Market(6)], {"gamma": "soft warning"})

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    payload = mcp_server.list_markets(limit=99)

    assert payload["ok"] is True
    assert payload["tool"] == "list_markets"
    pagination = payload["pagination"]
    assert isinstance(pagination, dict)
    assert pagination["limit"] == 5
    assert pagination["returned_count"] == 5
    assert pagination["total_count"] == 6
    assert pagination["next_cursor"] == "5"
    assert payload["count"] == 5
    assert len(payload["items"]) == 5
    assert payload["warnings"] == {"gamma": "soft warning"}


def test_fetch_signals_includes_pagination_and_warnings(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Item:
        def __init__(self, idx: int) -> None:
            from datetime import timezone, datetime

            self.source = type("S", (), {"value": "x"})()
            self.source_id = f"sid-{idx}"
            self.author = "a"
            self.url = "u"
            self.text = "t"
            self.published_at = datetime.now(timezone.utc)

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_all_with_meta(self):
            return ([_Item(i) for i in range(6)], {"x": "temporary provider warning"})

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "SignalClient", _Client)

    payload = mcp_server.fetch_signals(limit=99)
    assert payload["ok"] is True
    assert payload["count"] == 5
    pagination = payload["pagination"]
    assert isinstance(pagination, dict)
    assert pagination["total_count"] == 6
    assert payload["warnings"] == {"x": "temporary provider warning"}


def test_list_positions_and_pending_confirmations_tools(monkeypatch) -> None:
    class _Pending:
        def __init__(self) -> None:
            from datetime import datetime, timezone, timedelta
            from polymarket_mcp.models import BetDecision, BetSide

            self.confirmation_id = "c1"
            self.decision = BetDecision("m", "tok", BetSide.BUY, 0.5, 10.0, 0.8, "r")
            self.created_at = datetime.now(timezone.utc)
            self.expires_at = self.created_at + timedelta(minutes=1)

    class _Position:
        token_id = "tok"
        market_id = "m"
        size = 10.0
        value_usd = 10.0

    class _Ctx:
        pending_confirmations = {"c1": _Pending()}

        @staticmethod
        def positions_list():
            return [_Position()]

    monkeypatch.setattr(mcp_server, "_CTX", _Ctx())
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    p = mcp_server.list_positions()
    assert p["ok"] is True
    assert p["tool"] == "list_positions"
    assert p["count"] == 1

    c = mcp_server.list_pending_confirmations()
    assert c["ok"] is True
    assert c["tool"] == "list_pending_confirmations"
    assert c["count"] == 1


def test_request_context_mode_creates_and_closes(monkeypatch) -> None:
    req_settings = make_settings(mcp_context_mode="request")
    monkeypatch.setattr(mcp_server, "load_settings", lambda: req_settings)

    created = {"count": 0}
    closed = {"count": 0}

    class _ReqCtx:
        pending_confirmations = {}

        @staticmethod
        def positions_list():
            return []

    monkeypatch.setattr(mcp_server, "create_server_context", lambda: (created.__setitem__("count", created["count"] + 1) or _ReqCtx()))
    monkeypatch.setattr(mcp_server, "close_server_context", lambda _ctx: closed.__setitem__("count", closed["count"] + 1))
    monkeypatch.setattr(mcp_server, "server_run_cycle_once", lambda _ctx: {"ok": True})

    out = mcp_server.run_cycle_once()
    assert out["ok"] is True
    assert created["count"] == 1
    assert closed["count"] == 1


def test_search_markets_success_and_not_found(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Market:
        def __init__(self, idx: int) -> None:
            self.market_id = f"m{idx}"
            self.question = "q"
            self.slug = "s"
            self.yes_token_id = f"tok{idx}"
            self.best_ask = 0.5
            self.best_bid = 0.4
            self.volume_24h = 10.0
            self.liquidity = 20.0
            self.min_tick_size = 0.01
            self.neg_risk = False

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def search_markets_with_meta(self, _query: str, _limit: int):
            return ([_Market(1), _Market(2), _Market(3), _Market(4), _Market(5), _Market(6)], {"gamma": "warning"})

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    out = mcp_server.search_markets("trump", limit=99)
    assert out["ok"] is True
    assert out["tool"] == "search_markets"
    assert out["count"] == 5
    assert out["warnings"] == {"gamma": "warning"}
    assert out["pagination"]["total_count"] == 6


def test_get_current_price_and_orderbook(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def get_current_price_with_meta(self, _token_id: str):
            return ({"token_id": "tok", "mid_price": 0.5}, {})

        def get_orderbook_with_meta(self, _token_id: str, _depth: int):
            return ({"token_id": "tok", "bids": [], "asks": []}, {})

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    price = mcp_server.get_current_price("tok")
    assert price["ok"] is True
    assert price["tool"] == "get_current_price"
    assert price["result"]["mid_price"] == 0.5

    book = mcp_server.get_orderbook("tok", depth=15)
    assert book["ok"] is True
    assert book["tool"] == "get_orderbook"
    assert book["result"]["token_id"] == "tok"


def test_get_current_price_and_orderbook_not_found(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "load_settings", _settings)

    class _Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def get_current_price_with_meta(self, _token_id: str):
            return (None, {"gamma": "token_not_found"})

        def get_orderbook_with_meta(self, _token_id: str, _depth: int):
            return (None, {"clob": "orderbook_unavailable"})

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    price = mcp_server.get_current_price("tok")
    assert price["ok"] is False
    assert price["error_category"] == "not_found"

    book = mcp_server.get_orderbook("tok")
    assert book["ok"] is False
    assert book["error_category"] == "not_found"
