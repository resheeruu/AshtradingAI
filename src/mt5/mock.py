"""MT5 mock/offline layer for testing without a real MT5 terminal.

Simulates MT5 API behavior for unit tests and offline development.
Never requires a real MetaTrader 5 installation.
"""
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class MockMT5ConnectionManager:
    """Mock connection manager for testing.

    Mirrors the real MT5ConnectionManager interface including all
    MT5 API wrapper methods (symbol_info, symbol_info_tick, etc.).
    """

    def __init__(
        self,
        enabled: bool = True,
        demo_only: bool = True,
        demo_trading_enabled: bool = False,
        account_trade_mode: int = 0,
        server: str = "MetaQuotes-Demo",
        login: int = 12345678,
        balance: float = 10000.0,
        fail_init: bool = False,
        fail_account: bool = False,
        expected_server: str = "",
        expected_login: int = 0,
        live_trading: bool = False,
        terminal_trade_allowed: bool = True,
        symbols: Optional[Dict[str, dict]] = None,
        ticks: Optional[Dict[str, dict]] = None,
        positions: Optional[List[dict]] = None,
        order_check_fail: bool = False,
        order_send_fail: bool = False,
    ):
        self.enabled = enabled
        self.demo_only = demo_only
        self.demo_trading_enabled = demo_trading_enabled
        self.account_trade_mode = account_trade_mode
        self.server = server
        self.login = login
        self.balance = balance
        self.fail_init = fail_init
        self.fail_account = fail_account
        self.expected_server = expected_server
        self.expected_login = expected_login
        self.live_trading = live_trading
        self.terminal_trade_allowed = terminal_trade_allowed
        self._connected = False
        self._demo_verified = False
        self._trade_enabled = False
        self._last_error = ""
        self.magic_number = 20260904

        # Symbol definitions for mock
        self._symbols = symbols or {
            "BTCUSD": {
                "name": "BTCUSD", "point": 0.01, "digits": 2,
                "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
                "trade_mode": 0, "visible": True, "filling_mode": 3,
            },
            "ETHUSD": {
                "name": "ETHUSD", "point": 0.01, "digits": 2,
                "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
                "trade_mode": 0, "visible": True, "filling_mode": 3,
            },
        }

        # Tick data for mock
        self._ticks = ticks or {
            "BTCUSD": {"bid": 50000.0, "ask": 50001.0, "last": 50000.5, "time": 1700000000},
            "ETHUSD": {"bid": 3000.0, "ask": 3001.0, "last": 3000.5, "time": 1700000000},
        }

        # Positions for mock
        self._positions = positions or []

        # Order simulation
        self.order_check_fail = order_check_fail
        self.order_send_fail = order_send_fail
        self._order_counter = 100000
        self._deal_counter = 200000

        # Health state (mirrors real MT5Health interface)
        from src.mt5.health import MT5Health
        self.health = MT5Health()

    def connect(self) -> bool:
        if not self.enabled:
            return False

        # Gate: LIVE_TRADING
        if self.live_trading:
            self.health.record_error("LIVE_TRADING=true — MT5 demo adapter disabled")
            return False

        self.health.record_connecting()

        if self.fail_init:
            self.health.record_terminal_error("Mock init failure")
            return False

        if self.fail_account:
            self.health.record_terminal_error("Mock account failure")
            return False

        # Demo verification — only trade_mode == 0 accepted
        if self.demo_only and self.account_trade_mode != 0:
            self.health.record_not_demo(f"Not demo (trade_mode={self.account_trade_mode})")
            return False

        # Server mismatch
        if self.expected_server and self.server != self.expected_server:
            self.health.record_account_mismatch(
                f"Server mismatch: expected={self.expected_server}, actual={self.server}"
            )
            return False

        # Login mismatch
        if self.expected_login and self.login != self.expected_login:
            self.health.record_account_mismatch(
                f"Login mismatch: expected={self.expected_login}, actual={self.login}"
            )
            return False

        # Terminal trade permission
        if not self.terminal_trade_allowed:
            self.health.record_trade_disabled()
            return False

        terminal_info = {
            "version": "5.0.0",
            "build": 3000,
            "company": "MetaQuotes",
            "connected": True,
            "trade_allowed": self.terminal_trade_allowed,
        }
        account_info = {
            "login": self.login,
            "server": self.server,
            "name": "Test User",
            "currency": "USD",
            "balance": self.balance,
            "equity": self.balance,
            "margin": 0.0,
            "free_margin": self.balance,
            "leverage": 100,
            "trade_mode": self.account_trade_mode,
        }

        self.health.record_connected(terminal_info, account_info)
        self.health.set_demo_verified(True)
        self.health.set_trade_enabled(self.demo_trading_enabled)
        self._connected = True
        self._demo_verified = True
        self._trade_enabled = self.demo_trading_enabled
        return True

    def reconnect(self) -> bool:
        self.shutdown()
        return self.connect()

    def shutdown(self) -> None:
        self._connected = False
        self._demo_verified = False
        self._trade_enabled = False
        self.health.record_disconnected()

    def get_account_info(self) -> Optional[dict]:
        if not self._connected:
            return None
        return {
            "login": self.login,
            "server": self.server,
            "name": "Test User",
            "currency": "USD",
            "balance": self.balance,
            "equity": self.balance,
            "margin": 0.0,
            "free_margin": self.balance,
            "leverage": 100,
            "trade_mode": self.account_trade_mode,
        }

    def get_terminal_info(self) -> Optional[dict]:
        if not self._connected:
            return None
        return {
            "version": "5.0.0",
            "build": 3000,
            "company": "MetaQuotes",
            "connected": True,
            "trade_allowed": self.terminal_trade_allowed,
        }

    def is_connected(self) -> bool:
        return self._connected

    def can_trade(self) -> bool:
        return self.health.can_trade()

    # ── MT5 API Wrappers (mock) ───────────────────────────────────────

    def symbol_info(self, symbol: str) -> Optional[dict]:
        if not self._connected:
            return None
        return self._symbols.get(symbol)

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        if symbol in self._symbols:
            self._symbols[symbol]["visible"] = enable
            return True
        return False

    def symbol_info_tick(self, symbol: str) -> Optional[dict]:
        if not self._connected:
            return None
        return self._ticks.get(symbol)

    def order_check(self, request: dict) -> Optional[dict]:
        if self.order_check_fail:
            return {"retcode": 10013, "comment": "Mock order_check failure"}
        return {"retcode": 10009, "comment": ""}

    def order_send(self, request: dict) -> Optional[dict]:
        if self.order_send_fail:
            return {"retcode": 10013, "deal": 0, "order": 0, "volume": 0, "price": 0, "comment": "Mock order_send failure"}
        self._order_counter += 1
        self._deal_counter += 1
        return {
            "retcode": 10009,
            "deal": self._deal_counter,
            "order": self._order_counter,
            "volume": request.get("volume", 0),
            "price": request.get("price", 0),
            "comment": "",
        }

    def positions_get(self, symbol: Optional[str] = None) -> List[dict]:
        if not self._connected:
            return []
        if symbol:
            return [p for p in self._positions if p["symbol"] == symbol]
        return list(self._positions)

    def order_calc_margin(
        self, order_type: int, symbol: str, volume: float, price: float
    ) -> Optional[float]:
        return volume * price * 0.01  # 1% margin


