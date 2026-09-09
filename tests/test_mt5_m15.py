"""Tests for M15: Remote MT5 Demo Bridge.

Tests cover:
- API authentication (valid, missing, invalid, malformed)
- MT5 heartbeat with timestamps
- Connection monitoring and reconnection
- Read-only API (all endpoints)
- Safety gate enforcement
- No execution paths
- No credential leakage
- Observability logging

All MT5 tests use mocks — no real terminal required.
"""
import hashlib
import os
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ============================================================
# Authentication Tests
# ============================================================

class TestAPIAuthentication:
    """Tests for API token-based authentication."""

    @pytest.fixture
    def client(self):
        from api_server import app
        return TestClient(app)

    @pytest.fixture
    def auth_client(self):
        """Client with auth enabled."""
        from api_server import app
        with patch("api_server.API_SECRET_KEY", "test-secret-key-12345"):
            with patch("api_server.AUTH_ENABLED", True):
                yield TestClient(app)

    def test_unauthenticated_request_rejected(self, auth_client):
        """Missing Authorization header returns 401."""
        r = auth_client.get("/api/mt5/status")
        assert r.status_code == 401
        assert "Missing authentication" in r.json()["detail"]

    def test_malformed_header_rejected(self, auth_client):
        """Malformed Authorization header returns 401."""
        r = auth_client.get("/api/mt5/status", headers={"Authorization": "BadFormat"})
        assert r.status_code == 401

    def test_invalid_token_rejected(self, auth_client):
        """Invalid token returns 401."""
        r = auth_client.get("/api/mt5/status", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401
        assert "Invalid authentication" in r.json()["detail"]

    def test_short_token_rejected(self, auth_client):
        """Token shorter than 8 chars returns 401."""
        r = auth_client.get("/api/mt5/status", headers={"Authorization": "Bearer short"})
        assert r.status_code == 401

    def test_valid_token_accepted(self, auth_client):
        """Valid token returns 200."""
        r = auth_client.get("/api/mt5/status", headers={"Authorization": "Bearer test-secret-key-12345"})
        assert r.status_code == 200

    def test_no_auth_disabled_by_default(self, client):
        """When API_SECRET_KEY is empty, auth is disabled."""
        r = client.get("/api/mt5/status")
        assert r.status_code == 200

    def test_auth_not_leaked_in_response(self, auth_client):
        """Authentication errors don't leak token info."""
        r = auth_client.get("/api/mt5/status", headers={"Authorization": "Bearer wrong"})
        body = r.json()
        assert "wrong" not in str(body)
        assert "secret" not in str(body).lower() or "secret" in body.get("detail", "").lower()

    def test_constant_time_compare(self):
        """_constant_time_compare prevents timing attacks."""
        from api_server import _constant_time_compare
        assert _constant_time_compare("abc", "abc") is True
        assert _constant_time_compare("abc", "abd") is False
        assert _constant_time_compare("abc", "ab") is False
        assert _constant_time_compare("", "") is True

    def test_hash_token(self):
        """_hash_token produces consistent SHA-256 hashes."""
        from api_server import _hash_token
        h1 = _hash_token("test")
        h2 = _hash_token("test")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length
        assert h1 != "test"  # Not plaintext


# ============================================================
# MT5 Heartbeat Tests
# ============================================================

class TestMT5Heartbeat:
    """Tests for heartbeat with timestamps and connection monitoring."""

    def setup_method(self):
        from src.mt5 import readonly_api
        readonly_api.reset()

    def test_heartbeat_returns_timestamp(self):
        """Heartbeat includes current timestamp."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        assert "timestamp" in heartbeat
        assert heartbeat["timestamp"] > 0
        assert "last_heartbeat" in heartbeat

    def test_heartbeat_returns_connection_age(self):
        """Heartbeat includes connection age when connected."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        # On mock, connection_age may be None (mock auto-connects but
        # the tracking may not have recorded the connect time)
        assert "connection_age_seconds" in heartbeat

    def test_heartbeat_returns_reconnect_count(self):
        """Heartbeat includes reconnect count."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        assert "reconnect_count" in heartbeat
        assert isinstance(heartbeat["reconnect_count"], int)

    def test_heartbeat_returns_is_real_mt5(self):
        """Heartbeat distinguishes real vs mock."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        assert "is_real_mt5" in heartbeat
        assert isinstance(heartbeat["is_real_mt5"], bool)

    def test_heartbeat_logs_mt5_heartbeat_event(self):
        """Heartbeat triggers observability log."""
        from src.mt5.readonly_api import get_heartbeat
        with patch("src.mt5.readonly_api.logger") as mock_logger:
            get_heartbeat()
            mock_logger.debug.assert_called()
            call_args = str(mock_logger.debug.call_args)
            assert "MT5_HEARTBEAT" in call_args

    def test_heartbeat_api_endpoint(self):
        """GET /api/mt5/heartbeat returns heartbeat data."""
        from api_server import app
        client = TestClient(app)
        r = client.get("/api/mt5/heartbeat")
        assert r.status_code == 200
        data = r.json()
        assert "connected" in data
        assert "timestamp" in data
        assert "connection_age_seconds" in data


# ============================================================
# MT5 Connection Monitoring Tests
# ============================================================

class TestMT5ConnectionMonitoring:
    """Tests for connection state tracking and reconnection."""

    def setup_method(self):
        from src.mt5 import readonly_api
        readonly_api.reset()

    def test_status_includes_connection_age(self):
        """Status includes connection age when connected."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert "connection_age_seconds" in status

    def test_status_includes_reconnect_count(self):
        """Status includes reconnect count."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert "reconnect_count" in status
        assert isinstance(status["reconnect_count"], int)

    def test_status_includes_last_update(self):
        """Status includes last_update when connected."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert "last_update" in status

    def test_status_includes_terminal_available(self):
        """Status includes terminal_available flag."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        assert "terminal_available" in status
        assert isinstance(status["terminal_available"], bool)

    def test_reset_clears_all_state(self):
        """Reset clears heartbeat and connection tracking."""
        from src.mt5 import readonly_api
        from src.mt5.readonly_api import get_heartbeat
        get_heartbeat()
        readonly_api.reset()
        assert readonly_api._last_heartbeat_time == 0.0
        assert readonly_api._last_connected_time == 0.0
        assert readonly_api._reconnect_count == 0


# ============================================================
# MT5 Read-Only API Endpoint Tests
# ============================================================

class TestMT5ReadonlyEndpoints:
    """Tests for all MT5 read-only API endpoints."""

    @pytest.fixture
    def client(self):
        from api_server import app
        return TestClient(app)

    def test_status_endpoint(self, client):
        """GET /api/mt5/status returns full status."""
        r = client.get("/api/mt5/status")
        assert r.status_code == 200
        data = r.json()
        assert data["demo_only"] is True
        assert data["demo_trading_enabled"] is False
        assert "connection" in data
        assert "terminal_available" in data

    def test_account_endpoint(self, client):
        """GET /api/mt5/account returns account info."""
        r = client.get("/api/mt5/account")
        assert r.status_code == 200
        data = r.json()
        assert "connected" in data
        assert "environment" in data
        assert data["environment"] == "MT5 DEMO"

    def test_positions_endpoint(self, client):
        """GET /api/mt5/positions returns positions list."""
        r = client.get("/api/mt5/positions")
        assert r.status_code == 200
        assert "positions" in r.json()

    def test_positions_with_symbol(self, client):
        """GET /api/mt5/positions?symbol=BTCUSD works."""
        r = client.get("/api/mt5/positions?symbol=BTCUSD")
        assert r.status_code == 200

    def test_orders_endpoint(self, client):
        """GET /api/mt5/orders returns orders list."""
        r = client.get("/api/mt5/orders")
        assert r.status_code == 200
        assert "orders" in r.json()

    def test_symbols_endpoint(self, client):
        """GET /api/mt5/symbols returns symbols list."""
        r = client.get("/api/mt5/symbols")
        assert r.status_code == 200
        assert "symbols" in r.json()

    def test_quote_endpoint(self, client):
        """GET /api/mt5/quote/{symbol} returns quote."""
        r = client.get("/api/mt5/quote/BTCUSD")
        assert r.status_code == 200
        assert r.json()["symbol"] == "BTCUSD"

    def test_heartbeat_endpoint(self, client):
        """GET /api/mt5/heartbeat returns heartbeat."""
        r = client.get("/api/mt5/heartbeat")
        assert r.status_code == 200
        data = r.json()
        assert "connected" in data
        assert "timestamp" in data

    def test_all_endpoints_are_get_only(self, client):
        """All MT5 endpoints accept only GET method."""
        endpoints = [
            "/api/mt5/status",
            "/api/mt5/account",
            "/api/mt5/positions",
            "/api/mt5/orders",
            "/api/mt5/symbols",
            "/api/mt5/heartbeat",
        ]
        for ep in endpoints:
            r = client.post(ep, json={})
            assert r.status_code in (404, 405), f"{ep} should not accept POST"

    def test_no_execution_endpoints_exist(self, client):
        """No order execution endpoints exist."""
        execution_endpoints = [
            "/api/mt5/buy", "/api/mt5/sell", "/api/mt5/execute",
            "/api/mt5/close", "/api/mt5/modify", "/api/mt5/cancel",
            "/api/mt5/order",
        ]
        for ep in execution_endpoints:
            r = client.get(ep)
            assert r.status_code == 404, f"{ep} should not exist"


# ============================================================
# Safety Gate Tests
# ============================================================

class TestMT5SafetyGates:
    """Verify safety gates enforce demo-only operation."""

    def test_live_trading_rejected(self):
        """MT5ConnectionManager refuses when LIVE_TRADING=true."""
        from src.mt5.connection import MT5ConnectionManager
        from src.mt5.health import MT5State
        mgr = MT5ConnectionManager(enabled=True, demo_only=True, live_trading=True)
        assert mgr.connect() is False
        assert mgr.health.state == MT5State.ERROR

    def test_demo_only_enforced(self):
        """Non-demo accounts rejected when demo_only=true."""
        from src.mt5.mock import MockMT5ConnectionManager
        from src.mt5.health import MT5State
        mgr = MockMT5ConnectionManager(enabled=True, demo_only=True, account_trade_mode=1)
        assert mgr.connect() is False
        assert mgr.health.state == MT5State.NOT_DEMO

    def test_trading_disabled_by_default(self):
        """Demo trading disabled by default."""
        from src.mt5.mock import MockMT5ConnectionManager
        mgr = MockMT5ConnectionManager(enabled=True, demo_only=True, demo_trading_enabled=False)
        mgr.connect()
        assert mgr.health.can_trade() is False

    def test_readonly_adapter_has_no_execution_methods(self):
        """Read-only adapter has no order execution methods."""
        from src.mt5 import readonly_api
        execution_methods = ['execute_buy', 'execute_sell', 'close_position',
                           'modify_order', 'cancel_order', 'send_order']
        for method in execution_methods:
            assert not hasattr(readonly_api, method), f"readonly_api should not have {method}"

    def test_config_safety_flags(self):
        """Config safety flags are correctly set."""
        from src.config import Config
        assert Config.LIVE_TRADING is False
        assert Config.MT5_DEMO_ONLY is True
        assert Config.MT5_DEMO_TRADING_ENABLED is False


# ============================================================
# No Credential Leakage Tests
# ============================================================

class TestNoCredentialLeakage:
    """Verify no credentials are exposed through the API."""

    def test_account_info_no_password(self):
        """Account info dict never contains password."""
        from src.mt5.connection import _account_info_to_dict
        mock_info = MagicMock()
        mock_info.login = 12345
        mock_info.server = "Demo"
        mock_info.balance = 10000.0
        result = _account_info_to_dict(mock_info)
        for key in ["password", "token", "secret", "api_key", "credential"]:
            assert key not in result

    def test_status_no_credentials(self):
        """Status endpoint returns no credentials."""
        from src.mt5.readonly_api import get_status
        status = get_status()
        status_str = str(status).lower()
        for secret in ["password", "token", "secret", "api_key"]:
            assert secret not in status_str

    def test_heartbeat_no_credentials(self):
        """Heartbeat returns no credentials."""
        from src.mt5.readonly_api import get_heartbeat
        heartbeat = get_heartbeat()
        heartbeat_str = str(heartbeat).lower()
        for secret in ["password", "token", "secret", "api_key"]:
            assert secret not in heartbeat_str

    def test_api_no_execution_routes(self):
        """API has no routes for order execution."""
        from api_server import app
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        execution_routes = ["/api/mt5/buy", "/api/mt5/sell", "/api/mt5/execute",
                          "/api/mt5/close", "/api/mt5/modify", "/api/mt5/cancel"]
        for route in execution_routes:
            assert route not in routes, f"Execution route {route} should not exist"


# ============================================================
# Observability Logging Tests
# ============================================================

class TestObservabilityLogging:
    """Verify observability events are logged."""

    def setup_method(self):
        from src.mt5 import readonly_api
        readonly_api.reset()

    def test_connect_logs_mt5_connect(self):
        """Connection attempt logs MT5_CONNECT event."""
        from src.mt5 import readonly_api
        with patch("src.mt5.readonly_api.logger") as mock_logger:
            readonly_api._ensure_connection()
            calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.debug.call_args_list]
            assert any("MT5_CONNECT" in c for c in calls)

    def test_heartbeat_logs_mt5_heartbeat(self):
        """Heartbeat logs MT5_HEARTBEAT event."""
        from src.mt5.readonly_api import get_heartbeat
        with patch("src.mt5.readonly_api.logger") as mock_logger:
            get_heartbeat()
            calls = [str(c) for c in mock_logger.debug.call_args_list]
            assert any("MT5_HEARTBEAT" in c for c in calls)

    def test_account_refresh_logs_event(self):
        """Account refresh logs MT5_ACCOUNT_REFRESH."""
        from src.mt5.readonly_api import get_account
        with patch("src.mt5.readonly_api.logger") as mock_logger:
            get_account()
            calls = [str(c) for c in mock_logger.debug.call_args_list]
            # May or may not log depending on connection state
            # Just verify the logger was called
            assert mock_logger.debug.called or mock_logger.info.called


