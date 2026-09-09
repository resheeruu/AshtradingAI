"""MT5 read-only API adapter — wraps MT5ConnectionManager for the API layer.

M15: Remote MT5 Demo Bridge
- Read-only access to MT5 demo account data
- Heartbeat with timestamps and connection age
- Observability logging (MT5_CONNECT, MT5_DISCONNECT, etc.)
- No order execution, no trading, no modification

Safety: This adapter READS from MT5 only. It never sends orders.
The existing MT5ConnectionManager safety gates are the authority.
"""
import logging
import time
from typing import Optional, List

from src.config import Config

logger = logging.getLogger(__name__)

# ── Module State ───────────────────────────────────────────────────

_connection_manager = None
_mock_manager = None
_is_real_mt5 = False

# Heartbeat tracking
_last_heartbeat_time: float = 0.0
_last_connected_time: float = 0.0
_last_disconnect_time: float = 0.0
_heartbeat_count: int = 0
_reconnect_count: int = 0


# ── Connection Management ──────────────────────────────────────────

def _get_connection_manager():
    """Get or create the MT5 connection manager (lazy singleton).

    On non-Windows systems (e.g., Android/Termux), MetaTrader5 package
    is unavailable. Falls back to MockMT5ConnectionManager for graceful
    degradation.
    """
    global _connection_manager, _is_real_mt5

    if _connection_manager is not None:
        return _connection_manager

    from src.mt5.connection import MT5ConnectionManager

    _connection_manager = MT5ConnectionManager(
        enabled=Config.MT5_ENABLED,
        demo_only=Config.MT5_DEMO_ONLY,
        demo_trading_enabled=Config.MT5_DEMO_TRADING_ENABLED,
        path=Config.MT5_PATH or None,
        login=Config.MT5_LOGIN or None,
        password=Config.MT5_PASSWORD or None,
        server=Config.MT5_SERVER or None,
        timeout=Config.MT5_TIMEOUT,
        expected_server=Config.MT5_EXPECTED_SERVER,
        expected_login=Config.MT5_EXPECTED_LOGIN,
        magic_number=Config.MT5_MAGIC_NUMBER,
        live_trading=Config.LIVE_TRADING,
    )
    _is_real_mt5 = True

    return _connection_manager


def _ensure_connection() -> bool:
    """Ensure MT5 is connected. Returns True if connected."""
    global _last_connected_time, _last_disconnect_time, _reconnect_count

    mgr = _get_connection_manager()
    if mgr.health.is_connected:
        return True
    try:
        result = mgr.connect()
        if result:
            _last_connected_time = time.time()
            _reconnect_count += 1
            logger.info("MT5_CONNECT: Connected to MT5 terminal (reconnect #%d)", _reconnect_count)
        else:
            _last_disconnect_time = time.time()
            logger.debug("MT5_CONNECT: Connection attempt failed")
        return result
    except ImportError:
        logger.debug("MT5_CONNECT: MetaTrader5 package unavailable — using mock")
        return False
    except Exception as e:
        _last_disconnect_time = time.time()
        logger.error("MT5_CONNECT: Connection error: %s", e)
        return False


def _get_mock_manager():
    """Get mock manager for when MT5 is unavailable."""
    global _mock_manager
    if _mock_manager is None:
        from src.mt5.mock import MockMT5ConnectionManager
        _mock_manager = MockMT5ConnectionManager(
            enabled=Config.MT5_ENABLED,
            demo_only=Config.MT5_DEMO_ONLY,
            demo_trading_enabled=False,
            live_trading=Config.LIVE_TRADING,
        )
        _mock_manager.connect()
    return _mock_manager


def _safe_get_manager():
    """Get the appropriate manager — real if available, mock otherwise.

    Returns (manager, is_real).
    """
    global _is_real_mt5
    try:
        mgr = _get_connection_manager()
        connected = _ensure_connection()
        if connected:
            return mgr, _is_real_mt5
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Real MT5 unavailable: %s", e)

    return _get_mock_manager(), False


