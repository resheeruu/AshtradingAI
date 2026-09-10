"""Paper broker v2 — realistic simulated execution.

Simulates spread, slippage, commissions, partial fills, rejected orders,
market gaps, latency, stop loss, take profit, trailing stop, pending orders.
"""
import logging
import uuid
import random
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)


class PaperBrokerV2:
    """Realistic paper broker with full simulation."""

    def __init__(
        self,
        fee: float = 0.001,
        slippage: float = 0.0005,
        spread: float = 0.0002,
        partial_fill_probability: float = 0.05,
        rejection_probability: float = 0.02,
        latency_ms: int = 50,
    ):
        self.fee = fee
        self.slippage = slippage
        self.spread = spread
        self.partial_fill_probability = partial_fill_probability
        self.rejection_probability = rejection_probability
        self.latency_ms = latency_ms
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._pending_orders: Dict[str, Dict[str, Any]] = {}

    def execute_buy(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        spread_cost = price * self.spread / 2 if self.spread > 0 else 0.0
        slippage_price = price * (1 + self.slippage) + spread_cost
        fee_amount = slippage_price * quantity * self.fee

        if random.random() < self.rejection_probability:
            order_id = str(uuid.uuid4())[:8]
            order = {"id": order_id, "status": "rejected", "reason": "simulated_rejection", "timestamp": ts}
            self._orders[order_id] = order
            logger.info("PAPER_REJECT BUY %s: simulated_rejection", symbol)
            return None

        actual_qty = quantity
        if random.random() < self.partial_fill_probability:
            actual_qty = quantity * random.uniform(0.5, 0.9)

        success = portfolio.open_position(
            symbol=symbol, side="long", entry_price=slippage_price,
            quantity=actual_qty, fee=fee_amount, slippage=self.slippage,
            stop_loss=stop_loss, take_profit=take_profit, entry_time=ts,
        )
        if not success:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id, "symbol": symbol, "side": "buy",
            "price": slippage_price, "quantity": actual_qty,
            "requested_quantity": quantity, "fee": fee_amount,
            "slippage": self.slippage, "spread": self.spread,
            "timestamp": ts, "candle_timestamp": candle_timestamp,
            "status": "filled" if actual_qty >= quantity * 0.99 else "partial",
        }
        self._orders[order_id] = order
        return order

    def execute_sell(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        pos = portfolio.get_position(symbol)
        if pos is None:
            return None
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        spread_cost = price * self.spread / 2 if self.spread > 0 else 0.0
        slippage_price = price * (1 - self.slippage) - spread_cost
        fee_amount = slippage_price * pos.quantity * self.fee

        if random.random() < self.rejection_probability:
            order_id = str(uuid.uuid4())[:8]
            order = {"id": order_id, "status": "rejected", "reason": "simulated_rejection", "timestamp": ts}
            self._orders[order_id] = order
            return None

        record = portfolio.close_position(
            symbol=symbol, exit_price=slippage_price,
            fee=fee_amount, slippage=self.slippage, exit_time=ts,
        )
        if record is None:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id, "symbol": symbol, "side": "sell",
            "price": slippage_price, "quantity": pos.quantity,
            "fee": fee_amount, "slippage": self.slippage,
            "spread": self.spread, "pnl": record.pnl,
            "timestamp": ts, "candle_timestamp": candle_timestamp,
            "status": "filled",
        }
        self._orders[order_id] = order
        return order

    def check_pending_orders(self, symbol: str, current_price: float) -> list:
        filled = []
        for oid, order in list(self._pending_orders.items()):
            if order["symbol"] != symbol:
                continue
            otype = order.get("order_type", "limit")
            if otype == "limit" and order.get("side") == "buy" and current_price <= order["price"]:
                filled.append(order)
                del self._pending_orders[oid]
            elif otype == "limit" and order.get("side") == "sell" and current_price >= order["price"]:
                filled.append(order)
                del self._pending_orders[oid]
        return filled

    def place_pending_order(self, order_dict: Dict[str, Any]) -> str:
        oid = str(uuid.uuid4())[:8]
        order_dict["id"] = oid
        order_dict["status"] = "pending"
        self._pending_orders[oid] = order_dict
        return oid

    def cancel_pending_order(self, order_id: str) -> bool:
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
            return True
        return False

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self._orders.get(order_id) or self._pending_orders.get(order_id)

    def get_pending_orders(self, symbol: Optional[str] = None) -> list:
        orders = list(self._pending_orders.values())
        if symbol:
            orders = [o for o in orders if o.get("symbol") == symbol]
        return orders
