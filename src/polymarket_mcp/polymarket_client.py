from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx

from .config import Settings
from .models import CandidateMarket

MarketProvider = Callable[[httpx.Client, Settings, list[str]], list[CandidateMarket]]


class MarketClient:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.client: httpx.Client = httpx.Client(timeout=20)
        self.providers: dict[str, MarketProvider] = {
            "gamma": _fetch_gamma_candidates,
        }

    def close(self) -> None:
        self.client.close()

    def list_candidate_markets(self, keywords: list[str]) -> list[CandidateMarket]:
        candidates: list[CandidateMarket] = []
        for service_name in self.settings.market_services:
            provider = self.providers.get(service_name.strip().lower())
            if provider is None:
                continue
            try:
                candidates.extend(provider(self.client, self.settings, keywords))
            except Exception:  # noqa: BLE001
                continue
        return _dedupe(candidates)


def _dedupe(candidates: list[CandidateMarket]) -> list[CandidateMarket]:
    seen: set[str] = set()
    out: list[CandidateMarket] = []
    for item in candidates:
        if item.market_id in seen:
            continue
        seen.add(item.market_id)
        out.append(item)
    return out


def _fetch_gamma_candidates(client: httpx.Client, settings: Settings, keywords: list[str]) -> list[CandidateMarket]:
    params = {
        "limit": str(settings.market_limit),
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
    }
    response = _request_with_retry(client, f"{settings.gamma_base_url}/markets", params=params)
    if response is None:
        return []

    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []

    keyword_set = {kw.lower() for kw in keywords}
    candidates: list[CandidateMarket] = []
    for item in payload:
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

        enable_order_book = _parse_bool(item.get("enableOrderBook"), True)
        if not enable_order_book:
            continue

        token_ids_raw = item.get("clobTokenIds")
        token_ids = _parse_token_ids(token_ids_raw)
        if not token_ids:
            continue

        best_ask = _parse_float(item.get("bestAsk"), 0.99)
        best_bid = _parse_float(item.get("bestBid"), 0.0)
        volume = _parse_float(item.get("volume24hr"), 0.0)
        liquidity = _parse_float(item.get("liquidityNum"), 0.0)
        min_tick_size = _parse_float(item.get("minimum_tick_size"), 0.01)
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
                neg_risk=_parse_bool(item.get("negRisk"), False),
                enable_order_book=enable_order_book,
            )
        )
    return candidates


def _request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    attempts: int = 3,
) -> httpx.Response | None:
    delay_seconds = 0.5
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
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
