"""M7 Advanced Filter Cascade for strategy signal validation.

All filters operate on completed candles only. No lookahead.
Each filter returns a FilterResult with pass/fail and reason.
Filters fail closed: any error or invalid input = reject.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict

from src.indicators.technical import ema, atr


@dataclass
class FilterResult:
    """Result of a single filter evaluation."""
    passed: bool
    reason: str = ""
    value: Optional[float] = None


@dataclass
class FilterCascadeResult:
    """Aggregate result of all filters."""
    passed: bool
    results: Dict[str, FilterResult] = field(default_factory=dict)
    rejection_reason: str = ""

    def add(self, name: str, result: FilterResult) -> None:
        self.results[name] = result
        if not result.passed and not self.rejection_reason:
            self.rejection_reason = f"{name}: {result.reason}"
            self.passed = False


def _last_value(values: List[Optional[float]]) -> Optional[float]:
    """Get the last non-None value from a list."""
    for v in reversed(values):
        if v is not None:
            return v
    return None


def _prev_value(values: List[Optional[float]], offset: int = 1) -> Optional[float]:
    """Get a non-None value at offset from end (0 = last)."""
    non_none = [v for v in values if v is not None]
    idx = len(non_none) - 1 - offset
    if 0 <= idx < len(non_none):
        return non_none[idx]
    return None


class ATRFilter:
    """ATR volatility filter with min/max thresholds and change detection."""

    def __init__(
        self,
        enabled: bool = True,
        min_atr: float = 0.0,
        max_atr: float = 0.0,
        increase_threshold: float = 0.0,
        decrease_threshold: float = 0.0,
        period: int = 14,
    ):
        self.enabled = enabled
        self.min_atr = min_atr
        self.max_atr = max_atr
        self.increase_threshold = increase_threshold
        self.decrease_threshold = decrease_threshold
        self.period = period

    def evaluate(
        self,
        high: List[float],
        low: List[float],
        close: List[float],
        direction: str = "LONG",
    ) -> FilterResult:
        """Evaluate ATR filter. Fails closed on invalid data."""
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        if len(close) < self.period + 2:
            return FilterResult(passed=False, reason=f"insufficient data: need {self.period + 2} candles, got {len(close)}")

        # Reject NaN/inf in inputs (fail closed)
        for i in range(len(close)):
            if not math.isfinite(close[i]) or not math.isfinite(high[i]) or not math.isfinite(low[i]):
                return FilterResult(passed=False, reason=f"non-finite value in OHLC data at index {i}")

        atr_values = atr(high, low, close, self.period)
        current_atr = _last_value(atr_values)
        if current_atr is None or current_atr != current_atr:  # NaN check
            return FilterResult(passed=False, reason="ATR calculation failed or returned NaN")

        if not math.isfinite(current_atr) or current_atr <= 0:
            return FilterResult(passed=False, reason=f"ATR is non-positive or non-finite ({current_atr})")

        # Min threshold
        if self.min_atr > 0 and current_atr < self.min_atr:
            return FilterResult(passed=False, reason=f"ATR {current_atr:.6f} below minimum {self.min_atr}", value=current_atr)

        # Max threshold
        if self.max_atr > 0 and current_atr > self.max_atr:
            return FilterResult(passed=False, reason=f"ATR {current_atr:.6f} above maximum {self.max_atr}", value=current_atr)

        # ATR increase detection
        if self.increase_threshold > 0:
            prev_atr = _prev_value(atr_values, 1)
            if prev_atr is not None and prev_atr > 0:
                change = (current_atr - prev_atr) / prev_atr
                if change > self.increase_threshold:
                    return FilterResult(passed=False, reason=f"ATR increased by {change:.2%} (threshold: {self.increase_threshold:.2%})", value=current_atr)

        # ATR decrease detection
        if self.decrease_threshold > 0:
            prev_atr = _prev_value(atr_values, 1)
            if prev_atr is not None and prev_atr > 0:
                change = (prev_atr - current_atr) / prev_atr
                if change > self.decrease_threshold:
                    return FilterResult(passed=False, reason=f"ATR decreased by {change:.2%} (threshold: {self.decrease_threshold:.2%})", value=current_atr)

        return FilterResult(passed=True, value=current_atr)


class EMAAngleFilter:
    """EMA slope/angle filter for trend strength validation."""

    def __init__(
        self,
        enabled: bool = True,
        ema_period: int = 21,
        scale_factor: float = 10000.0,
        min_angle: float = 0.0002,
        max_angle: float = 0.0,
    ):
        self.enabled = enabled
        self.ema_period = ema_period
        self.scale_factor = scale_factor
        self.min_angle = min_angle
        self.max_angle = max_angle

    def evaluate(
        self,
        close: List[float],
        direction: str = "LONG",
    ) -> FilterResult:
        """Evaluate EMA angle. Fails closed on invalid data."""
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        if len(close) < self.ema_period + 2:
            return FilterResult(passed=False, reason=f"insufficient data: need {self.ema_period + 2} candles, got {len(close)}")

        ema_values = ema(close, self.ema_period)
        current = _last_value(ema_values)
        prev = _prev_value(ema_values, 1)

        if current is None or prev is None:
            return FilterResult(passed=False, reason="EMA calculation failed")

        if prev == 0:
            return FilterResult(passed=False, reason="EMA previous value is zero")

        # Raw slope: (current - prev) / prev * scale_factor
        raw_slope = (current - prev) / prev * self.scale_factor

        # For LONG: slope should be positive. For SHORT: negative.
        if direction == "LONG" and raw_slope < 0:
            return FilterResult(passed=False, reason=f"negative EMA slope for LONG ({raw_slope:.6f})", value=raw_slope)
        if direction == "SHORT" and raw_slope > 0:
            return FilterResult(passed=False, reason=f"positive EMA slope for SHORT ({raw_slope:.6f})", value=raw_slope)

        abs_slope = abs(raw_slope)

        # Min angle
        if self.min_angle > 0 and abs_slope < self.min_angle:
            return FilterResult(passed=False, reason=f"EMA angle {abs_slope:.6f} below minimum {self.min_angle}", value=raw_slope)

        # Max angle
        if self.max_angle > 0 and abs_slope > self.max_angle:
            return FilterResult(passed=False, reason=f"EMA angle {abs_slope:.6f} above maximum {self.max_angle}", value=raw_slope)

        return FilterResult(passed=True, value=raw_slope)


class PriceEMAFilter:
    """Price vs filter EMA positional filter."""

    def __init__(
        self,
        enabled: bool = True,
        ema_period: int = 50,
    ):
        self.enabled = enabled
        self.ema_period = ema_period

    def evaluate(
        self,
        close: List[float],
        direction: str = "LONG",
    ) -> FilterResult:
        """Evaluate price vs EMA. Fails closed on invalid data."""
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        if len(close) < self.ema_period:
            return FilterResult(passed=False, reason=f"insufficient data: need {self.ema_period} candles, got {len(close)}")

        ema_values = ema(close, self.ema_period)
        current_ema = _last_value(ema_values)
        if current_ema is None:
            return FilterResult(passed=False, reason="EMA calculation failed")

        price = close[-1]
        if price <= 0:
            return FilterResult(passed=False, reason=f"invalid price ({price})")

        if direction == "LONG" and price <= current_ema:
            return FilterResult(passed=False, reason=f"price {price:.4f} not above EMA {current_ema:.4f}")
        if direction == "SHORT" and price >= current_ema:
            return FilterResult(passed=False, reason=f"price {price:.4f} not below EMA {current_ema:.4f}")

        return FilterResult(passed=True, value=current_ema)


class CandleDirectionFilter:
    """Candle direction confirmation filter."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def evaluate(
        self,
        candles: List[Dict],
        direction: str = "LONG",
    ) -> FilterResult:
        """Evaluate candle direction. Uses the LAST COMPLETED candle (index -2 if current is forming).
        
        Fails closed on invalid data.
        """
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        # Use the second-to-last candle (completed, not forming)
        if len(candles) < 2:
            return FilterResult(passed=False, reason=f"insufficient candles: need 2, got {len(candles)}")

        candle = candles[-2]  # Last completed candle
        open_ = candle.get("open", 0)
        close = candle.get("close", 0)

        if open_ <= 0 or close <= 0:
            return FilterResult(passed=False, reason=f"invalid candle prices: open={open_}, close={close}")

        is_bullish = close > open_

        if direction == "LONG" and not is_bullish:
            return FilterResult(passed=False, reason=f"bearish candle in LONG direction (open={open_}, close={close})")
        if direction == "SHORT" and is_bullish:
            return FilterResult(passed=False, reason=f"bullish candle in SHORT direction (open={open_}, close={close})")

        return FilterResult(passed=True, value=1.0 if is_bullish else -1.0)


