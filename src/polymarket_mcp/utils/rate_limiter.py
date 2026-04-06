from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from time import monotonic


class EndpointCategory(str, Enum):
    MARKET_DATA = "market_data"
    TRADING_BURST = "trading_burst"
    TRADING_SUSTAINED = "trading_sustained"


@dataclass
class Bucket:
    max_tokens: int
    refill_per_second: float
    tokens: float
    last_refill: float


@dataclass(frozen=True)
class RateLimiterMetric:
    timestamp: datetime
    category: str
    wait_time_ms: float
    tokens_remaining: float
    max_tokens: int
    backoff_active: bool


class RateLimiter:
    def __init__(self) -> None:
        now = monotonic()
        self.buckets: dict[EndpointCategory, Bucket] = {
            EndpointCategory.MARKET_DATA: Bucket(max_tokens=200, refill_per_second=20.0, tokens=200.0, last_refill=now),
            EndpointCategory.TRADING_BURST: Bucket(max_tokens=2400, refill_per_second=240.0, tokens=2400.0, last_refill=now),
            EndpointCategory.TRADING_SUSTAINED: Bucket(max_tokens=24000, refill_per_second=40.0, tokens=24000.0, last_refill=now),
        }
        self.backoff_until: dict[EndpointCategory, float] = {}
        self.metrics: deque[RateLimiterMetric] = deque(maxlen=1000)

    def acquire(self, category: EndpointCategory, tokens: int = 1) -> float:
        bucket = self.buckets[category]
        now = monotonic()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(bucket.max_tokens, bucket.tokens + elapsed * bucket.refill_per_second)
            bucket.last_refill = now

        wait_time = 0.0
        backoff_deadline = self.backoff_until.get(category)
        if backoff_deadline is not None and backoff_deadline > now:
            wait_time = backoff_deadline - now

        if bucket.tokens < tokens:
            shortfall = tokens - bucket.tokens
            wait_time = max(wait_time, shortfall / bucket.refill_per_second)
            bucket.tokens = 0.0
        else:
            bucket.tokens -= tokens

        self.metrics.append(
            RateLimiterMetric(
                timestamp=datetime.now(timezone.utc),
                category=category.value,
                wait_time_ms=wait_time * 1000.0,
                tokens_remaining=bucket.tokens,
                max_tokens=bucket.max_tokens,
                backoff_active=(backoff_deadline is not None and backoff_deadline > now),
            )
        )
        return wait_time

    def handle_429(self, category: EndpointCategory, retry_after_seconds: float | None = None) -> float:
        now = monotonic()
        existing = self.backoff_until.get(category, now)
        base = max(existing - now, 1.0)
        next_backoff = retry_after_seconds if retry_after_seconds is not None else min(base * 2.0, 60.0)
        self.backoff_until[category] = now + next_backoff
        return next_backoff

    def metrics_summary(self) -> dict[str, object]:
        if not self.metrics:
            return {
                "total_requests": 0,
                "avg_wait_time_ms": 0.0,
                "max_wait_time_ms": 0.0,
                "backoff_events": 0,
                "by_category": {},
            }

        recent = list(self.metrics)
        by_category: dict[str, dict[str, float]] = {}
        for metric in recent:
            bucket = by_category.setdefault(metric.category, {"requests": 0.0, "avg_wait_time_ms": 0.0})
            bucket["requests"] += 1.0
            bucket["avg_wait_time_ms"] += metric.wait_time_ms

        for category, stats in by_category.items():
            requests = stats["requests"]
            stats["avg_wait_time_ms"] = stats["avg_wait_time_ms"] / requests if requests else 0.0
            stats["requests"] = int(requests)

        waits = [m.wait_time_ms for m in recent]
        return {
            "total_requests": len(recent),
            "avg_wait_time_ms": sum(waits) / len(waits),
            "max_wait_time_ms": max(waits),
            "backoff_events": sum(1 for m in recent if m.backoff_active),
            "by_category": by_category,
        }
