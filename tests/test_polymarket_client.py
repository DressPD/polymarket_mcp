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
