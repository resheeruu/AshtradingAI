"""Paper trading broker — virtual order execution with no real money."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)


class PaperBroker:
    """Simulates order execution for paper trading.

    Models: fee, slippage, and spread.
    Spread is applied symmetrically around the mid price.
    """

    def __init__(self, fee: float = 0.001, slippage: float = 0.0005, spread: float = 0.0):
        self.fee = fee
        self.slippage = slippage
        self.spread = spread  # Half-spread applied to both buy and sell
        self._order_book: dict[str, dict] = {}

    def execute_buy(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[dict]:
        # Buy at ask = mid + half-spread + slippage
        spread_cost = price * self.spread / 2 if self.spread > 0 else 0.0
        slippage_price = price * (1 + self.slippage) + spread_cost
        fee_amount = slippage_price * quantity * self.fee
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        success = portfolio.open_position(
            symbol=symbol,
            side="long",
            entry_price=slippage_price,
            quantity=quantity,
            fee=fee_amount,
            slippage=self.slippage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=ts,
        )
        if not success:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": "buy",
            "price": slippage_price,
            "quantity": quantity,
            "fee": fee_amount,
            "slippage": self.slippage,
            "timestamp": ts,
            "status": "filled",
        }
        self._order_book[order_id] = order
        return order

    def execute_sell(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        timestamp: Optional[str] = None,
    ) -> Optional[dict]:
        pos = portfolio.get_position(symbol)
        if pos is None:
            return None
        # Sell at bid = mid - half-spread - slippage
        spread_cost = price * self.spread / 2 if self.spread > 0 else 0.0
        slippage_price = price * (1 - self.slippage) - spread_cost
        fee_amount = slippage_price * pos.quantity * self.fee
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        record = portfolio.close_position(
            symbol=symbol,
            exit_price=slippage_price,
            fee=fee_amount,
            slippage=self.slippage,
            exit_time=ts,
        )
        if record is None:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": "sell",
            "price": slippage_price,
            "quantity": pos.quantity,
            "fee": fee_amount,
            "slippage": self.slippage,
            "pnl": record.pnl,
            "timestamp": ts,
            "status": "filled",
        }
        self._order_book[order_id] = order
        return order

    def get_order(self, order_id: str) -> Optional[dict]:
        return self._order_book.get(order_id)