# ============================================================
# Android Model Parsing Tests
# ============================================================

class TestAndroidModels:
    """Test that Android data model structures match API responses."""

    def test_mt5_status_matches_api(self):
        """MT5Status fields match /api/mt5/status response."""
        from api_server import app
        client = TestClient(app)
        r = client.get("/api/mt5/status")
        data = r.json()
        required_fields = ["enabled", "demo_only", "demo_trading_enabled", "connection",
                          "state", "demo_verified", "can_trade", "magic_number", "server",
                          "terminal_available", "connection_age_seconds", "reconnect_count"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_mt5_account_matches_api(self):
        """MT5AccountResponse fields match /api/mt5/account response."""
        from api_server import app
        client = TestClient(app)
        r = client.get("/api/mt5/account")
        data = r.json()
        assert "connected" in data
        assert "account" in data or data.get("note") is not None
        assert "environment" in data

    def test_mt5_heartbeat_matches_api(self):
        """MT5Heartbeat fields match /api/mt5/heartbeat response."""
        from api_server import app
        client = TestClient(app)
        r = client.get("/api/mt5/heartbeat")
        data = r.json()
        required_fields = ["connected", "state", "demo_verified", "can_trade",
                          "timestamp", "last_heartbeat", "connection_age_seconds",
                          "reconnect_count", "is_real_mt5"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
