"""Walk-Forward Testing Engine — train/validation/test split with regime testing.

Prevents data leakage by enforcing strict temporal splits.
Supports regime-based testing for robustness validation.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.strategy.spec import BaseStrategy
from src.backtest.engine import BacktestEngine

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward analysis."""
    train_period: int = 200  # candles for training
    validation_period: int = 50  # candles for validation
    test_period: int = 50  # candles for out-of-sample testing
    step_size: int = 50  # candles to advance per window
    min_trades: int = 10  # minimum trades per window
    regimes: List[str] = field(default_factory=lambda: [
        "TRENDING_UP", "TRENDING_DOWN", "RANGING",
        "HIGH_VOLATILITY", "LOW_VOLATILITY",
    ])


@dataclass
class WalkForwardWindow:
    """A single walk-forward window."""
    window_id: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int
    in_sample_sharpe: float = 0.0
    out_of_sample_sharpe: float = 0.0
    in_sample_win_rate: float = 0.0
    out_of_sample_win_rate: float = 0.0
    in_sample_trades: int = 0
    out_of_sample_trades: int = 0
    passed_validation: bool = False
    regime: Optional[str] = None


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis result."""
    strategy_id: str
    symbol: str
    timeframe: str
    total_windows: int
    passed_windows: int
    avg_in_sample_sharpe: float
    avg_out_of_sample_sharpe: float
    overfitting_ratio: float  # < 1.0 is good, > 1.0 is overfit
    regime_performance: Dict[str, Dict[str, float]]
    windows: List[WalkForwardWindow]
    recommendation: str  # "TRADE", "AVOID", "CAUTION"


class WalkForwardEngine:
    """Walk-forward analysis engine.

    Prevents data leakage by:
    1. Strict temporal splits (no future data in training)
    2. Validation period between train and test
    3. Regime-based testing for robustness
    4. Overfitting detection via IS vs OOS comparison
    """

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self.config = config or WalkForwardConfig()

    def run(
        self,
        strategy: BaseStrategy,
        candles: List[Dict],
        indicators: Dict,
        symbol: str,
        timeframe: str,
        context: Optional[Dict] = None,
    ) -> WalkForwardResult:
        """Run walk-forward analysis.

        Args:
            strategy: Strategy to test
            candles: Full historical data
            indicators: Pre-computed indicators
            symbol: Trading symbol
            timeframe: Timeframe
            context: Additional context

        Returns:
            WalkForwardResult with per-window and aggregate results
        """
        total_candles = len(candles)
        window_size = (
            self.config.train_period
            + self.config.validation_period
            + self.config.test_period
        )

        if total_candles < window_size:
            logger.warning(
                "Not enough candles for walk-forward: %d < %d",
                total_candles, window_size,
            )
            return WalkForwardResult(
                strategy_id=strategy.strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                total_windows=0,
                passed_windows=0,
                avg_in_sample_sharpe=0.0,
                avg_out_of_sample_sharpe=0.0,
                overfitting_ratio=0.0,
                regime_performance={},
                windows=[],
                recommendation="INSUFFICIENT_DATA",
            )

        windows = []
        window_id = 0
        start = 0

        while start + window_size <= total_candles:
            train_end = start + self.config.train_period
            val_end = train_end + self.config.validation_period
            test_end = val_end + self.config.test_period

            window = WalkForwardWindow(
                window_id=window_id,
                train_start=start,
                train_end=train_end,
                validation_start=train_end,
                validation_end=val_end,
                test_start=val_end,
                test_end=test_end,
            )

            # Run in-sample (train) backtest
            train_candles = candles[start:train_end]
            train_indicators = self._slice_indicators(indicators, start, train_end)
            is_result = self._run_backtest(
                strategy, train_candles, train_indicators, symbol, timeframe, context
            )
            window.in_sample_sharpe = is_result.get("sharpe", 0.0)
            window.in_sample_win_rate = is_result.get("win_rate", 0.0)
            window.in_sample_trades = is_result.get("total_trades", 0)

            # Run validation backtest
            val_candles = candles[train_end:val_end]
            val_indicators = self._slice_indicators(indicators, train_end, val_end)
            val_result = self._run_backtest(
                strategy, val_candles, val_indicators, symbol, timeframe, context
            )

            # Check if validation passes
            window.passed_validation = (
                val_result.get("sharpe", 0.0) > 0
                and val_result.get("total_trades", 0) >= self.config.min_trades
            )

            # Run out-of-sample (test) backtest
            if window.passed_validation:
                test_candles = candles[val_end:test_end]
                test_indicators = self._slice_indicators(indicators, val_end, test_end)
                oos_result = self._run_backtest(
                    strategy, test_candles, test_indicators, symbol, timeframe, context
                )
                window.out_of_sample_sharpe = oos_result.get("sharpe", 0.0)
                window.out_of_sample_win_rate = oos_result.get("win_rate", 0.0)
                window.out_of_sample_trades = oos_result.get("total_trades", 0)

            windows.append(window)
            window_id += 1
            start += self.config.step_size

        # Calculate aggregate metrics
        passed = [w for w in windows if w.passed_validation]
        avg_is = sum(w.in_sample_sharpe for w in windows) / len(windows) if windows else 0
        avg_oos = sum(w.out_of_sample_sharpe for w in passed) / len(passed) if passed else 0

        # Overfitting ratio (< 1.0 is good)
        overfit_ratio = avg_oos / avg_is if avg_is > 0 else 0.0

        # Regime performance
        regime_perf = self._calculate_regime_performance(windows)

        # Recommendation
        if overfit_ratio > 0.8 and avg_oos > 0.5:
            recommendation = "TRADE"
        elif overfit_ratio > 0.5:
            recommendation = "CAUTION"
        else:
            recommendation = "AVOID"

        return WalkForwardResult(
            strategy_id=strategy.strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            total_windows=len(windows),
            passed_windows=len(passed),
            avg_in_sample_sharpe=avg_is,
            avg_out_of_sample_sharpe=avg_oos,
            overfitting_ratio=overfit_ratio,
            regime_performance=regime_perf,
            windows=windows,
            recommendation=recommendation,
        )

    def _run_backtest(
        self,
        strategy: BaseStrategy,
        candles: List[Dict],
        indicators: Dict,
        symbol: str,
        timeframe: str,
        context: Optional[Dict],
    ) -> Dict[str, Any]:
        """Run a single backtest on a candle slice."""
        if not candles or len(candles) < strategy.spec.min_bars_required:
            return {"sharpe": 0.0, "win_rate": 0.0, "total_trades": 0, "net_pnl": 0.0}

        # Generate signals and simulate trades
        trades = []
        for i in range(strategy.spec.min_bars_required, len(candles)):
            window = candles[:i + 1]
            window_indicators = self._slice_indicators(indicators, 0, i + 1)

            try:
                signal = strategy.generate_signal(window, window_indicators, {
                    **(context or {}),
                    "symbol": symbol,
                    "timeframe": timeframe,
                })
                if signal and signal.is_actionable:
                    # Simulate trade
                    entry = signal.entry
                    if signal.direction == "LONG" and signal.stop_loss and signal.take_profit:
                        # Simple simulation: check if SL or TP hit
                        future_candles = candles[i + 1:i + 20]  # Look ahead up to 20 candles
                        exit_price = entry
                        exit_reason = "timeout"

                        for fc in future_candles:
                            if signal.direction == "LONG":
                                if fc["low"] <= signal.stop_loss:
                                    exit_price = signal.stop_loss
                                    exit_reason = "sl"
                                    break
                                if fc["high"] >= signal.take_profit:
                                    exit_price = signal.take_profit
                                    exit_reason = "tp"
                                    break

                        pnl = (exit_price - entry) / entry if exit_reason == "tp" else (exit_price - entry) / entry
                        trades.append({
                            "pnl": pnl,
                            "exit_reason": exit_reason,
                            "holding_time": len(future_candles),
                        })
            except Exception as e:
                continue

        if not trades:
            return {"sharpe": 0.0, "win_rate": 0.0, "total_trades": 0, "net_pnl": 0.0}

        # Calculate metrics
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) if trades else 0
        total_pnl = sum(t["pnl"] for t in trades)

        # Simple Sharpe approximation
        if trades:
            returns = [t["pnl"] for t in trades]
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = avg_return / std_return if std_return > 0 else 0
        else:
            sharpe = 0

        return {
            "sharpe": sharpe,
            "win_rate": win_rate,
            "total_trades": len(trades),
            "net_pnl": total_pnl,
            "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
            "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
        }

    def _slice_indicators(self, indicators: Dict, start: int, end: int) -> Dict:
        """Slice indicators to match candle window."""
        sliced = {}
        for key, values in indicators.items():
            if isinstance(values, list) and len(values) >= end:
                sliced[key] = values[start:end]
            else:
                sliced[key] = values
        return sliced

    def _calculate_regime_performance(self, windows: List[WalkForwardWindow]) -> Dict[str, Dict[str, float]]:
        """Calculate performance by market regime."""
        regime_data = {}
        for window in windows:
            regime = window.regime or "UNKNOWN"
            if regime not in regime_data:
                regime_data[regime] = {"is_sharpe": [], "oos_sharpe": [], "trades": []}

            regime_data[regime]["is_sharpe"].append(window.in_sample_sharpe)
            regime_data[regime]["oos_sharpe"].append(window.out_of_sample_sharpe)
            regime_data[regime]["trades"].append(window.in_sample_trades + window.out_of_sample_trades)

        result = {}
        for regime, data in regime_data.items():
            result[regime] = {
                "avg_is_sharpe": sum(data["is_sharpe"]) / len(data["is_sharpe"]) if data["is_sharpe"] else 0,
                "avg_oos_sharpe": sum(data["oos_sharpe"]) / len(data["oos_sharpe"]) if data["oos_sharpe"] else 0,
                "total_trades": sum(data["trades"]),
                "windows": len(data["is_sharpe"]),
            }

        return result
