"""Completed-candle scheduler — ensures trades only happen on completed candles."""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def timeframe_to_seconds(timeframe: str) -> int:
    return TIMEFRAME_SECONDS.get(timeframe, 3600)


def parse_candle_timestamp(ts: str) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def is_candle_completed(candle_ts: str, timeframe: str) -> bool:
    ts_epoch = parse_candle_timestamp(candle_ts)
    if ts_epoch is None:
        return False
    now = time.time()
    tf_seconds = timeframe_to_seconds(timeframe)
    return now >= ts_epoch + tf_seconds


class CandleScheduler:
    def __init__(self, timeframe: str):
        self.timeframe = timeframe
        self.tf_seconds = timeframe_to_seconds(timeframe)
        self._last_processed_ts: Optional[str] = None
        self._processed_set: set[str] = set()

    def set_last_processed(self, ts: str) -> None:
        self._last_processed_ts = ts
        self._processed_set.add(ts)

    @property
    def last_processed_candle(self) -> Optional[str]:
        return self._last_processed_ts

    def has_processed(self, candle_ts: str) -> bool:
        return candle_ts in self._processed_set

    def should_process(self, candle_ts: str) -> bool:
        if self.has_processed(candle_ts):
            return False
        if not is_candle_completed(candle_ts, self.timeframe):
            return False
        return True

    def mark_processed(self, candle_ts: str) -> None:
        self._last_processed_ts = candle_ts
        self._processed_set.add(candle_ts)

    def get_next_candle_time(self, last_candle_ts: Optional[str] = None) -> Optional[float]:
        ts = last_candle_ts or self._last_processed_ts
        if ts is None:
            return None
        epoch = parse_candle_timestamp(ts)
        if epoch is None:
            return None
        return epoch + self.tf_seconds

    def seconds_until_next_candle(self, last_candle_ts: Optional[str] = None) -> float:
        next_time = self.get_next_candle_time(last_candle_ts)
        if next_time is None:
            return 0.0
        remaining = next_time - time.time()
        return max(0.0, remaining)
