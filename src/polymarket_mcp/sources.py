from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from .config import Settings
from .models import SignalItem, SignalSource, utc_now

SignalProvider = Callable[[httpx.Client, Settings], list[SignalItem]]


class SignalClient:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.client: httpx.Client = httpx.Client(timeout=20)
        self.providers: dict[str, SignalProvider] = {
            "x": _fetch_x_recent,
            "truth_rss": _fetch_truth_social_rss,
            "official_rss": _fetch_official_press_rss,
            "newsapi": _fetch_newsapi,
            "custom_rss": _fetch_custom_rss,
        }

    def close(self) -> None:
        self.client.close()

    def fetch_all(self) -> list[SignalItem]:
        items: list[SignalItem] = []
        for service_name in self.settings.signal_services:
            provider = self.providers.get(service_name.strip().lower())
            if provider is None:
                continue
            try:
                items.extend(provider(self.client, self.settings))
            except Exception:  # noqa: BLE001
                continue
        return _within_lookback(_dedupe(items), self.settings.signal_lookback_minutes)


def _within_lookback(items: list[SignalItem], lookback_minutes: int) -> list[SignalItem]:
    cutoff = utc_now() - timedelta(minutes=lookback_minutes)
    return [item for item in items if item.published_at >= cutoff]


def _dedupe(items: list[SignalItem]) -> list[SignalItem]:
    seen: set[tuple[str, str]] = set()
    out: list[SignalItem] = []
    for item in items:
        key = (item.source.value, item.source_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _parse_x_datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_rss_datetime(value: str):
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=utc_now().tzinfo)
    return parsed


def _item_text(item: ElementTree.Element, tag: str) -> str:
    value = item.findtext(tag, default="")
    return value.strip()


def _fetch_x_recent(client: httpx.Client, settings: Settings) -> list[SignalItem]:
    if not settings.x_bearer_token:
        return []

    query = " OR ".join(f'"{kw}"' for kw in settings.signal_keywords)
    params = {
        "query": query,
        "max_results": "25",
        "tweet.fields": "created_at,author_id",
    }
    headers = {"Authorization": f"Bearer {settings.x_bearer_token}"}
    try:
        response = client.get("https://api.x.com/2/tweets/search/recent", params=params, headers=headers)
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []

    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []

    tweets = payload.get("data", [])
    if not isinstance(tweets, list):
        return []

    now = utc_now()
    results: list[SignalItem] = []
    for tweet in tweets:
        if not isinstance(tweet, dict):
            continue
        text = str(tweet.get("text", ""))
        if not _contains_keyword(text, settings.signal_keywords):
            continue
        created_raw = str(tweet.get("created_at", ""))
        try:
            published = _parse_x_datetime(created_raw)
        except ValueError:
            published = now
        tweet_id = str(tweet.get("id", ""))
        author = str(tweet.get("author_id", "unknown"))
        results.append(
            SignalItem(
                source=SignalSource.X,
                source_id=tweet_id,
                url=f"https://x.com/i/web/status/{tweet_id}",
                author=author,
                text=text,
                published_at=published,
                fetched_at=now,
            )
        )
    return results


def _parse_rss_feed(
    client: httpx.Client,
    feed_url: str,
    source: SignalSource,
    default_author: str,
    keywords: list[str],
) -> list[SignalItem]:
    try:
        response = client.get(feed_url)
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        return []

    now = utc_now()
    results: list[SignalItem] = []
    for item in root.findall(".//item"):
        title = _item_text(item, "title")
        link = _item_text(item, "link")
        guid = _item_text(item, "guid") or link
        description = _item_text(item, "description")
        author = _item_text(item, "author") or default_author
        pub = _item_text(item, "pubDate")
        content = f"{title} {description}".strip()
        if not _contains_keyword(content, keywords):
            continue
        published = _parse_rss_datetime(pub) if pub else now
        results.append(
            SignalItem(
                source=source,
                source_id=guid,
                url=link,
                author=author,
                text=content,
                published_at=published,
                fetched_at=now,
            )
        )
    return results


def _fetch_truth_social_rss(client: httpx.Client, settings: Settings) -> list[SignalItem]:
    return _parse_rss_feed(
        client=client,
        feed_url="https://www.presidency.ucsb.edu/taxonomy/term/428/all/feed/feed?items_per_page=20",
        source=SignalSource.TRUTH_SOCIAL,
        default_author="truth-social-fallback",
        keywords=settings.signal_keywords,
    )


def _fetch_official_press_rss(client: httpx.Client, settings: Settings) -> list[SignalItem]:
    return _parse_rss_feed(
        client=client,
        feed_url="https://www.presidency.ucsb.edu/documents/app-categories/press-office/press-releases?items_per_page=60",
        source=SignalSource.OFFICIAL_RSS,
        default_author="official-press",
        keywords=settings.signal_keywords,
    )


def _fetch_custom_rss(client: httpx.Client, settings: Settings) -> list[SignalItem]:
    all_items: list[SignalItem] = []
    for feed_url in settings.custom_rss_urls:
        all_items.extend(
            _parse_rss_feed(
                client=client,
                feed_url=feed_url,
                source=SignalSource.CUSTOM_RSS,
                default_author="custom-rss",
                keywords=settings.signal_keywords,
            )
        )
    return all_items


def _fetch_newsapi(client: httpx.Client, settings: Settings) -> list[SignalItem]:
    if not settings.news_api_key:
        return []

    query = " OR ".join(f'"{kw}"' for kw in settings.signal_keywords)
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": "20",
        "apiKey": settings.news_api_key,
    }
    try:
        response = client.get("https://newsapi.org/v2/everything", params=params)
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []

    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        return []

    now = utc_now()
    results: list[SignalItem] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", "")).strip()
        description = str(article.get("description", "")).strip()
        content = f"{title} {description}".strip()
        if not content or not _contains_keyword(content, settings.signal_keywords):
            continue
        published_raw = str(article.get("publishedAt", ""))
        try:
            published = _parse_x_datetime(published_raw)
        except ValueError:
            published = now
        source_info = article.get("source")
        source_name = "newsapi"
        if isinstance(source_info, dict):
            source_name = str(source_info.get("name", source_name))
        article_url = str(article.get("url", "")).strip()
        article_id = article_url or f"newsapi-{hash(content)}"
        results.append(
            SignalItem(
                source=SignalSource.NEWS_API,
                source_id=article_id,
                url=article_url,
                author=source_name,
                text=content,
                published_at=published,
                fetched_at=now,
            )
        )
    return results


def to_json(items: list[SignalItem]) -> str:
    data = [
        {
            "source": item.source.value,
            "source_id": item.source_id,
            "url": item.url,
            "author": item.author,
            "text": item.text,
            "published_at": item.published_at.isoformat(),
            "fetched_at": item.fetched_at.isoformat(),
        }
        for item in items
    ]
    return json.dumps(data, ensure_ascii=False)
