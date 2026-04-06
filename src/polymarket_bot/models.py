from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class SignalSource(str, Enum):
    X = "x"
    TRUTH_SOCIAL = "truth_social"
    OFFICIAL_RSS = "official_rss"


@dataclass(frozen=True)
class SignalItem:
    source: SignalSource
    source_id: str
    url: str
    author: str
    text: str
    published_at: datetime
    fetched_at: datetime


@dataclass(frozen=True)
class CandidateMarket:
    market_id: str
    question: str
    slug: str
    yes_token_id: str
    best_ask: float
    best_bid: float
    volume_24h: float
    liquidity: float
    min_tick_size: float = 0.01
    neg_risk: bool = False
    enable_order_book: bool = True


class BetSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class BetDecision:
    market_id: str
    token_id: str
    side: BetSide
    price: float
    usd_size: float
    confidence: float
    reason: str


@dataclass(frozen=True)
class ExecutedAction:
    status: str
    details: dict[str, str | float | int | bool]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
