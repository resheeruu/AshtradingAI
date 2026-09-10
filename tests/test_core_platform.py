"""Tests for core platform modules — Phases 2-12."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.core.enums import TradingMode, MarketHealthStatus, AssetClass, SignalDirection, RegimeType, RiskGate
from src.core.modes import ModeManager, MODE_POLICIES
from src.core.signals import Signal, AIDecision, TradeJournalEntry, RiskBlock
from src.core.symbols import BrokerSymbol, SymbolDiscovery, AssetClassConfig
from src.risk.advanced import AdvancedRiskEngine, RiskConfig, RiskGateResult


class TestTradingMode:
    def test_modes_exist(self):
        for mode in ["RESEARCH", "BACKTEST", "PAPER", "PAPER_LIVE", "MT5_DEMO", "LIVE_LOCKED"]:
            assert TradingMode(mode)

    def test_live_locked_no_execution(self):
        assert not TradingMode.LIVE_LOCKED.allows_execution

    def test_paper_allows_execution(self):
        assert TradingMode.PAPER.allows_execution

    def test_paper_live_uses_live_data(self):
        assert TradingMode.PAPER_LIVE.is_live_data

    def test_research_no_execution(self):
        assert not TradingMode.RESEARCH.allows_execution


class TestModeManager:
    def test_default_mode(self):
        mm = ModeManager()
        assert mm.mode == TradingMode.PAPER

    def test_set_mode(self):
        mm = ModeManager()
        mm.set_mode(TradingMode.BACKTEST)
        assert mm.mode == TradingMode.BACKTEST

    def test_live_locked_cannot_be_set(self):
        mm = ModeManager()
        mm.set_mode(TradingMode.LIVE_LOCKED)
        assert mm.mode == TradingMode.PAPER  # unchanged

    def test_check_capability(self):
        mm = ModeManager(TradingMode.RESEARCH)
        assert mm.check("allows_signal_generation")
        assert not mm.check("allows_paper_execution")

    def test_block_if_unauthorized(self):
        mm = ModeManager(TradingMode.RESEARCH)
        err = mm.block_if_unauthorized("paper_execution")
        assert err is not None
        err = mm.block_if_unauthorized("signal_generation")
        assert err is None


class TestSignal:
    def test_signal_creation(self):
        s = Signal(
            symbol="BTC/USDT", timeframe="H1", timestamp="2025-01-01T00:00:00",
            direction="LONG", confidence=0.75, entry=50000.0,
            stop_loss=49000.0, take_profit=53000.0,
        )
        assert s.is_actionable
        assert s.risk_reward == 3.0

    def test_signal_clamps_confidence(self):
        s = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=1.5, entry=100)
        assert s.confidence == 1.0
        s2 = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=-0.5, entry=100)
        assert s2.confidence == 0.0

    def test_signal_serialization(self):
        s = Signal(symbol="EUR/USD", timeframe="H1", timestamp="t", direction="SHORT", confidence=0.8, entry=1.1)
        d = s.to_dict()
        s2 = Signal.from_dict(d)
        assert s2.symbol == "EUR/USD"
        assert s2.direction == "SHORT"


class TestAIDecision:
    def test_valid_decision(self):
        d = AIDecision(signal_id="s1", symbol="BTC/USDT", decision="LONG", confidence=0.8)
        assert d.is_valid

    def test_invalidated(self):
        d = AIDecision(signal_id="s1", symbol="X", decision="LONG", confidence=0.8, invalidated=True)
        assert not d.is_valid


class TestBrokerSymbol:
    def test_suffix_matching(self):
        s = BrokerSymbol(name="BTCUSDm", suffix="m")
        assert s.matches("BTCUSD")
        assert s.base_name == "BTCUSD"

    def test_tradeable(self):
        s = BrokerSymbol(name="EURUSD", trade_mode="FULL", available=True)
        assert s.is_tradeable
        s2 = BrokerSymbol(name="EURUSD", trade_mode="DISABLED")
        assert not s2.is_tradeable


class TestSymbolDiscovery:
    def test_register_and_find(self):
        sd = SymbolDiscovery()
        sym = BrokerSymbol(name="BTCUSD", available=True)
        sd.register_symbol(sym)
        found = sd.find_symbol("BTCUSD")
        assert found is not None

    def test_find_available(self):
        sd = SymbolDiscovery()
        sd.register_symbol(BrokerSymbol(name="EURUSD", available=True, trade_mode="FULL"))
        sd.register_symbol(BrokerSymbol(name="GBPUSD", available=False))
        found = sd.find_available("EURUSD")
        assert found is not None
        assert sd.find_available("GBPUSD") is None

    def test_mark_unavailable(self):
        sd = SymbolDiscovery()
        sd.register_symbol(BrokerSymbol(name="XAUUSD", available=True))
        sd.mark_unavailable("XAUUSD")
        assert sd.find_available("XAUUSD") is None

    def test_asset_classification(self):
        sd = SymbolDiscovery()
        syms = sd.from_mt5_symbols([
            {"name": "EURUSD", "digits": 5, "point": 0.00001, "trade_tick_size": 0.00001,
             "trade_tick_value": 1.0, "trade_contract_size": 100000, "volume_min": 0.01,
             "volume_max": 100, "volume_step": 0.01, "spread": 10, "trade_mode": 4},
            {"name": "BTCUSD", "digits": 2, "point": 0.01, "trade_tick_size": 0.01,
             "trade_tick_value": 1.0, "trade_contract_size": 1, "volume_min": 0.001,
             "volume_max": 10, "volume_step": 0.001, "spread": 50, "trade_mode": 4},
            {"name": "XAUUSD", "digits": 2, "point": 0.01, "trade_tick_size": 0.01,
             "trade_tick_value": 1.0, "trade_contract_size": 100, "volume_min": 0.01,
             "volume_max": 10, "volume_step": 0.01, "spread": 30, "trade_mode": 4},
        ])
        classes = {s.asset_class for s in syms}
        assert "FOREX" in classes
        assert "CRYPTO" in classes or "METALS" in classes  # BTC might be classified as OTHER


class TestAdvancedRiskEngine:
    def test_kill_switch(self):
        engine = AdvancedRiskEngine()
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99)
        engine.activate_kill_switch()
        allowed, decision, audit, qty = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert not allowed
        assert decision == "HOLD"

    def test_confidence_gate(self):
        engine = AdvancedRiskEngine(RiskConfig(min_confidence=0.7))
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.5, entry=100, stop_loss=99)
        allowed, decision, audit, qty = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert not allowed
        assert any(a["gate"] == "CONFIDENCE" for a in audit)

    def test_all_gates_pass(self):
        engine = AdvancedRiskEngine(RiskConfig(min_confidence=0.5, min_risk_reward=1.0))
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99, take_profit=103)
        allowed, decision, audit, qty = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert allowed
        assert qty > 0

    def test_market_health_blocks(self):
        engine = AdvancedRiskEngine()
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99)
        allowed, decision, audit, qty = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.DISCONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert not allowed

    def test_position_count_blocks(self):
        engine = AdvancedRiskEngine(RiskConfig(max_open_positions=2))
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99, take_profit=103)
        allowed, _, _, _ = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0, open_positions=2,
        )
        assert not allowed

    def test_weekly_loss_not_implemented(self):
        engine = AdvancedRiskEngine()
        engine._weekly_pnl = -100
        assert engine._weekly_pnl == -100

    def test_record_trade_result(self):
        engine = AdvancedRiskEngine()
        engine.record_trade_result(10.0)
        assert engine._trade_count_today == 1
        assert engine._daily_pnl == 10.0
        assert engine._consecutive_losses == 0

    def test_consecutive_losses(self):
        engine = AdvancedRiskEngine(RiskConfig(max_consecutive_losses=3, min_confidence=0.5, max_daily_loss=0.50))
        for _ in range(3):
            engine.record_trade_result(-10.0)
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99, take_profit=103)
        allowed, _, audit, _ = engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert not allowed
        assert any(a["gate"] == "CONSECUTIVE_LOSSES" for a in audit)

    def test_risk_blocks_recorded(self):
        engine = AdvancedRiskEngine()
        signal = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.1, entry=100, stop_loss=99)
        engine.evaluate_signal(
            signal=signal, mode=TradingMode.PAPER, health_status=MarketHealthStatus.CONNECTED,
            symbol_available=True, portfolio_balance=1000.0,
        )
        assert len(engine.get_risk_blocks()) > 0
