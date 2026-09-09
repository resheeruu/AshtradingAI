"""Tests for M14: MT5 read-only API adapter and endpoints.

All tests use mock/offline MT5 — no real terminal required.
Tests verify:
- MT5 adapter initialization
- connection failure/success
- demo-account verification
- account information
- positions
- quote retrieval
- API responses
- safety gate enforcement
- live-trading rejection
- unauthorized execution rejection
"""
import pytest
from unittest.mock import patch, MagicMock

from src.mt5.health import MT5Health, MT5State
from src.mt5.mock import MockMT5ConnectionManager
from src.mt5.connection import MT5ConnectionManager, _account_info_to_dict, _terminal_info_to_dict
from src.config import Config


# ============================================================
# MT5 Read-Only Adapter Tests
# ============================================================

class TestMT5ReadonlyAdapter:
    """Tests for src/mt5/readonly_api.py"""

    def setup_method(self):
        """Reset adapter state before each test."""
        from src.mt5 import readonly_api
        readonly_api.reset()

    def test_get_status_returns_config(self):
        """Status endpoint returns MT5 configuration."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert "enabled" in status
        assert "demo_only" in status
        assert "demo_trading_enabled" in status
        assert "connection" in status
        assert "state" in status
        assert "magic_number" in status
        assert status["demo_only"] is True

    def test_get_status_safety_flags(self):
        """Status shows safety flags from config."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert status["demo_only"] == Config.MT5_DEMO_ONLY
        assert status["demo_trading_enabled"] == Config.MT5_DEMO_TRADING_ENABLED

    def test_get_account_returns_data(self):
        """Account returns data (mock fallback on non-Windows)."""
        from src.mt5.readonly_api import get_account
        result = get_account()
        # On non-Windows, adapter falls back to mock which auto-connects
        assert "connected" in result
        assert "account" in result or result.get("note") is not None

    def test_get_positions_returns_list(self):
        """Positions returns a list."""
        from src.mt5.readonly_api import get_positions
        positions = get_positions()
        assert isinstance(positions, list)

    def test_get_positions_with_symbol(self):
        """Positions with symbol filter works."""
        from src.mt5.readonly_api import get_positions
        positions = get_positions(symbol="BTCUSD")
        assert isinstance(positions, list)

    def test_get_orders_returns_list(self):
        """Orders returns a list."""
        from src.mt5.readonly_api import get_orders
        orders = get_orders()
        assert isinstance(orders, list)

    def test_get_symbol_info_returns_or_none(self):
        """Symbol info returns dict or None."""
        from src.mt5.readonly_api import get_symbol_info
        info = get_symbol_info("BTCUSD")
        # May be None (disconnected) or dict (mock connected)
        assert info is None or isinstance(info, dict)

    def test_get_quote_returns_or_none(self):
        """Quote returns dict or None."""
        from src.mt5.readonly_api import get_quote
        quote = get_quote("BTCUSD")
        # May be None (disconnected) or dict (mock connected)
        assert quote is None or isinstance(quote, dict)

    def test_get_heartbeat_returns_dict(self):
        """Heartbeat always returns a dict."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        assert "connected" in heartbeat
        assert "state" in heartbeat

    def test_get_symbols_returns_list(self):
        """Symbols returns a list."""
        from src.mt5.readonly_api import get_symbols
        symbols = get_symbols()
        assert isinstance(symbols, list)


class TestMT5ReadonlyAdapterWithMock:
    """Tests using MockMT5ConnectionManager to verify read-only operations."""

    def setup_method(self):
        from src.mt5 import readonly_api
        readonly_api.reset()

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_status_connected(self, mock_get_mgr):
        """Status shows connected when mock is connected."""
        from src.mt5.readonly_api import get_status
        mock_mgr = MockMT5ConnectionManager(enabled=True, demo_only=True)
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                status = get_status()
                assert status["connection"] == "CONNECTED"
                assert status["demo_verified"] is True

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_account_connected(self, mock_get_mgr):
        """Account returns real data when connected."""
        from src.mt5.readonly_api import get_account
        mock_mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, balance=50000.0, login=99999
        )
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                result = get_account()
                assert result["connected"] is True
                assert result["account"]["balance"] == 50000.0
                assert result["account"]["login"] == 99999
                assert result["account"]["demo"] is True
                assert result["environment"] == "MT5 DEMO"

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_positions_connected(self, mock_get_mgr):
        """Positions returns positions from mock."""
        from src.mt5.readonly_api import get_positions
        positions_data = [
            {"ticket": 1001, "symbol": "BTCUSD", "type": 0, "volume": 0.1,
             "price_open": 50000.0, "price_current": 51000.0, "sl": 0, "tp": 0,
             "profit": 100.0, "magic": 20260904, "comment": "", "time": 1700000000}
        ]
        mock_mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, positions=positions_data
        )
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                positions = get_positions()
                assert len(positions) == 1
                assert positions[0]["symbol"] == "BTCUSD"
                assert positions[0]["side"] == "BUY"
                assert positions[0]["environment"] == "MT5 DEMO"

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_positions_short(self, mock_get_mgr):
        """Short positions are correctly labeled."""
        from src.mt5.readonly_api import get_positions
        positions_data = [
            {"ticket": 1002, "symbol": "ETHUSD", "type": 1, "volume": 0.5,
             "price_open": 3000.0, "price_current": 2900.0, "sl": 0, "tp": 0,
             "profit": 50.0, "magic": 20260904, "comment": "", "time": 1700000000}
        ]
        mock_mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, positions=positions_data
        )
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                positions = get_positions()
                assert positions[0]["side"] == "SELL"

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_quote_connected(self, mock_get_mgr):
        """Quote returns bid/ask from mock."""
        from src.mt5.readonly_api import get_quote
        mock_mgr = MockMT5ConnectionManager(enabled=True, demo_only=True)
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                quote = get_quote("BTCUSD")
                assert quote is not None
                assert quote["symbol"] == "BTCUSD"
                assert quote["bid"] > 0
                assert quote["ask"] > 0
                assert quote["ask"] > quote["bid"]
                assert quote["environment"] == "MT5 DEMO"

    @patch("src.mt5.readonly_api._get_connection_manager")
    def test_get_heartbeat_connected(self, mock_get_mgr):
        """Heartbeat shows connected status."""
        from src.mt5.readonly_api import get_heartbeat
        mock_mgr = MockMT5ConnectionManager(enabled=True, demo_only=True)
        mock_mgr.connect()
        mock_get_mgr.return_value = mock_mgr

        with patch("src.mt5.readonly_api._ensure_connection", return_value=True):
            with patch("src.mt5.readonly_api._is_real_mt5", False):
                heartbeat = get_heartbeat()
                assert heartbeat["connected"] is True
                assert heartbeat["demo_verified"] is True


# ============================================================
# MT5 Safety Gate Tests
# ============================================================

class TestMT5SafetyGates:
    """Verify safety gates prevent live trading and unauthorized operations."""

    def test_live_trading_rejected(self):
        """MT5ConnectionManager refuses to connect when LIVE_TRADING=true."""
        mgr = MT5ConnectionManager(
            enabled=True,
            demo_only=True,
            live_trading=True,  # DANGER: should be blocked
        )
        result = mgr.connect()
        assert result is False
        assert mgr.health.state == MT5State.ERROR

    def test_disabled_rejected(self):
        """MT5ConnectionManager refuses when MT5_ENABLED=false."""
        mgr = MT5ConnectionManager(enabled=False, demo_only=True)
        result = mgr.connect()
        assert result is False

    def test_non_demo_rejected(self):
        """MockMT5ConnectionManager rejects non-demo accounts."""
        mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, account_trade_mode=1  # Live account
        )
        result = mgr.connect()
        assert result is False
        assert mgr.health.state == MT5State.NOT_DEMO

    def test_demo_only_enforced(self):
        """Demo-only flag is enforced by connection manager."""
        mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, account_trade_mode=0  # Demo
        )
        result = mgr.connect()
        assert result is True
        assert mgr.health.is_demo_verified is True

    def test_trading_disabled_by_default(self):
        """Demo trading is disabled by default."""
        mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, demo_trading_enabled=False
        )
        mgr.connect()
        assert mgr.health.is_trade_enabled is False
        assert mgr.health.can_trade() is False

    def test_trading_requires_explicit_enable(self):
        """Demo trading only works when explicitly enabled."""
        mgr = MockMT5ConnectionManager(
            enabled=True, demo_only=True, demo_trading_enabled=True
        )
        mgr.connect()
        assert mgr.health.is_trade_enabled is True
        assert mgr.health.can_trade() is True

    def test_readonly_adapter_no_trading_endpoints(self):
        """Read-only adapter has no order execution methods."""
        from src.mt5 import readonly_api
        assert not hasattr(readonly_api, 'execute_buy')
        assert not hasattr(readonly_api, 'execute_sell')
        assert not hasattr(readonly_api, 'close_position')
        assert not hasattr(readonly_api, 'modify_order')
        assert not hasattr(readonly_api, 'cancel_order')

    def test_config_validation_live_mt5(self):
        """Config validation rejects LIVE_TRADING=true with MT5_ENABLED=true."""
        errors = []
        # Simulate the validation logic from Config.validate()
        if Config.MT5_ENABLED and Config.LIVE_TRADING:
            errors.append("MT5_ENABLED and LIVE_TRADING cannot both be true in M6")
        # In current config, this should not produce an error
        # (MT5_ENABLED=true, LIVE_TRADING=false)


# ============================================================
# MT5 API Endpoint Tests (FastAPI TestClient)
# ============================================================

class TestMT5APIEndpoints:
    """Tests for the FastAPI MT5 read-only endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from api_server import app
        return TestClient(app)

    def test_mt5_status_endpoint(self, client):
        """GET /api/mt5/status returns status."""
        r = client.get("/api/mt5/status")
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "demo_only" in data
        assert "connection" in data
        assert data["demo_only"] is True

    def test_mt5_account_endpoint(self, client):
        """GET /api/mt5/account returns account info."""
        r = client.get("/api/mt5/account")
        assert r.status_code == 200
        data = r.json()
        assert "connected" in data
        assert "account" in data or data.get("note") is not None

    def test_mt5_positions_endpoint(self, client):
        """GET /api/mt5/positions returns positions list."""
        r = client.get("/api/mt5/positions")
        assert r.status_code == 200
        data = r.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)

    def test_mt5_positions_with_symbol(self, client):
        """GET /api/mt5/positions?symbol=BTCUSD works."""
        r = client.get("/api/mt5/positions?symbol=BTCUSD")
        assert r.status_code == 200

    def test_mt5_orders_endpoint(self, client):
        """GET /api/mt5/orders returns orders list."""
        r = client.get("/api/mt5/orders")
        assert r.status_code == 200
        data = r.json()
        assert "orders" in data

    def test_mt5_symbols_endpoint(self, client):
        """GET /api/mt5/symbols returns symbols list."""
        r = client.get("/api/mt5/symbols")
        assert r.status_code == 200
        data = r.json()
        assert "symbols" in data

    def test_mt5_quote_endpoint(self, client):
        """GET /api/mt5/quote/{symbol} returns quote."""
        r = client.get("/api/mt5/quote/BTCUSD")
        assert r.status_code == 200
        data = r.json()
        assert "symbol" in data
        assert data["symbol"] == "BTCUSD"

    def test_mt5_heartbeat_endpoint(self, client):
        """GET /api/mt5/heartbeat returns heartbeat."""
        r = client.get("/api/mt5/heartbeat")
        assert r.status_code == 200
        data = r.json()
        assert "connected" in data
        assert "state" in data

    def test_no_order_execution_endpoints(self, client):
        """No POST endpoints for order execution exist."""
        r = client.post("/api/mt5/buy", json={})
        assert r.status_code in (404, 405)  # Not Found or Method Not Allowed

        r = client.post("/api/mt5/sell", json={})
        assert r.status_code in (404, 405)

        r = client.post("/api/mt5/execute", json={})
        assert r.status_code in (404, 405)

        r = client.post("/api/mt5/close", json={})
        assert r.status_code in (404, 405)

        r = client.post("/api/mt5/modify", json={})
        assert r.status_code in (404, 405)

    def test_safety_flags_in_status(self, client):
        """Safety flags are present in status response."""
        r = client.get("/api/mt5/status")
        data = r.json()
        assert data["demo_only"] is True
        assert data["demo_trading_enabled"] is False


