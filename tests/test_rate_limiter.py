from __future__ import annotations

import polymarket_mcp.utils.rate_limiter as rl


def test_acquire_and_metrics_summary_empty_and_non_empty(monkeypatch) -> None:
    t = {"now": 1000.0}
    monkeypatch.setattr(rl, "monotonic", lambda: t["now"])

    limiter = rl.RateLimiter()

    empty = rl.RateLimiter().metrics_summary()
    assert empty["total_requests"] == 0
    assert empty["backoff_events"] == 0

    wait = limiter.acquire(rl.EndpointCategory.MARKET_DATA, tokens=1)
    assert wait == 0.0

    summary = limiter.metrics_summary()
    assert summary["total_requests"] == 1
    assert "market_data" in summary["by_category"]


def test_acquire_waits_for_shortfall_and_backoff(monkeypatch) -> None:
    t = {"now": 2000.0}
    monkeypatch.setattr(rl, "monotonic", lambda: t["now"])
    limiter = rl.RateLimiter()

    bucket = limiter.buckets[rl.EndpointCategory.MARKET_DATA]
    bucket.tokens = 0.0

    limiter.backoff_until[rl.EndpointCategory.MARKET_DATA] = t["now"] + 2.0
    wait = limiter.acquire(rl.EndpointCategory.MARKET_DATA, tokens=10)

    assert wait >= 2.0
    assert bucket.tokens == 0.0


def test_handle_429_uses_retry_after_or_exponential(monkeypatch) -> None:
    t = {"now": 3000.0}
    monkeypatch.setattr(rl, "monotonic", lambda: t["now"])
    limiter = rl.RateLimiter()

    first = limiter.handle_429(rl.EndpointCategory.TRADING_BURST, retry_after_seconds=3.0)
    assert first == 3.0

    t["now"] += 0.5
    second = limiter.handle_429(rl.EndpointCategory.TRADING_BURST)
    assert 5.0 <= second <= 6.0
