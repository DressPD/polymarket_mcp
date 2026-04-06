from __future__ import annotations

import polymarket_mcp.polymarket_client as poly
from polymarket_mcp.models import CandidateMarket

from ._helpers import make_settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    def get(self, _url: str, params=None):
        return self.response


def test_parse_token_ids_variants() -> None:
    assert poly._parse_token_ids(["a", "b"]) == ["a", "b"]
    assert poly._parse_token_ids("[\"a\",\"b\"]") == ["a", "b"]
    assert poly._parse_token_ids("a,b") == ["a", "b"]
    assert poly._parse_token_ids("[bad-json") == []


def test_fetch_gamma_candidates_filters_invalid_and_non_matching(monkeypatch) -> None:
    settings = make_settings(market_limit=5)
    payload = [
        {
            "id": "m1",
            "question": "Will Trump win?",
            "slug": "trump-win",
            "enableOrderBook": True,
            "clobTokenIds": "[\"tok1\"]",
            "bestAsk": "0.45",
            "bestBid": "0.44",
            "volume24hr": "100",
            "liquidityNum": "5000",
            "minimum_tick_size": "0.01",
            "negRisk": "false",
        },
        {
            "id": "m2",
            "question": "Unrelated market",
            "slug": "other",
            "enableOrderBook": True,
            "clobTokenIds": ["tok2"],
        },
        {
            "id": "",
            "question": "Missing id",
            "slug": "bad",
            "enableOrderBook": True,
            "clobTokenIds": ["tok3"],
        },
    ]
    with poly.httpx.Client() as client:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
        candidates = poly._fetch_gamma_candidates(client, settings, ["trump"])

    assert len(candidates) == 1
    assert candidates[0].market_id == "m1"
    assert candidates[0].yes_token_id == "tok1"


def test_request_with_retry_stops_on_permanent_http_status(monkeypatch) -> None:
    calls = {"n": 0}

    monkeypatch.setattr(poly.time, "sleep", lambda _s: None)
    with poly.httpx.Client() as client:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: (calls.__setitem__("n", calls["n"] + 1) or _FakeResponse(404)))
        response = poly._request_with_retry(client, "https://example.com", params={}, attempts=3)

    assert response is None
    assert calls["n"] == 1


def test_parse_helpers_and_dedupe() -> None:
    assert poly._parse_float(None, 1.2) == 1.2
    assert poly._parse_float("", 1.2) == 1.2
    assert poly._parse_float("1.5", 0.0) == 1.5
    assert poly._parse_float("x", 2.2) == 2.2
    assert poly._parse_float(3, 0.0) == 3.0

    assert poly._parse_bool(None, True) is True
    assert poly._parse_bool(True, False) is True
    assert poly._parse_bool("yes", False) is True
    assert poly._parse_bool("off", True) is False
    assert poly._parse_bool("weird", True) is True

    payload = [
        type("M", (), {"market_id": "m1"})(),
        type("M", (), {"market_id": "m1"})(),
        type("M", (), {"market_id": "m2"})(),
    ]
    out = poly._dedupe(payload)
    assert [m.market_id for m in out] == ["m1", "m2"]


