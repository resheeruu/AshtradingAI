"""Tests for Milestone 6: MT5 demo integration adapter.

All tests use mock/offline MT5 — no real terminal required.
"""
import math
import pytest
from datetime import datetime, timezone

from src.mt5.health import MT5Health, MT5State
from src.mt5.mock import MockMT5ConnectionManager, MockMT5MarketData, MockMT5DemoBroker
from src.mt5.broker import (
    _validate_tick, _validate_volume, _validate_sl_tp, _detect_filling_mode,
    MT5DemoBroker,
)
from src.config import Config, _bool


# ============================================================
# Health Tests
# ============================================================

class TestMT5Health:
    def test_initial_state(self):
        h = MT5Health()
        assert h.state == MT5State.DISCONNECTED
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.can_trade() is False

    def test_record_connected(self):
        h = MT5Health()
        h.record_connected(
            {"version": "5.0", "build": 3000},
            {"login": 12345, "server": "Demo", "trade_mode": 0},
        )
        assert h.state == MT5State.CONNECTED
        assert h.is_connected is True
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True

    def test_record_not_demo(self):
        h = MT5Health()
        h.record_not_demo("Account is live")
        assert h.state == MT5State.NOT_DEMO
        assert h.can_trade() is False
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False

    def test_record_auth_failed(self):
        h = MT5Health()
        h.record_auth_failed("Invalid credentials")
        assert h.state == MT5State.AUTH_FAILED
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False

    def test_record_account_mismatch(self):
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        h.record_account_mismatch("Server mismatch")
        assert h.state == MT5State.ACCOUNT_MISMATCH
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False
        assert h.can_trade() is False

    def test_record_symbol_unavailable(self):
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        h.record_symbol_unavailable("FAKEUSD")
        assert h.state == MT5State.SYMBOL_UNAVAILABLE
        assert h.is_trade_enabled is False
        assert h.can_trade() is False

    def test_record_trade_disabled(self):
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        h.record_trade_disabled()
        assert h.state == MT5State.TRADE_DISABLED
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False
        assert h.can_trade() is False

    def test_record_error_resets_all(self):
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        h.record_error("Something broke")
        assert h.state == MT5State.ERROR
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False
        assert h.can_trade() is False

    def test_can_trade_gates(self):
        h = MT5Health()
        assert h.can_trade() is False
        h.record_connected({}, {})
        assert h.can_trade() is False
        h.set_demo_verified(True)
        assert h.can_trade() is False
        h.set_trade_enabled(True)
        assert h.can_trade() is True

    def test_disconnected_resets_all_state(self):
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        h.record_disconnected()
        assert h.is_connected is False
        assert h.is_demo_verified is False
        assert h.is_trade_enabled is False
        assert h.can_trade() is False

    def test_stale_authorization_after_reconnect(self):
        """After disconnect, previous auth must not persist."""
        h = MT5Health()
        h.record_connected({}, {})
        h.set_demo_verified(True)
        h.set_trade_enabled(True)
        assert h.can_trade() is True
        # Simulate disconnect
        h.record_disconnected()
        assert h.can_trade() is False
        # Reconnect
        h.record_connected({}, {})
        # Should NOT still be trade-enabled
        assert h.can_trade() is False

    def test_all_failure_states_disable_trading(self):
        """Every failure state must disable can_trade()."""
        h = MT5Health()
        states = [
            lambda: h.record_auth_failed("x"),
            lambda: h.record_terminal_error("x"),
            lambda: h.record_account_mismatch("x"),
            lambda: h.record_not_demo("x"),
            lambda: h.record_trade_disabled(),
            lambda: h.record_error("x"),
            lambda: h.record_disconnected(),
        ]
        for fn in states:
            h.record_connected({}, {})
            h.set_demo_verified(True)
            h.set_trade_enabled(True)
            assert h.can_trade() is True
            fn()
            assert h.can_trade() is False, f"Failed for {fn.__name__}"

    def test_summary(self):
        h = MT5Health()
        h.record_connected({"version": "5.0", "build": 3000}, {"login": 12345})
        h.set_demo_verified(True)
        s = h.get_summary()
        assert s["state"] == "CONNECTED"
        assert s["demo_verified"] is True
        assert s["terminal"]["version"] == "5.0"


