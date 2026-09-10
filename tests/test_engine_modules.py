"""Tests for AI ensemble, reconciliation, watchdog, analytics, strategy eval."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.ai.ensemble import AIEnsemble, EnsembleResult
from src.ai.failover import ProviderFailover
from src.core.signals import AIDecision, Signal
from src.core.enums import AIProviderStatus
from src.engine.reconciliation import ReconciliationEngine, ReconciliationWarning
from src.engine.watchdog import EngineWatchdog, WatchdogStatus
from src.engine.analytics import PerformanceAnalyzer, PerformanceMetrics
from src.engine.strategy_eval import StrategyEvaluator, StrategyRating, rank_strategies
from src.engine.news_safety import NewsSafetyLayer, NewsEvent
from src.strategy.spec import (
    StrategySpec, EMATrendStrategy, RSIMeanReversion, MACDCrossover,
    BollingerBreakout, get_default_strategies,
)
from src.trading.paper.broker_v2 import PaperBrokerV2
from src.portfolio.portfolio import Portfolio


class TestAIEnsemble:
    def test_empty_ensemble(self):
        e = AIEnsemble()
        r = e.compute_consensus()
        assert r.decision == "HOLD"

    def test_consensus(self):
        e = AIEnsemble()
        e.add_opinion("p1", AIDecision(signal_id="s1", symbol="X", decision="LONG", confidence=0.8))
        e.add_opinion("p2", AIDecision(signal_id="s2", symbol="X", decision="LONG", confidence=0.7))
        e.add_opinion("p3", AIDecision(signal_id="s3", symbol="X", decision="HOLD", confidence=0.5))
        r = e.compute_consensus()
        assert r.decision == "LONG"
        assert r.agreement_score > 0.5

    def test_conflict_detection(self):
        e = AIEnsemble()
        e.add_opinion("p1", AIDecision(signal_id="s1", symbol="X", decision="LONG", confidence=0.8))
        e.add_opinion("p2", AIDecision(signal_id="s2", symbol="X", decision="SHORT", confidence=0.8))
        r = e.compute_consensus()
        assert r.conflict_score > 0.3

    def test_invalidated_by_low_agreement(self):
        e = AIEnsemble(min_agreement=0.9)
        e.add_opinion("p1", AIDecision(signal_id="s1", symbol="X", decision="LONG", confidence=0.8))
        e.add_opinion("p2", AIDecision(signal_id="s2", symbol="X", decision="SHORT", confidence=0.8))
        e.add_opinion("p3", AIDecision(signal_id="s3", symbol="X", decision="HOLD", confidence=0.5))
        r = e.compute_consensus()
        assert r.invalidated


class TestProviderFailover:
    def test_register_and_get(self):
        f = ProviderFailover()
        f.register("p1", "provider_obj")
        p = f.get_active_provider()
        assert p == "provider_obj"

    def test_failover_after_failures(self):
        f = ProviderFailover(max_failures=2)
        f.register("p1", "obj1")
        f.record_failure("p1")
        f.record_failure("p1")
        p = f.get_active_provider()
        assert p is None
        assert f.all_failed


class TestReconciliationEngine:
    def test_clean_reconciliation(self):
        r = ReconciliationEngine()
        warnings = r.reconcile(
            internal_positions={"EURUSD": {"quantity": 0.1}},
            broker_positions={"EURUSD": {"quantity": 0.1}},
        )
        assert len(warnings) == 0

    def test_missing_position(self):
        r = ReconciliationEngine()
        warnings = r.reconcile(
            internal_positions={"EURUSD": {"quantity": 0.1}},
            broker_positions={},
        )
        assert len(warnings) == 1
        assert warnings[0].warning_type == "MISSING_POSITION"

    def test_quantity_mismatch(self):
        r = ReconciliationEngine()
        warnings = r.reconcile(
            internal_positions={"EURUSD": {"quantity": 0.1}},
            broker_positions={"EURUSD": {"quantity": 0.2}},
        )
        assert len(warnings) == 1
        assert warnings[0].warning_type == "QUANTITY_MISMATCH"

    def test_status(self):
        r = ReconciliationEngine()
        r.reconcile({"X": {"quantity": 1}}, {"Y": {"quantity": 1}})
        status = r.get_status()
        assert status["total_warnings"] > 0


class TestWatchdog:
    def test_healthy(self):
        w = EngineWatchdog()
        w.register("engine")
        w.heartbeat("engine")
        assert w.overall == WatchdogStatus.HEALTHY

    def test_failed_blocks_trades(self):
        w = EngineWatchdog()
        w.register("engine")
        w.record_error("engine", "crash")
        assert w.overall == WatchdogStatus.FAILED
        assert w.trades_blocked

    def test_degraded(self):
        w = EngineWatchdog()
        w.register("a")
        w.register("b")
        w.heartbeat("a")
        w.record_degraded("b", "slow")
        assert w.overall == WatchdogStatus.DEGRADED


class TestPerformanceAnalyzer:
    def test_empty_trades(self):
        a = PerformanceAnalyzer()
        m = a.analyze([])
        assert m.trade_count == 0

    def test_winning_trades(self):
        a = PerformanceAnalyzer(starting_balance=1000)
        trades = [{"pnl": 10}, {"pnl": 20}, {"pnl": -5}, {"pnl": 15}]
        m = a.analyze(trades)
        assert m.trade_count == 4
        assert m.net_pnl == 40
        assert m.win_rate == 0.75

    def test_max_drawdown(self):
        a = PerformanceAnalyzer(starting_balance=100)
        trades = [{"pnl": 50}, {"pnl": -80}, {"pnl": 30}]
        m = a.analyze(trades)
        assert m.max_drawdown > 0


class TestStrategyEvaluator:
    def test_insufficient_data(self):
        e = StrategyEvaluator(min_trades=30)
        trades = [{"pnl": 10} for _ in range(5)]
        r = e.evaluate("test", trades)
        assert "INSUFFICIENT_DATA" in r.warnings

    def test_overfit_detection(self):
        e = StrategyEvaluator(min_trades=10)
        trades = [{"pnl": 100} for _ in range(20)]
        r = e.evaluate("test", trades)
        assert "OVERFIT_WARNING" in r.warnings


class TestStrategySpec:
    def test_valid_signal(self):
        spec = StrategySpec(strategy_id="test", name="Test", supported_timeframes=["H1"])
        sig = Signal(symbol="X", timeframe="H1", timestamp="t", direction="LONG", confidence=0.8, entry=100, stop_loss=99, strategy_id="test")
        valid, reason = spec.validate_signal(sig)
        assert valid

    def test_wrong_timeframe(self):
        spec = StrategySpec(strategy_id="test", name="Test", supported_timeframes=["H1"])
        sig = Signal(symbol="X", timeframe="M5", timestamp="t", direction="LONG", confidence=0.8, entry=100, strategy_id="test")
        valid, reason = spec.validate_signal(sig)
        assert not valid


class TestDefaultStrategies:
    def test_all_exist(self):
        strategies = get_default_strategies()
        assert len(strategies) >= 4
        ids = [s.strategy_id for s in strategies]
        assert "ema_trend" in ids
        assert "rsi_reversion" in ids


class TestPaperBrokerV2:
    def test_buy_and_sell(self):
        p = Portfolio(ai_id="test", starting_balance=1000)
        broker = PaperBrokerV2(fee=0.001, slippage=0.0005, spread=0.0002, rejection_probability=0.0, partial_fill_probability=0.0)
        order = broker.execute_buy(p, "EURUSD", 1.1, 100, stop_loss=1.09, take_profit=1.12)
        assert order is not None
        assert order["status"] == "filled"
        assert len(p.positions) == 1
        order2 = broker.execute_sell(p, "EURUSD", 1.11)
        assert order2 is not None
        assert "pnl" in order2


class TestNewsSafetyLayer:
    def test_unavailable(self):
        n = NewsSafetyLayer()
        assert not n.available
        safe, reason = n.check_symbol_safe("EURUSD")
        assert safe
        assert reason == "no_news_filtering"
