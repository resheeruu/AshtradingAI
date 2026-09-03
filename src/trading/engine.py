"""Trading engine that coordinates AI decisions, risk checks, and order execution."""
import logging
from typing import Optional

from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.trading.orders import Order

logger = logging.getLogger(__name__)


class TradingEngine:
    """Orchestrates trade execution for a single AI portfolio."""

    def __init__(
        self,
        portfolio: Portfolio,
        risk_manager: RiskManager,
        broker: PaperBroker,
    ):
        self.portfolio = portfolio
        self.risk_manager = risk_manager
        self.broker = broker

    def process_decision(
        self,
        decision: str,
        symbol: str,
        price: float,
        confidence: float,
        position_size: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[dict]:
        """Process an AI decision through risk checks and execute if allowed.

        Returns order dict if executed, None if rejected.
        """
        if decision == "HOLD":
            return None

        risk = self.risk_manager.evaluate(
            portfolio=self.portfolio,
            decision=decision,
            symbol=symbol,
            price=price,
            confidence=confidence,
            requested_size=position_size,
        )

        if not risk.allowed:
            logger.info(
                "[%s] RISK REJECT %s %s: %s",
                self.portfolio.ai_id, decision, symbol, risk.reason,
            )
            return None

        qty = risk.adjusted_size if risk.adjusted_size is not None else position_size
        if qty is None or qty <= 0:
            logger.warning("[%s] No valid position size for %s", self.portfolio.ai_id, symbol)
            return None

        if decision == "BUY":
            return self.broker.execute_buy(
                portfolio=self.portfolio,
                symbol=symbol,
                price=price,
                quantity=qty,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timestamp=timestamp,
            )
        elif decision == "SELL":
            return self.broker.execute_sell(
                portfolio=self.portfolio,
                symbol=symbol,
                price=price,
                timestamp=timestamp,
            )
        return None
