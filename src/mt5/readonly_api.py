"""MT5 read-only API adapter — wraps MT5ConnectionManager for the API layer.

Provides read-only access to MT5 demo account data.
No order execution, no trading, no modification capabilities.

Safety: This adapter READS from MT5 only. It never sends orders.
The existing MT5ConnectionManager safety gates are the authority.
"""
import logging
from typing import Optional, List, Dict, Any

from src.config import Config

logger = logging.getLogger(__name__)

_connection_manager = None
_mock_manager = None
_is_real_mt5 = False


def _get_connection_manager():
    """Get or create the MT5 connection manager (lazy singleton).

    On non-Windows systems (e.g., Android/Termux), MetaTrader5 package
    is unavailable. Falls back to MockMT5ConnectionManager for graceful
    degradation — all read operations return disconnected state.
    """
    global _connection_manager, _mock_manager, _is_real_mt5

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
    mgr = _get_connection_manager()
    if mgr.health.is_connected:
        return True
    try:
        return mgr.connect()
    except ImportError:
        logger.debug("MetaTrader5 package unavailable — MT5 read-only mode disabled")
        return False
    except Exception as e:
        logger.error("MT5 connection failed: %s", e)
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
    }


def get_account() -> dict:
    """Get MT5 demo account information (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return {
            "connected": False,
            "account": None,
            "note": "MT5 not connected. Account information unavailable.",
        }

    info = mgr.get_account_info()
    if info is None:
        return {
            "connected": True,
            "account": None,
            "note": "Connected but account info unavailable.",
        }

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

    # MT5ConnectionManager doesn't have orders_get wrapper yet.
    # Pending orders require mt5.orders_get() which isn't wrapped.
    # Return empty for now — positions are the primary read target.
    return []


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
    """MT5 connection heartbeat — lightweight health check."""
    mgr, is_real = _safe_get_manager()
    health = mgr.health

    return {
        "connected": health.is_connected,
        "state": health.state.value,
        "demo_verified": health.is_demo_verified,
        "can_trade": health.can_trade(),
        "last_error": health.last_error[:100] if health.last_error else None,
    }


def get_symbols() -> List[dict]:
    """Get list of available MT5 symbols (read-only)."""
    mgr, is_real = _safe_get_manager()

    if not mgr.health.is_connected:
        return []

    # MT5ConnectionManager doesn't have a symbols_get wrapper.
    # Use the configured SYMBOLS from Config as available symbols.
    symbols = []
    for sym in Config.SYMBOLS:
        info = mgr.symbol_info(sym)
        if info:
            symbols.append(info)
    return symbols


def reset():
    """Reset the adapter state (for testing)."""
    global _connection_manager, _mock_manager, _is_real_mt5
    if _connection_manager is not None:
        try:
            _connection_manager.shutdown()
        except Exception:
            pass
    _connection_manager = None
    _mock_manager = None
    _is_real_mt5 = False
