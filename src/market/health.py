"""Market data health tracking — separate from AI provider health."""
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MarketState(str, Enum):
    ONLINE = "ONLINE"
    STALE = "STALE"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_DATA = "INVALID_DATA"
    UNAVAILABLE = "UNAVAILABLE"


class MarketHealth:
    """Tracks market data freshness and availability per symbol."""

    def __init__(self, max_stale_seconds: int = 300):
        self.max_stale_seconds = max_stale_seconds
        self._symbol_state: dict[str, MarketState] = {}
        self._last_success_time: dict[str, float] = {}
        self._last_candle_ts: dict[str, str] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._last_error: dict[str, str] = {}

    def record_success(self, symbol: str, candle_timestamp: str) -> None:
        self._symbol_state[symbol] = MarketState.ONLINE
        self._last_success_time[symbol] = time.time()
        self._last_candle_ts[symbol] = candle_timestamp
        self._consecutive_failures[symbol] = 0

    def record_rate_limited(self, symbol: str) -> None:
        self._symbol_state[symbol] = MarketState.RATE_LIMITED

    def record_network_error(self, symbol: str, error: str = "") -> None:
        self._symbol_state[symbol] = MarketState.NETWORK_ERROR
        self._consecutive_failures[symbol] = self._consecutive_failures.get(symbol, 0) + 1
        self._last_error[symbol] = error

    def record_invalid_data(self, symbol: str, error: str = "") -> None:
        self._symbol_state[symbol] = MarketState.INVALID_DATA
        self._consecutive_failures[symbol] = self._consecutive_failures.get(symbol, 0) + 1
        self._last_error[symbol] = error

    def record_unavailable(self, symbol: str, error: str = "") -> None:
        self._symbol_state[symbol] = MarketState.UNAVAILABLE
        self._consecutive_failures[symbol] = self._consecutive_failures.get(symbol, 0) + 1
        self._last_error[symbol] = error

    def get_state(self, symbol: str) -> MarketState:
        state = self._symbol_state.get(symbol, MarketState.UNAVAILABLE)
        if state == MarketState.ONLINE and self._is_stale(symbol):
            self._symbol_state[symbol] = MarketState.STALE
            return MarketState.STALE
        return state

    def is_healthy(self, symbol: str) -> bool:
        return self.get_state(symbol) == MarketState.ONLINE

    def is_stale(self, symbol: str) -> bool:
        return self.get_state(symbol) == MarketState.STALE

    def _is_stale(self, symbol: str) -> bool:
        last = self._last_success_time.get(symbol, 0)
        if last == 0:
            return True
        return (time.time() - last) > self.max_stale_seconds

    def get_last_candle_timestamp(self, symbol: str) -> Optional[str]:
        return self._last_candle_ts.get(symbol)

    def get_consecutive_failures(self, symbol: str) -> int:
        return self._consecutive_failures.get(symbol, 0)

    def get_last_error(self, symbol: str) -> str:
        return self._last_error.get(symbol, "")

    def get_all_states(self) -> dict[str, str]:
        return {sym: self.get_state(sym).value for sym in self._symbol_state}

    def get_summary(self) -> dict:
        symbols = {}
        for sym in set(list(self._symbol_state.keys()) + list(self._last_candle_ts.keys())):
            symbols[sym] = {
                "state": self.get_state(sym).value,
                "last_candle": self._last_candle_ts.get(sym, ""),
                "consecutive_failures": self._consecutive_failures.get(sym, 0),
                "last_error": self._last_error.get(sym, "")[:100],
            }
        return {
            "max_stale_seconds": self.max_stale_seconds,
            "symbols": symbols,
        }
