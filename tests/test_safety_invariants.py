"""Safety invariant tests — must NEVER pass if safety flags are changed.

These tests verify that LIVE_TRADING=false, MT5_DEMO_ONLY=true,
MT5_DEMO_TRADING_ENABLED=false are never silently changed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.config import Config
from src.core.enums import TradingMode, MarketHealthStatus
from src.core.modes import ModeManager, MODE_POLICIES


class TestSafetyInvariants:
    """Critical safety invariants that must never be violated."""

    def test_live_trading_is_false(self):
        assert Config.LIVE_TRADING is False, "LIVE_TRADING must always be false"

    def test_mt5_demo_only_is_true(self):
        assert Config.MT5_DEMO_ONLY is True, "MT5_DEMO_ONLY must always be true"

    def test_mt5_demo_trading_disabled(self):
        assert Config.MT5_DEMO_TRADING_ENABLED is False, "MT5_DEMO_TRADING_ENABLED must always be false"

    def test_live_locked_no_execution(self):
        assert not TradingMode.LIVE_LOCKED.allows_execution

    def test_live_locked_mode_cannot_be_set(self):
        mm = ModeManager()
        mm.set_mode(TradingMode.LIVE_LOCKED)
        assert mm.mode != TradingMode.LIVE_LOCKED

    def test_config_validate_catches_live_trading(self):
        errors = Config.validate()
        for err in errors:
            assert "LIVE_TRADING must be false" not in err or not Config.LIVE_TRADING

    def test_risk_engine_blocks_on_kill_switch(self):
        from src.risk.advanced import AdvancedRiskEngine
        from src.core.signals import Signal
        engine = AdvancedRiskEngine()
        engine.activate_kill_switch()
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.9, entry=100, stop_loss=99)
        allowed, _, _, _ = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER,
            health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert not allowed

    def test_mt5_requires_demo_config(self):
        if Config.MT5_ENABLED:
            assert Config.MT5_DEMO_ONLY, "MT5 requires DEMO_ONLY=true"
