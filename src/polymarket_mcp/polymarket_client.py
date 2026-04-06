from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import httpx

from .config import Settings
from .models import CandidateMarket

MarketProvider = Callable[[httpx.Client, Settings, list[str]], list[CandidateMarket]]
LOGGER = logging.getLogger(__name__)


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
            normalized = service_name.strip().lower()
            provider = self.providers.get(normalized)
            if provider is None:
                LOGGER.warning("market provider unsupported: %s", normalized)
                continue
            try:
                candidates.extend(provider(self.client, self.settings, keywords))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("market provider failed: %s (%s)", normalized, exc)
                continue
        return _dedupe(candidates)

    def list_candidate_markets_with_meta(self, keywords: list[str]) -> tuple[list[CandidateMarket], dict[str, str]]:
        candidates: list[CandidateMarket] = []
        errors: dict[str, str] = {}
        for service_name in self.settings.market_services:
            normalized = service_name.strip().lower()
            provider = self.providers.get(normalized)
            if provider is None:
                errors[normalized] = "unsupported_provider"
                continue
            try:
                candidates.extend(provider(self.client, self.settings, keywords))
            except Exception as exc:  # noqa: BLE001
                errors[normalized] = str(exc)
        return _dedupe(candidates), errors

    def search_markets_with_meta(self, query: str, limit: int) -> tuple[list[CandidateMarket], dict[str, str]]:
        candidates: list[CandidateMarket] = []
        errors: dict[str, str] = {}
        normalized_query = query.strip()
        if not normalized_query:
            return [], {"search": "empty_query"}

        for service_name in self.settings.market_services:
            normalized = service_name.strip().lower()
            if normalized == "gamma":
                try:
                    candidates.extend(_search_gamma_markets(self.client, self.settings, normalized_query, limit))
                except Exception as exc:  # noqa: BLE001
                    errors[normalized] = str(exc)
                continue
            errors[normalized] = "unsupported_provider"

        return _dedupe(candidates), errors

    def get_current_price_with_meta(self, token_id: str) -> tuple[dict[str, object] | None, dict[str, str]]:
        normalized_token = token_id.strip()
        if not normalized_token:
            return None, {"price": "empty_token_id"}

        market = _find_market_by_token(self.client, self.settings, normalized_token)
        if market is None:
            return None, {"gamma": "token_not_found"}

        best_bid = _parse_float(market.get("bestBid"), 0.0)
        best_ask = _parse_float(market.get("bestAsk"), 0.0)
        mid_price = round((best_bid + best_ask) / 2, 6) if best_bid > 0 and best_ask > 0 else 0.0
        spread = round(max(0.0, best_ask - best_bid), 6)

        payload: dict[str, object] = {
            "market_id": str(market.get("id", "")),
            "question": str(market.get("question", "")),
            "token_id": normalized_token,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "min_tick_size": _parse_float(market.get("minimum_tick_size"), 0.01),
        }
        return payload, {}

    def get_orderbook_with_meta(self, token_id: str, depth: int = 20) -> tuple[dict[str, object] | None, dict[str, str]]:
        normalized_token = token_id.strip()
        if not normalized_token:
            return None, {"orderbook": "empty_token_id"}

        clipped_depth = max(1, min(100, depth))
        payload = _fetch_orderbook_payload(self.client, self.settings, normalized_token)
        if payload is None:
            return None, {"clob": "orderbook_unavailable"}

        bids = _normalize_orderbook_levels(payload.get("bids"), clipped_depth)
        asks = _normalize_orderbook_levels(payload.get("asks"), clipped_depth)
        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 0.0
        mid_price = round((best_bid + best_ask) / 2, 6) if best_bid > 0 and best_ask > 0 else 0.0
        spread = round(max(0.0, best_ask - best_bid), 6)

        return {
            "token_id": normalized_token,
            "depth": clipped_depth,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
        }, {}


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
        market = _candidate_from_gamma_item(item)
        if market is None:
            continue

        question_blob = f"{market.question} {market.slug}".lower()
        if not any(keyword in question_blob for keyword in keyword_set):
            continue
        candidates.append(market)
    return candidates


def _search_gamma_markets(client: httpx.Client, settings: Settings, query: str, limit: int) -> list[CandidateMarket]:
    params = {
        "limit": str(max(1, min(100, limit))),
        "closed": "false",
        "search": query,
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

    query_lower = query.lower()
    out: list[CandidateMarket] = []
    for item in payload:
        market = _candidate_from_gamma_item(item)
        if market is None:
            continue
        question_blob = f"{market.question} {market.slug}".lower()
        if query_lower not in question_blob:
            continue
        out.append(market)
    return out


def _find_market_by_token(client: httpx.Client, settings: Settings, token_id: str) -> dict[str, object] | None:
    params = {
        "limit": str(settings.market_limit),
        "closed": "false",
    }
    response = _request_with_retry(client, f"{settings.gamma_base_url}/markets", params=params)
    if response is None:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None

    for item in payload:
        if not isinstance(item, dict):
            continue
        token_ids = _parse_token_ids(item.get("clobTokenIds"))
        if token_id in token_ids:
            return item
    return None


def _fetch_orderbook_payload(client: httpx.Client, settings: Settings, token_id: str) -> dict[str, object] | None:
    endpoints = [
        (f"{settings.clob_host}/book", {"token_id": token_id}),
        (f"{settings.clob_host}/orderbook/{token_id}", {}),
        (f"{settings.clob_host}/orderbook", {"token_id": token_id}),
    ]
    for url, params in endpoints:
        response = _request_with_retry(client, url, params=params)
        if response is None:
            continue
        try:
            payload = response.json()
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("bids"), list) and isinstance(payload.get("asks"), list):
            return payload
    return None


def _normalize_orderbook_levels(raw_levels: object, depth: int) -> list[dict[str, float]]:
    if not isinstance(raw_levels, list):
        return []

    out: list[dict[str, float]] = []
    for raw in raw_levels:
        if len(out) >= depth:
            break
        if isinstance(raw, dict):
            price = _parse_float(raw.get("price"), -1.0)
            size = _parse_float(raw.get("size"), -1.0)
        elif isinstance(raw, list) and len(raw) >= 2:
            price = _parse_float(raw[0], -1.0)
            size = _parse_float(raw[1], -1.0)
        else:
            continue
        if price < 0 or size < 0:
            continue
        out.append({"price": round(price, 6), "size": round(size, 6)})
    return out


def _candidate_from_gamma_item(item: object) -> CandidateMarket | None:
    if not isinstance(item, dict):
        return None
    question = str(item.get("question", ""))
    slug = str(item.get("slug", ""))
    market_id = str(item.get("id", "")).strip()
    if not market_id or not question:
        return None

    enable_order_book = _parse_bool(item.get("enableOrderBook"), True)
    if not enable_order_book:
        return None

    token_ids_raw = item.get("clobTokenIds")
    token_ids = _parse_token_ids(token_ids_raw)
    if not token_ids:
        return None

    best_ask = _parse_float(item.get("bestAsk"), 0.99)
    best_bid = _parse_float(item.get("bestBid"), 0.0)
    volume = _parse_float(item.get("volume24hr"), 0.0)
    liquidity = _parse_float(item.get("liquidityNum"), 0.0)
    min_tick_size = _parse_float(item.get("minimum_tick_size"), 0.01)
    if min_tick_size <= 0:
        min_tick_size = 0.01

    return CandidateMarket(
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
