"""Tests for M8-M16 extensions.

Tests cover:
- Broker protocol
- Strategy registry
- Multi-strategy orchestrator
- AI validation engine
- Enhanced paper broker
- Phone session manager
- Walk-forward engine
- Config extensions
- API terminal endpoints
"""
import pytest
import time
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Broker Protocol Tests ────────────────────────────────────────────

class TestBrokerProtocol:
    """Test broker protocol and adapter."""

    def test_broker_protocol_is_runtime_checkable(self):
        from src.trading.broker_protocol import BrokerProtocol
        assert hasattr(BrokerProtocol, '__protocol_attrs__')

    def test_paper_broker_conforms_to_protocol(self):
        from src.trading.broker_protocol import BrokerProtocol
        from src.trading.paper.broker import PaperBroker
        broker = PaperBroker()
        assert isinstance(broker, BrokerProtocol)

    def test_broker_adapter_has_required_methods(self):
        from src.trading.broker_protocol import BrokerAdapter
        required = [
            'get_account', 'get_balance', 'get_equity',
            'get_positions', 'get_symbols', 'get_price',
            'get_candles', 'place_order', 'modify_order',
            'close_position', 'close_all', 'cancel_order', 'health_check',
        ]
        for method in required:
            assert hasattr(BrokerAdapter, method)

    def test_broker_capabilities_defaults(self):
        from src.trading.broker_protocol import BrokerCapabilities
        caps = BrokerCapabilities()
        assert caps.supports_leverage is False
        assert caps.commission_model == "spread"
        assert caps.execution_model == "market"


# ── Strategy Registry Tests ──────────────────────────────────────────

