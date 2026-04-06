from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .models import BetDecision, BetSide, CandidateMarket, SignalItem


@dataclass
class StrategyInput:
    signals: list[SignalItem]
    markets: list[CandidateMarket]


class Strategy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(self, payload: StrategyInput) -> list[BetDecision]:
        if not payload.signals or not payload.markets:
            return []

        confidence = self._confidence(payload.signals)
        if confidence < self.settings.min_confidence:
            return []

        decisions: list[BetDecision] = []
        for market in payload.markets:
            if market.best_ask <= 0 or market.best_ask >= 0.95:
                continue
            if market.liquidity < 1000:
                continue
            decisions.append(
                BetDecision(
                    market_id=market.market_id,
                    token_id=market.yes_token_id,
                    side=BetSide.BUY,
                    price=min(0.99, max(0.01, market.best_ask)),
                    usd_size=self.settings.max_usd_per_bet,
                    confidence=confidence,
                    reason=f"signals={len(payload.signals)} ask={market.best_ask:.3f}",
                )
            )
        return decisions

    def _confidence(self, signals: list[SignalItem]) -> float:
        texts = [item.text.lower() for item in signals]
        mentions = 0
        for keyword in self.settings.signal_keywords:
            mentions += sum(1 for text in texts if keyword.lower() in text)

        score = 0.62 + min(0.30, mentions * 0.03)
        return min(score, 0.95)
