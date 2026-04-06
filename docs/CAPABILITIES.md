# polymarket_mcp Capabilities

## What this service is

`polymarket_mcp` is a local MCP server and bot runtime that helps an LLM:

- collect political/news signals,
- inspect Polymarket markets and token pricing,
- simulate or submit guarded demo orders,
- manage a confirmation workflow,
- inspect in-memory positions.

Default behavior is safety-first (`dry_run` and no autonomous live trading).

---

## Core capabilities

### 1) Signal ingestion (multi-source)

The service can fetch and normalize signal items from multiple providers:

- `x`
- `truth_rss`
- `official_rss`
- `newsapi`
- `custom_rss`

Each signal item is normalized into a stable structure (source, text, URL, author, timestamp).

### 2) Market discovery and inspection

The service can scan candidate Polymarket markets and expose:

- market/question metadata,
- token IDs,
- bid/ask,
- liquidity and volume,
- market constraints like `min_tick_size` and `neg_risk`.

It also supports direct token-level checks:

- current best bid/ask/mid price,
- orderbook levels with depth control.

### 3) Strategy + cycle execution

The runtime can run one full cycle:

1. fetch signals,
2. fetch markets,
3. generate strategy decisions,
4. execute with guardrails (or dry-run).

This is exposed as MCP tool `run_cycle_once` for deterministic LLM orchestration.

### 4) Guarded order flow

The service supports demo submission and optional explicit confirmation:

- `submit_demo_order`
- `confirm_demo_order`

When thresholds are exceeded and autonomous mode is disabled, the service returns `requires_confirmation=true` and stores a pending item.

### 5) Position and pending state inspection

The service provides in-memory operational visibility:

- `list_positions`
- `list_pending_confirmations`

Positions track both units (`size`) and notional USD (`value_usd`).

### 6) MCP-first contract for LLMs

Every MCP tool returns a consistent envelope:

- `ok`
- `tool`
- `error` and `error_category` on failure
- payload fields (`result`, `items`, `count`, `pagination`, `warnings`) when relevant

List-like tools support MCP pagination with `limit` and `cursor`.

---

## MCP tool catalog (user-facing)

### Health and runtime

- `health`: Runtime status, enabled providers, limits, context mode.
- `run_cycle_once`: Execute one end-to-end cycle and return summary.

### Signals and markets

- `fetch_signals(limit?, cursor?)`: Paged signal retrieval plus provider warnings.
- `list_markets(limit?, cursor?)`: Paged candidate market retrieval.
- `search_markets(query, limit?, cursor?)`: Query-based market search.
- `get_current_price(token_id)`: Best bid/ask/mid for one token.
- `get_orderbook(token_id, depth=20)`: Orderbook ladders for one token.

### Demo order workflow

- `submit_demo_order()`: Submit one deterministic demo decision.
- `confirm_demo_order(confirmation_id)`: Confirm pending decision.
- `list_positions()`: Current in-memory positions.
- `list_pending_confirmations()`: Awaiting confirmation queue.

---

## Safety controls and guardrails

The engine enforces configurable controls:

- max order size (`MAX_ORDER_SIZE_USD`)
- max total exposure (`MAX_TOTAL_EXPOSURE_USD`)
- max per-market exposure (`MAX_POSITION_SIZE_PER_MARKET`)
- minimum liquidity (`MIN_LIQUIDITY_REQUIRED`)
- maximum spread tolerance (`MAX_SPREAD_TOLERANCE`)
- confirmation threshold (`REQUIRE_CONFIRMATION_ABOVE_USD`)

Runtime mode controls:

- `BOT_DRY_RUN`
- `BOT_ENABLE_LIVE_TRADING`
- `ENABLE_AUTONOMOUS_TRADING`

Defaults are configured to avoid accidental live trading.

---

## Reliability behavior

The service is designed to keep operating when partial failures happen:

- provider failures are surfaced as warnings instead of silent drops,
- unsupported provider names are reported,
- cycle-level exceptions are caught and emitted as structured errors,
- MCP responses keep stable shapes even when upstream sources fail.

---

## What it does not do (yet)

Current scope is intentionally bounded:

- no persistent database for orders/positions/history,
- no full portfolio analytics dashboard,
- no advanced execution algos (TWAP/VWAP/iceberg),
- no exchange/broker abstraction beyond current providers.

Use `GAP_IMPROVEMENTS.MD` for next implementation milestones.
