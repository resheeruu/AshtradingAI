"""Strategy contract/specification — single source of truth for backtesting and live.

Both backtester and live execution consume the same signal definition.
If behavior differs: STRATEGY_PARITY_ERROR.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.signals import Signal
from src.core.enums import RegimeType

logger = logging.getLogger(__name__)


@dataclass
class StrategySpec:
    """Immutable strategy specification shared by all execution modes."""
    strategy_id: str
    name: str
    version: str = "1.0.0"
    supported_timeframes: List[str] = field(default_factory=lambda: ["H1"])
    supported_asset_classes: List[str] = field(default_factory=lambda: ["FOREX"])
    supported_regimes: List[str] = field(default_factory=lambda: [r.value for r in RegimeType])
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    min_bars_required: int = 50
    generates_stops: bool = True
    risk_reward_min: float = 1.0

    def validate_signal(self, signal: Signal) -> tuple:
        """Validate a signal against this strategy spec. Returns (valid, reason)."""
        if signal.strategy_id != self.strategy_id:
            return False, f"Strategy mismatch: expected={self.strategy_id}, got={signal.strategy_id}"
        if signal.timeframe not in self.supported_timeframes:
            return False, f"Timeframe {signal.timeframe} not supported by {self.strategy_id}"
        if signal.regime and signal.regime not in self.supported_regimes:
            return False, f"Regime {signal.regime} not supported by {self.strategy_id}"
        if signal.direction not in ("LONG", "SHORT", "NEUTRAL"):
            return False, f"Invalid direction: {signal.direction}"
        if self.generates_stops and signal.stop_loss is None:
            return False, f"Strategy {self.strategy_id} requires stop_loss"
        if signal.risk_reward is not None and signal.risk_reward > 0 and signal.risk_reward < self.risk_reward_min:
            return False, f"Risk/reward {signal.risk_reward} below minimum {self.risk_reward_min}"
        return True, ""


class BaseStrategy(ABC):
    """Abstract strategy that produces standardized signals."""

    def __init__(self, spec: StrategySpec):
        self.spec = spec
        self._id = spec.strategy_id

    @property
    def strategy_id(self) -> str:
        return self._id

    @abstractmethod
    def generate_signal(self, candles: list, indicators: dict, context: dict) -> Optional[Signal]:
        """Generate a signal from candle data and indicators. Never execute."""
        pass

    def supports_regime(self, regime: str) -> bool:
        return regime in self.spec.supported_regimes

    def supports_timeframe(self, timeframe: str) -> bool:
        return timeframe in self.spec.supported_timeframes


# ── Built-in Strategy Implementations ──────────────────────────────────

class EMATrendStrategy(BaseStrategy):
    """EMA trend-following strategy."""

    def __init__(self, fast=12, slow=26, atr_period=14, atr_sl_mult=2.0, atr_tp_mult=3.0):
        super().__init__(StrategySpec(
            strategy_id="ema_trend",
            name="EMA Trend",
            parameters={"fast": fast, "slow": slow, "atr_period": atr_period},
            min_bars_required=max(slow, 50),
        ))
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.slow + 5:
            return None
        ema_fast = indicators.get(f"ema_{self.fast}", [])
        ema_slow = indicators.get(f"ema_{self.slow}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not ema_fast or not ema_slow or not atr:
            return None
        ef = ema_fast[-1]
        es = ema_slow[-1]
        a = atr[-1]
        price = candles[-1]["close"]
        if a <= 0:
            return None
        if ef > es and price > ef:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.65,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "atr": a},
            )
        if ef < es and price < ef:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.65,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "atr": a},
            )
        return None


class RSIMeanReversion(BaseStrategy):
    """RSI mean-reversion strategy."""

    def __init__(self, rsi_period=14, oversold=30, overbought=70, atr_period=14):
        super().__init__(StrategySpec(
            strategy_id="rsi_reversion",
            name="RSI Mean Reversion",
            parameters={"rsi_period": rsi_period, "oversold": oversold, "overbought": overbought},
            min_bars_required=max(rsi_period + 5, 50),
            supported_regimes=["RANGING", "LOW_VOLATILITY"],
        ))
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.atr_period = atr_period

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.rsi_period + 5:
            return None
        rsi = indicators.get(f"rsi_{self.rsi_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not rsi:
            return None
        r = rsi[-1]
        a = atr[-1] if atr else 0
        price = candles[-1]["close"]
        if a <= 0:
            return None
        if r < self.oversold:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.60,
                entry=price, stop_loss=price - a * 2.0,
                take_profit=price + a * 3.0,
                strategy_id=self._id,
                features={"rsi": r, "atr": a},
            )
        if r > self.overbought:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.60,
                entry=price, stop_loss=price + a * 2.0,
                take_profit=price - a * 3.0,
                strategy_id=self._id,
                features={"rsi": r, "atr": a},
            )
        return None


class MACDCrossover(BaseStrategy):
    """MACD crossover strategy."""

    def __init__(self, fast=12, slow=26, signal=9, atr_period=14):
        super().__init__(StrategySpec(
            strategy_id="macd_cross",
            name="MACD Crossover",
            parameters={"fast": fast, "slow": slow, "signal": signal},
            min_bars_required=max(slow + signal, 50),
        ))
        self.fast_p = fast
        self.slow_p = slow
        self.signal_p = signal
        self.atr_period = atr_period

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.slow_p + self.signal_p + 5:
            return None
        macd = indicators.get("macd", [])
        macd_signal = indicators.get("macd_signal", [])
        macd_hist = indicators.get("macd_hist", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not macd or not macd_signal or len(macd) < 2 or len(macd_signal) < 2:
            return None
        a = atr[-1] if atr else 0
        price = candles[-1]["close"]
        if a <= 0:
            return None
        if macd[-2] < macd_signal[-2] and macd[-1] > macd_signal[-1]:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.62,
                entry=price, stop_loss=price - a * 2.0,
                take_profit=price + a * 3.0,
                strategy_id=self._id,
                features={"macd": macd[-1], "signal": macd_signal[-1]},
            )
        if macd[-2] > macd_signal[-2] and macd[-1] < macd_signal[-1]:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.62,
                entry=price, stop_loss=price + a * 2.0,
                take_profit=price - a * 3.0,
                strategy_id=self._id,
                features={"macd": macd[-1], "signal": macd_signal[-1]},
            )
        return None


class BollingerBreakout(BaseStrategy):
    """Bollinger Band breakout strategy."""

    def __init__(self, period=20, std_dev=2.0, atr_period=14):
        super().__init__(StrategySpec(
            strategy_id="bb_breakout",
            name="Bollinger Breakout",
            parameters={"period": period, "std_dev": std_dev},
            min_bars_required=max(period + 5, 50),
        ))
        self.period = period
        self.std_dev = std_dev
        self.atr_period = atr_period

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.period + 5:
            return None
        upper = indicators.get("bb_upper", [])
        lower = indicators.get("bb_lower", [])
        mid = indicators.get("bb_mid", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not upper or not lower or not mid:
            return None
        a = atr[-1] if atr else 0
        price = candles[-1]["close"]
        if a <= 0:
            return None
        if price > upper[-1]:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.58,
                entry=price, stop_loss=mid[-1],
                take_profit=price + a * 3.0,
                strategy_id=self._id,
                features={"bb_upper": upper[-1], "bb_lower": lower[-1], "bb_mid": mid[-1]},
            )
        if price < lower[-1]:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.58,
                entry=price, stop_loss=mid[-1],
                take_profit=price - a * 3.0,
                strategy_id=self._id,
                features={"bb_upper": upper[-1], "bb_lower": lower[-1], "bb_mid": mid[-1]},
            )
        return None


def get_default_strategies() -> List[BaseStrategy]:
    """Return all built-in strategies."""
    return [
        EMATrendStrategy(),
        RSIMeanReversion(),
        MACDCrossover(),
        BollingerBreakout(),
    ]
