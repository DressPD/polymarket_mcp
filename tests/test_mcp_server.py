from __future__ import annotations

import polymarket_mcp.mcp_server as mcp_server
from polymarket_mcp.config import Settings

from ._helpers import make_settings


def _settings() -> Settings:
    return make_settings(signal_keywords=["trump"], signal_services=["x"], mcp_default_limit=3, mcp_max_limit=5)


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

        def list_candidate_markets(self, _keywords):
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

        def fetch_all(self):
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

        def list_candidate_markets(self, _keywords):
            return [_Market(1), _Market(2), _Market(3), _Market(4), _Market(5), _Market(6)]

        def close(self) -> None:
            return None

    monkeypatch.setattr(mcp_server, "MarketClient", _Client)

    payload = mcp_server.list_markets(limit=99)

    assert payload["ok"] is True
    assert payload["tool"] == "list_markets"
    assert payload["limit"] == 5
    assert payload["count"] == 5
    assert len(payload["items"]) == 5