class EMAOrderFilter:
    """EMA ordering / trend structure filter."""

    def __init__(
        self,
        enabled: bool = True,
        fast_period: int = 12,
        medium_period: int = 26,
        slow_period: int = 50,
    ):
        self.enabled = enabled
        self.fast_period = fast_period
        self.medium_period = medium_period
        self.slow_period = slow_period

    def evaluate(
        self,
        close: List[float],
        direction: str = "LONG",
    ) -> FilterResult:
        """Evaluate EMA ordering. Fails closed on invalid data."""
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        required = self.slow_period + 1
        if len(close) < required:
            return FilterResult(passed=False, reason=f"insufficient data: need {required} candles, got {len(close)}")

        ema_fast_vals = ema(close, self.fast_period)
        ema_med_vals = ema(close, self.medium_period)
        ema_slow_vals = ema(close, self.slow_period)

        fast = _last_value(ema_fast_vals)
        med = _last_value(ema_med_vals)
        slow = _last_value(ema_slow_vals)

        if any(v is None for v in (fast, med, slow)):
            return FilterResult(passed=False, reason="EMA calculation failed for one or more periods")

        if direction == "LONG":
            if not (fast > med > slow):
                return FilterResult(passed=False, reason=f"LONG EMA order violated: fast={fast:.4f} med={med:.4f} slow={slow:.4f}")
        else:  # SHORT
            if not (fast < med < slow):
                return FilterResult(passed=False, reason=f"SHORT EMA order violated: fast={fast:.4f} med={med:.4f} slow={slow:.4f}")

        return FilterResult(passed=True)


