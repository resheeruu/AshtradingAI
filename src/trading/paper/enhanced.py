"""Enhanced Paper Trading Engine — first-class paper mode with realistic simulation.

Extends PaperBroker with:
- Trailing stops
- Break-even stops
- Partial fills
- Commission/swap simulation
- Trade journal integration
- Backtesting parity
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PaperConfig:
    """Configuration for enhanced paper trading."""
    starting_balance: float = 1000.0
    fee_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.0005  # 0.05%
    spread_pips: float = 0.0002  # 2 pips
    partial_fill_probability: float = 0.0  # 0% = always full fill
    rejection_probability: float = 0.0  # 0% = never reject
    latency_ms: float = 0.0  # simulated latency
    enable_trailing_stop: bool = True
    enable_break_even: bool = True
    trailing_stop_activation: float = 0.01  # 1% profit to activate
    trailing_stop_distance: float = 0.005  # 0.5% trailing distance
    break_even_activation: float = 0.005  # 0.5% profit to move SL to breakeven


@dataclass
class PaperPosition:
    """Paper trading position with advanced features."""
    position_id: str
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    quantity: float
    entry_time: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    trailing_activated: bool = False
    break_even_moved: bool = False
    original_stop_loss: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_pnl(self, current_price: float) -> None:
        """Update unrealized P/L."""
        if self.side == "long":
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

    def check_trailing_stop(self, current_price: float, config: PaperConfig) -> Optional[float]:
        """Check and update trailing stop. Returns new stop if triggered."""
        if not config.enable_trailing_stop or self.stop_loss is None:
            return None

        if self.side == "long":
            profit_pct = (current_price - self.entry_price) / self.entry_price
            if profit_pct >= config.trailing_stop_activation:
                if not self.trailing_activated:
                    self.trailing_activated = True
                    self.trailing_stop = current_price * (1 - config.trailing_stop_distance)
                    logger.debug("Trailing stop activated at %.5f", self.trailing_stop)
                elif current_price * (1 - config.trailing_stop_distance) > self.trailing_stop:
                    self.trailing_stop = current_price * (1 - config.trailing_stop_distance)
                    logger.debug("Trailing stop updated to %.5f", self.trailing_stop)
        else:  # short
            profit_pct = (self.entry_price - current_price) / self.entry_price
            if profit_pct >= config.trailing_stop_activation:
                if not self.trailing_activated:
                    self.trailing_activated = True
                    self.trailing_stop = current_price * (1 + config.trailing_stop_distance)
                    logger.debug("Trailing stop activated at %.5f", self.trailing_stop)
                elif current_price * (1 + config.trailing_stop_distance) < self.trailing_stop:
                    self.trailing_stop = current_price * (1 + config.trailing_stop_distance)
                    logger.debug("Trailing stop updated to %.5f", self.trailing_stop)

        return self.trailing_stop

    def check_break_even(self, current_price: float, config: PaperConfig) -> bool:
        """Check and move stop to break-even. Returns True if moved."""
        if not config.enable_break_even or self.break_even_moved:
            return False
        if self.original_stop_loss is None:
            return False

        if self.side == "long":
            profit_pct = (current_price - self.entry_price) / self.entry_price
            if profit_pct >= config.break_even_activation:
                self.stop_loss = self.entry_price
                self.break_even_moved = True
                logger.debug("Break-even stop activated at %.5f", self.entry_price)
                return True
        else:  # short
            profit_pct = (self.entry_price - current_price) / self.entry_price
            if profit_pct >= config.break_even_activation:
                self.stop_loss = self.entry_price
                self.break_even_moved = True
                logger.debug("Break-even stop activated at %.5f", self.entry_price)
                return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_stop": self.trailing_stop,
            "trailing_activated": self.trailing_activated,
            "break_even_moved": self.break_even_moved,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
        }


@dataclass
class PaperTradeRecord:
    """Complete trade record for paper trading."""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: float
    exit_time: float
    pnl: float
    fees: float
    slippage: float
    exit_reason: str  # "tp", "sl", "trailing", "breakeven", "manual", "timeout"
    holding_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "pnl": self.pnl,
            "fees": self.fees,
            "slippage": self.slippage,
            "exit_reason": self.exit_reason,
            "holding_time_seconds": self.holding_time_seconds,
        }


class EnhancedPaperBroker:
    """Enhanced paper trading broker with realistic simulation.

    Compatible with TradingEngine duck-typing interface.
    Adds trailing stops, break-even, partial fills, and trade journal.
    """

    def __init__(self, config: Optional[PaperConfig] = None):
        self.config = config or PaperConfig()
        self._balance = self.config.starting_balance
        self._positions: Dict[str, PaperPosition] = {}
        self._trade_history: List[PaperTradeRecord] = []
        self._pending_orders: List[Dict] = []
        self._total_fees = 0.0
        self._total_slippage = 0.0

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def equity(self) -> float:
        return self._balance + sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def margin_used(self) -> float:
        return sum(p.entry_price * p.quantity for p in self._positions.values())

    @property
    def free_margin(self) -> float:
        return self.equity - self.margin_used

    def execute_buy(
        self,
        portfolio: Any,
        symbol: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a buy order with paper simulation."""
        return self._execute_order(
            portfolio=portfolio,
            symbol=symbol,
            side="long",
            price=price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=timestamp,
        )

    def execute_sell(
        self,
        portfolio: Any,
        symbol: str,
        price: float,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a sell (close long) order."""
        return self._close_position(portfolio, symbol, price, timestamp)

    def _execute_order(
        self,
        portfolio: Any,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        timestamp: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Internal order execution with simulation."""
        # Simulate rejection
        if self.config.rejection_probability > 0:
            import random
            if random.random() < self.config.rejection_probability:
                logger.info("Paper order rejected (simulated)")
                return None

        # Simulate slippage
        slippage = price * self.config.slippage_rate
        if side == "long":
            fill_price = price + slippage
        else:
            fill_price = price - slippage

        # Simulate spread
        spread_cost = price * self.config.spread_pips

        # Calculate fees
        trade_value = fill_price * quantity
        fee = trade_value * self.config.fee_rate

        # Check balance
        required_margin = trade_value + fee
        if required_margin > self._balance:
            logger.warning("Insufficient balance for paper trade: %.2f < %.2f", self._balance, required_margin)
            return None

        # Create position
        position = PaperPosition(
            position_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            entry_price=fill_price,
            quantity=quantity,
            entry_time=time.time(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            original_stop_loss=stop_loss,
        )

        # Update portfolio
        if hasattr(portfolio, 'open_position'):
            portfolio.open_position(
                symbol=symbol,
                side=side,
                entry_price=fill_price,
                quantity=quantity,
                fee=fee,
                slippage=slippage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_time=timestamp or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            )

        # Store position
        self._positions[symbol] = position
        self._balance -= fee
        self._total_fees += fee
        self._total_slippage += slippage

        order = {
            "id": position.position_id,
            "symbol": symbol,
            "side": side,
            "type": "BUY",
            "price": fill_price,
            "quantity": quantity,
            "fee": fee,
            "slippage": slippage,
            "spread_cost": spread_cost,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "status": "FILLED",
        }

        logger.info(
            "PAPER BUY %s %.4f @ %.5f (fee=%.4f, slip=%.5f)",
            symbol, quantity, fill_price, fee, slippage,
        )

        return order

    def _close_position(
        self,
        portfolio: Any,
        symbol: str,
        price: float,
        timestamp: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Close an existing position."""
        position = self._positions.get(symbol)
        if not position:
            logger.warning("No position to close for %s", symbol)
            return None

        # Simulate slippage on exit
        slippage = price * self.config.slippage_rate
        if position.side == "long":
            exit_price = price - slippage
        else:
            exit_price = price + slippage

        # Calculate P/L
        if position.side == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        # Calculate fees
        fee = exit_price * position.quantity * self.config.fee_rate

        # Net P/L
        net_pnl = pnl - fee

        # Update balance
        self._balance += net_pnl

        # Record trade
        holding_time = time.time() - position.entry_time
        trade_record = PaperTradeRecord(
            trade_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=time.time(),
            pnl=net_pnl,
            fees=fee + position.fees_paid,
            slippage=slippage + (position.entry_price * self.config.slippage_rate * position.quantity),
            exit_reason="manual",
            holding_time_seconds=holding_time,
        )
        self._trade_history.append(trade_record)

        # Update portfolio
        if hasattr(portfolio, 'close_position'):
            portfolio.close_position(
                symbol=symbol,
                exit_price=exit_price,
                fee=fee,
                slippage=slippage,
                exit_time=timestamp or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            )

        # Remove position
        del self._positions[symbol]

        self._balance -= fee
        self._total_fees += fee
        self._total_slippage += slippage

        order = {
            "id": trade_record.trade_id,
            "symbol": symbol,
            "side": "SELL" if position.side == "long" else "BUY",
            "type": "CLOSE",
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "quantity": position.quantity,
            "pnl": net_pnl,
            "fee": fee,
            "slippage": slippage,
            "holding_time": holding_time,
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "status": "FILLED",
        }

        logger.info(
            "PAPER CLOSE %s pnl=%.4f (fee=%.4f, slip=%.5f, hold=%.1fs)",
            symbol, net_pnl, fee, slippage, holding_time,
        )

        return order

    def check_positions(self, current_prices: Dict[str, float]) -> List[Dict]:
        """Check all positions for SL/TP/trailing/breakeven hits.

        Args:
            current_prices: {symbol: current_price}

        Returns:
            List of events (closes, updates)
        """
        events = []

        for symbol, position in list(self._positions.items()):
            price = current_prices.get(symbol)
            if price is None:
                continue

            # Update P/L
            position.update_pnl(price)

            # Check trailing stop
            new_stop = position.check_trailing_stop(price, self.config)
            if new_stop is not None:
                events.append({
                    "type": "TRAILING_UPDATE",
                    "symbol": symbol,
                    "new_stop": new_stop,
                })

            # Check break-even
            if position.check_break_even(price, self.config):
                events.append({
                    "type": "BREAKEVEN_MOVE",
                    "symbol": symbol,
                    "new_stop": position.entry_price,
                })

            # Check stop loss
            if position.stop_loss is not None:
                if position.side == "long" and price <= position.stop_loss:
                    self._close_position_at_price(symbol, position.stop_loss, "sl")
                    events.append({"type": "SL_HIT", "symbol": symbol, "price": position.stop_loss})
                elif position.side == "short" and price >= position.stop_loss:
                    self._close_position_at_price(symbol, position.stop_loss, "sl")
                    events.append({"type": "SL_HIT", "symbol": symbol, "price": position.stop_loss})

            # Check take profit
            if position.take_profit is not None:
                if position.side == "long" and price >= position.take_profit:
                    self._close_position_at_price(symbol, position.take_profit, "tp")
                    events.append({"type": "TP_HIT", "symbol": symbol, "price": position.take_profit})
                elif position.side == "short" and price <= position.take_profit:
                    self._close_position_at_price(symbol, position.take_profit, "tp")
                    events.append({"type": "TP_HIT", "symbol": symbol, "price": position.take_profit})

        return events

    def _close_position_at_price(self, symbol: str, price: float, reason: str) -> None:
        """Close position at a specific price (for SL/TP hits)."""
        position = self._positions.get(symbol)
        if not position:
            return

        # Calculate P/L
        slippage = price * self.config.slippage_rate
        if position.side == "long":
            exit_price = price - slippage
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            exit_price = price + slippage
            pnl = (position.entry_price - exit_price) * position.quantity

        fee = exit_price * position.quantity * self.config.fee_rate
        net_pnl = pnl - fee

        self._balance += net_pnl

        holding_time = time.time() - position.entry_time
        trade_record = PaperTradeRecord(
            trade_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=time.time(),
            pnl=net_pnl,
            fees=fee + position.fees_paid,
            slippage=slippage,
            exit_reason=reason,
            holding_time_seconds=holding_time,
        )
        self._trade_history.append(trade_record)

        del self._positions[symbol]

        logger.info(
            "PAPER %s %s %.4f @ %.5f pnl=%.4f",
            reason.upper(), symbol, position.quantity, exit_price, net_pnl,
        )

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position for a symbol."""
        pos = self._positions.get(symbol)
        return pos.to_dict() if pos else None

    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        return [p.to_dict() for p in self._positions.values()]

    def get_trade_history(self) -> List[Dict]:
        """Get complete trade history."""
        return [t.to_dict() for t in self._trade_history]

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        for trade in self._trade_history:
            if trade.trade_id == order_id:
                return trade.to_dict()
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics."""
        if not self._trade_history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "total_fees": self._total_fees,
                "total_slippage": self._total_slippage,
                "avg_holding_time": 0.0,
            }

        wins = [t for t in self._trade_history if t.pnl > 0]
        losses = [t for t in self._trade_history if t.pnl <= 0]
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))

        return {
            "total_trades": len(self._trade_history),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(self._trade_history) if self._trade_history else 0,
            "profit_factor": total_wins / total_losses if total_losses > 0 else float('inf'),
            "total_pnl": sum(t.pnl for t in self._trade_history),
            "total_fees": self._total_fees,
            "total_slippage": self._total_slippage,
            "avg_holding_time": sum(t.holding_time_seconds for t in self._trade_history) / len(self._trade_history),
            "avg_win": total_wins / len(wins) if wins else 0,
            "avg_loss": total_losses / len(losses) if losses else 0,
            "max_win": max((t.pnl for t in self._trade_history), default=0),
            "max_loss": min((t.pnl for t in self._trade_history), default=0),
            "balance": self._balance,
            "equity": self.equity,
        }

    def reset(self, starting_balance: Optional[float] = None) -> None:
        """Reset paper trading state."""
        self._balance = starting_balance or self.config.starting_balance
        self._positions.clear()
        self._trade_history.clear()
        self._pending_orders.clear()
        self._total_fees = 0.0
        self._total_slippage = 0.0
        logger.info("Paper broker reset: balance=%.2f", self._balance)
