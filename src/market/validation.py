"""OHLCV candle validation — rejects malformed data before it reaches strategies."""
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def validate_candle(candle: Dict, index: int = 0) -> Optional[str]:
    """Validate a single candle dict. Returns error string or None if valid."""
    required_keys = ("timestamp", "open", "high", "low", "close", "volume")
    for key in required_keys:
        if key not in candle:
            return f"missing key '{key}'"

    for field in ("open", "high", "low", "close", "volume"):
        val = candle[field]
        if not isinstance(val, (int, float)):
            return f"'{field}' is not numeric (got {type(val).__name__})"
        if val != val:  # NaN check
            return f"'{field}' is NaN"
        if field != "volume" and val <= 0:
            return f"'{field}' must be positive (got {val})"
        if field == "volume" and val < 0:
            return f"'volume' must be non-negative (got {val})"

    ts = candle["timestamp"]
    if not isinstance(ts, str) or not ts:
        return "timestamp is not a non-empty string"

    high = candle["high"]
    low = candle["low"]
    open_ = candle["open"]
    close = candle["close"]

    if low > high:
        return f"low ({low}) > high ({high})"
    if open_ < low or open_ > high:
        return f"open ({open_}) outside low-high range [{low}, {high}]"
    if close < low or close > high:
        return f"close ({close}) outside low-high range [{low}, {high}]"

    return None


def validate_candles(candles: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """Validate a list of candles. Returns (valid_candles, error_messages).

    - Rejects candles with missing/impossible fields.
    - Removes duplicate timestamps (keeps first occurrence).
    - Rejects out-of-order timestamps.
    """
    if not candles:
        return [], ["empty candle list"]

    valid: List[Dict] = []
    errors: List[str] = []
    seen_timestamps: set = set()
    prev_ts: Optional[str] = None

    for i, candle in enumerate(candles):
        err = validate_candle(candle, index=i)
        if err:
            errors.append(f"candle[{i}]: {err}")
            continue

        ts = candle["timestamp"]
        if ts in seen_timestamps:
            errors.append(f"candle[{i}]: duplicate timestamp '{ts}'")
            continue
        seen_timestamps.add(ts)

        if prev_ts is not None and ts < prev_ts:
            errors.append(f"candle[{i}]: timestamp '{ts}' out of order (previous='{prev_ts}')")
            continue

        prev_ts = ts
        valid.append(candle)

    if errors:
        logger.warning("Validation: %d invalid candles out of %d", len(errors), len(candles))

    return valid, errors
