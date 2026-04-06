# GAP_IMPROVEMENTS

## Current state

- Phase-1 quick wins implemented:
  - `search_markets`
  - `get_current_price`
  - `get_orderbook`
- Reliability contract improved:
  - pagination metadata
  - provider warnings metadata
  - request/shared context mode support
- Validation green:
  - `pytest`: 80 passed
  - coverage: 90.70%
  - bot smoke: pass
  - MCP smoke: pass

## Next steps

1. Add trading lifecycle tools
   - `create_limit_order`
   - `create_market_order`
   - `get_order_status`
   - `get_open_orders`
   - `cancel_order`

2. Add signer module for production order flow
   - `auth/signer.py` EIP-712 signing
   - typed order payload validation
   - explicit error mapping for auth/signature failures

3. Add market analysis expansion
   - `get_market_volume`
   - `get_liquidity`
   - `get_price_history`
   - `get_spread`

4. Add portfolio/PnL tools
   - `get_portfolio_summary`
   - `get_positions` (external/account-backed, not only in-memory)
   - `get_pnl`
   - `get_trade_history`

5. Add optional realtime mode
   - websocket manager with reconnect/backoff
   - subscription tools for price/orderbook/trade notifications

6. Reduce static-type warnings
   - annotate class attributes and unknown payload paths
   - add typed adapters for external JSON parsing
   - isolate Any from optional `py_clob_client` integration

7. Add docs for production runbook
   - rate-limit handling strategy
   - heartbeat and orderbook readiness checks
   - operational alerts and failure triage