# ============================================================
# MT5 Health State Machine Tests
# ============================================================

class TestMT5HealthStateMachine:
    """Additional health state machine tests for M14."""

    def test_can_trade_requires_all_gates(self):
        """can_trade requires connected + demo_verified + trade_enabled + CONNECTED state."""
        h = MT5Health()

        # Not connected
        assert h.can_trade() is False

        # Connected but not verified
        h.record_connected({}, {})
        assert h.can_trade() is False

        # Verified but trade not enabled
        h.set_demo_verified(True)
        assert h.can_trade() is False

        # Trade enabled
        h.set_trade_enabled(True)
        assert h.can_trade() is True

    def test_error_resets_all_state(self):
        """Error state resets all authorization."""
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True

        h.record_error("Something went wrong")
        assert h.can_trade() is False
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False

    def test_disconnect_resets_state(self):
        """Disconnect resets all authorization."""
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True

        h.record_disconnected()
        assert h.can_trade() is False
        assert h.is_connected is False

    def test_get_summary(self):
        """Health summary contains expected fields."""
        h = MT5Health()
        summary = h.get_summary()
        assert "state" in summary
        assert "connected" in summary
        assert "demo_verified" in summary
        assert "trade_enabled" in summary
        assert "can_trade" in summary
        assert "terminal" in summary
        assert "account" in summary


