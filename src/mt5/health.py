"""MT5 connection and demo health tracking — separate from market and AI health."""
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MT5State(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    AUTH_FAILED = "AUTH_FAILED"
    TERMINAL_ERROR = "TERMINAL_ERROR"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    NOT_DEMO = "NOT_DEMO"
    SYMBOL_UNAVAILABLE = "SYMBOL_UNAVAILABLE"
    TRADE_DISABLED = "TRADE_DISABLED"
    ERROR = "ERROR"


class MT5Health:
    """Tracks MT5 connection and demo verification health.

    All failure states reset trading authorization to prevent stale access.
    can_trade() returns True ONLY when ALL gates are positively true.
    """

    def __init__(self):
        self._state: MT5State = MT5State.DISCONNECTED
        self._last_error: str = ""
        self._terminal_info: dict = {}
        self._account_info: dict = {}
        self._connected: bool = False
        self._demo_verified: bool = False
        self._trade_enabled: bool = False

    @property
    def state(self) -> MT5State:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_demo_verified(self) -> bool:
        return self._demo_verified

    @property
    def is_trade_enabled(self) -> bool:
        return self._trade_enabled

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def terminal_info(self) -> dict:
        return self._terminal_info

    @property
    def account_info(self) -> dict:
        return self._account_info

    def _reset_trading_state(self) -> None:
        """Reset all authorization state. Called by every failure path."""
        self._connected = False
        self._demo_verified = False
        self._trade_enabled = False

    def record_connecting(self) -> None:
        self._state = MT5State.CONNECTING
        self._reset_trading_state()

    def record_connected(self, terminal_info: dict, account_info: dict) -> None:
        self._state = MT5State.CONNECTED
        self._connected = True
        self._terminal_info = terminal_info
        self._account_info = account_info
        self._last_error = ""

    def record_auth_failed(self, error: str = "") -> None:
        self._state = MT5State.AUTH_FAILED
        self._reset_trading_state()
        self._last_error = error

    def record_terminal_error(self, error: str = "") -> None:
        self._state = MT5State.TERMINAL_ERROR
        self._reset_trading_state()
        self._last_error = error

    def record_account_mismatch(self, error: str = "") -> None:
        self._state = MT5State.ACCOUNT_MISMATCH
        self._reset_trading_state()
        self._last_error = error

    def record_not_demo(self, error: str = "") -> None:
        self._state = MT5State.NOT_DEMO
        self._reset_trading_state()
        self._last_error = error

    def record_symbol_unavailable(self, symbol: str) -> None:
        self._state = MT5State.SYMBOL_UNAVAILABLE
        self._trade_enabled = False
        self._last_error = f"Symbol unavailable: {symbol}"

    def record_trade_disabled(self) -> None:
        self._state = MT5State.TRADE_DISABLED
        self._reset_trading_state()
        self._last_error = "Trading is disabled on this account"

    def record_error(self, error: str = "") -> None:
        self._state = MT5State.ERROR
        self._reset_trading_state()
        self._last_error = error

    def record_disconnected(self) -> None:
        self._state = MT5State.DISCONNECTED
        self._reset_trading_state()

    def set_demo_verified(self, verified: bool) -> None:
        self._demo_verified = verified

    def set_trade_enabled(self, enabled: bool) -> None:
        self._trade_enabled = enabled

    def can_trade(self) -> bool:
        """Check if MT5 demo trading is allowed by all safety gates.

        Returns True ONLY when ALL of the following are positively true:
        - connected
        - demo_verified
        - trade_enabled
        - state == CONNECTED
        """
        return (
            self._connected
            and self._demo_verified
            and self._trade_enabled
            and self._state == MT5State.CONNECTED
        )

    def get_summary(self) -> dict:
        return {
            "state": self._state.value,
            "connected": self._connected,
            "demo_verified": self._demo_verified,
            "trade_enabled": self._trade_enabled,
            "can_trade": self.can_trade(),
            "last_error": self._last_error[:200],
            "terminal": {
                "version": self._terminal_info.get("version", ""),
                "build": self._terminal_info.get("build", 0),
                "company": self._terminal_info.get("company", ""),
            },
            "account": {
                "login": self._account_info.get("login", 0),
                "server": self._account_info.get("server", ""),
                "name": self._account_info.get("name", ""),
                "currency": self._account_info.get("currency", ""),
                "balance": self._account_info.get("balance", 0.0),
                "equity": self._account_info.get("equity", 0.0),
                "trade_mode": self._account_info.get("trade_mode", -1),
            },
        }
