"""Tests for M17 Android Trading Terminal.

Tests cover:
- Terminal API endpoints
- Terminal commands
- Session management
- Risk override
- Mode switching
- Backtest integration
- Journal integration
"""
import pytest
import time
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Terminal API Tests ────────────────────────────────────────────────

class TestTerminalAPI:
    """Test terminal API endpoints."""

    def test_terminal_dashboard_returns_all_sections(self):
        from api_terminal import get_terminal_dashboard
        import asyncio
        result = asyncio.run(get_terminal_dashboard())
        assert "mode" in result
        assert "phone" in result
        assert "engine" in result
        assert "strategy" in result
        assert "risk" in result
        assert "positions" in result
        assert "pnl" in result
        assert "last_ai_decision" in result
        assert "timestamp" in result

    def test_terminal_mode_returns_safety_status(self):
        from api_terminal import get_trading_mode
        import asyncio
        result = asyncio.run(get_trading_mode())
        assert "mode" in result
        assert "allowed_modes" in result
        assert "live_allowed" in result
        assert "live_requires_confirmation" in result
        assert "safety" in result

    def test_terminal_mode_switch_rejects_live_without_confirmation(self):
        from api_terminal import switch_trading_mode, ModeSwitchRequest
        import asyncio
        request = ModeSwitchRequest(target_mode="live", confirmation="")
        result = asyncio.run(switch_trading_mode(request))
        assert result["status"] == "error"
        assert "live" in result["message"].lower() or "confirmation" in result["message"].lower()

    def test_terminal_mode_switch_allows_paper(self):
        from api_terminal import switch_trading_mode, ModeSwitchRequest
        import asyncio
        request = ModeSwitchRequest(target_mode="paper")
        result = asyncio.run(switch_trading_mode(request))
        assert result["status"] == "switched"
        assert result["current_mode"] == "paper"

    def test_terminal_commands_list(self):
        from api_terminal import list_terminal_commands
        import asyncio
        result = asyncio.run(list_terminal_commands())
        assert "commands" in result
        assert len(result["commands"]) > 0
        cmd_names = [cmd["name"] for cmd in result["commands"]]
        assert "help" in cmd_names
        assert "status" in cmd_names
        assert "start" in cmd_names
        assert "stop" in cmd_names
        assert "kill" in cmd_names

    def test_terminal_execute_help_command(self):
        from api_terminal import execute_terminal_command, TerminalCommandRequest
        import asyncio
        request = TerminalCommandRequest(command="help")
        result = asyncio.run(execute_terminal_command(request))
        assert result["status"] == "ok"
        assert "commands" in result["message"].lower() or "help" in result["message"].lower()

    def test_terminal_execute_status_command(self):
        from api_terminal import execute_terminal_command, TerminalCommandRequest
        import asyncio
        request = TerminalCommandRequest(command="status")
        result = asyncio.run(execute_terminal_command(request))
        assert "session" in result

    def test_terminal_execute_unknown_command(self):
        from api_terminal import execute_terminal_command, TerminalCommandRequest
        import asyncio
        request = TerminalCommandRequest(command="nonexistent")
        result = asyncio.run(execute_terminal_command(request))
        assert result["status"] == "error"
        assert "unknown" in result["message"].lower()

    def test_terminal_heartbeat(self):
        from api_terminal import terminal_heartbeat
        import asyncio
        result = asyncio.run(terminal_heartbeat())
        assert result["status"] == "ok"
        assert "timestamp" in result
        assert "session_active" in result


# ── Session Management Tests ─────────────────────────────────────────

class TestSessionManagement:
    """Test session control endpoints."""

    def test_session_status_returns_expected_fields(self):
        from api_terminal import get_session_status
        import asyncio
        result = asyncio.run(get_session_status())
        assert "status" in result
        assert "session" in result
        assert "activity" in result

    def test_session_control_start(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="start")
        result = asyncio.run(control_session(request))
        assert result["status"] == "started"
        assert "session_id" in result

    def test_session_control_stop(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="stop")
        result = asyncio.run(control_session(request))
        assert result["status"] == "stopped"

    def test_session_control_pause(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="pause")
        result = asyncio.run(control_session(request))
        assert result["status"] == "paused"

    def test_session_control_resume(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="resume")
        result = asyncio.run(control_session(request))
        assert result["status"] == "resumed"

    def test_session_control_emergency_stop(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="emergency_stop")
        result = asyncio.run(control_session(request))
        assert result["status"] == "emergency_stop"

    def test_session_control_unknown_action(self):
        from api_terminal import control_session, SessionControlRequest
        import asyncio
        request = SessionControlRequest(action="unknown")
        with pytest.raises(Exception):
            asyncio.run(control_session(request))

    def test_session_start_with_mode(self):
        from api_terminal import start_session, SessionStartRequest
        import asyncio
        request = SessionStartRequest(mode="paper")
        result = asyncio.run(start_session(request))
        assert result["status"] == "started"
        assert result["mode"] == "paper"

    def test_session_start_rejects_live(self):
        from api_terminal import start_session, SessionStartRequest
        import asyncio
        request = SessionStartRequest(mode="live")
        result = asyncio.run(start_session(request))
        assert result["status"] == "error"
        assert "live" in result["message"].lower()


