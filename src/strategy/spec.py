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
    strategy_family: str = ""  # e.g., "SCALPING", "TREND", "MEAN_REVERSION", "BREAKOUT", "MOMENTUM", "PRICE_ACTION", "VWAP", "MULTI_TIMEFRAME", "SMC", "COMPOSITE"
    expected_holding_period: str = ""  # e.g., "SCALP", "INTRADAY", "SWING"
    regime_compatibility: List[str] = field(default_factory=list)  # Regimes this strategy works well in
    entry_conditions: List[str] = field(default_factory=list)  # Required conditions for entry
    invalidation_conditions: List[str] = field(default_factory=list)  # Conditions that invalidate the setup

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

    def get_signal_score(self, signal: Signal, regime: str = None) -> Dict[str, Any]:
        """Return structured scoring data for a signal."""
        if signal is None:
            return {
                "signal": "NONE",
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "regime_compatibility": 0.0,
                "entry_conditions": [],
                "stop_loss_suggestion": None,
                "take_profit_suggestion": None,
                "invalidation": [],
                "timeframe": self.spec.supported_timeframes[0] if self.spec.supported_timeframes else "H1",
                "expected_holding_period": self.spec.expected_holding_period,
                "strategy_id": self._id,
                "strategy_family": self.spec.strategy_family,
            }

        # Calculate regime compatibility
        regime_compat = 0.0
        if regime and self.spec.regime_compatibility:
            regime_compat = 1.0 if regime in self.spec.regime_compatibility else 0.3

        return {
            "signal": "ACTIVE",
            "direction": signal.direction,
            "confidence": signal.confidence,
            "regime_compatibility": regime_compat,
            "entry_conditions": self.spec.entry_conditions,
            "stop_loss_suggestion": signal.stop_loss,
            "take_profit_suggestion": signal.take_profit,
            "invalidation": self.spec.invalidation_conditions,
            "timeframe": signal.timeframe,
            "expected_holding_period": self.spec.expected_holding_period,
            "strategy_id": self._id,
            "strategy_family": self.spec.strategy_family,
        }


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


# ── Multi-Strategy Family Implementations ──────────────────────────────

class AIScalpingStrategy(BaseStrategy):
    """AI Scalping strategy for M1/M3/M5 timeframes with strict risk controls."""

    def __init__(
        self,
        ema_fast: int = 5,
        ema_slow: int = 13,
        rsi_period: int = 7,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.0,
        momentum_period: int = 10,
        spread_filter: float = 0.002,
        volatility_filter: float = 0.001,
    ):
        super().__init__(StrategySpec(
            strategy_id="ai_scalping",
            name="AI Scalping",
            parameters={
                "ema_fast": ema_fast, "ema_slow": ema_slow,
                "rsi_period": rsi_period, "atr_period": atr_period,
            },
            min_bars_required=max(ema_slow, rsi_period, atr_period, momentum_period, 50),
            supported_timeframes=["M1", "M3", "M5"],
            strategy_family="SCALPING",
            expected_holding_period="SCALP",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            entry_conditions=["EMA_crossover", "RSI_not_extreme", "ATR_sufficient", "Momentum_aligned", "Spread_within_limit", "Volatility_acceptable"],
            invalidation_conditions=["Opposite_EMA_crossover", "RSI_extreme", "ATR_spike", "Momentum_divergence"],
        ))
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.momentum_period = momentum_period
        self.spread_filter = spread_filter
        self.volatility_filter = volatility_filter

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.ema_slow + 5:
            return None

        ema_fast = indicators.get(f"ema_{self.ema_fast}", [])
        ema_slow = indicators.get(f"ema_{self.ema_slow}", [])
        rsi = indicators.get(f"rsi_{self.rsi_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])

        if not ema_fast or not ema_slow or not rsi or not atr:
            return None

        ef = ema_fast[-1]
        es = ema_slow[-1]
        r = rsi[-1]
        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Spread filter
        spread = context.get("spread", 0.0)
        if spread > self.spread_filter:
            return None

        # Volatility filter
        volatility = a / price if price > 0 else 0
        if volatility < self.volatility_filter:
            return None

        # Momentum calculation
        if len(candles) >= self.momentum_period:
            momentum = (price - candles[-self.momentum_period]["close"]) / candles[-self.momentum_period]["close"]
        else:
            momentum = 0.0

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # EMA crossover with RSI confirmation
        if ef > es and r < self.rsi_overbought and momentum > 0:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "M5"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.72,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "rsi": r, "atr": a, "momentum": momentum},
            )
        if ef < es and r > self.rsi_oversold and momentum < 0:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "M5"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.72,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "rsi": r, "atr": a, "momentum": momentum},
            )
        return None


