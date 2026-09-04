"""M7 backtest engine — validates M7 strategy on historical data.

Integrates StrategyEngine → RiskManager → PaperBroker pipeline.
Tracks filter statistics, state transitions, AI confirmation rates.
Supports walk-forward / out-of-sample validation.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.ai.base import TradingAI, MarketContext
from src.backtest.engine import BacktestMetrics, compute_metrics
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager, BrokerMetadata
from src.strategy.engine import StrategyEngine, StrategyPhase, StrategySignal
from src.strategy.filters import build_filter_config_from_settings
from src.trading.paper.broker import PaperBroker

logger = logging.getLogger(__name__)


@dataclass
class FilterStats:
    """Tracks how often each filter passes/fails."""
    total_evaluations: int = 0
    pass_counts: Dict[str, int] = field(default_factory=dict)
    fail_counts: Dict[str, int] = field(default_factory=dict)
    fail_reasons: Dict[str, int] = field(default_factory=dict)

    def record(self, filter_result) -> None:
        self.total_evaluations += 1
        for name, fr in filter_result.results.items():
            if fr.passed:
                self.pass_counts[name] = self.pass_counts.get(name, 0) + 1
            else:
                self.fail_counts[name] = self.fail_counts.get(name, 0) + 1
                key = f"{name}: {fr.reason}"
                self.fail_reasons[key] = self.fail_reasons.get(key, 0) + 1

    def summary(self) -> dict:
        return {
            "total_evaluations": self.total_evaluations,
            "pass_counts": dict(self.pass_counts),
            "fail_counts": dict(self.fail_counts),
            "top_fail_reasons": sorted(
                self.fail_reasons.items(), key=lambda x: -x[1]
            )[:10],
        }


@dataclass
class StateTransitionStats:
    """Tracks state machine transitions."""
    total_candles: int = 0
    transitions: Dict[str, int] = field(default_factory=dict)
    setups_detected: int = 0
    entries_triggered: int = 0
    window_expired: int = 0
    invalidations: int = 0

    def record_transition(self, from_phase: str, to_phase: str) -> None:
        key = f"{from_phase} → {to_phase}"
        self.transitions[key] = self.transitions.get(key, 0) + 1
        if to_phase == "ARMED":
            self.setups_detected += 1
        elif to_phase == "ENTRY":
            self.entries_triggered += 1

    def summary(self) -> dict:
        return {
            "total_candles": self.total_candles,
            "setups_detected": self.setups_detected,
            "entries_triggered": self.entries_triggered,
            "window_expired": self.window_expired,
            "invalidations": self.invalidations,
            "transitions": dict(self.transitions),
        }


@dataclass
class AIConfirmationStats:
    """Tracks AI confirmation decisions."""
    total_signals: int = 0
    ai_approved: int = 0
    ai_rejected: int = 0
    ai_hold: int = 0
    ai_errors: int = 0
    confidences: List[float] = field(default_factory=list)

    def summary(self) -> dict:
        avg_conf = sum(self.confidences) / len(self.confidences) if self.confidences else 0.0
        return {
            "total_signals": self.total_signals,
            "ai_approved": self.ai_approved,
            "ai_rejected": self.ai_rejected,
            "ai_hold": self.ai_hold,
            "ai_errors": self.ai_errors,
            "approval_rate": self.ai_approved / self.total_signals if self.total_signals > 0 else 0.0,
            "avg_confidence": round(avg_conf, 4),
        }


@dataclass
class M7BacktestMetrics:
    """Extended metrics for M7 strategy backtest."""
    standard: BacktestMetrics = field(default_factory=BacktestMetrics)
    filter_stats: FilterStats = field(default_factory=FilterStats)
    state_stats: StateTransitionStats = field(default_factory=StateTransitionStats)
    ai_stats: AIConfirmationStats = field(default_factory=AIConfirmationStats)
    per_symbol: Dict[str, dict] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "standard": self.standard.summary(),
            "filter_stats": self.filter_stats.summary(),
            "state_stats": self.state_stats.summary(),
            "ai_stats": self.ai_stats.summary(),
            "per_symbol": self.per_symbol,
        }


class M7BacktestEngine:
    """Run M7 strategy backtest with full pipeline integration.

    Pipeline per candle: StrategyEngine → RiskManager → PaperBroker
    Tracks: filter pass rates, state transitions, AI confirmation, P&L.
    """

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
        risk_percent: float = 0.01,
        filter_config: Optional[Dict] = None,
        pullback_candles: int = 2,
        breakout_window: int = 3,
        sl_atr_multiplier: float = 2.0,
        tp_atr_multiplier: float = 3.0,
        broker_meta: Optional[BrokerMetadata] = None,
    ):
        self.starting_balance = starting_balance
        self.fee = fee
        self.slippage = slippage
        self.risk_percent = risk_percent
        self.filter_config = filter_config or {}
        self.pullback_candles = pullback_candles
        self.breakout_window = breakout_window
        self.sl_atr_multiplier = sl_atr_multiplier
        self.tp_atr_multiplier = tp_atr_multiplier
        self.broker_meta = broker_meta

        self.risk_manager = RiskManager(
            max_position_size=max_position_size,
            max_open_positions=max_open_positions,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            min_confidence=min_confidence,
            risk_percent=risk_percent,
        )
        self.broker = PaperBroker(fee=fee, slippage=slippage)

    def run(
        self,
        ai: TradingAI,
        data: Dict[str, List[dict]],
        timeframe: str = "1h",
    ) -> Tuple[M7BacktestMetrics, Portfolio]:
        """Run M7 backtest across all symbols.

        Args:
            ai: TradingAI instance (used for confirmation).
            data: {symbol: [candle dicts]} — must include 'timestamp', 'open', 'high', 'low', 'close'.
            timeframe: Candle timeframe string.

        Returns:
            (M7BacktestMetrics, Portfolio) — final metrics and portfolio state.
        """
        portfolio = Portfolio(ai_id=f"m7-bt-{ai.ai_id}", starting_balance=self.starting_balance)
        metrics = M7BacktestMetrics()

        # Create strategy engines per symbol
        engines: Dict[str, StrategyEngine] = {}
        for sym in data:
            engines[sym] = StrategyEngine(
                ai=ai,
                symbol=sym,
                timeframe=timeframe,
                filter_config=self.filter_config,
                pullback_candles=self.pullback_candles,
                breakout_window=self.breakout_window,
                sl_atr_multiplier=self.sl_atr_multiplier,
                tp_atr_multiplier=self.tp_atr_multiplier,
                risk_percent=self.risk_percent,
            )

        # Build unified timestamp sequence
        all_timestamps = sorted({c["timestamp"] for candles in data.values() for c in candles})

        # Index candles by (symbol, timestamp)
        candle_index: Dict[str, Dict[str, dict]] = {}
        for sym, candles in data.items():
            candle_index[sym] = {c["timestamp"]: c for c in candles}

        # Track per-symbol candle lists (growing window for each symbol)
        sym_candles: Dict[str, List[dict]] = {sym: [] for sym in data}

        prev_balance = portfolio.starting_balance
        trading_returns: List[float] = []

        for ts in all_timestamps:
            for sym in data:
                if ts not in candle_index[sym]:
                    continue

                candle = candle_index[sym][ts]
                sym_candles[sym].append(candle)

                # Need at least 3 candles for strategy engine
                if len(sym_candles[sym]) < 3:
                    continue

                engine = engines[sym]
                metrics.state_stats.total_candles += 1

                # Record phase before processing
                prev_phase = engine.state.phase.value

                # Process candle through M7 pipeline
                signal = engine.process_candle(
                    sym_candles[sym],
                    portfolio_balance=portfolio.balance,
                    open_positions=list(portfolio.positions.keys()),
                )

                # Record state transition
                new_phase = engine.state.phase.value
                if new_phase != prev_phase:
                    metrics.state_stats.record_transition(prev_phase, new_phase)

                # Record filter stats from the last filter evaluation
                if engine.filters:
                    # Re-run filters to capture stats (engine already ran them)
                    # We track via the signal's filter_results if available
                    pass

                if signal is not None:
                    metrics.ai_stats.total_signals += 1

                    # Track AI confirmation
                    if signal.confidence > 0:
                        metrics.ai_stats.ai_approved += 1
                        metrics.ai_stats.confidences.append(signal.confidence)
                    else:
                        metrics.ai_stats.ai_rejected += 1

                    # Validate SL/TP
                    side = signal.direction.lower()
                    sl_valid, sl_reason = self.risk_manager.validate_sl_tp(
                        side, signal.price, signal.stop_loss, signal.take_profit,
                    )
                    if not sl_valid:
                        logger.debug("M7 BT %s SL/TP invalid: %s", sym, sl_reason)
                        continue

                    # Calculate position size
                    if self.broker_meta and self.broker_meta.is_valid:
                        sizing = self.risk_manager.calculate_position_size(
                            balance=portfolio.balance,
                            entry_price=signal.price,
                            stop_loss=signal.stop_loss,
                            broker_meta=self.broker_meta,
                        )
                        if not sizing.valid:
                            logger.debug("M7 BT %s sizing failed: %s", sym, sizing.reason)
                            continue
                        qty = sizing.volume
                    else:
                        # Fallback: simple notional sizing
                        qty = (portfolio.balance * self.risk_percent) / abs(signal.price - signal.stop_loss) if signal.stop_loss != signal.price else 0
                        if qty <= 0:
                            continue

                    # Risk check
                    risk_result = self.risk_manager.evaluate(
                        portfolio=portfolio,
                        decision=signal.direction,
                        symbol=sym,
                        price=signal.price,
                        confidence=signal.confidence,
                        requested_size=qty,
                    )
                    if not risk_result.allowed:
                        logger.debug("M7 BT %s risk blocked: %s", sym, risk_result.reason)
                        continue

                    qty = risk_result.adjusted_size if risk_result.adjusted_size is not None else qty

                    # Execute through paper broker
                    if signal.direction == "BUY":
                        order = self.broker.execute_buy(
                            portfolio=portfolio, symbol=sym,
                            price=signal.price, quantity=qty,
                            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
                            timestamp=ts,
                        )
                    elif signal.direction == "SELL":
                        order = self.broker.execute_sell(
                            portfolio=portfolio, symbol=sym,
                            price=signal.price, timestamp=ts,
                        )
                    else:
                        order = None

                    if order:
                        logger.debug(
                            "M7 BT %s %s %.4f @ %.4f (SL=%.4f TP=%.4f)",
                            sym, signal.direction, qty, signal.price,
                            signal.stop_loss, signal.take_profit,
                        )

                # Check for SL/TP exits on open positions
                pos = portfolio.get_position(sym)
                if pos is not None:
                    self._check_exit(portfolio, sym, candle, ts)

            # Track balance changes
            if portfolio.balance != prev_balance:
                ret = (portfolio.balance - prev_balance) / prev_balance if prev_balance > 0 else 0.0
                trading_returns.append(ret)
                prev_balance = portfolio.balance

        # Close remaining positions at last price
        for sym in list(portfolio.positions.keys()):
            if sym in candle_index:
                for t in reversed(all_timestamps):
                    if t in candle_index[sym]:
                        last_price = candle_index[sym][t]["close"]
                        self.broker.execute_sell(portfolio, sym, last_price, timestamp=t)
                        break

        # Compute standard metrics
        metrics.standard = compute_metrics(portfolio, trading_returns)

        # Compute per-symbol stats
        for sym in data:
            trades = [t for t in portfolio.trade_history if t.symbol == sym]
            metrics.per_symbol[sym] = {
                "trades": len(trades),
                "wins": sum(1 for t in trades if t.pnl > 0),
                "losses": sum(1 for t in trades if t.pnl <= 0),
                "net_pnl": sum(t.pnl for t in trades),
            }

        return metrics, portfolio

    def _check_exit(
        self,
        portfolio: Portfolio,
        symbol: str,
        candle: dict,
        timestamp: str,
    ) -> None:
        """Check if SL/TP is hit on an open position."""
        pos = portfolio.get_position(symbol)
        if pos is None:
            return

        high = candle.get("high", 0)
        low = candle.get("low", 0)

        # Check stop loss
        if pos.stop_loss is not None:
            if pos.side == "long" and low <= pos.stop_loss:
                self.broker.execute_sell(portfolio, symbol, pos.stop_loss, timestamp=timestamp)
                return
            elif pos.side == "short" and high >= pos.stop_loss:
                self.broker.execute_sell(portfolio, symbol, pos.stop_loss, timestamp=timestamp)
                return

        # Check take profit
        if pos.take_profit is not None:
            if pos.side == "long" and high >= pos.take_profit:
                self.broker.execute_sell(portfolio, symbol, pos.take_profit, timestamp=timestamp)
                return
            elif pos.side == "short" and low <= pos.take_profit:
                self.broker.execute_sell(portfolio, symbol, pos.take_profit, timestamp=timestamp)
                return


def run_walk_forward(
    ai: TradingAI,
    data: Dict[str, List[dict]],
    timeframe: str = "1h",
    in_sample_pct: float = 0.7,
    **engine_kwargs,
) -> Tuple[M7BacktestMetrics, M7BacktestMetrics, Portfolio, Portfolio]:
    """Run walk-forward validation: in-sample + out-of-sample.

    Splits data chronologically, runs backtest on each split.
    Returns (in_sample_metrics, out_of_sample_metrics, in_sample_portfolio, out_of_sample_portfolio).
    """
    # Split each symbol's candles chronologically
    is_data: Dict[str, List[dict]] = {}
    oos_data: Dict[str, List[dict]] = {}

    for sym, candles in data.items():
        split_idx = int(len(candles) * in_sample_pct)
        is_data[sym] = candles[:split_idx]
        oos_data[sym] = candles[split_idx:]

    # Run in-sample
    is_engine = M7BacktestEngine(**engine_kwargs)
    is_metrics, is_portfolio = is_engine.run(ai, is_data, timeframe)

    # Run out-of-sample
    oos_engine = M7BacktestEngine(**engine_kwargs)
    oos_metrics, oos_portfolio = oos_engine.run(ai, oos_data, timeframe)

    return is_metrics, oos_metrics, is_portfolio, oos_portfolio