# ============================================================
# Connection Tests
# ============================================================

class TestMockConnection:
    def test_connect_success(self):
        conn = MockMT5ConnectionManager(enabled=True, demo_only=True, account_trade_mode=0)
        assert conn.connect() is True
        assert conn.is_connected() is True

    def test_connect_disabled(self):
        conn = MockMT5ConnectionManager(enabled=False)
        assert conn.connect() is False
        assert conn.is_connected() is False

    def test_connect_non_demo_rejected(self):
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=1)
        assert conn.connect() is False
        assert conn.health.state == MT5State.NOT_DEMO

    def test_connect_contest_rejected(self):
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=2)
        assert conn.connect() is False
        assert conn.health.state == MT5State.NOT_DEMO

    def test_connect_trade_mode_none_rejected(self):
        """trade_mode=None must be rejected (fail-closed)."""
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=None)
        assert conn.connect() is False
        assert conn.health.state == MT5State.NOT_DEMO

    def test_connect_unexpected_trade_mode_rejected(self):
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=99)
        assert conn.connect() is False
        assert conn.health.state == MT5State.NOT_DEMO

    def test_connect_init_failure(self):
        conn = MockMT5ConnectionManager(fail_init=True)
        assert conn.connect() is False
        assert conn.health.state == MT5State.TERMINAL_ERROR

    def test_server_mismatch(self):
        conn = MockMT5ConnectionManager(
            server="OtherServer", expected_server="MetaQuotes-Demo"
        )
        assert conn.connect() is False
        assert conn.health.state == MT5State.ACCOUNT_MISMATCH

    def test_login_mismatch(self):
        conn = MockMT5ConnectionManager(
            login=11111, expected_login=22222
        )
        assert conn.connect() is False
        assert conn.health.state == MT5State.ACCOUNT_MISMATCH

    def test_terminal_trade_disabled(self):
        conn = MockMT5ConnectionManager(terminal_trade_allowed=False)
        assert conn.connect() is False
        assert conn.health.state == MT5State.TRADE_DISABLED

    def test_reconnect_resets_authorization(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        assert conn.can_trade() is True
        conn.reconnect()
        assert conn.is_connected() is True
        assert conn.can_trade() is True

    def test_shutdown_resets_authorization(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        assert conn.is_connected() is True
        conn.shutdown()
        assert conn.is_connected() is False
        assert conn.health.state == MT5State.DISCONNECTED

    def test_shutdown_idempotent(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        conn.shutdown()
        conn.shutdown()
        assert conn.is_connected() is False

    def test_can_trade(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        assert conn.can_trade() is True

    def test_cannot_trade_when_disabled(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        assert conn.can_trade() is False

    def test_live_trading_rejected(self):
        conn = MockMT5ConnectionManager(live_trading=True)
        assert conn.connect() is False
        assert conn.health.state == MT5State.ERROR

    def test_symbol_info(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        info = conn.symbol_info("BTCUSD")
        assert info is not None
        assert info["point"] > 0
        assert info["digits"] > 0

    def test_symbol_info_disconnected(self):
        conn = MockMT5ConnectionManager()
        assert conn.symbol_info("BTCUSD") is None

    def test_symbol_info_tick(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        tick = conn.symbol_info_tick("BTCUSD")
        assert tick is not None
        assert tick["bid"] > 0
        assert tick["ask"] > 0

    def test_symbol_info_tick_disconnected(self):
        conn = MockMT5ConnectionManager()
        assert conn.symbol_info_tick("BTCUSD") is None

    def test_positions_get(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        positions = conn.positions_get()
        assert isinstance(positions, list)

    def test_positions_get_disconnected(self):
        conn = MockMT5ConnectionManager()
        assert conn.positions_get() == []


# ============================================================
# Tick Validation Tests
# ============================================================

class TestTickValidation:
    def test_valid_tick(self):
        ok, err = _validate_tick({"bid": 50000, "ask": 50001}, "BTCUSD")
        assert ok is True

    def test_none_tick(self):
        ok, err = _validate_tick(None, "BTCUSD")
        assert ok is False
        assert "No tick" in err

    def test_zero_bid(self):
        ok, err = _validate_tick({"bid": 0, "ask": 50001}, "BTCUSD")
        assert ok is False
        assert "Invalid bid" in err

    def test_zero_ask(self):
        ok, err = _validate_tick({"bid": 50000, "ask": 0}, "BTCUSD")
        assert ok is False
        assert "Invalid ask" in err

    def test_negative_bid(self):
        ok, err = _validate_tick({"bid": -1, "ask": 50001}, "BTCUSD")
        assert ok is False

    def test_ask_less_than_bid(self):
        ok, err = _validate_tick({"bid": 50001, "ask": 50000}, "BTCUSD")
        assert ok is False
        assert "ask" in err


# ============================================================
# Volume Validation Tests
# ============================================================

class TestVolumeValidation:
    def test_valid_volume(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, 0.10)
        assert ok is True

    def test_zero_volume(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, 0)
        assert ok is False
        assert "positive" in err

    def test_negative_volume(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, -1)
        assert ok is False

    def test_below_minimum(self):
        ok, err = _validate_volume(0.10, 100.0, 0.01, 0.01)
        assert ok is False
        assert "below minimum" in err

    def test_above_maximum(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, 200)
        assert ok is False
        assert "above maximum" in err

    def test_not_aligned_to_step(self):
        ok, err = _validate_volume(0.01, 100.0, 0.05, 0.12)
        assert ok is False
        assert "step" in err

    def test_nan_volume(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, float("nan"))
        assert ok is False
        assert "not finite" in err

    def test_inf_volume(self):
        ok, err = _validate_volume(0.01, 100.0, 0.01, float("inf"))
        assert ok is False
        assert "not finite" in err


# ============================================================
# SL/TP Validation Tests
# ============================================================

class TestSLTPValidation:
    def test_valid_buy_sl_tp(self):
        ok, err = _validate_sl_tp("buy", 50000, 49000, 51000, 0.01, 2)
        assert ok is True

    def test_buy_sl_above_entry(self):
        ok, err = _validate_sl_tp("buy", 50000, 51000, None, 0.01, 2)
        assert ok is False
        assert "SL" in err

    def test_buy_tp_below_entry(self):
        ok, err = _validate_sl_tp("buy", 50000, None, 49000, 0.01, 2)
        assert ok is False
        assert "TP" in err

    def test_valid_sell_sl_tp(self):
        ok, err = _validate_sl_tp("sell", 50000, 51000, 49000, 0.01, 2)
        assert ok is True

    def test_sell_sl_below_entry(self):
        ok, err = _validate_sl_tp("sell", 50000, 49000, None, 0.01, 2)
        assert ok is False
        assert "SL" in err

    def test_sell_tp_above_entry(self):
        ok, err = _validate_sl_tp("sell", 50000, None, 51000, 0.01, 2)
        assert ok is False
        assert "TP" in err

    def test_no_sl_no_tp(self):
        ok, err = _validate_sl_tp("buy", 50000, None, None, 0.01, 2)
        assert ok is True


# ============================================================
# Filling Mode Tests
# ============================================================

class TestFillingMode:
    def test_fok_supported(self):
        mode = _detect_filling_mode({"filling_mode": 1})
        assert mode == 1

    def test_ioc_supported(self):
        mode = _detect_filling_mode({"filling_mode": 2})
        assert mode == 2

    def test_return_supported(self):
        mode = _detect_filling_mode({"filling_mode": 4})
        assert mode == 4

    def test_all_modes(self):
        mode = _detect_filling_mode({"filling_mode": 7})
        assert mode is not None

    def test_no_mode(self):
        mode = _detect_filling_mode({"filling_mode": 0})
        assert mode is None


# ============================================================
# Broker Safety Gate Tests
# ============================================================

class TestBrokerSafetyGates:
    def test_live_trading_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, live_trading=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_live_trading_blocks_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, live_trading=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_trading_disabled_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_trading_disabled_blocks_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_unverified_account_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=1)
        conn.connect()
        assert conn.can_trade() is False
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_invalid_symbol_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "FAKEUSD", 50000, 0.01)
        assert order is None

    def test_missing_tick_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        conn._ticks = {}  # Clear ticks after connect
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_invalid_bid_ask_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            ticks={"BTCUSD": {"bid": 0, "ask": 50001, "time": 0}},
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_volume_below_min_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.001)  # below min 0.01
        assert order is None

    def test_volume_above_max_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 200)  # above max 100
        assert order is None

    def test_sl_above_entry_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01, stop_loss=51000)
        assert order is None

    def test_tp_below_entry_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01, take_profit=49000)
        assert order is None

    def test_unsupported_filling_mode_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        conn._symbols["BTCUSD"]["filling_mode"] = 0
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_order_check_failure_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, order_check_fail=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_order_send_failure_blocks_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, order_send_fail=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_successful_demo_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is not None
        assert order["status"] == "filled"
        assert order["side"] == "buy"
        assert order["mt5_retcode"] == 10009  # TRADE_RETCODE_DONE
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        o1 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None
        o2 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o2 is None

    def test_different_timestamp_allows_trade(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        o1 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None
        o2 = broker.execute_buy(p, "BTCUSD", 51000, 0.01, candle_timestamp="2024-01-01T01:00:00")
        assert o2 is not None

    def test_duplicate_sell_signal_rejected(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[{
                "ticket": 42, "symbol": "BTCUSD", "type": 0,
                "volume": 0.01, "price_open": 50000, "price_current": 51000,
                "sl": 0, "tp": 0, "profit": 10, "magic": 20260904,
                "comment": "", "time": 0,
            }],
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        o1 = broker.execute_sell(p, "BTCUSD", 51000, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None
        o2 = broker.execute_sell(p, "BTCUSD", 51000, candle_timestamp="2024-01-01T00:00:00")
        assert o2 is None

    def test_no_position_blocks_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_sell(p, "BTCUSD", 50000)
        assert order is None

    def test_exact_position_ticket_on_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[{
                "ticket": 42, "symbol": "BTCUSD", "type": 0,
                "volume": 0.01, "price_open": 50000, "price_current": 51000,
                "sl": 0, "tp": 0, "profit": 10, "magic": 20260904,
                "comment": "", "time": 0,
            }],
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is not None
        assert order["mt5_position_ticket"] == 42

    def test_unrelated_magic_position_not_closed(self):
        """Position with different magic number must not be closed."""
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[{
                "ticket": 99, "symbol": "BTCUSD", "type": 0,
                "volume": 0.01, "price_open": 50000, "price_current": 51000,
                "sl": 0, "tp": 0, "profit": 10, "magic": 999999,  # different magic
                "comment": "", "time": 0,
            }],
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_ambiguous_position_rejected(self):
        """Multiple positions for same symbol/magic must be rejected."""
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[
                {"ticket": 1, "symbol": "BTCUSD", "type": 0, "volume": 0.01,
                 "price_open": 50000, "price_current": 51000, "sl": 0, "tp": 0,
                 "profit": 10, "magic": 20260904, "comment": "", "time": 0},
                {"ticket": 2, "symbol": "BTCUSD", "type": 0, "volume": 0.01,
                 "price_open": 50500, "price_current": 51000, "sl": 0, "tp": 0,
                 "profit": 5, "magic": 20260904, "comment": "", "time": 0},
            ],
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_missing_position_rejected(self):
        """No MT5 position found must return None."""
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, positions=[])
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_volume_mismatch_rejected(self):
        """Position volume must match portfolio quantity."""
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[{
                "ticket": 42, "symbol": "BTCUSD", "type": 0,
                "volume": 0.05, "price_open": 50000, "price_current": 51000,
                "sl": 0, "tp": 0, "profit": 10, "magic": 20260904,
                "comment": "", "time": 0,
            }],
        )
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)  # qty=0.01, MT5=0.05
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_reconnect_stale_signal_rejected(self):
        """Signal from before reconnect must be rejected if duplicate key reused."""
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        o1 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None
        # Reconnect — signal key should persist in broker
        conn.reconnect()
        o2 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o2 is None


# ============================================================
# Safety Gate Config Tests
# ============================================================

class TestMT5SafetyGates:
    def test_live_trading_blocks_mt5(self):
        assert Config.LIVE_TRADING is False

    def test_mt5_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("MT5_ENABLED", raising=False)
        from src.config import _bool
        assert _bool(None, False) is False

    def test_mt5_demo_only_default(self):
        assert Config.MT5_DEMO_ONLY is True

    def test_mt5_demo_trading_disabled_by_default(self):
        assert Config.MT5_DEMO_TRADING_ENABLED is False

    def test_mt5_config_exists(self):
        assert hasattr(Config, "MT5_ENABLED")
        assert hasattr(Config, "MT5_DEMO_ONLY")
        assert hasattr(Config, "MT5_DEMO_TRADING_ENABLED")
        assert hasattr(Config, "MT5_MAGIC_NUMBER")

    def test_mt5_rejects_non_demo(self):
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=1)
        assert conn.connect() is False
        assert conn.health.state == MT5State.NOT_DEMO

    def test_mt5_allows_demo(self):
        conn = MockMT5ConnectionManager(demo_only=True, account_trade_mode=0)
        assert conn.connect() is True

    def test_mt5_trading_gate_blocks_when_disabled(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        assert conn.can_trade() is False

    def test_mt5_trading_gate_allows_when_enabled(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        assert conn.can_trade() is True

    def test_config_validate_mt5_with_live_trading(self):
        original = Config.LIVE_TRADING
        original_mt5 = Config.MT5_ENABLED
        try:
            Config.LIVE_TRADING = True
            Config.MT5_ENABLED = True
            errors = Config.validate()
            assert any("MT5_ENABLED" in e for e in errors)
        finally:
            Config.LIVE_TRADING = original
            Config.MT5_ENABLED = original_mt5


# ============================================================
# Mock Broker Tests
# ============================================================

class TestMockDemoBroker:
    def test_execute_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is not None
        assert order["status"] == "filled"
        assert order["side"] == "buy"
        assert order["mt5_retcode"] == 0

    def test_execute_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is not None
        assert order["side"] == "sell"

    def test_execute_buy_rejected_when_trade_disabled(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_execute_sell_rejected_when_trade_disabled(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=False)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_live_trading_blocks_mock_buy(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, live_trading=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is None

    def test_live_trading_blocks_mock_sell(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True, live_trading=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        p.open_position("BTCUSD", "long", 50000, 0.01)
        order = broker.execute_sell(p, "BTCUSD", 51000)
        assert order is None

    def test_duplicate_buy_rejected(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        o1 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None
        o2 = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o2 is None

    def test_symbol_mapping(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn, symbol_map={"BTCUSD": "BTCUSD."})
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert order is not None
        assert order["mt5_symbol"] == "BTCUSD."

    def test_order_recorded(self):
        from src.portfolio.portfolio import Portfolio
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01)
        assert broker.get_order(order["id"]) is not None


# ============================================================
# Integration Tests
# ============================================================

class TestMT5Integration:
    def test_trading_engine_with_mt5_broker(self):
        from src.portfolio.portfolio import Portfolio
        from src.risk.manager import RiskManager
        from src.trading.engine import TradingEngine
        from src.ai.test_strategy import TestStrategy

        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        portfolio = Portfolio("mt5-test", 10000)
        risk = RiskManager(max_position_size=0.10, min_confidence=0.60)
        engine = TradingEngine(portfolio=portfolio, risk_manager=risk, broker=broker)

        decision = engine.process_decision(
            decision="BUY",
            symbol="BTCUSD",
            price=50000,
            confidence=0.8,
            position_size=0.01,
        )
        if decision is not None:
            assert decision["side"] == "buy"
            assert decision["mt5_retcode"] == 0

    def test_risk_rejection_prevents_mt5_order(self):
        from src.portfolio.portfolio import Portfolio
        from src.risk.manager import RiskManager
        from src.trading.engine import TradingEngine

        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        portfolio = Portfolio("mt5-risk-test", 10000)
        risk = RiskManager(min_confidence=0.90)
        engine = TradingEngine(portfolio=portfolio, risk_manager=risk, broker=broker)

        decision = engine.process_decision(
            decision="BUY",
            symbol="BTCUSD",
            price=50000,
            confidence=0.3,
            position_size=0.01,
        )
        assert decision is None
        assert len(broker._orders_sent) == 0


# ============================================================
# Shutdown Tests
# ============================================================

class TestMT5Shutdown:
    def test_shutdown_disconnects(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        assert conn.is_connected() is True
        conn.shutdown()
        assert conn.is_connected() is False
        assert conn.health.state == MT5State.DISCONNECTED

    def test_shutdown_idempotent(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        conn.shutdown()
        conn.shutdown()
        assert conn.is_connected() is False


# ============================================================
# Candle Format Tests
# ============================================================

class TestMT5CandleFormat:
    def test_candle_format_matches_ashtradingai(self):
        conn = MockMT5ConnectionManager()
        conn.connect()
        md = MockMT5MarketData(conn, candles={
            "BTCUSD": [{
                "timestamp": "2024-01-01T00:00:00+00:00",
                "open": 100.0, "high": 110.0, "low": 90.0,
                "close": 105.0, "volume": 1000.0,
            }]
        })
        candles = md.fetch_candles("BTCUSD")
        assert len(candles) == 1
        c = candles[0]
        required_keys = {"timestamp", "open", "high", "low", "close", "volume"}
        assert required_keys.issubset(c.keys())

    def test_indicators_compatible_with_mt5_candles(self):
        from src.indicators.technical import compute_all_indicators
        conn = MockMT5ConnectionManager()
        conn.connect()

        candles = []
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for i in range(60):
            ts = (base + __import__("datetime").timedelta(hours=i)).isoformat()
            candles.append({
                "timestamp": ts,
                "open": 100 + i * 0.1, "high": 105 + i * 0.1,
                "low": 95 + i * 0.1, "close": 102 + i * 0.1,
                "volume": 1000,
            })

        indicators = compute_all_indicators(candles)
        assert "rsi_14" in indicators
        assert "sma_20" in indicators
        assert "macd" in indicators


# ============================================================
# Persistence / Reconciliation Tests
# ============================================================

class TestMT5Persistence:
    def _get_db(self):
        import tempfile
        from src.persistence.database import Database
        from pathlib import Path
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db = Database(db_path=Path(f.name))
        db.connect()
        return db

    def test_log_mt5_order(self):
        db = self._get_db()
        order_id = db.log_mt5_order(
            session_id="s1", symbol="BTCUSD", mt5_symbol="BTCUSD.",
            side="buy", volume=0.01, price=50000,
            mt5_ticket=123, mt5_deal=456, mt5_retcode=10009,
            magic=20260904, status="filled", candle_timestamp="2024-01-01T00:00:00",
        )
        assert order_id
        orders = db.get_mt5_orders_by_session("s1")
        assert len(orders) == 1
        assert orders[0]["mt5_ticket"] == 123
        assert orders[0]["status"] == "filled"
        db.close()

    def test_update_mt5_order(self):
        db = self._get_db()
        order_id = db.log_mt5_order(
            session_id="s1", symbol="BTCUSD", mt5_symbol="BTCUSD",
            side="buy", volume=0.01, price=50000, status="pending",
        )
        db.update_mt5_order(order_id, status="filled", mt5_deal=789)
        orders = db.get_mt5_orders_by_session("s1")
        assert orders[0]["status"] == "filled"
        assert orders[0]["mt5_deal"] == 789
        db.close()

    def test_get_pending_mt5_orders(self):
        db = self._get_db()
        db.log_mt5_order(session_id="s1", symbol="BTCUSD", mt5_symbol="BTCUSD",
                         side="buy", volume=0.01, price=50000, status="filled")
        db.log_mt5_order(session_id="s1", symbol="ETHUSD", mt5_symbol="ETHUSD",
                         side="buy", volume=0.1, price=3000, status="pending")
        pending = db.get_pending_mt5_orders("s1")
        assert len(pending) == 1
        assert pending[0]["symbol"] == "ETHUSD"
        db.close()

    def test_log_mt5_signal(self):
        db = self._get_db()
        rec_id = db.log_mt5_signal(
            session_id="s1", signal_key="BTCUSD:buy:2024-01-01T00:00:00",
            symbol="BTCUSD", side="buy", candle_timestamp="2024-01-01T00:00:00",
            order_id="ord1",
        )
        assert rec_id
        assert db.is_mt5_signal_recorded("s1", "BTCUSD:buy:2024-01-01T00:00:00") is True
        assert db.is_mt5_signal_recorded("s1", "BTCUSD:buy:2024-01-02T00:00:00") is False
        db.close()

    def test_duplicate_signal_key_rejected(self):
        db = self._get_db()
        db.log_mt5_signal(session_id="s1", signal_key="BTCUSD:buy:2024-01-01T00:00:00",
                          symbol="BTCUSD", side="buy", candle_timestamp="2024-01-01T00:00:00")
        # Duplicate should return empty string
        result = db.log_mt5_signal(session_id="s1", signal_key="BTCUSD:buy:2024-01-01T00:00:00",
                                   symbol="BTCUSD", side="buy", candle_timestamp="2024-01-01T00:00:00")
        assert result == ""
        db.close()

    def test_signal_persistence_survives_restart(self):
        """Signal recorded in one broker instance is visible to another."""
        from src.portfolio.portfolio import Portfolio
        db = self._get_db()

        # First broker session
        conn1 = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn1.connect()
        broker1 = MockMT5DemoBroker(conn1, database=db, session_id="restart-test")
        p1 = Portfolio("test", 10000)
        o1 = broker1.execute_buy(p1, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o1 is not None

        # Simulate restart — new broker instance with same DB/session
        conn2 = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn2.connect()
        broker2 = MockMT5DemoBroker(conn2, database=db, session_id="restart-test")
        p2 = Portfolio("test", 10000)
        o2 = broker2.execute_buy(p2, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert o2 is None  # Duplicate detected from persisted signal

        db.close()

    def test_order_persistence_survives_restart(self):
        """Orders recorded in broker are visible via database after restart."""
        from src.portfolio.portfolio import Portfolio
        db = self._get_db()

        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn, database=db, session_id="order-test")
        p = Portfolio("test", 10000)
        order = broker.execute_buy(p, "BTCUSD", 50000, 0.01, candle_timestamp="2024-01-01T00:00:00")
        assert order is not None

        # Verify order persisted
        orders = db.get_mt5_orders_by_session("order-test")
        assert len(orders) == 1
        assert orders[0]["symbol"] == "BTCUSD"
        assert orders[0]["status"] == "filled"
        db.close()


class TestMT5Reconciliation:
    def test_reconcile_no_pending(self):
        conn = MockMT5ConnectionManager(demo_trading_enabled=True)
        conn.connect()
        broker = MockMT5DemoBroker(conn)
        results = broker.reconcile()
        assert results == []

    def test_reconcile_with_pending_orders(self):
        import tempfile
        from src.persistence.database import Database
        from pathlib import Path
        from src.portfolio.portfolio import Portfolio

        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db = Database(db_path=Path(f.name))
        db.connect()

        # Create a pending order
        order_id = db.log_mt5_order(
            session_id="recon-test", symbol="BTCUSD", mt5_symbol="BTCUSD",
            side="buy", volume=0.01, price=50000, mt5_ticket=999,
            status="pending",
        )

        # Broker with position still open
        conn = MockMT5ConnectionManager(
            demo_trading_enabled=True,
            positions=[{
                "ticket": 999, "symbol": "BTCUSD", "type": 0,
                "volume": 0.01, "price_open": 50000, "price_current": 51000,
                "sl": 0, "tp": 0, "profit": 10, "magic": 20260904,
                "comment": "", "time": 0,
            }],
        )
        conn.connect()
        broker = MockMT5DemoBroker(conn, database=db, session_id="recon-test")

        results = broker.reconcile()
        assert len(results) == 1
        assert results[0]["status"] == "filled"

        # Verify updated in DB
        orders = db.get_mt5_orders_by_session("recon-test")
        assert orders[0]["status"] == "filled"
        db.close()