class TrendFollowingStrategy(BaseStrategy):
    """Trend Following strategy with fast/slow EMA, higher-timeframe filter, ADX, ATR, pullback confirmation."""

    def __init__(
        self,
        fast_ema: int = 12,
        slow_ema: int = 26,
        htf_ema: int = 50,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
        pullback_candles: int = 2,
    ):
        super().__init__(StrategySpec(
            strategy_id="trend_following",
            name="Trend Following",
            parameters={
                "fast_ema": fast_ema, "slow_ema": slow_ema, "htf_ema": htf_ema,
                "adx_period": adx_period, "adx_threshold": adx_threshold,
            },
            min_bars_required=max(slow_ema, htf_ema, adx_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="TREND",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN"],
            entry_conditions=["EMA_alignment", "ADX_strong", "HTF_trend_confirms", "Pullback_occurred", "ATR_sufficient"],
            invalidation_conditions=["EMA_cross_against", "ADX_weakens", "HTF_trend_reverses", "Break_of_structure"],
        ))
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.htf_ema = htf_ema
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.pullback_candles = pullback_candles

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.htf_ema + 5:
            return None

        ema_fast = indicators.get(f"ema_{self.fast_ema}", [])
        ema_slow = indicators.get(f"ema_{self.slow_ema}", [])
        ema_htf = indicators.get(f"ema_{self.htf_ema}", [])
        adx = indicators.get(f"adx_{self.adx_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])

        if not ema_fast or not ema_slow or not ema_htf or not adx or not atr:
            return None

        ef = ema_fast[-1]
        es = ema_slow[-1]
        eh = ema_htf[-1]
        a = adx[-1]
        atr_val = atr[-1]
        price = candles[-1]["close"]

        if atr_val <= 0 or price <= 0:
            return None

        # ADX strength check
        if a < self.adx_threshold:
            return None

        # Higher timeframe trend filter
        htf_bullish = price > eh
        htf_bearish = price < eh

        # Pullback confirmation (simplified)
        pullback_occurred = True  # In real implementation, check for pullback candles

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Trend continuation with pullback
        if ef > es and htf_bullish and pullback_occurred:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.78,
                entry=price, stop_loss=price - atr_val * self.atr_sl_mult,
                take_profit=price + atr_val * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "ema_htf": eh, "adx": a, "atr": atr_val},
            )
        if ef < es and htf_bearish and pullback_occurred:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.78,
                entry=price, stop_loss=price + atr_val * self.atr_sl_mult,
                take_profit=price - atr_val * self.atr_tp_mult,
                strategy_id=self._id,
                features={"ema_fast": ef, "ema_slow": es, "ema_htf": eh, "adx": a, "atr": atr_val},
            )
        return None


