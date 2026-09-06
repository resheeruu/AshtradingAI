"""Market regime detection — deterministic, testable, no ML.

Classifies market conditions as:
- TRENDING_UP
- TRENDING_DOWN
- RANGING
- HIGH_VOLATILITY
- LOW_VOLATILITY
- UNKNOWN

Uses existing indicators (EMA, ATR, SMA). Exposes regime as contextual
information. Default behavior is conservative: UNKNOWN when confidence insufficient.
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict

from src.indicators.technical import ema, atr, sma


class Regime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeResult:
    """Result of regime classification."""
    regime: Regime
    confidence: float  # 0.0 - 1.0
    details: Dict[str, float] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def summary(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "details": {k: round(v, 6) for k, v in self.details.items()},
        }


class RegimeDetector:
    """Deterministic market regime classifier.

    Uses EMA slope for trend direction, ATR for volatility,
    and price-SMA distance for ranging detection.

    Configuration:
    - ema_fast: Fast EMA period for slope
    - ema_slow: Slow EMA period for slope
    - atr_period: ATR period for volatility
    - atr_high_threshold: ATR percentile above which = HIGH_VOLATILITY
    - atr_low_threshold: ATR percentile below which = LOW_VOLATILITY
    - trend_threshold: Minimum EMA slope for trend classification
    - range_threshold: Maximum price-SMA distance for ranging
    - min_confidence: Minimum confidence to assign a regime (else UNKNOWN)
    """

    def __init__(
        self,
        ema_fast: int = 12,
        ema_slow: int = 26,
        atr_period: int = 14,
        atr_lookback: int = 50,
        atr_high_percentile: float = 0.80,
        atr_low_percentile: float = 0.20,
        trend_threshold: float = 0.0002,
        range_threshold: float = 0.02,
        min_confidence: float = 0.4,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.atr_period = atr_period
        self.atr_lookback = atr_lookback
        self.atr_high_percentile = atr_high_percentile
        self.atr_low_percentile = atr_low_percentile
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold
        self.min_confidence = min_confidence

    def detect(
        self,
        high: List[float],
        low: List[float],
        close: List[float],
    ) -> RegimeResult:
        """Classify market regime from completed candle data.

        Fails closed: insufficient data → UNKNOWN.
        """
        min_len = max(self.ema_slow + 2, self.atr_period + 2, self.atr_lookback)
        if len(close) < min_len:
            return RegimeResult(regime=Regime.UNKNOWN, confidence=0.0,
                                details={"reason": "insufficient_data"})

        # --- Trend Detection via EMA slope ---
        ema_fast_vals = ema(close, self.ema_fast)
        ema_slow_vals = ema(close, self.ema_slow)

        ef = _last_val(ema_fast_vals)
        es = _last_val(ema_slow_vals)
        ef_prev = _prev_val(ema_fast_vals)
        es_prev = _prev_val(ema_slow_vals)

        if ef is None or es is None or ef_prev is None or es_prev is None:
            return RegimeResult(regime=Regime.UNKNOWN, confidence=0.0,
                                details={"reason": "ema_calculation_failed"})

        # EMA slope (normalized)
        fast_slope = (ef - ef_prev) / ef_prev if ef_prev != 0 else 0.0
        slow_slope = (es - es_prev) / es_prev if es_prev != 0 else 0.0

        # --- Volatility Detection via ATR ---
        atr_vals = atr(high, low, close, self.atr_period)
        current_atr = _last_val(atr_vals)
        if current_atr is None or current_atr <= 0 or not math.isfinite(current_atr):
            return RegimeResult(regime=Regime.UNKNOWN, confidence=0.0,
                                details={"reason": "atr_calculation_failed"})

        # ATR percentile over lookback
        lookback_start = max(0, len(atr_vals) - self.atr_lookback)
        recent_atr = [v for v in atr_vals[lookback_start:] if v is not None and v > 0]
        if len(recent_atr) < 5:
            return RegimeResult(regime=Regime.UNKNOWN, confidence=0.0,
                                details={"reason": "insufficient_atr_history"})

        sorted_atr = sorted(recent_atr)
        high_atr = _percentile(sorted_atr, self.atr_high_percentile)
        low_atr = _percentile(sorted_atr, self.atr_low_percentile)

        is_high_vol = current_atr >= high_atr if high_atr > 0 else False
        is_low_vol = current_atr <= low_atr if low_atr > 0 else False

        # --- Range Detection via price vs SMA ---
        sma_vals = sma(close, 20)
        current_sma = _last_val(sma_vals)
        if current_sma is not None and current_sma > 0:
            price_dist = abs(close[-1] - current_sma) / current_sma
        else:
            price_dist = 1.0  # assume not ranging

        is_ranging = price_dist < self.range_threshold

        # --- Combine signals ---
        details = {
            "fast_ema_slope": fast_slope,
            "slow_ema_slope": slow_slope,
            "current_atr": current_atr,
            "atr_high_threshold": high_atr,
            "atr_low_threshold": low_atr,
            "price_sma_distance": price_dist,
            "is_high_vol": float(is_high_vol),
            "is_low_vol": float(is_low_vol),
            "is_ranging": float(is_ranging),
        }

        # Priority: HIGH_VOLATILITY overrides everything.
        # RANGING takes precedence over weak trend signals because a market
        # that is oscillating around its SMA is genuinely ranging regardless
        # of the instantaneous EMA slope at the boundary.
        # Trend classification comes after RANGING so that strong directional
        # moves are caught, but genuine ranging is not mis-classified.
        # LOW_VOLATILITY only applies when there is no trend and no range.
        if is_high_vol:
            confidence = min(1.0, 0.5 + (current_atr / high_atr - 1.0) * 0.5) if high_atr > 0 else 0.5
            return RegimeResult(regime=Regime.HIGH_VOLATILITY,
                                confidence=max(confidence, self.min_confidence),
                                details=details)

        if is_ranging:
            confidence = min(1.0, 0.5 + (self.range_threshold - price_dist) / self.range_threshold * 0.5)
            return RegimeResult(regime=Regime.RANGING,
                                confidence=max(confidence, self.min_confidence),
                                details=details)

        # Trend classification (before LOW_VOLATILITY — a clear directional
        # trend is more actionable than noting low volatility)
        if fast_slope > self.trend_threshold and slow_slope > 0:
            confidence = min(1.0, 0.5 + fast_slope / self.trend_threshold * 0.1)
            return RegimeResult(regime=Regime.TRENDING_UP,
                                confidence=max(confidence, self.min_confidence),
                                details=details)

        if fast_slope < -self.trend_threshold and slow_slope < 0:
            confidence = min(1.0, 0.5 + abs(fast_slope) / self.trend_threshold * 0.1)
            return RegimeResult(regime=Regime.TRENDING_DOWN,
                                confidence=max(confidence, self.min_confidence),
                                details=details)

        if is_low_vol:
            confidence = min(1.0, 0.5 + (1.0 - current_atr / low_atr) * 0.5) if low_atr > 0 else 0.5
            return RegimeResult(regime=Regime.LOW_VOLATILITY,
                                confidence=max(confidence, self.min_confidence),
                                details=details)

        # Mixed signals — low confidence
        return RegimeResult(regime=Regime.UNKNOWN, confidence=0.3, details=details)


def _last_val(values: List[Optional[float]]) -> Optional[float]:
    for v in reversed(values):
        if v is not None:
            return v
    return None


def _prev_val(values: List[Optional[float]]) -> Optional[float]:
    found = 0
    for v in reversed(values):
        if v is not None:
            found += 1
            if found == 2:
                return v
    return None


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(pct * (len(sorted_vals) - 1))
    return sorted_vals[min(idx, len(sorted_vals) - 1)]