# ── Read-Only API Methods ──────────────────────────────────────────

def get_status() -> dict:
    """Get MT5 connection and configuration status."""
    mgr, is_real = _safe_get_manager()
    health = mgr.health
    now = time.time()

    connection_age = None
    if _last_connected_time > 0:
        connection_age = int(now - _last_connected_time)

    return {
        "enabled": Config.MT5_ENABLED,
        "demo_only": Config.MT5_DEMO_ONLY,
        "demo_trading_enabled": Config.MT5_DEMO_TRADING_ENABLED,
        "connection": "CONNECTED" if health.is_connected else "DISCONNECTED",
        "state": health.state.value,
        "demo_verified": health.is_demo_verified,
        "can_trade": health.can_trade(),
        "is_real_mt5": is_real,
        "last_error": health.last_error or None,
        "magic_number": Config.MT5_MAGIC_NUMBER,
        "server": Config.MT5_SERVER,
        "platform": "MetaTrader 5 DEMO" if health.is_connected else "NOT AVAILABLE",
        "terminal_available": is_real and health.is_connected,
        "last_update": int(now) if health.is_connected else None,
        "connection_age_seconds": connection_age,
        "reconnect_count": _reconnect_count,
    }


def get_account() -> dict:
    """Get MT5 demo account information (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return {
            "connected": False,
            "account": None,
            "environment": "MT5 DEMO",
            "note": "MT5 not connected. Account information unavailable.",
            "last_heartbeat": _last_heartbeat_time if _last_heartbeat_time > 0 else None,
        }

    info = mgr.get_account_info()
    if info is None:
        return {
            "connected": True,
            "account": None,
            "environment": "MT5 DEMO",
            "note": "Connected but account info unavailable.",
        }

    logger.debug("MT5_ACCOUNT_REFRESH: login=%s balance=%.2f", info.get("login", "?"), info.get("balance", 0.0))

    return {
        "connected": True,
        "account": {
            "login": info.get("login", 0),
            "server": info.get("server", ""),
            "name": info.get("name", ""),
            "currency": info.get("currency", ""),
            "balance": info.get("balance", 0.0),
            "equity": info.get("equity", 0.0),
            "margin": info.get("margin", 0.0),
            "free_margin": info.get("free_margin", 0.0),
            "leverage": info.get("leverage", 0),
            "trade_mode": info.get("trade_mode", -1),
            "demo": info.get("trade_mode", -1) == 0,
        },
        "environment": "MT5 DEMO",
    }


def get_positions(symbol: Optional[str] = None) -> List[dict]:
    """Get open MT5 demo positions (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return []

    positions = mgr.positions_get(symbol=symbol)
    if positions:
        logger.debug("MT5_POSITION_REFRESH: %d positions", len(positions))

    result = []
    for pos in positions:
        pos_type = "BUY" if pos.get("type", 0) == 0 else "SELL"
        result.append({
            "ticket": pos.get("ticket", 0),
            "symbol": pos.get("symbol", ""),
            "side": pos_type,
            "volume": pos.get("volume", 0.0),
            "entry_price": pos.get("price_open", 0.0),
            "current_price": pos.get("price_current", 0.0),
            "stop_loss": pos.get("sl", 0.0),
            "take_profit": pos.get("tp", 0.0),
            "unrealized_pnl": pos.get("profit", 0.0),
            "magic": pos.get("magic", 0),
            "comment": pos.get("comment", ""),
            "time": pos.get("time", 0),
            "environment": "MT5 DEMO",
        })
    return result


def get_orders() -> List[dict]:
    """Get pending MT5 demo orders (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return []

    orders = mgr.orders_get()
    result = []
    for order in orders:
        result.append({
            "ticket": order.get("ticket", 0),
            "symbol": order.get("symbol", ""),
            "type": order.get("type", -1),
            "volume": order.get("volume", 0.0),
            "volume_initial": order.get("volume_initial", 0.0),
            "price_open": order.get("price_open", 0.0),
            "sl": order.get("sl", 0.0),
            "tp": order.get("tp", 0.0),
            "price_current": order.get("price_current", 0.0),
            "magic": order.get("magic", 0),
            "comment": order.get("comment", ""),
            "time_setup": order.get("time_setup", 0),
            "time_expiration": order.get("time_expiration", 0),
            "environment": "MT5 DEMO",
        })
    if result:
        logger.debug("MT5_ORDER_REFRESH: %d pending orders", len(result))
    return result


def get_symbol_info(symbol: str) -> Optional[dict]:
    """Get MT5 symbol information (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return None

    return mgr.symbol_info(symbol)


def get_quote(symbol: str) -> Optional[dict]:
    """Get current bid/ask quote for a symbol (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return None

    tick = mgr.symbol_info_tick(symbol)
    if tick is None:
        return None

    return {
        "symbol": symbol,
        "bid": tick.get("bid", 0.0),
        "ask": tick.get("ask", 0.0),
        "spread": round(tick.get("ask", 0.0) - tick.get("bid", 0.0), 5),
        "last": tick.get("last", 0.0),
        "time": tick.get("time", 0),
        "volume": tick.get("volume", 0.0),
        "environment": "MT5 DEMO",
    }


def get_heartbeat() -> dict:
    """MT5 connection heartbeat — lightweight health check with timestamps.

    Returns:
        connected: current connection state
        state: health state machine value
        demo_verified: whether demo account is verified
        can_trade: whether trading is permitted (always false in read-only)
        last_error: most recent error message (if any)
        timestamp: current server time
        last_heartbeat: time of last heartbeat call
        connection_age_seconds: how long since last successful connect
        reconnect_count: total reconnection attempts
    """
    global _last_heartbeat_time

    mgr, is_real = _safe_get_manager()
    health = mgr.health
    now = time.time()
    _last_heartbeat_time = now

    connection_age = None
    if _last_connected_time > 0:
        connection_age = int(now - _last_connected_time)

    logger.debug("MT5_HEARTBEAT: connected=%s state=%s", health.is_connected, health.state.value)

    return {
        "connected": health.is_connected,
        "state": health.state.value,
        "demo_verified": health.is_demo_verified,
        "can_trade": health.can_trade(),
        "last_error": health.last_error[:100] if health.last_error else None,
        "timestamp": int(now),
        "last_heartbeat": int(now),
        "connection_age_seconds": connection_age,
        "reconnect_count": _reconnect_count,
        "is_real_mt5": is_real,
    }


def get_symbols() -> List[dict]:
    """Get list of available MT5 symbols (read-only).

    When connected to real MT5, returns ALL symbols from the terminal.
    Falls back to configured symbols if MT5 discovery fails.
    """
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return []

    # Try MT5 terminal symbol discovery first
    if is_real:
        all_symbols = mgr.symbols_get()
        if all_symbols:
            logger.debug("MT5_SYMBOL_REFRESH: %d symbols from terminal", len(all_symbols))
            return all_symbols

    # Fallback: look up configured symbols
    symbols = []
    for sym in Config.SYMBOLS:
        info = mgr.symbol_info(sym)
        if info:
            symbols.append(info)
    return symbols


def reset():
    """Reset the adapter state (for testing)."""
    global _connection_manager, _mock_manager, _is_real_mt5
    global _last_heartbeat_time, _last_connected_time, _last_disconnect_time
    global _heartbeat_count, _reconnect_count

    if _connection_manager is not None:
        try:
            _connection_manager.shutdown()
        except Exception:
            pass
    _connection_manager = None
    _mock_manager = None
    _is_real_mt5 = False
    _last_heartbeat_time = 0.0
    _last_connected_time = 0.0
    _last_disconnect_time = 0.0
    _heartbeat_count = 0
    _reconnect_count = 0
