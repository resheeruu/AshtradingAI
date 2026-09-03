"""Order type definitions and utilities."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    price: Optional[float] = None  # None = market order
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    ai_id: str = ""
    order_type: str = "market"  # "market" or "limit"

    def validate(self) -> bool:
        if self.side not in ("buy", "sell"):
            return False
        if self.quantity <= 0:
            return False
        if self.price is not None and self.price <= 0:
            return False
        return True
