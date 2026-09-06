"""Baseline strategies for comparison against M7.

Provides deterministic, no-API-key strategies using the same execution
pipeline as M7. Enables fair comparison on identical data/fees/slippage.

Baselines:
- BuyAndHold: Buy at start, hold until end
- SMACrossover: Simple moving average crossover
- RSIMeanReversion: RSI-based mean reversion (existing TestStrategy pattern)
"""
from typing import Dict, Any, List

from src.ai.base import TradingAI, MarketContext
from src.indicators.technical import sma, rsi


class BuyAndHold(TradingAI):
    """Buy on first candle, hold until end. Baseline for long-only."""

    def __init__(self):
        super().__init__(ai_id="baseline-buy-hold", model="buy-and-hold")
        self._bought = False

    def decide(self, context: MarketContext) -> Dict[str, Any]:
        has_position = context.symbol in context.open_positions
        if not self._bought and not has_position:
            self._bought = True
            size = (context.portfolio_balance * 0.95) / context.current_price if context.current_price > 0 else 0
            return {
                "decision": "BUY",
                "confidence": 1.0,
                "reason": "baseline: buy and hold",
                "suggested_position_size": size,
            }
        return {"decision": "HOLD", "confidence": 1.0, "reason": "baseline: holding"}


class SMACrossover(TradingAI):
    """Simple moving average crossover. Buy when fast SMA > slow SMA, sell when <."""

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        super().__init__(ai_id="baseline-sma-cross", model=f"sma-{fast_period}/{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def decide(self, context: MarketContext) -> Dict[str, Any]:
        candles = context.candles
        if len(candles) < self.slow_period + 2:
            return {"decision": "HOLD", "confidence": 0.0, "reason": "insufficient_data"}

        close = [c["close"] for c in candles]
        fast_vals = sma(close, self.fast_period)
        slow_vals = sma(close, self.slow_period)

        fast_now = _last_val(fast_vals)
        fast_prev = _prev_val(fast_vals)
        slow_now = _last_val(slow_vals)
        slow_prev = _prev_val(slow_vals)

        if any(v is None for v in (fast_now, fast_prev, slow_now, slow_prev)):
            return {"decision": "HOLD", "confidence": 0.0, "reason": "indicators_not_ready"}

        has_position = context.symbol in context.open_positions

        # Golden cross: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now and not has_position:
            size = (context.portfolio_balance * 0.95) / context.current_price if context.current_price > 0 else 0
            return {
                "decision": "BUY",
                "confidence": 0.7,
                "reason": f"SMA golden cross (fast={fast_now:.2f} > slow={slow_now:.2f})",
                "suggested_position_size": size,
            }

        # Death cross: fast crosses below slow
        if fast_prev >= slow_prev and fast_now < slow_now and has_position:
            return {
                "decision": "SELL",
                "confidence": 0.7,
                "reason": f"SMA death cross (fast={fast_now:.2f} < slow={slow_now:.2f})",
            }

        return {"decision": "HOLD", "confidence": 0.5, "reason": "no crossover"}


class RSIMeanReversion(TradingAI):
    """RSI mean reversion baseline. Buy oversold, sell overbought."""

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        super().__init__(ai_id="baseline-rsi", model=f"rsi-{period}")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def decide(self, context: MarketContext) -> Dict[str, Any]:
        candles = context.candles
        if len(candles) < self.period + 2:
            return {"decision": "HOLD", "confidence": 0.0, "reason": "insufficient_data"}

        close = [c["close"] for c in candles]
        rsi_vals = rsi(close, self.period)
        current_rsi = _last_val(rsi_vals)

        if current_rsi is None:
            return {"decision": "HOLD", "confidence": 0.0, "reason": "rsi_calculation_failed"}

        has_position = context.symbol in context.open_positions

        if current_rsi < self.oversold and not has_position:
            size = (context.portfolio_balance * 0.10) / context.current_price if context.current_price > 0 else 0
            return {
                "decision": "BUY",
                "confidence": 0.65,
                "reason": f"RSI oversold ({current_rsi:.1f})",
                "suggested_position_size": size,
                "stop_loss": context.current_price * 0.97,
                "take_profit": context.current_price * 1.05,
            }
        elif current_rsi > self.overbought and has_position:
            return {
                "decision": "SELL",
                "confidence": 0.65,
                "reason": f"RSI overbought ({current_rsi:.1f})",
            }

        return {"decision": "HOLD", "confidence": 0.5, "reason": f"RSI neutral ({current_rsi:.1f})"}


def get_all_baselines() -> List[TradingAI]:
    """Return all baseline strategies for comparison."""
    return [BuyAndHold(), SMACrossover(), RSIMeanReversion()]


def _last_val(values):
    for v in reversed(values):
        if v is not None:
            return v
    return None


def _prev_val(values):
    found = 0
    for v in reversed(values):
        if v is not None:
            found += 1
            if found == 2:
                return v
    return None
