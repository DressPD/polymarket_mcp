# Polymarket MCP Architecture

## Overview

This project exposes a local MCP server with deterministic tools for signal ingestion, market scanning, strategy evaluation, and guarded execution.

- Read-only capabilities: health, signal fetch, market listing, one-cycle simulation.
- Trade-adjacent capabilities: demo confirmation workflow (`submit_demo_order`, `confirm_demo_order`).

## Core Runtime Components

`ServerContext` is the dependency container.

- `settings`: validated runtime config from environment.
- `signal_client`: pluggable signal providers (`x`, `truth_rss`, `official_rss`, `newsapi`, `custom_rss`).
- `market_client`: pluggable market providers (`gamma` currently).
- `strategy`: confidence/liquidity based decisioning.
- `execution`: dry-run default with live-order pathway.
- `auth_client`: L2 credential cache wrapper.
- `rate_limiter`: category buckets + backoff + metrics summary.
- `safety_limits`: order/exposure/liquidity/spread/confirmation gates.

## Authentication Model

- L1-like identity input via env vars:
  - `POLYMARKET_PRIVATE_KEY`
  - `POLYMARKET_FUNDER_ADDRESS`
- L2 credentials optional:
  - `POLYMARKET_API_KEY`
  - `POLYMARKET_API_SECRET`
  - `POLYMARKET_API_PASSPHRASE`

`PolymarketAuthClient` caches credentials in memory and can persist discovered credentials into `.env` when file exists.

## Safety Validation Pipeline

`SafetyLimits.validate_order` applies five checks:

1. Order size cap (`MAX_ORDER_SIZE_USD`)
2. Total exposure cap (`MAX_TOTAL_EXPOSURE_USD`)
3. Per-market exposure cap (`MAX_POSITION_SIZE_PER_MARKET`)
4. Liquidity minimum (`MIN_LIQUIDITY_REQUIRED`)
5. Spread tolerance (`MAX_SPREAD_TOLERANCE`)

`ExposureCalculator` computes deterministic before/after exposure impact for BUY/SELL cases.

Confirmation gate:

- If order value exceeds `REQUIRE_CONFIRMATION_ABOVE_USD`
- And `ENABLE_AUTONOMOUS_TRADING=false`
- Server returns `requires_confirmation=true` and stores pending request for explicit confirm.

## MCP Tool Envelope

All tools return stable envelopes:

- `ok`: boolean
- `tool`: tool name
- `error` + `error_category` when failure
- `result` or `items` payload on success

## Rate Limiting

`RateLimiter` tracks endpoint categories:

- `market_data`
- `trading_burst`
- `trading_sustained`

Each category uses token bucket refill semantics plus optional 429 backoff state.
Metrics are collected in-memory and summarized via `metrics_summary()`.

## Logging

`utils/logger.py` provides redaction filter for sensitive tokens and key-value style secrets.

## Tests

- `tests/test_safety_limits_comprehensive.py`: exposure + five-gate validation + confirmation threshold checks.
- Existing tests cover strategy, execution, and MCP envelope behavior.
