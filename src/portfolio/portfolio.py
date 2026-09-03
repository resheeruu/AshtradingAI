"""Portfolio accounting for isolated virtual portfolios."""
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    quantity: float
    entry_time: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def notional_value(self) -> float:
        return self.entry_price * self.quantity


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    fee: float
    slippage: float
    pnl: float
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None


class Portfolio:
    """Isolated portfolio for a single AI."""

    def __init__(self, ai_id: str, starting_balance: float):
        self.ai_id = ai_id
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.daily_pnl: float = 0.0

    def can_open_position(self) -> bool:
        return True

    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        fee: float = 0.0,
        slippage: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_time: Optional[str] = None,
    ) -> bool:
        cost = entry_price * quantity + fee
        if cost > self.balance:
            logger.warning("[%s] Insufficient balance: need %.4f, have %.4f", self.ai_id, cost, self.balance)
            return False
        self.balance -= cost
        self.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=entry_time,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        logger.info("[%s] OPEN %s %s qty=%.6f price=%.4f fee=%.4f",
                     self.ai_id, side.upper(), symbol, quantity, entry_price, fee)
        return True

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        fee: float = 0.0,
        slippage: float = 0.0,
        exit_time: Optional[str] = None,
    ) -> Optional[TradeRecord]:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return None
        proceeds = exit_price * pos.quantity - fee
        if pos.side == "long":
            pnl = proceeds - pos.notional_value
        else:
            pnl = pos.notional_value - proceeds
        self.balance += proceeds
        self.daily_pnl += pnl
        record = TradeRecord(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            fee=fee,
            slippage=slippage,
            pnl=pnl,
            entry_time=pos.entry_time,
            exit_time=exit_time,
        )
        self.trade_history.append(record)
        logger.info("[%s] CLOSE %s %s pnl=%.4f fee=%.4f",
                     self.ai_id, pos.side.upper(), symbol, pnl, fee)
        return record

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def reset_daily_pnl(self) -> None:
        self.daily_pnl = 0.0

    def summary(self) -> dict:
        return {
            "ai_id": self.ai_id,
            "balance": round(self.balance, 4),
            "starting_balance": self.starting_balance,
            "unrealized_pnl": 0.0,
            "positions": len(self.positions),
            "total_trades": len(self.trade_history),
        }
