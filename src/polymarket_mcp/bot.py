from __future__ import annotations

import json
import time
from datetime import datetime

import httpx

from .config import Settings
from .execution import ExecutionEngine
from .polymarket_client import MarketClient
from .sources import SignalClient
from .strategy import Strategy, StrategyInput


class PolymarketBot:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.sources: SignalClient = SignalClient(settings)
        self.markets: MarketClient = MarketClient(settings)
        self.strategy: Strategy = Strategy(settings)
        self.execution: ExecutionEngine = ExecutionEngine(settings)

    def close(self) -> None:
        self.sources.close()
        self.markets.close()

    def run_cycle(self) -> dict[str, object]:
        errors: list[str] = []

        try:
            signals = self.sources.fetch_all()
        except httpx.HTTPError as exc:
            errors.append(f"signal_fetch_http_error:{exc}")
            signals = []
        except Exception as exc:  # noqa: BLE001
            errors.append(f"signal_fetch_error:{exc}")
            signals = []

        try:
            markets = self.markets.list_candidate_markets(self.settings.signal_keywords)
        except httpx.HTTPError as exc:
            errors.append(f"market_fetch_http_error:{exc}")
            markets = []
        except Exception as exc:  # noqa: BLE001
            errors.append(f"market_fetch_error:{exc}")
            markets = []

        try:
            decisions = self.strategy.decide(StrategyInput(signals=signals, markets=markets))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"strategy_error:{exc}")
            decisions = []

        try:
            actions = self.execution.execute(decisions)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"execution_error:{exc}")
            actions = []

        return {
            "timestamp": datetime.now().isoformat(),
            "signal_count": len(signals),
            "market_count": len(markets),
            "decision_count": len(decisions),
            "action_count": len(actions),
            "errors": errors,
            "actions": [
                {
                    "status": action.status,
                    "details": action.details,
                }
                for action in actions
            ],
        }

    def run_forever(self) -> None:
        while True:
            try:
                result = self.run_cycle()
            except Exception as exc:  # noqa: BLE001
                result = {
                    "timestamp": datetime.now().isoformat(),
                    "signal_count": 0,
                    "market_count": 0,
                    "decision_count": 0,
                    "action_count": 0,
                    "errors": [f"cycle_error:{exc}"],
                    "actions": [],
                }
            print(json.dumps(result, ensure_ascii=False))
            time.sleep(self.settings.poll_interval_seconds)
