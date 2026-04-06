# polymarket_mcp

Signal-driven Polymarket bot with pluggable data services and local MCP wrapper for LLM clients.

## What this project does

- Polls multi-source signals (configurable provider order):
  - `x` (X recent-search API)
  - `truth_rss` (fallback feed path)
  - `official_rss` (official press feeds)
  - `newsapi` (optional NewsAPI key)
  - `custom_rss` (user-defined feeds)
- Scans Polymarket markets through pluggable market providers (`gamma` implemented).
- Runs a simple confidence + liquidity strategy.
- Executes orders through a guarded execution engine:
  - `dry_run` default
  - explicit live-trading gate
  - max USD per bet
  - max bets per hour

## Safety defaults

- `BOT_DRY_RUN=true`
- `BOT_ENABLE_LIVE_TRADING=false`

Bot prints simulated actions until you explicitly switch both flags.

## Setup

```bash
cd /path/to/polymarket_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

If editable install fails in old pip environments, use:

```bash
pip install .
```

Optional live trading dependencies:

```bash
pip install -e .[trade]
```

## Run

```bash
PYTHONPATH=src python -m polymarket_mcp.main
```

## Run MCP server locally

Start MCP over stdio (local process):

```bash
cd /path/to/polymarket_mcp
source .venv/bin/activate
pip install -e .
PYTHONPATH=src python -m polymarket_mcp.mcp_server
```

Available MCP tools:

- `health`
- `run_cycle_once`
- `fetch_signals`
- `list_markets`

Tool response envelope is consistent:

- `ok`: boolean
- `tool`: tool name
- `error` + `error_category` on failures
- tool-specific payload under stable keys (`result`, `items`, `count`, `limit`)

MCP limits are controlled by:

- `MCP_DEFAULT_LIMIT` (default tool list size)
- `MCP_MAX_LIMIT` (hard cap for tool list size)

## Connect MCP to clients

### GitHub Copilot CLI

Config file: `~/.copilot/mcp-config.json`

```json
{
  "mcpServers": {
    "polymarket_mcp": {
      "type": "local",
      "command": "/path/to/polymarket_mcp/.venv/bin/python",
      "args": ["-m", "polymarket_mcp.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/polymarket_mcp/src",
        "BOT_DRY_RUN": "true",
        "BOT_ENABLE_LIVE_TRADING": "false"
      },
      "tools": ["*"]
    }
  }
}
```

Then run Copilot CLI and verify with `/mcp show`.

### GitHub Copilot in VS Code

Workspace config: `.vscode/mcp.json`

```json
{
  "servers": {
    "polymarket_mcp": {
      "type": "stdio",
      "command": "/path/to/polymarket_mcp/.venv/bin/python",
      "args": ["-m", "polymarket_mcp.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/polymarket_mcp/src",
        "BOT_DRY_RUN": "true",
        "BOT_ENABLE_LIVE_TRADING": "false"
      }
    }
  }
}
```

Open Chat and enable MCP server tools.

### Claude Desktop

Open: **Settings → Developer → Edit Config**.

```json
{
  "mcpServers": {
    "polymarket_mcp": {
      "command": "/path/to/polymarket_mcp/.venv/bin/python",
      "args": ["-m", "polymarket_mcp.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/polymarket_mcp/src",
        "BOT_DRY_RUN": "true",
        "BOT_ENABLE_LIVE_TRADING": "false"
      }
    }
  }
}
```

Restart Claude Desktop fully after config changes.

### OpenCode

Config file: `~/.opencode.json` (or project `.opencode.json`)

```json
{
  "mcpServers": {
    "polymarket_mcp": {
      "command": "/path/to/polymarket_mcp/.venv/bin/python",
      "args": ["-m", "polymarket_mcp.mcp_server"],
      "type": "stdio",
      "env": [
        "PYTHONPATH=/path/to/polymarket_mcp/src",
        "BOT_DRY_RUN=true",
        "BOT_ENABLE_LIVE_TRADING=false"
      ]
    }
  }
}
```

Output is JSON per cycle:

```json
{
  "signal_count": 2,
  "market_count": 5,
  "decision_count": 1,
  "action_count": 1,
  "actions": [
    {
      "status": "dry_run_order",
      "details": {
        "market_id": "123",
        "token_id": "...",
        "side": "BUY",
        "price": 0.55,
        "usd_size": 5.0,
        "confidence": 0.71,
        "reason": "signals=4 ask=0.550"
      }
    }
  ]
}
```

## Live trading switch

Set all required variables:

- `BOT_DRY_RUN=false`
- `BOT_ENABLE_LIVE_TRADING=true`
- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_FUNDER_ADDRESS`

Optional if pre-generated:

- `POLYMARKET_API_KEY`
- `POLYMARKET_API_SECRET`
- `POLYMARKET_API_PASSPHRASE`

If creds missing, bot attempts `create_or_derive_api_creds()` via `py-clob-client`.

## Where to get keys

- X Bearer token:
  - https://docs.x.com/fundamentals/authentication/oauth-2-0/bearer-tokens
  - https://developer.x.com/en/portal/dashboard/apps-and-keys
- Polymarket authentication and credentials:
  - https://docs.polymarket.com/developers/CLOB/authentication
  - https://docs.polymarket.com/api-reference/authentication
  - https://docs.polymarket.com/quickstart
  - Settings page: https://polymarket.com/settings

### Polymarket key mapping

- `POLYMARKET_PRIVATE_KEY`: your wallet private key used to sign L1 auth/order payloads.
- `POLYMARKET_FUNDER_ADDRESS`: polygon address funding/signing context.
- `POLYMARKET_API_KEY/POLYMARKET_API_SECRET/POLYMARKET_API_PASSPHRASE`: L2 creds generated/derived through official client from L1 auth.

## Tests

```bash
PYTHONPATH=src pytest -q
```

## Important notes

- This is starter logic. Not production trading advice.
- Respect platform ToS and jurisdiction rules.
- Truth Social direct official public API was not verified in this run. Current path uses feed-based ingestion fallback.
- Add stronger risk modules before real funds:
  - portfolio exposure caps
  - duplicate-order/idempotency keys
  - stop-loss style guardrails
  - persistent storage for audit/recovery

## Reliability upgrades included

- HTTP retry with backoff for Gamma market fetches.
- Structured failure isolation in `run_cycle()` so one stage failure does not crash loop.
- RSS parsing via XML parser (safer than string split parsing).
- Market validation gates:
  - require valid market id/question/token ids
  - require `enableOrderBook=true`
  - parse and preserve `minimum_tick_size` and `negRisk`
- Execution validation gates:
  - reject invalid price/size/confidence
  - catch live order submission errors and return structured failure action
- MCP wrapper improvements:
  - consistent `ok` envelope in tool responses
  - bounded `limit` handling via config (`MCP_DEFAULT_LIMIT`, `MCP_MAX_LIMIT`)
  - health payload includes runtime limits and UTC time
