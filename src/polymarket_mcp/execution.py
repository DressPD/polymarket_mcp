from __future__ import annotations

from collections import deque
import math
from datetime import timedelta
from importlib import import_module
from typing import TYPE_CHECKING, Any

from .config import Settings
from .models import BetDecision, ExecutedAction, utc_now

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Deque


class ExecutionEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.executed_timestamps: Deque[datetime] = deque()

    def execute(self, decisions: list[BetDecision]) -> list[ExecutedAction]:
        actions: list[ExecutedAction] = []
        for decision in decisions:
            validation_error = self._validate_decision(decision)
            if validation_error:
                actions.append(
                    ExecutedAction(
                        status="skipped_invalid_decision",
                        details={
                            "market_id": decision.market_id,
                            "reason": validation_error,
                        },
                    )
                )
                continue

            if not self._allow_by_rate_limit():
                actions.append(
                    ExecutedAction(
                        status="skipped_rate_limit",
                        details={
                            "market_id": decision.market_id,
                            "reason": "max bets per hour reached",
                        },
                    )
                )
                continue

            if decision.usd_size > self.settings.max_usd_per_bet:
                actions.append(
                    ExecutedAction(
                        status="skipped_risk_limit",
                        details={
                            "market_id": decision.market_id,
                            "usd_size": decision.usd_size,
                        },
                    )
                )
                continue

            if self.settings.dry_run or not self.settings.enable_live_trading:
                self.executed_timestamps.append(utc_now())
                actions.append(
                    ExecutedAction(
                        status="dry_run_order",
                        details={
                            "market_id": decision.market_id,
                            "token_id": decision.token_id,
                            "side": decision.side.value,
                            "price": decision.price,
                            "usd_size": decision.usd_size,
                            "confidence": decision.confidence,
                            "reason": decision.reason,
                        },
                    )
                )
                continue

            try:
                order_id = self._live_order(decision)
            except Exception as exc:  # noqa: BLE001
                actions.append(
                    ExecutedAction(
                        status="live_order_failed",
                        details={
                            "market_id": decision.market_id,
                            "reason": str(exc),
                        },
                    )
                )
                continue

            self.executed_timestamps.append(utc_now())
            actions.append(
                ExecutedAction(
                    status="live_order_submitted",
                    details={
                        "market_id": decision.market_id,
                        "order_id": order_id,
                        "token_id": decision.token_id,
                        "side": decision.side.value,
                        "price": decision.price,
                        "usd_size": decision.usd_size,
                        "confidence": decision.confidence,
                    },
                )
            )
        return actions

    def _allow_by_rate_limit(self) -> bool:
        cutoff = utc_now() - timedelta(hours=1)
        while self.executed_timestamps and self.executed_timestamps[0] < cutoff:
            self.executed_timestamps.popleft()
        return len(self.executed_timestamps) < self.settings.max_bets_per_hour

    def _live_order(self, decision: BetDecision) -> str:
        try:
            clob_client_module = import_module("py_clob_client.client")
            clob_types_module = import_module("py_clob_client.clob_types")
            constants_module = import_module("py_clob_client.order_builder.constants")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("py-clob-client is not installed. Install with `[trade]` extras.") from exc

        ClobClient = getattr(clob_client_module, "ClobClient")
        ApiCreds = getattr(clob_types_module, "ApiCreds")
        OrderArgs = getattr(clob_types_module, "OrderArgs")
        OrderType = getattr(clob_types_module, "OrderType")
        BUY = getattr(constants_module, "BUY")

        if not self.settings.private_key or not self.settings.funder_address:
            raise RuntimeError("Missing POLYMARKET_PRIVATE_KEY or POLYMARKET_FUNDER_ADDRESS")

        creds: Any = None
        if self.settings.poly_api_key and self.settings.poly_api_secret and self.settings.poly_api_passphrase:
            creds = ApiCreds(
                api_key=self.settings.poly_api_key,
                api_secret=self.settings.poly_api_secret,
                api_passphrase=self.settings.poly_api_passphrase,
            )

        client = ClobClient(
            host=self.settings.clob_host,
            chain_id=self.settings.chain_id,
            key=self.settings.private_key,
            creds=creds,
            signature_type=self.settings.signature_type,
            funder=self.settings.funder_address,
        )

        if creds is None:
            derived = client.create_or_derive_api_creds()
            client.set_api_creds(derived)

        size_shares = max(1.0, decision.usd_size / max(decision.price, 0.01))
        order_args = OrderArgs(
            token_id=decision.token_id,
            price=decision.price,
            size=size_shares,
            side=BUY,
        )

        signed_order = client.create_order(order_args)
        response: Any = client.post_order(signed_order, OrderType.GTC)
        order_id = response.get("orderID") or response.get("orderId") or "unknown"
        return str(order_id)

    def _validate_decision(self, decision: BetDecision) -> str | None:
        if not decision.market_id:
            return "missing market_id"
        if not decision.token_id:
            return "missing token_id"
        if not math.isfinite(decision.price) or decision.price <= 0 or decision.price >= 1:
            return "price must be between 0 and 1"
        if not math.isfinite(decision.usd_size) or decision.usd_size <= 0:
            return "usd_size must be positive"
        if decision.confidence < 0 or decision.confidence > 1:
            return "confidence must be between 0 and 1"
        return None
