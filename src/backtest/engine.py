"""Deterministic backtesting engine."""
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.ai.base import TradingAI, MarketContext
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.indicators.technical import compute_all_indicators

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    starting_balance: float = 0.0
    ending_balance: float = 0.0
    net_profit: float = 0.0
    return_pct: float = 0.0
    num_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    fees_paid: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    long_trades: int = 0
    short_trades: int = 0

    def summary(self) -> dict:
        return {
            "starting_balance": round(self.starting_balance, 2),
            "ending_balance": round(self.ending_balance, 2),
            "net_profit": round(self.net_profit, 2),
            "return_pct": round(self.return_pct, 4),
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "profit_factor": round(self.profit_factor, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "fees_paid": round(self.fees_paid, 4),
            "largest_win": round(self.largest_win, 4),
            "largest_loss": round(self.largest_loss, 4),
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
        }


def compute_metrics(portfolio: Portfolio, trading_returns: List[float]) -> BacktestMetrics:
    """Compute full metrics from portfolio state and trade returns."""
    m = BacktestMetrics()
    m.starting_balance = portfolio.starting_balance
    m.ending_balance = portfolio.balance
    m.net_profit = m.ending_balance - m.starting_balance
    m.return_pct = m.net_profit / m.starting_balance if m.starting_balance > 0 else 0.0

    trades = portfolio.trade_history
    m.num_trades = len(trades)
    m.winning_trades = sum(1 for t in trades if t.pnl > 0)
    m.losing_trades = sum(1 for t in trades if t.pnl <= 0)
    m.win_rate = m.winning_trades / m.num_trades if m.num_trades > 0 else 0.0

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [abs(t.pnl) for t in trades if t.pnl <= 0]
    m.avg_win = sum(wins) / len(wins) if wins else 0.0
    m.avg_loss = sum(losses) / len(losses) if losses else 0.0
    m.largest_win = max(wins) if wins else 0.0
    m.largest_loss = -max(losses) if losses else 0.0

    m.fees_paid = sum(t.fee for t in trades)
    m.long_trades = sum(1 for t in trades if t.side == "long")
    m.short_trades = sum(1 for t in trades if t.side == "short")

    total_wins = sum(wins)
    total_losses = sum(losses)
    m.profit_factor = total_wins / total_losses if total_losses > 0 else (float("inf") if total_wins > 0 else 0.0)

    # Max drawdown
    if portfolio.starting_balance > 0:
        balances = [portfolio.starting_balance]
        running = portfolio.starting_balance
        for t in trades:
            running += t.pnl
            balances.append(running)
        peak = balances[0]
        max_dd = 0.0
        for b in balances:
            if b > peak:
                peak = b
            dd = (peak - b) / peak
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = max_dd

    # Sharpe and Sortino (annualised, risk-free rate assumed 0)
    MIN_STD = 1e-10
    if trading_returns and len(trading_returns) > 1:
        n = len(trading_returns)
        mean_r = sum(trading_returns) / n
        variance = sum((r - mean_r) ** 2 for r in trading_returns) / (n - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        if std_r > MIN_STD:
            m.sharpe_ratio = max(-10.0, min(10.0, mean_r / std_r * math.sqrt(252)))

        downside = [r for r in trading_returns if r < 0]
        if len(downside) > 1:
            d_mean = sum(downside) / len(downside)
            d_var = sum((r - d_mean) ** 2 for r in downside) / (len(downside) - 1)
            d_std = math.sqrt(d_var) if d_var > 0 else 0.0
            if d_std > MIN_STD:
                m.sortino_ratio = max(-10.0, min(10.0, mean_r / d_std * math.sqrt(252)))

    return m


class BacktestEngine:
    """Run a deterministic backtest for a single AI on historical data."""

    def __init__(
        self,
        starting_balance: float = 1000.0,
        fee: float = 0.001,
        slippage: float = 0.0005,
        max_position_size: float = 0.10,
        max_open_positions: int = 3,
        max_daily_loss: float = 0.03,
        max_drawdown: float = 0.15,
        min_confidence: float = 0.60,
    ):
        self.starting_balance = starting_balance
        self.fee = fee
        self.slippage = slippage
        self.risk_manager = RiskManager(
            max_position_size=max_position_size,
            max_open_positions=max_open_positions,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            min_confidence=min_confidence,
        )
        self.broker = PaperBroker(fee=fee, slippage=slippage)

    def run(
        self,
        ai: TradingAI,
        data: Dict[str, List[dict]],
        timeframe: str = "1h",
    ) -> tuple:
        """Run backtest. data is {symbol: [candle dicts]}."""
        portfolio = Portfolio(ai_id=ai.ai_id, starting_balance=self.starting_balance)

        # Build indicators per symbol
        prepared: Dict[str, List[dict]] = {}
        indicator_data: Dict[str, dict] = {}
        for sym, candles in data.items():
            if len(candles) >= 50:
                indicators = compute_all_indicators(candles)
                indicator_data[sym] = indicators
            prepared[sym] = candles

        # Build timestamp index
        all_timestamps = set()
        for candles in prepared.values():
            for c in candles:
                all_timestamps.add(c["timestamp"])
        timestamps = sorted(all_timestamps)

        # Index candles by timestamp
        candle_index: Dict[str, Dict[str, dict]] = {}
        for sym, candles in prepared.items():
            candle_index[sym] = {c["timestamp"]: c for c in candles}

        trading_returns: List[float] = []
        prev_balance = portfolio.starting_balance

        for ts in timestamps:
            for symbol in prepared:
                if ts not in candle_index[symbol]:
                    continue
                row = candle_index[symbol][ts]
                candles = prepared[symbol]
                # Get context up to current timestamp
                ctx_candles = [c for c in candles if c["timestamp"] <= ts]
                if len(ctx_candles) < 20:
                    continue

                # Build indicators for context
                ctx_indicators = {}
                if symbol in indicator_data:
                    ind = indicator_data[symbol]
                    idx = None
                    for i, c in enumerate(candles):
                        if c["timestamp"] == ts:
                            idx = i
                            break
                    if idx is not None:
                        for key, vals in ind.items():
                            if idx < len(vals) and vals[idx] is not None:
                                ctx_indicators[key] = vals[idx]

                ctx = MarketContext(
                    symbol=symbol,
                    timeframe=timeframe,
                    current_price=row["close"],
                    candles=ctx_candles,
                    indicators=ctx_indicators,
                    portfolio_balance=portfolio.balance,
                    open_positions=list(portfolio.positions.keys()),
                    timestamp=ts,
                )

                try:
                    decision = ai.decide(ctx)
                except Exception as e:
                    logger.error("[%s] AI error: %s", ai.ai_id, e)
                    decision = {"decision": "HOLD", "confidence": 0.0}

                decision_str = decision.get("decision", "HOLD")
                if decision_str not in ("BUY", "SELL", "HOLD"):
                    decision_str = "HOLD"

                pos = portfolio.get_position(symbol)
                if decision_str == "SELL" and pos is None:
                    continue
                if decision_str == "BUY" and pos is not None:
                    continue

                qty = decision.get("suggested_position_size")
                if qty is not None and qty <= 0:
                    qty = None

                result = _process_decision(
                    portfolio, self.risk_manager, self.broker,
                    decision=decision_str,
                    symbol=symbol,
                    price=row["close"],
                    confidence=decision.get("confidence", 0.0),
                    position_size=qty,
                    stop_loss=decision.get("stop_loss"),
                    take_profit=decision.get("take_profit"),
                    timestamp=ts,
                )

                if portfolio.balance != prev_balance:
                    ret = (portfolio.balance - prev_balance) / prev_balance if prev_balance > 0 else 0.0
                    trading_returns.append(ret)
                    prev_balance = portfolio.balance

        # Close remaining positions
        for symbol in list(portfolio.positions.keys()):
            if symbol in candle_index:
                for ts in reversed(timestamps):
                    if ts in candle_index[symbol]:
                        last_price = candle_index[symbol][ts]["close"]
                        self.broker.execute_sell(portfolio, symbol, last_price, timestamp=ts)
                        break

        metrics = compute_metrics(portfolio, trading_returns)
        return metrics, portfolio


def _process_decision(portfolio, risk_manager, broker, decision, symbol, price, confidence,
                       position_size=None, stop_loss=None, take_profit=None, timestamp=None):
    if decision == "HOLD":
        return None
    risk = risk_manager.evaluate(
        portfolio=portfolio, decision=decision, symbol=symbol,
        price=price, confidence=confidence, requested_size=position_size,
    )
    if not risk.allowed:
        return None
    qty = risk.adjusted_size if risk.adjusted_size is not None else position_size
    if qty is None or qty <= 0:
        return None
    if decision == "BUY":
        return broker.execute_buy(portfolio, symbol, price, qty,
                                   stop_loss=stop_loss, take_profit=take_profit, timestamp=timestamp)
    elif decision == "SELL":
        return broker.execute_sell(portfolio, symbol, price, timestamp=timestamp)
    return None
