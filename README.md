# polymarket_bot

Simple backend bot scaffold. Goal: ingest Trump-related signals in near real time, scan Polymarket markets, place small rule-based bets with strict risk limits.

## What this project does

- Polls multi-source signals:
  - X recent-search API (if `X_BEARER_TOKEN` set)
  - RSS fallback feed path for Truth/press ingestion
  - Official press feed path
- Scans Polymarket Gamma API markets (`/markets`) for keyword-matching questions.
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
cd /Users/dress/Desktop/Personal/Projects/Code/polymarket_bot
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
PYTHONPATH=src python -m polymarket_bot.main
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