class MockMT5MarketData:
    """Mock market data for testing."""

    def __init__(self, connection_manager, candles: Optional[Dict[str, List[Dict]]] = None):
        self.connection = connection_manager
        self.candles = candles or {}
        self.symbol_map = {}

    def map_symbol(self, ash_symbol: str) -> str:
        return self.symbol_map.get(ash_symbol, ash_symbol)

    def fetch_candles(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> List[Dict]:
        if not self.connection.is_connected():
            return []
        return self.candles.get(symbol, [])[-limit:]

    def get_last_price(self, symbol: str) -> float:
        if not self.connection.is_connected():
            return 0.0
        candles = self.candles.get(symbol, [])
        if candles:
            return candles[-1]["close"]
        return 0.0

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        if not self.connection.is_connected():
            return None
        return self.connection.symbol_info(symbol)


class MockMT5DemoBroker:
    """Mock demo broker for testing.

    Mirrors the real MT5DemoBroker interface including duplicate protection,
    LIVE_TRADING gate, and persistence.
    """

    def __init__(self, connection_manager, symbol_map: Optional[dict] = None,
                 database=None, session_id: str = ""):
        self.connection = connection_manager
        self.symbol_map = symbol_map or {}
        self._order_book: dict[str, dict] = {}
        self._orders_sent: List[dict] = []
        self.magic_number = 20260904
        self._sent_signals: set = set()
        self._db = database
        self._session_id = session_id
        if self._db and self._session_id:
            self._load_persisted_signals()

    def _load_persisted_signals(self) -> None:
        try:
            signals = self._db.get_mt5_signals_by_session(self._session_id)
            for s in signals:
                self._sent_signals.add(s["signal_key"])
        except Exception:
            pass

    def _map_symbol(self, ash_symbol: str) -> str:
        return self.symbol_map.get(ash_symbol, ash_symbol)

    def _signal_key(self, symbol: str, side: str, candle_timestamp: str) -> str:
        return f"{symbol}:{side}:{candle_timestamp}"

    def execute_buy(
        self, portfolio, symbol, price, quantity,
        stop_loss=None, take_profit=None, timestamp=None,
        candle_timestamp=None,
    ) -> Optional[dict]:
        from src.portfolio.portfolio import Portfolio

        # LIVE_TRADING gate
        if getattr(self.connection, "live_trading", False):
            return None

        if not self.connection.can_trade():
            return None

        mt5_symbol = self._map_symbol(symbol)
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        ct = candle_timestamp or ts

        # Duplicate protection
        sig_key = self._signal_key(symbol, "buy", ct)
        if sig_key in self._sent_signals:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "mt5_symbol": mt5_symbol,
            "side": "buy",
            "price": price,
            "quantity": quantity,
            "fee": 0.0,
            "slippage": 0.0,
            "pnl": None,
            "timestamp": ts,
            "status": "filled",
            "mt5_deal": 12345,
            "mt5_order": 67890,
            "mt5_retcode": 0,
            "magic": self.magic_number,
        }
        self._order_book[order_id] = order
        self._orders_sent.append(order)
        self._sent_signals.add(sig_key)
        if self._db and self._session_id:
            try:
                self._db.log_mt5_signal(
                    session_id=self._session_id, signal_key=sig_key,
                    symbol=symbol, side="buy",
                    candle_timestamp=ct, order_id=order_id,
                )
                self._db.log_mt5_order(
                    session_id=self._session_id, symbol=symbol,
                    mt5_symbol=mt5_symbol, side="buy", volume=quantity,
                    price=price, mt5_ticket=67890, mt5_deal=12345,
                    mt5_retcode=0, magic=self.magic_number,
                    status="filled", candle_timestamp=ct,
                )
            except Exception:
                pass
        return order

    def execute_sell(
        self, portfolio, symbol, price, timestamp=None,
        candle_timestamp=None,
    ) -> Optional[dict]:
        pos = portfolio.get_position(symbol)
        if pos is None:
            return None

        # LIVE_TRADING gate
        if getattr(self.connection, "live_trading", False):
            return None

        if not self.connection.can_trade():
            return None

        mt5_symbol = self._map_symbol(symbol)
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        ct = candle_timestamp or ts

        # Duplicate protection
        sig_key = self._signal_key(symbol, "sell", ct)
        if sig_key in self._sent_signals:
            return None

        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "mt5_symbol": mt5_symbol,
            "side": "sell",
            "price": price,
            "quantity": pos.quantity,
            "fee": 0.0,
            "slippage": 0.0,
            "pnl": None,
            "timestamp": ts,
            "status": "filled",
            "mt5_deal": 12346,
            "mt5_order": 67891,
            "mt5_retcode": 0,
            "magic": self.magic_number,
        }
        self._order_book[order_id] = order
        self._orders_sent.append(order)
        self._sent_signals.add(sig_key)
        if self._db and self._session_id:
            try:
                self._db.log_mt5_signal(
                    session_id=self._session_id, signal_key=sig_key,
                    symbol=symbol, side="sell",
                    candle_timestamp=ct, order_id=order_id,
                )
                self._db.log_mt5_order(
                    session_id=self._session_id, symbol=symbol,
                    mt5_symbol=mt5_symbol, side="sell",
                    volume=pos.quantity, price=price,
                    mt5_ticket=67891, mt5_deal=12346,
                    mt5_retcode=0, magic=self.magic_number,
                    status="filled", candle_timestamp=ct,
                )
            except Exception:
                pass
        return order

    def get_order(self, order_id: str) -> Optional[dict]:
        return self._order_book.get(order_id)

    def reconcile(self) -> List[dict]:
        if not self._db or not self._session_id:
            return []

        results = []
        try:
            pending = self._db.get_pending_mt5_orders(self._session_id)
            for order_row in pending:
                mt5_ticket = order_row.get("mt5_ticket", 0)
                if not mt5_ticket:
                    self._db.update_mt5_order(order_row["id"], status="unknown")
                    results.append({"order_id": order_row["id"], "status": "unknown"})
                    continue

                positions = self.connection.positions_get(
                    symbol=order_row.get("mt5_symbol", "")
                )
                found = any(p["ticket"] == mt5_ticket for p in positions)

                if found:
                    self._db.update_mt5_order(order_row["id"], status="filled")
                    results.append({"order_id": order_row["id"], "status": "filled"})
                else:
                    self._db.update_mt5_order(order_row["id"], status="closed_external")
                    results.append({"order_id": order_row["id"], "status": "closed_external"})

        except Exception:
            pass

        return results