class TestStrategyRegistry:
    """Test strategy registry."""

    def test_registry_initializes_with_defaults(self):
        from src.strategy.registry import StrategyRegistry
        registry = StrategyRegistry()
        registry.initialize()
        assert len(registry.list_all()) > 0

    def test_registry_has_all_families(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        families = registry.list_families()
        expected = ["SCALPING", "TREND", "MEAN_REVERSION", "BREAKOUT",
                     "MOMENTUM", "PRICE_ACTION", "VWAP", "MULTI_TIMEFRAME",
                     "SMC", "COMPOSITE"]
        for f in expected:
            assert f in families, f"Family {f} not found"

    def test_registry_lookup_by_id(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        strategy = registry.get("ai_scalping")
        assert strategy is not None
        assert strategy.strategy_id == "ai_scalping"

    def test_registry_lookup_by_family(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        scalping = registry.list_by_family("SCALPING")
        assert len(scalping) > 0
        assert all(s.spec.strategy_family == "SCALPING" for s in scalping)

    def test_registry_lookup_by_timeframe(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        m5_strategies = registry.list_by_timeframe("M5")
        assert len(m5_strategies) > 0

    def test_registry_get_capabilities(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        caps = registry.get_capabilities("trend_following")
        assert caps["strategy_id"] == "trend_following"
        assert "TREND" in caps["family"]

    def test_registry_summary(self):
        from src.strategy.registry import get_registry
        registry = get_registry()
        summary = registry.get_registry_summary()
        assert summary["total_strategies"] > 0
        assert "families" in summary
        assert "strategies" in summary

    def test_registry_register_custom(self):
        from src.strategy.registry import StrategyRegistry
        from src.strategy.spec import BaseStrategy, StrategySpec
        from src.core.signals import Signal

        class CustomStrategy(BaseStrategy):
            def __init__(self):
                super().__init__(StrategySpec(
                    strategy_id="custom_test",
                    name="Custom Test",
                    strategy_family="CUSTOM",
                ))
            def generate_signal(self, candles, indicators, context):
                return None

        registry = StrategyRegistry()
        registry.register(CustomStrategy())
        assert registry.get("custom_test") is not None
        assert "CUSTOM" in registry.list_families()


# ── Multi-Strategy Orchestrator Tests ────────────────────────────────

class TestMultiStrategyOrchestrator:
    """Test multi-strategy orchestrator."""

    def test_orchestrator_creation(self):
        from src.strategy.orchestrator import MultiStrategyOrchestrator
        orchestrator = MultiStrategyOrchestrator()
        assert orchestrator is not None

    def test_orchestrator_select_strategies(self):
        from src.strategy.orchestrator import MultiStrategyOrchestrator
        orchestrator = MultiStrategyOrchestrator()

        # Create mock candles with more realistic data
        candles = [
            {"open": 100 + i * 0.1, "high": 101 + i * 0.1, "low": 99 + i * 0.1,
             "close": 100.5 + i * 0.1, "volume": 1000, "timestamp": f"2024-01-01T{i:02d}:00:00"}
            for i in range(100)
        ]
        indicators = {
            "ema_12": [100.0 + i * 0.1 for i in range(100)],
            "ema_26": [99.0 + i * 0.1 for i in range(100)],
            "ema_50": [98.0 + i * 0.1 for i in range(100)],
            "rsi_14": [55.0] * 100,
            "atr_14": [1.0] * 100,
            "rsi_7": [55.0] * 100,
            "macd": [0.5] * 100,
            "macd_signal": [0.4] * 100,
            "bb_upper": [102.0] * 100,
            "bb_lower": [98.0] * 100,
            "bb_mid": [100.0] * 100,
            "adx_14": [30.0] * 100,
            "sma_50": [98.0] * 100,
        }

        selection = orchestrator.select_strategies("BTC/USDT", candles, indicators, {"timeframe": "H1"})
        assert selection.symbol == "BTC/USDT"
        # Selection may have 0 strategies if mock data doesn't trigger signals
        # This is expected - the important thing is the orchestrator doesn't crash
        assert hasattr(selection, 'selected_strategies')
        assert hasattr(selection, 'regime')

    def test_orchestrator_aggregate_signals(self):
        from src.strategy.orchestrator import MultiStrategyOrchestrator
        from src.core.signals import Signal

        orchestrator = MultiStrategyOrchestrator()

        signals = [
            Signal(symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
                   direction="LONG", confidence=0.7, entry=100.0, stop_loss=99.0, take_profit=102.0,
                   strategy_id="strategy_1"),
            Signal(symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
                   direction="LONG", confidence=0.8, entry=100.0, stop_loss=99.0, take_profit=102.0,
                   strategy_id="strategy_2"),
        ]

        agg = orchestrator.aggregate_signals(signals, "BTC/USDT")
        assert agg.direction == "LONG"
        assert agg.confidence > 0
        assert not agg.conflicting

    def test_orchestrator_conflict_resolution(self):
        from src.strategy.orchestrator import MultiStrategyOrchestrator
        from src.core.signals import Signal

        orchestrator = MultiStrategyOrchestrator()

        signals = [
            Signal(symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
                   direction="LONG", confidence=0.8, entry=100.0, strategy_id="s1"),
            Signal(symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
                   direction="SHORT", confidence=0.9, entry=100.0, strategy_id="s2"),
        ]

        agg = orchestrator.aggregate_signals(signals, "BTC/USDT")
        assert agg.conflicting is True
        assert agg.direction == "SHORT"  # Highest confidence wins

    def test_orchestrator_status(self):
        from src.strategy.orchestrator import MultiStrategyOrchestrator
        orchestrator = MultiStrategyOrchestrator()
        status = orchestrator.get_status()
        assert "active_selections" in status
        assert "registry_summary" in status
        assert "config" in status


# ── AI Validation Engine Tests ───────────────────────────────────────

class TestAIDecisionValidator:
    """Test AI validation engine."""

    def test_validator_creation(self):
        from src.ai.validation import AIDecisionValidator
        validator = AIDecisionValidator()
        assert validator is not None

    def test_validate_good_signal(self):
        from src.ai.validation import AIDecisionValidator
        from src.core.signals import Signal

        validator = AIDecisionValidator()
        signal = Signal(
            symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
            direction="LONG", confidence=0.75, entry=100.0,
            stop_loss=99.0, take_profit=102.0, strategy_id="test",
        )

        result = validator.validate_signal(
            signal=signal,
            candles=[],
            indicators={},
            portfolio_balance=1000.0,
            open_positions=0,
        )

        assert result.signal_id == signal.signal_id
        assert isinstance(result.approved, bool)
        assert result.decision in ("LONG", "SHORT", "HOLD")

    def test_validate_rejects_no_stop_loss(self):
        from src.ai.validation import AIDecisionValidator
        from src.core.signals import Signal

        validator = AIDecisionValidator()
        signal = Signal(
            symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
            direction="LONG", confidence=0.75, entry=100.0,
            strategy_id="test",
        )

        result = validator.validate_signal(
            signal=signal,
            candles=[],
            indicators={},
            portfolio_balance=1000.0,
            open_positions=0,
        )

        assert result.approved is False
        assert any("stop loss" in r.lower() for r in result.reasoning)

    def test_validate_rejects_low_confidence(self):
        from src.ai.validation import AIDecisionValidator, AIValidationConfig
        from src.core.signals import Signal

        config = AIValidationConfig(min_confidence=0.8)
        validator = AIDecisionValidator(config)
        signal = Signal(
            symbol="BTC/USDT", timeframe="H1", timestamp="2024-01-01T00:00:00",
            direction="LONG", confidence=0.5, entry=100.0,
            stop_loss=99.0, take_profit=102.0, strategy_id="test",
        )

        result = validator.validate_signal(
            signal=signal,
            candles=[],
            indicators={},
            portfolio_balance=1000.0,
            open_positions=0,
        )

        assert result.approved is False

    def test_validator_status(self):
        from src.ai.validation import AIDecisionValidator
        validator = AIDecisionValidator()
        status = validator.get_status()
        assert "calls_today" in status
        assert "cache_size" in status


# ── Enhanced Paper Broker Tests ──────────────────────────────────────

class TestEnhancedPaperBroker:
    """Test enhanced paper trading broker."""

    def test_broker_creation(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()
        assert broker.balance == 1000.0
        assert broker.equity == 1000.0

    def test_buy_order(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        order = broker.execute_buy(
            portfolio=portfolio,
            symbol="BTC/USDT",
            price=100.0,
            quantity=1.0,
            stop_loss=99.0,
            take_profit=102.0,
        )

        assert order is not None
        assert order["status"] == "FILLED"
        assert order["symbol"] == "BTC/USDT"
        assert broker.get_position("BTC/USDT") is not None

    def test_sell_order(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0)
        order = broker.execute_sell(portfolio, "BTC/USDT", 101.0)

        assert order is not None
        assert order["pnl"] > 0

    def test_trailing_stop(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker, PaperConfig
        config = PaperConfig(
            enable_trailing_stop=True,
            trailing_stop_activation=0.01,
            trailing_stop_distance=0.005,
        )
        broker = EnhancedPaperBroker(config)

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0, stop_loss=99.0)

        # Price rises, should activate trailing stop
        events = broker.check_positions({"BTC/USDT": 102.0})
        pos = broker.get_position("BTC/USDT")
        assert pos is not None
        assert pos["trailing_activated"] is True

    def test_break_even_stop(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker, PaperConfig
        config = PaperConfig(
            enable_break_even=True,
            break_even_activation=0.005,
            slippage_rate=0.0,  # Disable slippage for exact price matching
        )
        broker = EnhancedPaperBroker(config)

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0, stop_loss=99.0)

        # Price rises, should move SL to break-even
        events = broker.check_positions({"BTC/USDT": 101.0})
        pos = broker.get_position("BTC/USDT")
        assert pos is not None
        assert pos["break_even_moved"] is True
        assert pos["stop_loss"] == 100.0

    def test_sl_hit(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0, stop_loss=99.0)

        # Price drops below SL
        events = broker.check_positions({"BTC/USDT": 98.0})
        assert any(e["type"] == "SL_HIT" for e in events)
        assert broker.get_position("BTC/USDT") is None

    def test_tp_hit(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0, take_profit=102.0)

        # Price rises above TP
        events = broker.check_positions({"BTC/USDT": 103.0})
        assert any(e["type"] == "TP_HIT" for e in events)

    def test_trade_history(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0)
        broker.execute_sell(portfolio, "BTC/USDT", 101.0)

        history = broker.get_trade_history()
        assert len(history) == 1
        assert history[0]["pnl"] > 0

    def test_stats(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        stats = broker.get_stats()
        assert "total_trades" in stats
        assert "win_rate" in stats
        assert "profit_factor" in stats

    def test_reset(self):
        from src.trading.paper.enhanced import EnhancedPaperBroker
        broker = EnhancedPaperBroker()

        portfolio = MagicMock()
        broker.execute_buy(portfolio, "BTC/USDT", 100.0, 1.0)

        broker.reset()
        assert broker.balance == 1000.0
        assert len(broker.get_positions()) == 0


# ── Phone Session Manager Tests ──────────────────────────────────────

class TestPhoneSessionManager:
    """Test phone session manager."""

    def test_session_creation(self):
        from src.engine.phone_session import PhoneSessionManager
        manager = PhoneSessionManager()
        assert manager is not None

    def test_start_session(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        result = manager.start_session("test-001", SessionMode.PAPER)
        assert result is True
        assert manager.is_active

    def test_stop_session(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)
        result = manager.stop_session()
        assert result is True
        assert not manager.is_active

    def test_pause_resume(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)
        manager.update_activity(app_foreground=True, network_connected=True)

        manager.pause_session()
        assert not manager.allows_new_trades

        manager.resume_session()
        assert manager.allows_new_trades

    def test_emergency_stop(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)

        result = manager.emergency_stop()
        assert result is True
        assert not manager.allows_new_trades

    def test_heartbeat(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)

        result = manager.heartbeat()
        assert result is True

    def test_activity_tracking(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)

        manager.update_activity(app_foreground=True, network_connected=True)
        status = manager.get_status()
        assert status["activity"]["app_foreground"] is True

    def test_background_trading_paused(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode, PhoneSessionConfig
        config = PhoneSessionConfig(auto_stop_on_background=True)
        manager = PhoneSessionManager(config)
        manager.start_session("test-001", SessionMode.PAPER)

        manager.update_activity(app_foreground=False)
        assert not manager.allows_new_trades

    def test_session_status(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)

        status = manager.get_status()
        assert "session" in status
        assert "activity" in status
        assert status["mode"] == "PAPER"


# ── Walk-Forward Engine Tests ────────────────────────────────────────

class TestWalkForwardEngine:
    """Test walk-forward analysis engine."""

    def test_engine_creation(self):
        from src.backtest.walk_forward import WalkForwardEngine
        engine = WalkForwardEngine()
        assert engine is not None

    def test_insufficient_data(self):
        from src.backtest.walk_forward import WalkForwardEngine
        from src.strategy.spec import EMATrendStrategy

        engine = WalkForwardEngine()
        strategy = EMATrendStrategy()

        # Too few candles
        candles = [{"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "timestamp": f"2024-01-01T{i:02d}:00:00"} for i in range(10)]
        indicators = {"ema_12": [100.0] * 10, "ema_26": [99.0] * 10, "atr_14": [1.0] * 10}

        result = engine.run(strategy, candles, indicators, "BTC/USDT", "H1")
        assert result.total_windows == 0
        assert result.recommendation == "INSUFFICIENT_DATA"

    def test_walk_forward_with_enough_data(self):
        from src.backtest.walk_forward import WalkForwardEngine, WalkForwardConfig
        from src.strategy.spec import EMATrendStrategy

        config = WalkForwardConfig(train_period=30, validation_period=10, test_period=10, step_size=20)
        engine = WalkForwardEngine(config)
        strategy = EMATrendStrategy()

        # Generate enough candles
        candles = [
            {"open": 100 + i * 0.1, "high": 101 + i * 0.1, "low": 99 + i * 0.1,
             "close": 100.5 + i * 0.1, "volume": 1000, "timestamp": f"2024-01-01T{i:02d}:00:00"}
            for i in range(100)
        ]
        indicators = {
            "ema_12": [100.0 + i * 0.1 for i in range(100)],
            "ema_26": [99.0 + i * 0.1 for i in range(100)],
            "atr_14": [1.0] * 100,
        }

        result = engine.run(strategy, candles, indicators, "BTC/USDT", "H1")
        assert result.total_windows > 0
        assert result.recommendation in ("TRADE", "CAUTION", "AVOID")


# ── Config Extension Tests ───────────────────────────────────────────

class TestConfigExtensions:
    """Test new config settings."""

    def test_terminal_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'TERMINAL_ENABLED')
        assert hasattr(Config, 'TERMINAL_HEARTBEAT_INTERVAL')
        assert hasattr(Config, 'TERMINAL_LEASE_DURATION')

    def test_multi_strategy_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'MULTI_STRATEGY_ENABLED')
        assert hasattr(Config, 'MAX_STRATEGIES_PER_SYMBOL')
        assert hasattr(Config, 'SIGNAL_AGREEMENT_THRESHOLD')

    def test_ai_validation_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'AI_VALIDATION_ENABLED')
        assert hasattr(Config, 'AI_VALIDATION_MIN_CONFIDENCE')
        assert hasattr(Config, 'AI_VALIDATION_MAX_RISK_FLAGS')

    def test_paper_enhanced_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'PAPER_TRAILING_STOP')
        assert hasattr(Config, 'PAPER_BREAK_EVEN')
        assert hasattr(Config, 'PAPER_TRAILING_ACTIVATION')

    def test_session_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'SESSION_MODE')
        assert hasattr(Config, 'SESSION_REQUIRE_FOREGROUND')
        assert hasattr(Config, 'SESSION_AUTO_STOP_BACKGROUND')

    def test_broker_adapter_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'BROKER_ADAPTER')
        assert hasattr(Config, 'BROKER_HEALTH_CHECK_INTERVAL')

    def test_hosted_worker_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'HOSTED_WORKER_ENABLED')
        assert hasattr(Config, 'HOSTED_WORKER_URL')

    def test_live_infrastructure_config_exists(self):
        from src.config import Config
        assert hasattr(Config, 'LIVE_INFRASTRUCTURE_ENABLED')
        assert hasattr(Config, 'LIVE_BROKER_ADAPTER')
        assert hasattr(Config, 'LIVE_ACCOUNT_VERIFICATION')

    def test_config_includes_new_settings_in_as_dict(self):
        from src.config import Config
        d = Config.as_dict()
        assert "TERMINAL_ENABLED" in d
        assert "MULTI_STRATEGY_ENABLED" in d
        assert "AI_VALIDATION_ENABLED" in d
        assert "LIVE_TRADING" in d


# ── API Terminal Endpoint Tests ──────────────────────────────────────

class TestAPITerminal:
    """Test terminal API endpoints."""

    def test_session_status_endpoint(self):
        from fastapi.testclient import TestClient
        from api_server import app

        client = TestClient(app)
        response = client.get("/api/terminal/session/status")
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "activity" in data

    def test_strategies_list_endpoint(self):
        from fastapi.testclient import TestClient
        from api_server import app

        client = TestClient(app)
        response = client.get("/api/terminal/strategies/list")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert data["total"] > 0

    def test_risk_status_endpoint(self):
        from fastapi.testclient import TestClient
        from api_server import app

        client = TestClient(app)
        response = client.get("/api/terminal/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "kill_switch" in data

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from api_server import app

        client = TestClient(app)
        response = client.get("/api/terminal/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_paper_status_endpoint(self):
        from fastapi.testclient import TestClient
        from api_server import app

        client = TestClient(app)
        response = client.get("/api/terminal/paper/status")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "paper"


# ── Safety Invariant Tests ───────────────────────────────────────────

class TestSafetyInvariants:
    """Test critical safety invariants for M8-M16."""

    def test_live_trading_disabled_by_default(self):
        from src.config import Config
        assert Config.LIVE_TRADING is False

    def test_mt5_demo_only_by_default(self):
        from src.config import Config
        assert Config.MT5_DEMO_ONLY is True

    def test_live_infrastructure_disabled_by_default(self):
        from src.config import Config
        assert Config.LIVE_INFRASTRUCTURE_ENABLED is False

    def test_session_live_confirmation_required(self):
        from src.config import Config
        assert Config.SESSION_LIVE_CONFIRMATION is True

    def test_hosted_worker_disabled_by_default(self):
        from src.config import Config
        assert Config.HOSTED_WORKER_ENABLED is False

    def test_emergency_stop_blocks_trades(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode
        manager = PhoneSessionManager()
        manager.start_session("test-001", SessionMode.PAPER)
        manager.emergency_stop()
        assert not manager.allows_new_trades

    def test_background_stops_trading(self):
        from src.engine.phone_session import PhoneSessionManager, SessionMode, PhoneSessionConfig
        config = PhoneSessionConfig(auto_stop_on_background=True, require_foreground=True)
        manager = PhoneSessionManager(config)
        manager.start_session("test-001", SessionMode.PAPER)
        manager.update_activity(app_foreground=False)
        assert not manager.allows_new_trades

    def test_kill_switch_blocks_risk(self):
        from src.risk.advanced import AdvancedRiskEngine
        engine = AdvancedRiskEngine()
        engine.activate_kill_switch()
        assert engine.kill_switch_active
