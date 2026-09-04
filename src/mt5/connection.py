"""MT5 connection manager — handles initialize, verify, reconnect, shutdown.

All MetaTrader5 API calls are encapsulated here. The rest of AshtradingAI
never imports MetaTrader5 directly.

Safety gates enforced:
1. LIVE_TRADING must be false
2. MT5_ENABLED must be true
3. Terminal must initialize
4. Account must be positively verified as demo (trade_mode == 0)
5. Server/login must match expected (if configured)
6. Demo trading must be explicitly enabled
"""
import logging
import time
from typing import Optional, Dict, Any, List, Tuple

from src.mt5.health import MT5Health, MT5State

logger = logging.getLogger(__name__)

# Lazy import: only load MetaTrader5 when actually needed
_mt5 = None


def _get_mt5():
    """Lazy-import MetaTrader5 to avoid import errors on non-MT5 systems."""
    global _mt5
    if _mt5 is None:
        try:
            import MetaTrader5 as mt5
            _mt5 = mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 package not installed. "
                "Install with: pip install MetaTrader5. "
                "Note: MT5 Python package requires Windows and MetaTrader 5 Desktop terminal."
            )
    return _mt5


class MT5ConnectionManager:
    """Manages MT5 terminal connection, verification, and lifecycle.

    All direct MetaTrader5 API calls go through this class.
    The broker and market data adapters use these methods instead
    of importing MetaTrader5 directly.
    """

    def __init__(
        self,
        enabled: bool = False,
        demo_only: bool = True,
        demo_trading_enabled: bool = False,
        path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        timeout: int = 10000,
        expected_server: str = "",
        expected_login: int = 0,
        magic_number: int = 20260904,
        live_trading: bool = False,
    ):
        self.enabled = enabled
        self.demo_only = demo_only
        self.demo_trading_enabled = demo_trading_enabled
        self.path = path
        self.login = login
        self.password = password
        self.server = server
        self.timeout = timeout
        self.expected_server = expected_server
        self.expected_login = expected_login
        self.magic_number = magic_number
        self.live_trading = live_trading
        self.health = MT5Health()
        self._initialized = False

    def connect(self) -> bool:
        """Initialize MT5 terminal and verify account configuration.

        Returns True only if ALL safety checks pass.
        """
        # Gate 0: LIVE_TRADING must be false
        if self.live_trading:
            logger.critical(
                "MT5 SAFETY: LIVE_TRADING=true. MT5 demo adapter refuses to operate."
            )
            self.health.record_error("LIVE_TRADING=true — MT5 demo adapter disabled")
            return False

        # Gate 1: MT5_ENABLED must be true
        if not self.enabled:
            logger.info("MT5 is disabled (MT5_ENABLED=false)")
            return False

        self.health.record_connecting()

        mt5 = _get_mt5()

        # Initialize terminal connection
        init_kwargs: Dict[str, Any] = {"timeout": self.timeout}
        if self.path:
            init_kwargs["path"] = self.path
        if self.login:
            init_kwargs["login"] = self.login
        if self.password:
            init_kwargs["password"] = self.password
        if self.server:
            init_kwargs["server"] = self.server

        if not mt5.initialize(**init_kwargs):
            error = mt5.last_error()
            self.health.record_terminal_error(str(error))
            logger.error("MT5 initialize failed: %s", error)
            return False

        self._initialized = True

        # Verify terminal info
        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            self.health.record_terminal_error("Cannot retrieve terminal info")
            self.shutdown()
            return False

        # Verify account info
        account_info = mt5.account_info()
        if account_info is None:
            self.health.record_terminal_error("Cannot retrieve account info")
            self.shutdown()
            return False

        account_dict = _account_info_to_dict(account_info)
        terminal_dict = _terminal_info_to_dict(terminal_info)

        # Gate 2: Demo verification (mandatory when demo_only is true)
        # trade_mode: 0=demo, 1=real, 2=contest
        # Only trade_mode == 0 is accepted. None/missing/unknown = rejected.
        if self.demo_only:
            trade_mode = getattr(account_info, "trade_mode", None)
            if trade_mode != 0:
                self.health.record_not_demo(
                    f"Account is not demo (trade_mode={trade_mode}). "
                    "Set MT5_DEMO_ONLY=false only if you understand the risk."
                )
                logger.critical(
                    "MT5 SAFETY: Refusing non-demo account (trade_mode=%s)", trade_mode
                )
                self.shutdown()
                return False

        # Gate 3: Server mismatch check
        if self.expected_server:
            actual_server = getattr(account_info, "server", "")
            if actual_server != self.expected_server:
                self.health.record_account_mismatch(
                    f"Server mismatch: expected={self.expected_server}, actual={actual_server}"
                )
                logger.error(
                    "MT5 server mismatch: expected=%s, actual=%s",
                    self.expected_server, actual_server,
                )
                self.shutdown()
                return False

        # Gate 4: Login mismatch check
        if self.expected_login:
            actual_login = getattr(account_info, "login", 0)
            if actual_login != self.expected_login:
                self.health.record_account_mismatch(
                    f"Login mismatch: expected={self.expected_login}, actual={actual_login}"
                )
                logger.error(
                    "MT5 login mismatch: expected=%d, actual=%d",
                    self.expected_login, actual_login,
                )
                self.shutdown()
                return False

        # Gate 5: Terminal trade permission
        trade_allowed = getattr(terminal_info, "trade_allowed", False)
        if not trade_allowed:
            self.health.record_trade_disabled()
            logger.warning("MT5 terminal trade permission denied")
            self.shutdown()
            return False

        # Connection successful
        self.health.record_connected(terminal_dict, account_dict)
        self.health.set_demo_verified(True)
        self.health.set_trade_enabled(self.demo_trading_enabled)

        logger.info(
            "MT5 connected: login=%s server=%s demo=%s trade_enabled=%s",
            account_dict.get("login", "?"),
            account_dict.get("server", "?"),
            self.health.is_demo_verified,
            self.health.is_trade_enabled,
        )
        return True

    def reconnect(self) -> bool:
        """Attempt to reconnect after a disconnect.

        All previous authorization is invalidated until new connection
        is positively verified.
        """
        logger.info("MT5 reconnecting...")
        self.shutdown()
        time.sleep(1)
        return self.connect()

    def shutdown(self) -> None:
        """Cleanly shut down MT5 terminal connection."""
        if self._initialized:
            try:
                mt5 = _get_mt5()
                mt5.shutdown()
            except Exception as e:
                logger.debug("MT5 shutdown error: %s", e)
            self._initialized = False
        self.health.record_disconnected()

    def get_account_info(self) -> Optional[dict]:
        """Retrieve current account information."""
        if not self.health.is_connected:
            return None
        try:
            mt5 = _get_mt5()
            info = mt5.account_info()
            return _account_info_to_dict(info) if info else None
        except Exception as e:
            logger.error("Failed to get account info: %s", e)
            return None

    def get_terminal_info(self) -> Optional[dict]:
        """Retrieve current terminal information."""
        if not self.health.is_connected:
            return None
        try:
            mt5 = _get_mt5()
            info = mt5.terminal_info()
            return _terminal_info_to_dict(info) if info else None
        except Exception as e:
            logger.error("Failed to get terminal info: %s", e)
            return None

    def is_connected(self) -> bool:
        return self.health.is_connected

    def can_trade(self) -> bool:
        return self.health.can_trade()

    # ── MT5 API Wrappers ──────────────────────────────────────────────
    # All direct MetaTrader5 API calls go through these methods.
    # The broker and market data adapters MUST use these wrappers.

    def symbol_info(self, symbol: str) -> Optional[dict]:
        """Get symbol information. Returns None if unavailable."""
        if not self.health.is_connected:
            return None
        try:
            mt5 = _get_mt5()
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                "name": getattr(info, "name", ""),
                "point": getattr(info, "point", 0.0),
                "digits": getattr(info, "digits", 0),
                "volume_min": getattr(info, "volume_min", 0.0),
                "volume_max": getattr(info, "volume_max", 0.0),
                "volume_step": getattr(info, "volume_step", 0.0),
                "trade_mode": getattr(info, "trade_mode", -1),
                "visible": getattr(info, "visible", False),
                "filling_mode": getattr(info, "filling_mode", 0),
            }
        except Exception as e:
            logger.error("symbol_info failed for %s: %s", symbol, e)
            return None

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        """Select/deselect a symbol in the Market Watch."""
        try:
            mt5 = _get_mt5()
            return mt5.symbol_select(symbol, enable)
        except Exception as e:
            logger.error("symbol_select failed for %s: %s", symbol, e)
            return False

    def symbol_info_tick(self, symbol: str) -> Optional[dict]:
        """Get current tick. Returns None if unavailable or stale."""
        if not self.health.is_connected:
            return None
        try:
            mt5 = _get_mt5()
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            return {
                "bid": float(getattr(tick, "bid", 0)),
                "ask": float(getattr(tick, "ask", 0)),
                "last": float(getattr(tick, "last", 0)),
                "time": getattr(tick, "time", 0),
                "flags": getattr(tick, "flags", 0),
                "volume": float(getattr(tick, "volume", 0)),
                "volume_real": float(getattr(tick, "volume_real", 0)),
            }
        except Exception as e:
            logger.error("symbol_info_tick failed for %s: %s", symbol, e)
            return None

    def order_check(self, request: dict) -> Optional[dict]:
        """Validate an order request without sending it."""
        try:
            mt5 = _get_mt5()
            result = mt5.order_check(request)
            if result is None:
                return None
            return {
                "retcode": result.retcode,
                "comment": getattr(result, "comment", ""),
                "request_id": getattr(result, "request_id", 0),
                "request": getattr(result, "request", {}),
            }
        except Exception as e:
            logger.error("order_check failed: %s", e)
            return None

    def order_send(self, request: dict) -> Optional[dict]:
        """Send an order to MT5. Only call after order_check passes."""
        try:
            mt5 = _get_mt5()
            result = mt5.order_send(request)
            if result is None:
                return None
            return {
                "retcode": result.retcode,
                "deal": getattr(result, "deal", 0),
                "order": getattr(result, "order", 0),
                "volume": float(getattr(result, "volume", 0)),
                "price": float(getattr(result, "price", 0)),
                "comment": getattr(result, "comment", ""),
                "request_id": getattr(result, "request_id", 0),
            }
        except Exception as e:
            logger.error("order_send failed: %s", e)
            return None

    def positions_get(self, symbol: Optional[str] = None) -> List[dict]:
        """Get open positions, optionally filtered by symbol."""
        if not self.health.is_connected:
            return []
        try:
            mt5 = _get_mt5()
            kwargs = {}
            if symbol:
                kwargs["symbol"] = symbol
            positions = mt5.positions_get(**kwargs)
            if positions is None:
                return []
            result = []
            for pos in positions:
                result.append({
                    "ticket": pos.ticket,
                    "symbol": getattr(pos, "symbol", ""),
                    "type": getattr(pos, "type", -1),
                    "volume": float(getattr(pos, "volume", 0)),
                    "price_open": float(getattr(pos, "price_open", 0)),
                    "price_current": float(getattr(pos, "price_current", 0)),
                    "sl": float(getattr(pos, "sl", 0)),
                    "tp": float(getattr(pos, "tp", 0)),
                    "profit": float(getattr(pos, "profit", 0)),
                    "magic": getattr(pos, "magic", 0),
                    "comment": getattr(pos, "comment", ""),
                    "time": getattr(pos, "time", 0),
                })
            return result
        except Exception as e:
            logger.error("positions_get failed: %s", e)
            return []

    def order_calc_margin(
        self, order_type: int, symbol: str, volume: float, price: float
    ) -> Optional[float]:
        """Calculate margin required for an order."""
        try:
            mt5 = _get_mt5()
            margin = mt5.order_calc_margin(order_type, symbol, volume, price)
            return float(margin) if margin is not None else None
        except Exception as e:
            logger.error("order_calc_margin failed: %s", e)
            return None


def _account_info_to_dict(info) -> dict:
    """Convert MT5 AccountInfo to a plain dict (no secrets)."""
    return {
        "login": getattr(info, "login", 0),
        "server": getattr(info, "server", ""),
        "name": getattr(info, "name", ""),
        "currency": getattr(info, "currency", ""),
        "balance": getattr(info, "balance", 0.0),
        "equity": getattr(info, "equity", 0.0),
        "margin": getattr(info, "margin", 0.0),
        "free_margin": getattr(info, "margin_free", 0.0),
        "leverage": getattr(info, "leverage", 0),
        "trade_mode": getattr(info, "trade_mode", -1),
        "limit_orders": getattr(info, "limit_orders", 0),
    }


def _terminal_info_to_dict(info) -> dict:
    """Convert MT5 TerminalInfo to a plain dict."""
    return {
        "version": getattr(info, "version", ""),
        "build": getattr(info, "build", 0),
        "company": getattr(info, "company", ""),
        "connected": getattr(info, "connected", False),
        "trade_allowed": getattr(info, "trade_allowed", False),
    }
