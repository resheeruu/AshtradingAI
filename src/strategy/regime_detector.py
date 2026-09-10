"""Market Regime Detection for multi-strategy engine.

Detects market conditions and influences strategy selection.
Uses existing indicators and data without lookahead bias.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from src.core.enums import RegimeType

logger = logging.getLogger(__name__)


@dataclass
class MarketRegime:
    """Market regime detection result."""
    regime: RegimeType
    confidence: float
    indicators: Dict[str, Any]
    timestamp: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "indicators": self.indicators,
            "timestamp": self.timestamp,
            "description": self.description,
        }


class MarketRegimeDetector:
    """Centralized market regime detection using existing indicators."""

    def __init__(
        self,
        trend_ema_fast: int = 12,
        trend_ema_slow: int = 26,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
        adx_weak_threshold: float = 20.0,
        volatility_lookback: int = 20,
        volatility_high_threshold: float = 1.5,
        volatility_low_threshold: float = 0.5,
        breakout_lookback: int = 20,
    ):
        self.trend_ema_fast = trend_ema_fast
        self.trend_ema_slow = trend_ema_slow
        self.adx_period = adx_period
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_weak_threshold = adx_weak_threshold
        self.volatility_lookback = volatility_lookback
        self.volatility_high_threshold = volatility_high_threshold
        self.volatility_low_threshold = volatility_low_threshold
        self.breakout_lookback = breakout_lookback

    def detect(self, candles: List[Dict], indicators: Dict[str, Any], timestamp: str = "") -> MarketRegime:
        """Detect current market regime from candles and indicators."""
        if not candles or len(candles) < 50:
            return MarketRegime(
                regime=RegimeType.UNCERTAIN,
                confidence=0.0,
                indicators={},
                timestamp=timestamp,
                description="Insufficient data for regime detection",
            )

        # Extract indicators
        ema_fast = indicators.get(f"ema_{self.trend_ema_fast}", [])
        ema_slow = indicators.get(f"ema_{self.trend_ema_slow}", [])
        adx = indicators.get(f"adx_{self.adx_period}", [])
        atr = indicators.get(f"atr_14", [])

        if not ema_fast or not ema_slow or not adx or not atr:
            return MarketRegime(
                regime=RegimeType.UNCERTAIN,
                confidence=0.0,
                indicators={},
                timestamp=timestamp,
                description="Missing required indicators",
            )

        # Get current values
        ef = ema_fast[-1] if ema_fast else 0
        es = ema_slow[-1] if ema_slow else 0
        a = adx[-1] if adx else 0
        atr_val = atr[-1] if atr else 0
        price = candles[-1]["close"]

        if ef == 0 or es == 0 or a == 0 or atr_val == 0 or price == 0:
            return MarketRegime(
                regime=RegimeType.UNCERTAIN,
                confidence=0.0,
                indicators={},
                timestamp=timestamp,
                description="Invalid indicator values",
            )

        # Calculate regime factors
        trend_strength = abs(ef - es) / es if es > 0 else 0
        trend_direction = "UP" if ef > es else "DOWN"
        volatility = atr_val / price if price > 0 else 0

        # Volatility regime
        atr_values = atr[-self.volatility_lookback:] if len(atr) >= self.volatility_lookback else atr
        avg_atr = sum(atr_values) / len(atr_values) if atr_values else atr_val
        volatility_ratio = atr_val / avg_atr if avg_atr > 0 else 1.0

        # Breakout detection
        highs = [c["high"] for c in candles[-self.breakout_lookback:]]
        lows = [c["low"] for c in candles[-self.breakout_lookback:]]
        upper_channel = max(highs)
        lower_channel = min(lows)
        breakout_up = price > upper_channel
        breakout_down = price < lower_channel

        # Determine regime
        regime = RegimeType.UNCERTAIN
        confidence = 0.0
        description = ""

        # Check for high volatility
        if volatility_ratio > self.volatility_high_threshold:
            regime = RegimeType.HIGH_VOLATILITY
            confidence = min(0.9, volatility_ratio / 2.0)
            description = f"High volatility: {volatility_ratio:.2f}x average"
        # Check for low volatility
        elif volatility_ratio < self.volatility_low_threshold:
            regime = RegimeType.LOW_VOLATILITY
            confidence = min(0.9, 1.0 - volatility_ratio)
            description = f"Low volatility: {volatility_ratio:.2f}x average"
        # Check for breakout
        elif breakout_up or breakout_down:
            regime = RegimeType.BREAKOUT
            confidence = 0.8
            description = f"Breakout detected: {'up' if breakout_up else 'down'}"
        # Check for trend
        elif a > self.adx_trend_threshold:
            if trend_direction == "UP":
                regime = RegimeType.TRENDING_UP
                confidence = min(0.9, a / 100.0 + trend_strength)
                description = f"Trending up: ADX={a:.1f}, trend_strength={trend_strength:.3f}"
            else:
                regime = RegimeType.TRENDING_DOWN
                confidence = min(0.9, a / 100.0 + trend_strength)
                description = f"Trending down: ADX={a:.1f}, trend_strength={trend_strength:.3f}"
        # Check for ranging
        elif a < self.adx_weak_threshold:
            regime = RegimeType.RANGING
            confidence = min(0.9, 1.0 - a / 100.0)
            description = f"Ranging: ADX={a:.1f}"
        # Otherwise uncertain
        else:
            regime = RegimeType.UNCERTAIN
            confidence = 0.5
            description = f"Uncertain: ADX={a:.1f}"

        indicators_used = {
            "ema_fast": ef,
            "ema_slow": es,
            "adx": a,
            "atr": atr_val,
            "volatility_ratio": volatility_ratio,
            "trend_strength": trend_strength,
            "trend_direction": trend_direction,
            "breakout_up": breakout_up,
            "breakout_down": breakout_down,
        }

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            indicators=indicators_used,
            timestamp=timestamp,
            description=description,
        )

    def get_strategy_preferences(self, regime: MarketRegime) -> Dict[str, float]:
        """Return strategy preferences based on regime."""
        preferences = {
            "ai_scalping": 0.5,
            "trend_following": 0.5,
            "mean_reversion": 0.5,
            "breakout": 0.5,
            "momentum": 0.5,
            "price_action": 0.5,
            "vwap_intraday": 0.5,
            "multi_timeframe": 0.5,
            "smc_market_structure": 0.5,
            "ai_composite": 0.5,
        }

        # Adjust based on regime
        if regime.regime == RegimeType.TRENDING_UP or regime.regime == RegimeType.TRENDING_DOWN:
            preferences["trend_following"] = 0.9
            preferences["momentum"] = 0.8
            preferences["multi_timeframe"] = 0.7
            preferences["smc_market_structure"] = 0.6
            preferences["mean_reversion"] = 0.3
        elif regime.regime == RegimeType.RANGING:
            preferences["mean_reversion"] = 0.9
            preferences["vwap_intraday"] = 0.8
            preferences["price_action"] = 0.7
            preferences["trend_following"] = 0.3
            preferences["momentum"] = 0.4
        elif regime.regime == RegimeType.BREAKOUT:
            preferences["breakout"] = 0.9
            preferences["momentum"] = 0.8
            preferences["smc_market_structure"] = 0.7
            preferences["mean_reversion"] = 0.2
        elif regime.regime == RegimeType.HIGH_VOLATILITY:
            # Reduce all preferences in high volatility
            for key in preferences:
                preferences[key] = 0.3
            preferences["ai_composite"] = 0.6  # AI composite can handle volatility better
        elif regime.regime == RegimeType.LOW_VOLATILITY:
            preferences["mean_reversion"] = 0.8
            preferences["vwap_intraday"] = 0.7
            preferences["breakout"] = 0.4
            preferences["momentum"] = 0.4

        # Apply confidence modifier
        confidence_modifier = regime.confidence
        for key in preferences:
            preferences[key] *= confidence_modifier

        return preferences