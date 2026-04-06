from __future__ import annotations

from datetime import timedelta

import httpx
import polymarket_mcp.sources as sources
from polymarket_mcp.models import SignalItem, SignalSource, utc_now

from ._helpers import make_settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: object = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _signal(source_id: str, minutes_ago: int = 1) -> SignalItem:
    now = utc_now()
    return SignalItem(
        source=SignalSource.X,
        source_id=source_id,
        url=f"https://x.com/{source_id}",
        author="a",
        text="trump text",
        published_at=now - timedelta(minutes=minutes_ago),
        fetched_at=now,
    )


def test_fetch_x_recent_filters_non_matching_and_invalid_payloads(monkeypatch) -> None:
    settings = make_settings(x_bearer_token="token", signal_keywords=["trump"])
    payload = {
        "data": [
            {"id": "1", "author_id": "a", "text": "Trump update", "created_at": "2025-01-01T00:00:00Z"},
            {"id": "2", "author_id": "b", "text": "No keyword", "created_at": "2025-01-01T00:00:00Z"},
            "bad-row",
        ]
    }
    client = httpx.Client()
    monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
    try:
        items = sources._fetch_x_recent(client, settings)
    finally:
        client.close()

    assert len(items) == 1
    assert items[0].source == SignalSource.X
    assert items[0].source_id == "1"


def test_within_lookback_and_dedupe() -> None:
    now = utc_now()
    old = SignalItem(
        source=SignalSource.X,
        source_id="1",
        url="u1",
        author="a",
        text="trump",
        published_at=now - timedelta(minutes=120),
        fetched_at=now,
    )
    fresh = SignalItem(
        source=SignalSource.X,
        source_id="2",
        url="u2",
        author="a",
        text="trump",
        published_at=now - timedelta(minutes=5),
        fetched_at=now,
    )
    dup = SignalItem(
        source=SignalSource.X,
        source_id="2",
        url="u3",
        author="b",
        text="trump",
        published_at=now - timedelta(minutes=4),
        fetched_at=now,
    )

    deduped = sources._dedupe([old, fresh, dup])
    filtered = sources._within_lookback(deduped, 60)

    assert len(deduped) == 2
    assert [item.source_id for item in filtered] == ["2"]


def test_contains_keyword_and_datetime_helpers() -> None:
    assert sources._contains_keyword("Donald Trump speaks", ["trump"]) is True
    assert sources._contains_keyword("No match", ["trump"]) is False

    xdt = sources._parse_x_datetime("2025-01-01T00:00:00Z")
    assert xdt.tzinfo is not None

    rss_with_tz = sources._parse_rss_datetime("Mon, 01 Jan 2024 12:00:00 GMT")
    assert rss_with_tz.tzinfo is not None

    rss_no_tz = sources._parse_rss_datetime("Mon, 01 Jan 2024 12:00:00")
    assert rss_no_tz.tzinfo is not None


def test_item_text_strips_value() -> None:
    from xml.etree import ElementTree

    item = ElementTree.fromstring("<item><title>  hello  </title></item>")
    assert sources._item_text(item, "title") == "hello"
    assert sources._item_text(item, "missing") == ""


def test_parse_rss_feed_success_and_error_cases(monkeypatch) -> None:
    xml = (
        "<rss><channel>"
        "<item><title>Trump title</title><link>https://e/1</link><guid>g1</guid><description>desc</description><author>a</author><pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate></item>"
        "<item><title>Other</title><link>https://e/2</link></item>"
        "</channel></rss>"
    )
    client = httpx.Client()
    try:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, text=xml))
        items = sources._parse_rss_feed(client, "https://feed", SignalSource.OFFICIAL_RSS, "def", ["trump"])
        assert len(items) == 1
        assert items[0].source_id == "g1"

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(500, text=""))
        assert sources._parse_rss_feed(client, "https://feed", SignalSource.OFFICIAL_RSS, "def", ["trump"]) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, text="<broken"))
        assert sources._parse_rss_feed(client, "https://feed", SignalSource.OFFICIAL_RSS, "def", ["trump"]) == []
    finally:
        client.close()


def test_specific_rss_wrappers_and_custom_rss(monkeypatch) -> None:
    settings = make_settings(custom_rss_urls=["https://c1", "https://c2"])
    captured: list[tuple[str, SignalSource]] = []

    def _fake_parse(client, feed_url, source, default_author, keywords):
        captured.append((feed_url, source))
        return []

    monkeypatch.setattr(sources, "_parse_rss_feed", _fake_parse)

    client = httpx.Client()
    try:
        assert sources._fetch_truth_social_rss(client, settings) == []
        assert sources._fetch_official_press_rss(client, settings) == []
        assert sources._fetch_custom_rss(client, settings) == []
    finally:
        client.close()
    assert len(captured) == 4


def test_fetch_x_recent_http_and_payload_failures(monkeypatch) -> None:
    settings = make_settings(x_bearer_token="token", signal_keywords=["trump"])

    client = httpx.Client()
    try:
        def _raise_http(*_args, **_kwargs):
            raise httpx.HTTPError("boom")

        monkeypatch.setattr(client, "get", _raise_http)
        assert sources._fetch_x_recent(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(500, payload={}))
        assert sources._fetch_x_recent(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=ValueError("bad")))
        assert sources._fetch_x_recent(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=[1, 2]))
        assert sources._fetch_x_recent(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload={"data": "nope"}))
        assert sources._fetch_x_recent(client, settings) == []
    finally:
        client.close()


def test_fetch_newsapi_success_and_failure_paths(monkeypatch) -> None:
    settings = make_settings(news_api_key="k", signal_keywords=["trump"])
    payload = {
        "articles": [
            {
                "title": "Trump headline",
                "description": "details",
                "publishedAt": "2025-01-01T00:00:00Z",
                "source": {"name": "wire"},
                "url": "https://n/1",
            },
            {"title": "Other", "description": "none"},
            "bad",
        ]
    }
    client = httpx.Client()
    try:
        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=payload))
        items = sources._fetch_newsapi(client, settings)
        assert len(items) == 1
        assert items[0].source == SignalSource.NEWS_API

        no_key = make_settings(news_api_key=None)
        assert sources._fetch_newsapi(client, no_key) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(500, payload={}))
        assert sources._fetch_newsapi(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=ValueError("bad")))
        assert sources._fetch_newsapi(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload=[1]))
        assert sources._fetch_newsapi(client, settings) == []

        monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: _FakeResponse(200, payload={"articles": "bad"}))
        assert sources._fetch_newsapi(client, settings) == []
    finally:
        client.close()


def test_signal_client_fetch_all_provider_handling_and_to_json() -> None:
    settings = make_settings(signal_services=["x", "unknown"], signal_lookback_minutes=60)
    client = sources.SignalClient(settings)
    try:
        client.providers["x"] = lambda _c, _s: [_signal("1"), _signal("1")]
        out = client.fetch_all()
        assert len(out) == 1
        json_blob = sources.to_json(out)
        assert '"source_id": "1"' in json_blob

        client.providers["x"] = lambda _c, _s: (_ for _ in ()).throw(RuntimeError("fail"))
        assert client.fetch_all() == []
    finally:
        client.close()