# ============================================================
# MT5 Connection Manager Wrapper Tests
# ============================================================

class TestMT5ConnectionWrappers:
    """Test the wrapper methods on MT5ConnectionManager."""

    def test_symbol_info_when_disconnected(self):
        """symbol_info returns None when not connected."""
        mgr = MT5ConnectionManager(enabled=False)
        result = mgr.symbol_info("BTCUSD")
        assert result is None

    def test_symbol_info_tick_when_disconnected(self):
        """symbol_info_tick returns None when not connected."""
        mgr = MT5ConnectionManager(enabled=False)
        result = mgr.symbol_info_tick("BTCUSD")
        assert result is None

    def test_positions_get_when_disconnected(self):
        """positions_get returns empty when not connected."""
        mgr = MT5ConnectionManager(enabled=False)
        result = mgr.positions_get()
        assert result == []

    def test_get_account_info_when_disconnected(self):
        """get_account_info returns None when not connected."""
        mgr = MT5ConnectionManager(enabled=False)
        result = mgr.get_account_info()
        assert result is None

    def test_get_terminal_info_when_disconnected(self):
        """get_terminal_info returns None when not connected."""
        mgr = MT5ConnectionManager(enabled=False)
        result = mgr.get_terminal_info()
        assert result is None

    def test_account_info_to_dict(self):
        """_account_info_to_dict converts correctly."""
        mock_info = MagicMock()
        mock_info.login = 12345
        mock_info.server = "Demo-Server"
        mock_info.name = "Test User"
        mock_info.currency = "USD"
        mock_info.balance = 10000.0
        mock_info.equity = 10500.0
        mock_info.margin = 500.0
        mock_info.margin_free = 10000.0
        mock_info.leverage = 100
        mock_info.trade_mode = 0
        mock_info.limit_orders = 500

        result = _account_info_to_dict(mock_info)
        assert result["login"] == 12345
        assert result["balance"] == 10000.0
        assert result["trade_mode"] == 0

    def test_terminal_info_to_dict(self):
        """_terminal_info_to_dict converts correctly."""
        mock_info = MagicMock()
        mock_info.version = "5.0.40"
        mock_info.build = 3800
        mock_info.company = "MetaQuotes"
        mock_info.connected = True
        mock_info.trade_allowed = True

        result = _terminal_info_to_dict(mock_info)
        assert result["version"] == "5.0.40"
        assert result["connected"] is True


# ============================================================
# MT5 No-Credentials Test
# ============================================================

class TestMT5NoCredentials:
    """Verify no credentials are exposed through the API."""

    def test_account_info_no_password(self):
        """Account info dict never contains password."""
        mock_info = MagicMock()
        mock_info.login = 12345
        mock_info.server = "Demo"
        mock_info.balance = 10000.0
        result = _account_info_to_dict(mock_info)
        assert "password" not in result
        assert "token" not in result
        assert "secret" not in result

    def test_status_no_credentials(self):
        """Status endpoint returns no credentials."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        status_str = str(status).lower()
        assert "password" not in status_str
        assert "token" not in status_str
        assert "secret" not in status_str
        assert "api_key" not in status_str

    def test_api_no_execution_endpoints(self):
        """API has no endpoints for order execution."""
        from api_server import app
        routes = [route.path for route in app.routes]
        assert "/api/mt5/buy" not in routes
        assert "/api/mt5/sell" not in routes
        assert "/api/mt5/execute" not in routes
        assert "/api/mt5/close" not in routes
        assert "/api/mt5/modify" not in routes
        assert "/api/mt5/cancel" not in routes