class SessionFilter:
    """Time/session filter with timezone awareness and midnight-crossing support."""

    def __init__(
        self,
        enabled: bool = False,
        start_hour: int = 0,
        start_minute: int = 0,
        end_hour: int = 23,
        end_minute: int = 59,
        timezone_str: str = "UTC",
    ):
        self.enabled = enabled
        self.start_hour = start_hour
        self.start_minute = start_minute
        self.end_hour = end_hour
        self.end_minute = end_minute
        self.timezone_str = timezone_str

    def evaluate(
        self,
        candle_timestamp: str,
    ) -> FilterResult:
        """Evaluate session filter. Fails closed on invalid data."""
        if not self.enabled:
            return FilterResult(passed=True, reason="disabled")

        try:
            dt = datetime.fromisoformat(candle_timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return FilterResult(passed=False, reason=f"invalid timestamp: {candle_timestamp}")

        # Convert to target timezone (simplified: assume UTC offset)
        # For full timezone support, use pytz/zoneinfo
        hour = dt.hour
        minute = dt.minute
        current_minutes = hour * 60 + minute
        start_minutes = self.start_hour * 60 + self.start_minute
        end_minutes = self.end_hour * 60 + self.end_minute

        if start_minutes <= end_minutes:
            # Normal session (e.g., 9:00 - 17:00)
            in_session = start_minutes <= current_minutes <= end_minutes
        else:
            # Midnight-crossing session (e.g., 22:00 - 6:00)
            in_session = current_minutes >= start_minutes or current_minutes <= end_minutes

        if not in_session:
            return FilterResult(passed=False, reason=f"outside session: {hour:02d}:{minute:02d} not in {self.start_hour:02d}:{self.start_minute:02d}-{self.end_hour:02d}:{self.end_minute:02d}")

        return FilterResult(passed=True)


class FilterCascade:
    """Runs all configured filters and aggregates results."""

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.atr_filter = ATRFilter(
            enabled=cfg.get("atr_enabled", True),
            min_atr=cfg.get("atr_min", 0.0),
            max_atr=cfg.get("atr_max", 0.0),
            increase_threshold=cfg.get("atr_increase", 0.0),
            decrease_threshold=cfg.get("atr_decrease", 0.0),
            period=cfg.get("atr_period", 14),
        )
        self.angle_filter = EMAAngleFilter(
            enabled=cfg.get("angle_enabled", True),
            ema_period=cfg.get("angle_ema_period", 21),
            scale_factor=cfg.get("angle_scale", 10000.0),
            min_angle=cfg.get("min_angle", 0.0002),
            max_angle=cfg.get("max_angle", 0.0),
        )
        self.price_ema_filter = PriceEMAFilter(
            enabled=cfg.get("price_ema_enabled", True),
            ema_period=cfg.get("price_ema_period", 50),
        )
        self.candle_filter = CandleDirectionFilter(
            enabled=cfg.get("candle_enabled", True),
        )
        self.ema_order_filter = EMAOrderFilter(
            enabled=cfg.get("ema_order_enabled", True),
            fast_period=cfg.get("ema_fast", 12),
            medium_period=cfg.get("ema_medium", 26),
            slow_period=cfg.get("ema_slow", 50),
        )
        self.session_filter = SessionFilter(
            enabled=cfg.get("session_enabled", False),
            start_hour=cfg.get("session_start_hour", 0),
            start_minute=cfg.get("session_start_minute", 0),
            end_hour=cfg.get("session_end_hour", 23),
            end_minute=cfg.get("session_end_minute", 59),
            timezone_str=cfg.get("session_tz", "UTC"),
        )

    def evaluate(
        self,
        candles: List[Dict],
        direction: str = "LONG",
        candle_timestamp: Optional[str] = None,
    ) -> FilterCascadeResult:
        """Run all filters. Fails closed: any error = reject."""
        result = FilterCascadeResult(passed=True)

        close = [c["close"] for c in candles]
        high = [c["high"] for c in candles]
        low = [c["low"] for c in candles]

        # Filter 1: ATR
        result.add("ATR", self.atr_filter.evaluate(high, low, close, direction))

        # Filter 2: EMA Angle
        result.add("EMA_Angle", self.angle_filter.evaluate(close, direction))

        # Filter 3: Price vs EMA
        result.add("Price_EMA", self.price_ema_filter.evaluate(close, direction))

        # Filter 4: Candle Direction
        result.add("Candle", self.candle_filter.evaluate(candles, direction))

        # Filter 5: EMA Ordering
        result.add("EMA_Order", self.ema_order_filter.evaluate(close, direction))

        # Filter 6: Session
        ts = candle_timestamp or (candles[-1].get("timestamp", "") if candles else "")
        result.add("Session", self.session_filter.evaluate(ts))

        return result


def build_filter_config_from_settings(settings: Dict) -> Dict:
    """Build FilterCascade config dict from Config-like settings dict."""
    return {
        "atr_enabled": settings.get("M7_ATR_FILTER_ENABLED", True),
        "atr_min": settings.get("M7_ATR_MIN", 0.0),
        "atr_max": settings.get("M7_ATR_MAX", 0.0),
        "atr_increase": settings.get("M7_ATR_INCREASE_THRESHOLD", 0.0),
        "atr_decrease": settings.get("M7_ATR_DECREASE_THRESHOLD", 0.0),
        "atr_period": settings.get("M7_ATR_PERIOD", 14),
        "angle_enabled": settings.get("M7_ANGLE_FILTER_ENABLED", True),
        "angle_ema_period": settings.get("M7_ANGLE_EMA_PERIOD", 21),
        "angle_scale": settings.get("M7_ANGLE_SCALE_FACTOR", 10000.0),
        "min_angle": settings.get("M7_MIN_ANGLE", 0.0002),
        "max_angle": settings.get("M7_MAX_ANGLE", 0.0),
        "price_ema_enabled": settings.get("M7_PRICE_EMA_FILTER_ENABLED", True),
        "price_ema_period": settings.get("M7_PRICE_EMA_PERIOD", 50),
        "candle_enabled": settings.get("M7_CANDLE_FILTER_ENABLED", True),
        "ema_order_enabled": settings.get("M7_EMA_ORDER_FILTER_ENABLED", True),
        "ema_fast": settings.get("M7_EMA_FAST_PERIOD", 12),
        "ema_medium": settings.get("M7_EMA_MEDIUM_PERIOD", 26),
        "ema_slow": settings.get("M7_EMA_SLOW_PERIOD", 50),
        "session_enabled": settings.get("M7_SESSION_FILTER_ENABLED", False),
        "session_start_hour": settings.get("M7_SESSION_START_HOUR", 0),
        "session_start_minute": settings.get("M7_SESSION_START_MINUTE", 0),
        "session_end_hour": settings.get("M7_SESSION_END_HOUR", 23),
        "session_end_minute": settings.get("M7_SESSION_END_MINUTE", 59),
        "session_tz": settings.get("M7_SESSION_TIMEZONE", "UTC"),
    }
