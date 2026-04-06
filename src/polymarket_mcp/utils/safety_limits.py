from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderRequest:
    token_id: str
    market_id: str
    side: str
    price: float
    size: float


@dataclass(frozen=True)
class Position:
    token_id: str
    market_id: str
    size: float
    value_usd: float


@dataclass(frozen=True)
class MarketData:
    market_id: str
    token_id: str
    best_bid: float
    best_ask: float
    bid_liquidity: float
    ask_liquidity: float


@dataclass(frozen=True)
class ExposureImpact:
    before_usd: float
    after_usd: float
    delta_usd: float
    reasoning: str
    is_increase: bool


class ExposureCalculator:
    @staticmethod
    def calculate_order_impact(current_exposure: float, order: OrderRequest, current_positions: list[Position]) -> ExposureImpact:
        order_value = order.price * order.size
        side = order.side.upper()

        if side == "BUY":
            after = current_exposure + order_value
            reasoning = "BUY adds exposure"
        else:
            existing = next((p for p in current_positions if p.token_id == order.token_id and p.size > 0), None)
            if existing is None:
                after = current_exposure + order_value
                reasoning = "SELL opens short exposure"
            else:
                reduced = min(order_value, existing.value_usd)
                after = current_exposure - reduced
                reasoning = "SELL closes long exposure"

        return ExposureImpact(
            before_usd=current_exposure,
            after_usd=after,
            delta_usd=after - current_exposure,
            reasoning=reasoning,
            is_increase=after > current_exposure,
        )


@dataclass
class SafetyLimits:
    max_order_size_usd: float
    max_total_exposure_usd: float
    max_position_size_per_market: float
    min_liquidity_required: float
    max_spread_tolerance: float
    require_confirmation_above_usd: float
    auto_cancel_on_large_spread: bool = True

    def should_require_confirmation(self, order: OrderRequest, autonomous_trading_enabled: bool) -> bool:
        if autonomous_trading_enabled:
            return False
        return order.price * order.size > self.require_confirmation_above_usd

    def validate_order(self, order: OrderRequest, current_positions: list[Position], market_data: MarketData) -> tuple[bool, str | None]:
        order_value = order.price * order.size
        if order_value > self.max_order_size_usd:
            return False, f"order value ${order_value:.2f} exceeds max order ${self.max_order_size_usd:.2f}"

        current_exposure = self._calculate_total_exposure(current_positions)
        impact = ExposureCalculator.calculate_order_impact(current_exposure, order, current_positions)
        if impact.after_usd > self.max_total_exposure_usd:
            return False, f"total exposure ${impact.after_usd:.2f} exceeds ${self.max_total_exposure_usd:.2f}"

        market_exposure = sum(abs(p.value_usd) for p in current_positions if p.market_id == order.market_id)
        next_market_exposure = market_exposure + order_value
        if next_market_exposure > self.max_position_size_per_market:
            return False, f"market exposure ${next_market_exposure:.2f} exceeds ${self.max_position_size_per_market:.2f}"

        liquidity = market_data.bid_liquidity + market_data.ask_liquidity
        if liquidity < self.min_liquidity_required:
            return False, f"insufficient liquidity ${liquidity:.2f} below ${self.min_liquidity_required:.2f}"

        if market_data.best_bid <= 0:
            spread = 1.0
        else:
            spread = max(0.0, (market_data.best_ask - market_data.best_bid) / market_data.best_bid)
        if spread > self.max_spread_tolerance and self.auto_cancel_on_large_spread:
            return False, f"spread {spread:.4f} exceeds {self.max_spread_tolerance:.4f}"

        return True, None

    @staticmethod
    def _calculate_total_exposure(current_positions: list[Position]) -> float:
        return sum(abs(position.value_usd) for position in current_positions)