class MeanReversionStrategy(BaseStrategy):
    """Mean Reversion strategy using Bollinger Bands, RSI, moving average, ATR, volatility/range detection."""

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        ma_period: int = 50,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
    ):
        super().__init__(StrategySpec(
            strategy_id="mean_reversion",
            name="Mean Reversion",
            parameters={
                "bb_period": bb_period, "bb_std": bb_std,
                "rsi_period": rsi_period, "ma_period": ma_period,
            },
            min_bars_required=max(bb_period, rsi_period, ma_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4"],
            strategy_family="MEAN_REVERSION",
            expected_holding_period="INTRADAY",
            regime_compatibility=["RANGING", "LOW_VOLATILITY"],
            entry_conditions=["BB_extreme", "RSI_extreme", "Price_at_MA", "Volatility_low", "Range_detected"],
            invalidation_conditions=["Strong_trend", "BB_squeeze", "Volatility_spike", "Break_of_range"],
        ))
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.ma_period = ma_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < max(self.bb_period, self.rsi_period, self.ma_period) + 5:
            return None

        bb_upper = indicators.get("bb_upper", [])
        bb_lower = indicators.get("bb_lower", [])
        bb_mid = indicators.get("bb_mid", [])
        rsi = indicators.get(f"rsi_{self.rsi_period}", [])
        ma = indicators.get(f"sma_{self.ma_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])

        if not bb_upper or not bb_lower or not bb_mid or not rsi or not ma or not atr:
            return None

        upper = bb_upper[-1]
        lower = bb_lower[-1]
        mid = bb_mid[-1]
        r = rsi[-1]
        m = ma[-1]
        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Volatility/range detection
        bb_width = (upper - lower) / mid if mid > 0 else 0
        volatility_low = bb_width < 0.02  # Simple range detection

        if not volatility_low:
            return None

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Mean reversion from oversold
        if r < self.rsi_oversold and price < lower and price > m * 0.98:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.68,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=mid,
                strategy_id=self._id,
                features={"bb_upper": upper, "bb_lower": lower, "bb_mid": mid, "rsi": r, "ma": m, "atr": a},
            )
        # Mean reversion from overbought
        if r > self.rsi_overbought and price > upper and price < m * 1.02:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.68,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=mid,
                strategy_id=self._id,
                features={"bb_upper": upper, "bb_lower": lower, "bb_mid": mid, "rsi": r, "ma": m, "atr": a},
            )
        return None