def test_request_with_retry_handles_http_error_then_success(monkeypatch) -> None:
    class _Resp:
        def __init__(self, code):
            self.status_code = code

    monkeypatch.setattr(poly.time, "sleep", lambda _s: None)
    calls = {"n": 0}
    with poly.httpx.Client() as c:
        def _get(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise poly.httpx.HTTPError("net")
            return _Resp(200)

        monkeypatch.setattr(c, "get", _get)
        response = poly._request_with_retry(c, "https://x", params={}, attempts=3)
    assert response is not None
    assert calls["n"] == 2


def test_fetch_gamma_candidates_additional_filters(monkeypatch) -> None:
    settings = make_settings(market_limit=5)
    payload = [
        {"id": "m0", "question": "Trump x", "slug": "s", "enableOrderBook": False, "clobTokenIds": ["t"]},
        {"id": "m1", "question": "Trump y", "slug": "s", "enableOrderBook": True, "clobTokenIds": []},
        {"id": "m2", "question": "Trump z", "slug": "s", "enableOrderBook": True, "clobTokenIds": ["t2"], "minimum_tick_size": 0},
    ]
    with poly.httpx.Client() as client:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
        out = poly._fetch_gamma_candidates(client, settings, ["trump"])
    assert len(out) == 1
    assert out[0].market_id == "m2"
    assert out[0].min_tick_size == 0.01


def test_market_client_provider_flow_and_close() -> None:
    settings = make_settings(market_services=["gamma", "unknown"])
    client = poly.MarketClient(settings)
    try:
        sample = CandidateMarket(
            market_id="m1",
            question="q",
            slug="s",
            yes_token_id="tok",
            best_ask=0.5,
            best_bid=0.4,
            volume_24h=10.0,
            liquidity=1000.0,
        )
        client.providers["gamma"] = lambda _c, _s, _k: [sample, sample]
        out = client.list_candidate_markets(["trump"])
        assert len(out) == 1

        client.providers["gamma"] = lambda _c, _s, _k: (_ for _ in ()).throw(RuntimeError("bad"))
        assert client.list_candidate_markets(["trump"]) == []
    finally:
        client.close()


def test_market_client_list_candidate_markets_logs_provider_failures(monkeypatch) -> None:
    settings = make_settings(market_services=["gamma", "unknown"])
    client = poly.MarketClient(settings)
    try:
        warnings: list[str] = []
        monkeypatch.setattr(poly.LOGGER, "warning", lambda msg, *args: warnings.append(msg % args if args else msg))
        client.providers["gamma"] = lambda _c, _s, _k: (_ for _ in ()).throw(RuntimeError("gamma down"))
        out = client.list_candidate_markets(["trump"])
        assert out == []
        assert any("market provider failed" in line for line in warnings)
        assert any("market provider unsupported" in line for line in warnings)
    finally:
        client.close()


def test_market_client_with_meta_collects_provider_errors() -> None:
    settings = make_settings(market_services=["gamma", "unknown"])
    client = poly.MarketClient(settings)
    try:
        client.providers["gamma"] = lambda _c, _s, _k: (_ for _ in ()).throw(RuntimeError("gamma down"))
        out, errors = client.list_candidate_markets_with_meta(["trump"])
        assert out == []
        assert errors["gamma"] == "gamma down"
        assert errors["unknown"] == "unsupported_provider"
    finally:
        client.close()


def test_search_markets_with_meta_and_empty_query(monkeypatch) -> None:
    settings = make_settings(market_services=["gamma", "unknown"])
    client = poly.MarketClient(settings)
    try:
        sample = CandidateMarket(
            market_id="m1",
            question="Will Trump win?",
            slug="trump-win",
            yes_token_id="tok",
            best_ask=0.55,
            best_bid=0.5,
            volume_24h=200.0,
            liquidity=5000.0,
        )
        monkey = [sample, sample]
        monkeypatch.setattr(poly, "_search_gamma_markets", lambda *_args, **_kwargs: monkey)
        out, errors = client.search_markets_with_meta("trump", 10)
        assert len(out) == 1
        assert errors["unknown"] == "unsupported_provider"

        out2, errors2 = client.search_markets_with_meta("   ", 10)
        assert out2 == []
        assert errors2["search"] == "empty_query"
    finally:
        client.close()


def test_get_current_price_with_meta(monkeypatch) -> None:
    settings = make_settings(market_limit=5)
    payload = [
        {
            "id": "m1",
            "question": "Will Trump win?",
            "slug": "trump-win",
            "clobTokenIds": ["tok1"],
            "bestBid": "0.41",
            "bestAsk": "0.43",
            "minimum_tick_size": "0.01",
        }
    ]
    with poly.httpx.Client() as client:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
        monkeypatch.setattr(poly, "_request_with_retry", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
        market_client = poly.MarketClient(settings)
        try:
            market_client.client = client
            result, errors = market_client.get_current_price_with_meta("tok1")
            assert errors == {}
            assert result is not None
            assert result["mid_price"] == 0.42
            missing, missing_errors = market_client.get_current_price_with_meta("missing")
            assert missing is None
            assert missing_errors["gamma"] == "token_not_found"
        finally:
            market_client.close()


def test_get_orderbook_with_meta(monkeypatch) -> None:
    settings = make_settings()
    orderbook = {
        "bids": [["0.40", "10"], ["0.39", "5"]],
        "asks": [{"price": "0.42", "size": "8"}, {"price": "0.43", "size": "6"}],
    }
    market_client = poly.MarketClient(settings)
    try:
        monkeypatch.setattr(poly, "_fetch_orderbook_payload", lambda *_args, **_kwargs: orderbook)
        payload, errors = market_client.get_orderbook_with_meta("tok1", depth=1)
        assert errors == {}
        assert payload is not None
        assert payload["depth"] == 1
        assert payload["best_bid"] == 0.4
        assert payload["best_ask"] == 0.42

        monkeypatch.setattr(poly, "_fetch_orderbook_payload", lambda *_args, **_kwargs: None)
        payload2, errors2 = market_client.get_orderbook_with_meta("tok1", depth=5)
        assert payload2 is None
        assert errors2["clob"] == "orderbook_unavailable"
    finally:
        market_client.close()
