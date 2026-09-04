"""Risk management layer that sits between AI decisions and order execution.

Extended in M7 with broker-aware position sizing and SL/TP validation.
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional, Dict

from src.portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""
    adjusted_size: Optional[float] = None


@dataclass
class BrokerMetadata:
    """Broker-specific instrument metadata for position sizing."""
    tick_value: float = 0.0    # Value per tick movement per unit
    tick_size: float = 0.0     # Minimum price movement
    point: float = 0.0         # Point value (often = tick_size)
    contract_size: float = 1.0 # Units per lot
    volume_min: float = 0.01   # Minimum order volume
    volume_max: float = 100.0  # Maximum order volume
    volume_step: float = 0.01  # Volume increment
    digits: int = 2            # Price decimal places

    @property
    def is_valid(self) -> bool:
        """Check if metadata is sufficient for safe position sizing."""
        return self.tick_size > 0 and self.tick_value > 0 and self.volume_step > 0


@dataclass
class PositionSizingResult:
    """Result of broker-aware position sizing calculation."""
    volume: float
    risk_amount: float
    sl_distance: float
    value_per_point: float
    valid: bool = True
    reason: str = ""


class RiskManager:
    """Enforces risk limits across all AI portfolios."""

    def __init__(
        self,
        max_position_size: float = 0.10,
        max_open_positions: int = 3,
        max_daily_loss: float = 0.03,
        max_drawdown: float = 0.15,
        min_confidence: float = 0.60,
        risk_percent: float = 0.01,
    ):
        self.max_position_size = max_position_size
        self.max_open_positions = max_open_positions
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        self.min_confidence = min_confidence
        self.risk_percent = risk_percent
        self._kill_switch = False

    def activate_kill_switch(self) -> None:
        self._kill_switch = True
        logger.critical("KILL SWITCH ACTIVATED — all trading halted")

    def deactivate_kill_switch(self) -> None:
        self._kill_switch = False
        logger.info("Kill switch deactivated")

    def evaluate(
        self,
        portfolio: Portfolio,
        decision: str,
        symbol: str,
        price: float,
        confidence: float,
        requested_size: Optional[float] = None,
    ) -> RiskDecision:
        """Evaluate whether an AI decision is allowed given risk constraints."""
        if decision == "HOLD":
            return RiskDecision(allowed=True)

        if self._kill_switch:
            return RiskDecision(allowed=False, reason="kill_switch_active")

        if confidence < self.min_confidence:
            return RiskDecision(allowed=False, reason=f"confidence {confidence:.2f} below minimum {self.min_confidence}")

        # Drawdown check
        if portfolio.starting_balance > 0:
            drawdown = (portfolio.starting_balance - portfolio.balance) / portfolio.starting_balance
            if drawdown >= self.max_drawdown:
                return RiskDecision(allowed=False, reason=f"drawdown {drawdown:.2%} exceeds limit {self.max_drawdown:.2%}")

        # Daily loss check
        if portfolio.starting_balance > 0:
            daily_loss_pct = abs(min(portfolio.daily_pnl, 0)) / portfolio.starting_balance
            if daily_loss_pct >= self.max_daily_loss:
                return RiskDecision(allowed=False, reason=f"daily loss {daily_loss_pct:.2%} exceeds limit {self.max_daily_loss:.2%}")

        # Position count check
        if decision == "BUY" and len(portfolio.positions) >= self.max_open_positions:
            return RiskDecision(allowed=False, reason="max_open_positions reached")

        # Position size check
        max_notional = portfolio.balance * self.max_position_size
        if requested_size is not None:
            notional = requested_size * price
            if notional > max_notional:
                adjusted = max_notional / price
                return RiskDecision(allowed=True, adjusted_size=adjusted, reason="position_size_capped")
        else:
            if max_notional <= 0:
                return RiskDecision(allowed=False, reason="insufficient_balance")

        return RiskDecision(allowed=True)

    # ── M7: Broker-Aware Position Sizing ──────────────────────────────

    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
        broker_meta: Optional[BrokerMetadata] = None,
        risk_percent: Optional[float] = None,
    ) -> PositionSizingResult:
        """Calculate position size using broker-aware metadata.

        Formula:
        Account Equity → Risk% → Max Risk Amount → SL Distance →
        Broker Tick Value/Size → Raw Position Size → Volume Step Normalization →
        Min/Max Validation → Final Position Size

        Fails closed: insufficient metadata → BLOCK TRADE.
        """
        rp = risk_percent or self.risk_percent
        risk_amount = balance * rp

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0 or not math.isfinite(sl_distance):
            return PositionSizingResult(
                volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                value_per_point=0.0, valid=False, reason=f"invalid SL distance ({sl_distance})"
            )

        if broker_meta is None or not broker_meta.is_valid:
            return PositionSizingResult(
                volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                value_per_point=0.0, valid=False, reason="insufficient broker metadata for safe sizing"
            )

        # Value per point: tick_value * (point / tick_size)
        point = broker_meta.point if broker_meta.point > 0 else broker_meta.tick_size
        value_per_point = broker_meta.tick_value * (point / broker_meta.tick_size)

        if value_per_point <= 0 or not math.isfinite(value_per_point):
            return PositionSizingResult(
                volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                value_per_point=0.0, valid=False, reason=f"invalid value_per_point ({value_per_point})"
            )

        # SL distance in points
        sl_points = sl_distance / point if point > 0 else 0
        if sl_points <= 0:
            return PositionSizingResult(
                volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                value_per_point=value_per_point, valid=False, reason="SL distance is zero in points"
            )

        # Raw lot size: risk_amount / (sl_distance_in_points * value_per_point * contract_size)
        contract_size = broker_meta.contract_size if broker_meta.contract_size > 0 else 1.0
        raw_volume = risk_amount / (sl_points * value_per_point * contract_size)

        # Volume step normalization
        step = broker_meta.volume_step
        if step > 0:
            normalized = round(raw_volume / step) * step
        else:
            normalized = raw_volume

        # Min/max validation
        vol_min = broker_meta.volume_min
        vol_max = broker_meta.volume_max
        if vol_min > 0 and normalized < vol_min:
            if raw_volume < vol_min:
                return PositionSizingResult(
                    volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                    value_per_point=value_per_point, valid=False,
                    reason=f"calculated volume {normalized:.4f} below minimum {vol_min}"
                )
            normalized = vol_min

        if vol_max > 0 and normalized > vol_max:
            normalized = vol_max

        if normalized <= 0 or not math.isfinite(normalized):
            return PositionSizingResult(
                volume=0.0, risk_amount=risk_amount, sl_distance=sl_distance,
                value_per_point=value_per_point, valid=False, reason="final volume is zero or non-finite"
            )

        return PositionSizingResult(
            volume=normalized,
            risk_amount=risk_amount,
            sl_distance=sl_distance,
            value_per_point=value_per_point,
        )

    # ── M7: SL/TP Validation ─────────────────────────────────────────

    def validate_sl_tp(
        self,
        side: str,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> tuple:
        """Validate SL/TP placement. Returns (valid: bool, reason: str).

        LONG: SL < entry, TP > entry
        SHORT: SL > entry, TP < entry
        """
        if stop_loss is not None:
            if not math.isfinite(stop_loss) or stop_loss <= 0:
                return False, f"invalid SL value ({stop_loss})"
            if side == "buy" and stop_loss >= entry_price:
                return False, f"LONG SL ({stop_loss}) must be below entry ({entry_price})"
            if side == "sell" and stop_loss <= entry_price:
                return False, f"SHORT SL ({stop_loss}) must be above entry ({entry_price})"
            sl_distance = abs(entry_price - stop_loss)
            if sl_distance <= 0:
                return False, "SL distance is zero"

        if take_profit is not None:
            if not math.isfinite(take_profit) or take_profit <= 0:
                return False, f"invalid TP value ({take_profit})"
            if side == "buy" and take_profit <= entry_price:
                return False, f"LONG TP ({take_profit}) must be above entry ({entry_price})"
            if side == "sell" and take_profit >= entry_price:
                return False, f"SHORT TP ({take_profit}) must be below entry ({entry_price})"

        return True, ""