# ── Risk Override Tests ──────────────────────────────────────────────

class TestRiskOverride:
    """Test risk management endpoints."""

    def test_risk_status_returns_expected_fields(self):
        from api_terminal import get_risk_status
        import asyncio
        result = asyncio.run(get_risk_status())
        assert "kill_switch" in result
        assert "trades_today" in result
        assert "daily_pnl" in result
        assert "consecutive_losses" in result
        assert "max_positions" in result
        assert "open_positions" in result

    def test_risk_kill_switch_toggles(self):
        from api_terminal import toggle_kill_switch
        import asyncio
        result = asyncio.run(toggle_kill_switch())
        assert result["status"] == "toggled"

    def test_risk_check_returns_decision(self):
        from api_terminal import check_risk, RiskCheckRequest
        import asyncio
        request = RiskCheckRequest(
            symbol="EURUSD",
            direction="LONG",
            confidence=0.8,
            entry=1.1000
        )
        result = asyncio.run(check_risk(request))
        assert "allowed" in result
        assert "decision" in result
        assert "audit" in result


# ── Backtest Integration Tests ───────────────────────────────────────

class TestBacktestIntegration:
    """Test backtest endpoints."""

    def test_backtest_run_returns_results(self):
        from api_terminal import run_backtest, BacktestRequest
        import asyncio
        request = BacktestRequest(
            strategy_id="ema_trend",
            symbol="EURUSD",
            timeframe="H1",
            candles=500
        )
        result = asyncio.run(run_backtest(request))
        assert result["status"] == "completed"
        assert "results" in result
        assert "net_pnl" in result["results"]
        assert "win_rate" in result["results"]

    def test_backtest_walk_forward_returns_results(self):
        from api_terminal import run_walk_forward, WalkForwardRequest
        import asyncio
        request = WalkForwardRequest(
            strategy_id="ema_crossover",
            symbol="EURUSD",
            timeframe="H1"
        )
        result = asyncio.run(run_walk_forward(request))
        assert result["status"] == "completed"
        assert "results" in result
        assert "in_sample_sharpe" in result["results"]
        assert "out_of_sample_sharpe" in result["results"]


# ── Journal Integration Tests ────────────────────────────────────────

class TestJournalIntegration:
    """Test journal endpoints."""

    def test_journal_entries_returns_list(self):
        from api_terminal import get_journal_entries
        import asyncio
        result = asyncio.run(get_journal_entries())
        assert "entries" in result
        assert "total" in result
        assert isinstance(result["entries"], list)

    def test_journal_entry_returns_none_for_nonexistent(self):
        from api_terminal import get_journal_entry
        import asyncio
        result = asyncio.run(get_journal_entry("nonexistent_id"))
        assert result["entry"] is None


# ── Health Endpoint Tests ────────────────────────────────────────────

class TestHealthEndpoints:
    """Test health endpoints."""

    def test_health_returns_healthy(self):
        from api_terminal import get_health
        import asyncio
        result = asyncio.run(get_health())
        assert result["status"] == "healthy"
        assert "broker" in result
        assert "ai" in result

    def test_health_detailed_returns_components(self):
        from api_terminal import get_detailed_health
        import asyncio
        result = asyncio.run(get_detailed_health())
        assert result["overall"] == "healthy"
        assert "components" in result
        assert "broker" in result["components"]
        assert "ai" in result["components"]


# ── Strategy Endpoint Tests ──────────────────────────────────────────

class TestStrategyEndpoints:
    """Test strategy endpoints."""

    def test_strategies_list_returns_strategies(self):
        from api_terminal import list_strategies
        import asyncio
        result = asyncio.run(list_strategies())
        assert "strategies" in result
        assert "total" in result
        assert "families" in result

    def test_strategies_select_returns_selection(self):
        from api_terminal import select_strategies, StrategySelectRequest
        import asyncio
        request = StrategySelectRequest(
            symbol="EURUSD",
            timeframe="H1"
        )
        result = asyncio.run(select_strategies(request))
        assert "selected" in result
        assert "strategies" in result


# ── Signal Validation Tests ──────────────────────────────────────────

class TestSignalValidation:
    """Test signal validation endpoints."""

    def test_signal_validate_returns_decision(self):
        from api_terminal import validate_signal, SignalValidateRequest
        import asyncio
        request = SignalValidateRequest(
            signal_id="test_signal_001",
            symbol="EURUSD",
            direction="LONG",
            confidence=0.8,
            entry=1.1000
        )
        result = asyncio.run(validate_signal(request))
        assert "approved" in result
        assert "decision" in result
        assert "confidence" in result
        assert "reasoning" in result
        assert "risk_flags" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
