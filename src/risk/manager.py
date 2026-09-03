"""Risk management layer that sits between AI decisions and order execution."""
import logging
from dataclasses import dataclass
from typing import Optional

from src.portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""
    adjusted_size: Optional[float] = None


class RiskManager:
    """Enforces risk limits across all AI portfolios."""

    def __init__(
        self,
        max_position_size: float = 0.10,
        max_open_positions: int = 3,
        max_daily_loss: float = 0.03,
        max_drawdown: float = 0.15,
        min_confidence: float = 0.60,
    ):
        self.max_position_size = max_position_size
        self.max_open_positions = max_open_positions
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        self.min_confidence = min_confidence
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
        if self._kill_switch:
            return RiskDecision(allowed=False, reason="kill_switch_active")

        if decision == "HOLD":
            return RiskDecision(allowed=True)

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
