"""Market data health monitoring — detects stale, degraded, or invalid data."""
import logging
import time
from enum import Enum
from typing import Dict, Optional

from src.core.enums import MarketHealthStatus

logger = logging.getLogger(__name__)


class MarketDataHealth:
    """Per-symbol and global market data health tracking."""

    def __init__(self, max_stale_seconds: int = 300):
        self.max_stale_seconds = max_stale_seconds
        self._symbol_state: Dict[str, dict] = {}
        self._overall_status = MarketHealthStatus.DISCONNECTED

    def record_success(self, symbol: str, timestamp: str) -> None:
        now = time.time()
        state = self._symbol_state.setdefault(symbol, {})
        state["last_success"] = now
        state["last_timestamp"] = timestamp
        state["consecutive_failures"] = 0
        state["status"] = MarketHealthStatus.CONNECTED
        self._update_overall()

    def record_unavailable(self, symbol: str, reason: str) -> None:
        state = self._symbol_state.setdefault(symbol, {})
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["last_error"] = reason
        if state["consecutive_failures"] >= 3:
            state["status"] = MarketHealthStatus.DISCONNECTED
        else:
            state["status"] = MarketHealthStatus.DEGRADED
        self._update_overall()

    def record_invalid_data(self, symbol: str, reason: str) -> None:
        state = self._symbol_state.setdefault(symbol, {})
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["last_error"] = reason
        state["status"] = MarketHealthStatus.INVALID
        self._update_overall()

    def record_stale(self, symbol: str) -> None:
        state = self._symbol_state.setdefault(symbol, {})
        state["status"] = MarketHealthStatus.STALE
        self._update_overall()

    def record_recovering(self, symbol: str) -> None:
        state = self._symbol_state.setdefault(symbol, {})
        state["status"] = MarketHealthStatus.RECOVERING
        self._update_overall()

    def is_stale(self, symbol: str) -> bool:
        state = self._symbol_state.get(symbol, {})
        last = state.get("last_success", 0)
        return (time.time() - last) > self.max_stale_seconds

    def get_symbol_status(self, symbol: str) -> MarketHealthStatus:
        return self._symbol_state.get(symbol, {}).get("status", MarketHealthStatus.DISCONNECTED)

    def get_overall_status(self) -> MarketHealthStatus:
        return self._overall_status

    def get_all_statuses(self) -> Dict[str, str]:
        return {s: st.get("status", MarketHealthStatus.DISCONNECTED).value
                for s, st in self._symbol_state.items()}

    def _update_overall(self) -> None:
        statuses = [st.get("status") for st in self._symbol_state.values()]
        if not statuses:
            self._overall_status = MarketHealthStatus.DISCONNECTED
        elif all(s == MarketHealthStatus.CONNECTED for s in statuses):
            self._overall_status = MarketHealthStatus.CONNECTED
        elif any(s == MarketHealthStatus.DISCONNECTED for s in statuses):
            self._overall_status = MarketHealthStatus.DEGRADED
        elif any(s == MarketHealthStatus.INVALID for s in statuses):
            self._overall_status = MarketHealthStatus.INVALID
        elif any(s == MarketHealthStatus.STALE for s in statuses):
            self._overall_status = MarketHealthStatus.STALE
        else:
            self._overall_status = MarketHealthStatus.CONNECTED

    def get_summary(self) -> Dict[str, str]:
        return {
            "overall": self._overall_status.value,
            "symbols": self.get_all_statuses(),
        }


# ── Legacy compatibility (used by test_milestone5.py) ──────────────────

class MarketState(str, Enum):
    ONLINE = "ONLINE"
    STALE = "STALE"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_DATA = "INVALID_DATA"
    UNAVAILABLE = "UNAVAILABLE"


class MarketHealth:
    """Legacy market health tracker — kept for backward compatibility."""

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

    def get_last_candle_timestamp(self, symbol: str) -> Optional[str]:
        return self._last_candle_ts.get(symbol)

    def is_stale(self, symbol: str) -> bool:
        last = self._last_success_time.get(symbol, 0)
        return (time.time() - last) > self.max_stale_seconds

    def is_healthy(self, symbol: str) -> bool:
        state = self.get_state(symbol)
        return state == MarketState.ONLINE and not self._is_stale(symbol)

    def get_consecutive_failures(self, symbol: str) -> int:
        return self._consecutive_failures.get(symbol, 0)

    def get_last_error(self, symbol: str) -> str:
        return self._last_error.get(symbol, "")

    def get_all_states(self) -> dict[str, MarketState]:
        return dict(self._symbol_state)

    def get_summary(self) -> dict:
        return {
            "max_stale_seconds": self.max_stale_seconds,
            "symbols": {
                s: {"state": state.value, "failures": self._consecutive_failures.get(s, 0)}
                for s, state in self._symbol_state.items()
            },
        }

    def _is_stale(self, symbol: str) -> bool:
        last = self._last_success_time.get(symbol, 0)
        if last == 0:
            return True
        return (time.time() - last) > self.max_stale_seconds
