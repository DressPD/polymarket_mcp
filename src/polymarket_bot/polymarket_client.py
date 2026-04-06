from __future__ import annotations

import json
import time

import httpx

from .config import Settings
from .models import CandidateMarket


class PolymarketClient:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.client: httpx.Client = httpx.Client(timeout=20)

    def close(self) -> None:
        self.client.close()

    def list_candidate_markets(self, keywords: list[str]) -> list[CandidateMarket]:
        params = {
            "limit": str(self.settings.market_limit),
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        response = self._request_with_retry(
            f"{self.settings.gamma_base_url}/markets",
            params=params,
        )
        if response is None:
            return []

        try:
            markets_payload = response.json()
        except ValueError:
            return []
        if not isinstance(markets_payload, list):
            return []

        keyword_set = {kw.lower() for kw in keywords}
        candidates: list[CandidateMarket] = []
        for item in markets_payload:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", ""))
            slug = str(item.get("slug", ""))
            market_id = str(item.get("id", "")).strip()
            if not market_id or not question:
                continue

            question_blob = f"{question} {slug}".lower()
            if not any(keyword in question_blob for keyword in keyword_set):
                continue

            enable_order_book = self._parse_bool(item.get("enableOrderBook"), True)
            if not enable_order_book:
                continue

            token_ids_raw = item.get("clobTokenIds")
            token_ids = self._parse_token_ids(token_ids_raw)
            if not token_ids:
                continue

            best_ask = self._parse_float(item.get("bestAsk"), 0.99)
            best_bid = self._parse_float(item.get("bestBid"), 0.0)
            volume = self._parse_float(item.get("volume24hr"), 0.0)
            liquidity = self._parse_float(item.get("liquidityNum"), 0.0)
            min_tick_size = self._parse_float(item.get("minimum_tick_size"), 0.01)
            if min_tick_size <= 0:
                min_tick_size = 0.01
            candidates.append(
                CandidateMarket(
                    market_id=market_id,
                    question=question,
                    slug=slug,
                    yes_token_id=token_ids[0],
                    best_ask=best_ask,
                    best_bid=best_bid,
                    volume_24h=volume,
                    liquidity=liquidity,
                    min_tick_size=min_tick_size,
                    neg_risk=self._parse_bool(item.get("negRisk"), False),
                    enable_order_book=enable_order_book,
                )
            )
        return candidates

    def _request_with_retry(self, url: str, params: dict[str, str], attempts: int = 3) -> httpx.Response | None:
        delay_seconds = 0.5
        for attempt in range(attempts):
            try:
                response = self.client.get(url, params=params)
            except httpx.HTTPError:
                response = None

            if response is not None and response.status_code == 200:
                return response

            if response is not None and response.status_code in {400, 401, 403, 404}:
                return None

            if attempt < attempts - 1:
                time.sleep(delay_seconds)
                delay_seconds *= 2
        return None

    @staticmethod
    def _parse_token_ids(token_ids_raw: object) -> list[str]:
        if isinstance(token_ids_raw, list):
            return [str(item) for item in token_ids_raw if str(item)]
        if isinstance(token_ids_raw, str):
            stripped = token_ids_raw.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed if str(item)]
                except json.JSONDecodeError:
                    return []
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return []

    @staticmethod
    def _parse_float(value: object, default: float) -> float:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

    @staticmethod
    def _parse_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default
