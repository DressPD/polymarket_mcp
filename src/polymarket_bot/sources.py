from __future__ import annotations

import json
from datetime import timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from .config import Settings
from .models import SignalItem, SignalSource, utc_now


class SourceClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(timeout=20)

    def close(self) -> None:
        self.client.close()

    def fetch_all(self) -> list[SignalItem]:
        items: list[SignalItem] = []
        items.extend(self._fetch_x_recent())
        items.extend(self._fetch_truth_social_rss())
        items.extend(self._fetch_official_press_rss())
        return self._within_lookback(items)

    def _within_lookback(self, items: list[SignalItem]) -> list[SignalItem]:
        cutoff = utc_now() - timedelta(minutes=self.settings.signal_lookback_minutes)
        return [item for item in items if item.published_at >= cutoff]

    def _fetch_x_recent(self) -> list[SignalItem]:
        if not self.settings.x_bearer_token:
            return []

        query = " OR ".join(f'"{kw}"' for kw in self.settings.signal_keywords)
        url = "https://api.x.com/2/tweets/search/recent"
        params = {
            "query": query,
            "max_results": "25",
            "tweet.fields": "created_at,author_id",
        }
        headers = {"Authorization": f"Bearer {self.settings.x_bearer_token}"}
        try:
            response = self.client.get(url, params=params, headers=headers)
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
            if not self._contains_keyword(text):
                continue
            created_raw = str(tweet.get("created_at", ""))
            try:
                created_at = self._parse_x_datetime(created_raw)
            except ValueError:
                created_at = now
            tweet_id = str(tweet.get("id", ""))
            author = str(tweet.get("author_id", "unknown"))
            results.append(
                SignalItem(
                    source=SignalSource.X,
                    source_id=tweet_id,
                    url=f"https://x.com/i/web/status/{tweet_id}",
                    author=author,
                    text=text,
                    published_at=created_at,
                    fetched_at=now,
                )
            )
        return results

    def _fetch_truth_social_rss(self) -> list[SignalItem]:
        return self._parse_rss_feed(
            feed_url="https://www.presidency.ucsb.edu/taxonomy/term/428/all/feed/feed?items_per_page=20",
            source=SignalSource.TRUTH_SOCIAL,
            default_author="truth-social-fallback",
        )

    def _fetch_official_press_rss(self) -> list[SignalItem]:
        return self._parse_rss_feed(
            feed_url="https://www.presidency.ucsb.edu/documents/app-categories/press-office/press-releases?items_per_page=60",
            source=SignalSource.OFFICIAL_RSS,
            default_author="official-press",
        )

    def _parse_rss_feed(
        self,
        feed_url: str,
        source: SignalSource,
        default_author: str,
    ) -> list[SignalItem]:
        try:
            response = self.client.get(feed_url)
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
            title = self._item_text(item, "title")
            link = self._item_text(item, "link")
            guid = self._item_text(item, "guid") or link
            description = self._item_text(item, "description")
            author = self._item_text(item, "author") or default_author
            pub = self._item_text(item, "pubDate")
            if not self._contains_keyword(f"{title} {description}"):
                continue
            published_at = self._parse_rss_datetime(pub) if pub else now
            results.append(
                SignalItem(
                    source=source,
                    source_id=guid,
                    url=link,
                    author=author,
                    text=f"{title} {description}".strip(),
                    published_at=published_at,
                    fetched_at=now,
                )
            )
        return results

    def _contains_keyword(self, text: str) -> bool:
        normalized = text.lower()
        return any(keyword.lower() in normalized for keyword in self.settings.signal_keywords)

    @staticmethod
    def _parse_x_datetime(value: str):
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _parse_rss_datetime(value: str):
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=utc_now().tzinfo)
        return parsed

    @staticmethod
    def _item_text(item: ElementTree.Element, tag: str) -> str:
        value = item.findtext(tag, default="")
        return value.strip()


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