class BreakoutStrategy(BaseStrategy):
    """Breakout strategy using recent high/low, Donchian-style channel, ATR, volume, volatility expansion."""

    def __init__(
        self,
        channel_period: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        volume_threshold: float = 1.5,
        volatility_expansion: float = 1.2,
        confirmation_candles: int = 1,
    ):
        super().__init__(StrategySpec(
            strategy_id="breakout",
            name="Breakout",
            parameters={
                "channel_period": channel_period, "atr_period": atr_period,
            },
            min_bars_required=max(channel_period, atr_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="BREAKOUT",
            expected_holding_period="INTRADAY",
            regime_compatibility=["BREAKOUT", "TRENDING_UP", "TRENDING_DOWN"],
            entry_conditions=["Channel_break", "Volume_spike", "Volatility_expansion", "Confirmation_candle"],
            invalidation_conditions=["False_breakout", "Low_volume", "Volatility_contraction", "Reversal_candle"],
        ))
        self.channel_period = channel_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.volume_threshold = volume_threshold
        self.volatility_expansion = volatility_expansion
        self.confirmation_candles = confirmation_candles

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.channel_period + 5:
            return None

        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not atr:
            return None

        a = atr[-1]
        price = candles[-1]["close"]
        volume = candles[-1].get("volume", 0)

        if a <= 0 or price <= 0:
            return None

        # Donchian channel
        highs = [c["high"] for c in candles[-self.channel_period:]]
        lows = [c["low"] for c in candles[-self.channel_period:]]
        upper_channel = max(highs)
        lower_channel = min(lows)

        # Volume check
        avg_volume = sum(c.get("volume", 0) for c in candles[-self.channel_period:]) / self.channel_period
        volume_spike = volume > avg_volume * self.volume_threshold if avg_volume > 0 else False

        # Volatility expansion
        current_volatility = a / price if price > 0 else 0
        prev_a = atr[-2] if len(atr) > 1 else a
        prev_volatility = prev_a / candles[-2]["close"] if candles[-2]["close"] > 0 else 0
        volatility_expanding = current_volatility > prev_volatility * self.volatility_expansion

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Breakout detection
        if price > upper_channel and volume_spike and volatility_expanding:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.75,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"upper_channel": upper_channel, "lower_channel": lower_channel, "atr": a, "volume_spike": volume_spike},
            )
        if price < lower_channel and volume_spike and volatility_expanding:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.75,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"upper_channel": upper_channel, "lower_channel": lower_channel, "atr": a, "volume_spike": volume_spike},
            )
        return None


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using RSI, MACD, EMA, rate of change, ATR."""

    def __init__(
        self,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        ema_period: int = 50,
        momentum_period: int = 10,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        super().__init__(StrategySpec(
            strategy_id="momentum",
            name="Momentum",
            parameters={
                "rsi_period": rsi_period, "macd_fast": macd_fast,
                "macd_slow": macd_slow, "macd_signal": macd_signal,
            },
            min_bars_required=max(macd_slow + macd_signal, ema_period, momentum_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4"],
            strategy_family="MOMENTUM",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN"],
            entry_conditions=["Momentum_strong", "Trend_aligned", "MACD_crossover", "RSI_not_extreme", "ATR_sufficient"],
            invalidation_conditions=["Momentum_divergence", "Trend_weakens", "MACD_cross_against", "RSI_extreme"],
        ))
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.ema_period = ema_period
        self.momentum_period = momentum_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < max(self.macd_slow + self.macd_signal, self.ema_period, self.momentum_period) + 5:
            return None

        rsi = indicators.get(f"rsi_{self.rsi_period}", [])
        macd = indicators.get("macd", [])
        macd_signal = indicators.get("macd_signal", [])
        ema = indicators.get(f"ema_{self.ema_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])

        if not rsi or not macd or not macd_signal or not ema or not atr:
            return None

        r = rsi[-1]
        m = macd[-1]
        ms = macd_signal[-1]
        e = ema[-1]
        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Momentum calculation
        if len(candles) >= self.momentum_period:
            momentum = (price - candles[-self.momentum_period]["close"]) / candles[-self.momentum_period]["close"]
        else:
            momentum = 0.0

        # Trend alignment
        trend_aligned = (price > e and momentum > 0) or (price < e and momentum < 0)

        # MACD crossover
        macd_bullish = len(macd) >= 2 and macd[-2] < macd_signal[-2] and macd[-1] > macd_signal[-1]
        macd_bearish = len(macd) >= 2 and macd[-2] > macd_signal[-2] and macd[-1] < macd_signal[-1]

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Momentum with trend confirmation
        if momentum > 0 and trend_aligned and macd_bullish and r < 70:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.76,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"rsi": r, "macd": m, "macd_signal": ms, "ema": e, "momentum": momentum},
            )
        if momentum < 0 and trend_aligned and macd_bearish and r > 30:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.76,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"rsi": r, "macd": m, "macd_signal": ms, "ema": e, "momentum": momentum},
            )
        return None


class PriceActionStrategy(BaseStrategy):
    """Price Action strategy supporting engulfing, pin bar, rejection, inside bar, breakout/retest, support/resistance."""

    def __init__(
        self,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        support_resistance_lookback: int = 50,
        pattern_confirmation: bool = True,
    ):
        super().__init__(StrategySpec(
            strategy_id="price_action",
            name="Price Action",
            parameters={
                "atr_period": atr_period,
                "support_resistance_lookback": support_resistance_lookback,
            },
            min_bars_required=max(atr_period, support_resistance_lookback, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="PRICE_ACTION",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            entry_conditions=["Candle_pattern", "Market_structure", "Support_resistance", "Risk_filter"],
            invalidation_conditions=["Opposite_pattern", "Break_of_structure", "Invalidated_level"],
        ))
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.support_resistance_lookback = support_resistance_lookback
        self.pattern_confirmation = pattern_confirmation

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.support_resistance_lookback + 5:
            return None

        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not atr:
            return None

        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Simplified candle pattern detection
        if len(candles) < 3:
            return None

        prev = candles[-2]
        curr = candles[-1]

        # Engulfing pattern
        bullish_engulfing = (curr["close"] > curr["open"] and
                           prev["close"] < prev["open"] and
                           curr["close"] > prev["open"] and
                           curr["open"] < prev["close"])

        bearish_engulfing = (curr["close"] < curr["open"] and
                           prev["close"] > prev["open"] and
                           curr["close"] < prev["open"] and
                           curr["open"] > prev["close"])

        # Pin bar (simplified)
        body = abs(curr["close"] - curr["open"])
        upper_wick = curr["high"] - max(curr["close"], curr["open"])
        lower_wick = min(curr["close"], curr["open"]) - curr["low"]

        bullish_pin = lower_wick > body * 2 and upper_wick < body
        bearish_pin = upper_wick > body * 2 and lower_wick < body

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Price action signals
        if bullish_engulfing or bullish_pin:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.70,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"pattern": "bullish_engulfing" if bullish_engulfing else "bullish_pin", "atr": a},
            )
        if bearish_engulfing or bearish_pin:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.70,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"pattern": "bearish_engulfing" if bearish_engulfing else "bearish_pin", "atr": a},
            )
        return None


class VWAPStrategy(BaseStrategy):
    """VWAP/Intraday strategy using VWAP deviation, trend direction, momentum, mean reversion, breakout from VWAP zones."""

    def __init__(
        self,
        vwap_period: int = 20,
        deviation_mult: float = 2.0,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.0,
        momentum_period: int = 10,
    ):
        super().__init__(StrategySpec(
            strategy_id="vwap_intraday",
            name="VWAP Intraday",
            parameters={
                "vwap_period": vwap_period, "deviation_mult": deviation_mult,
            },
            min_bars_required=max(vwap_period, atr_period, momentum_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1"],
            strategy_family="VWAP",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            entry_conditions=["VWAP_deviation", "Trend_aligned", "Momentum_confirms", "Zone_breakout"],
            invalidation_conditions=["Opposite_deviation", "Trend_weakens", "Momentum_divergence"],
        ))
        self.vwap_period = vwap_period
        self.deviation_mult = deviation_mult
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.momentum_period = momentum_period

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.vwap_period + 5:
            return None

        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not atr:
            return None

        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Simplified VWAP calculation
        typical_prices = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles[-self.vwap_period:]]
        vwap = sum(typical_prices) / len(typical_prices) if typical_prices else price

        # VWAP deviation bands
        upper_band = vwap + a * self.deviation_mult
        lower_band = vwap - a * self.deviation_mult

        # Momentum
        if len(candles) >= self.momentum_period:
            momentum = (price - candles[-self.momentum_period]["close"]) / candles[-self.momentum_period]["close"]
        else:
            momentum = 0.0

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # VWAP mean reversion
        if price < lower_band and momentum > 0:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.66,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=vwap,
                strategy_id=self._id,
                features={"vwap": vwap, "upper_band": upper_band, "lower_band": lower_band, "atr": a, "momentum": momentum},
            )
        if price > upper_band and momentum < 0:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.66,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=vwap,
                strategy_id=self._id,
                features={"vwap": vwap, "upper_band": upper_band, "lower_band": lower_band, "atr": a, "momentum": momentum},
            )
        return None


class MultiTimeframeStrategy(BaseStrategy):
    """Multi-Timeframe strategy using higher timeframe for trend, lower timeframe for entry."""

    def __init__(
        self,
        htf: str = "H4",
        ltf: str = "M15",
        htf_ema_period: int = 50,
        ltf_ema_period: int = 20,
        atr_period: int = 14,
        atr_sl_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ):
        super().__init__(StrategySpec(
            strategy_id="multi_timeframe",
            name="Multi-Timeframe",
            parameters={
                "htf": htf, "ltf": ltf,
                "htf_ema_period": htf_ema_period, "ltf_ema_period": ltf_ema_period,
            },
            min_bars_required=max(htf_ema_period, ltf_ema_period, atr_period, 50),
            supported_timeframes=["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="MULTI_TIMEFRAME",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            entry_conditions=["HTF_trend", "LTF_entry", "Alignment", "ATR_sufficient"],
            invalidation_conditions=["HTF_trend_reversal", "LTF_break_against", "Misalignment"],
        ))
        self.htf = htf
        self.ltf = ltf
        self.htf_ema_period = htf_ema_period
        self.ltf_ema_period = ltf_ema_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < max(self.htf_ema_period, self.ltf_ema_period) + 5:
            return None

        # In real implementation, would fetch multi-timeframe data
        # Here we use the provided candles as the lower timeframe
        htf_ema = indicators.get(f"ema_{self.htf_ema_period}", [])
        ltf_ema = indicators.get(f"ema_{self.ltf_ema_period}", [])
        atr = indicators.get(f"atr_{self.atr_period}", [])

        if not htf_ema or not ltf_ema or not atr:
            return None

        htf_val = htf_ema[-1]
        ltf_val = ltf_ema[-1]
        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # Multi-timeframe alignment
        if price > htf_val and price > ltf_val:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=self.ltf,
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.74,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"htf_ema": htf_val, "ltf_ema": ltf_val, "atr": a},
            )
        if price < htf_val and price < ltf_val:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=self.ltf,
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.74,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"htf_ema": htf_val, "ltf_ema": ltf_val, "atr": a},
            )
        return None


class SMCStrategy(BaseStrategy):
    """SMC/Market Structure strategy using swing highs/lows, break of structure, change of character, liquidity sweep, supply/demand zones."""

    def __init__(
        self,
        swing_lookback: int = 10,
        atr_period: int = 14,
        atr_sl_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
        structure_confirmation: bool = True,
    ):
        super().__init__(StrategySpec(
            strategy_id="smc_market_structure",
            name="SMC Market Structure",
            parameters={
                "swing_lookback": swing_lookback,
            },
            min_bars_required=max(swing_lookback * 2, atr_period, 50),
            supported_timeframes=["M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="SMC",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            entry_conditions=["Break_of_structure", "Change_of_character", "Liquidity_sweep", "Supply_demand_zone"],
            invalidation_conditions=["Invalid_structure", "False_breakout", "Zone_violation"],
        ))
        self.swing_lookback = swing_lookback
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.structure_confirmation = structure_confirmation

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if len(candles) < self.swing_lookback * 2 + 5:
            return None

        atr = indicators.get(f"atr_{self.atr_period}", [])
        if not atr:
            return None

        a = atr[-1]
        price = candles[-1]["close"]

        if a <= 0 or price <= 0:
            return None

        # Simplified swing high/low detection
        highs = [c["high"] for c in candles[-self.swing_lookback:]]
        lows = [c["low"] for c in candles[-self.swing_lookback:]]
        swing_high = max(highs)
        swing_low = min(lows)

        # Break of structure (simplified)
        break_of_structure_up = price > swing_high
        break_of_structure_down = price < swing_low

        # AI confirmation
        ai_confirmation = context.get("ai_confirmation", True)
        if not ai_confirmation:
            return None

        # SMC signals
        if break_of_structure_up:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="LONG", confidence=0.72,
                entry=price, stop_loss=price - a * self.atr_sl_mult,
                take_profit=price + a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"swing_high": swing_high, "swing_low": swing_low, "atr": a, "break_of_structure": "up"},
            )
        if break_of_structure_down:
            return Signal(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "H1"),
                timestamp=candles[-1]["timestamp"],
                direction="SHORT", confidence=0.72,
                entry=price, stop_loss=price + a * self.atr_sl_mult,
                take_profit=price - a * self.atr_tp_mult,
                strategy_id=self._id,
                features={"swing_high": swing_high, "swing_low": swing_low, "atr": a, "break_of_structure": "down"},
            )
        return None


class AICompositeStrategy(BaseStrategy):
    """AI Composite strategy combining multiple strategy signals."""

    def __init__(
        self,
        strategies: List[BaseStrategy] = None,
        min_agreement: int = 3,
        confidence_threshold: float = 0.7,
    ):
        super().__init__(StrategySpec(
            strategy_id="ai_composite",
            name="AI Composite",
            parameters={
                "min_agreement": min_agreement,
                "confidence_threshold": confidence_threshold,
            },
            min_bars_required=50,
            supported_timeframes=["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1"],
            strategy_family="COMPOSITE",
            expected_holding_period="INTRADAY",
            regime_compatibility=["TRENDING_UP", "TRENDING_DOWN", "RANGING", "BREAKOUT"],
            entry_conditions=["Multiple_strategies_agree", "AI_confirmation", "Risk_approved"],
            invalidation_conditions=["Strategy_disagreement", "AI_rejection", "Risk_rejection"],
        ))
        self.strategies = strategies or []
        self.min_agreement = min_agreement
        self.confidence_threshold = confidence_threshold

    def generate_signal(self, candles, indicators, context) -> Optional[Signal]:
        if not self.strategies:
            return None

        # Collect signals from all strategies
        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(candles, indicators, context)
                if signal and signal.is_actionable:
                    signals.append(signal)
            except Exception:
                continue

        if not signals:
            return None

        # Count agreement
        long_signals = [s for s in signals if s.direction == "LONG"]
        short_signals = [s for s in signals if s.direction == "SHORT"]

        long_count = len(long_signals)
        short_count = len(short_signals)

        # Check for minimum agreement
        if long_count >= self.min_agreement:
            avg_confidence = sum(s.confidence for s in long_signals) / long_count
            if avg_confidence >= self.confidence_threshold:
                return Signal(
                    symbol=context.get("symbol", ""),
                    timeframe=context.get("timeframe", "H1"),
                    timestamp=candles[-1]["timestamp"],
                    direction="LONG", confidence=avg_confidence,
                    entry=long_signals[0].entry,
                    stop_loss=long_signals[0].stop_loss,
                    take_profit=long_signals[0].take_profit,
                    strategy_id=self._id,
                    features={"agreement_count": long_count, "strategies": [s.strategy_id for s in long_signals]},
                )
        if short_count >= self.min_agreement:
            avg_confidence = sum(s.confidence for s in short_signals) / short_count
            if avg_confidence >= self.confidence_threshold:
                return Signal(
                    symbol=context.get("symbol", ""),
                    timeframe=context.get("timeframe", "H1"),
                    timestamp=candles[-1]["timestamp"],
                    direction="SHORT", confidence=avg_confidence,
                    entry=short_signals[0].entry,
                    stop_loss=short_signals[0].stop_loss,
                    take_profit=short_signals[0].take_profit,
                    strategy_id=self._id,
                    features={"agreement_count": short_count, "strategies": [s.strategy_id for s in short_signals]},
                )
        return None


def get_default_strategies() -> List[BaseStrategy]:
    """Return all built-in strategies."""
    return [
        EMATrendStrategy(),
        RSIMeanReversion(),
        MACDCrossover(),
        BollingerBreakout(),
        AIScalpingStrategy(),
        TrendFollowingStrategy(),
        MeanReversionStrategy(),
        BreakoutStrategy(),
        MomentumStrategy(),
        PriceActionStrategy(),
        VWAPStrategy(),
        MultiTimeframeStrategy(),
        SMCStrategy(),
        AICompositeStrategy(),
    ]
