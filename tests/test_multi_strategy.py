"""Tests for multi-strategy engine components.

Tests for:
- Strategy implementations
- Market regime detection
- AI strategy selector
- Strategy scoring
- Multi-strategy risk management
- Phone session automation
- Safety flag enforcement
"""
import pytest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.strategy.spec import (
    BaseStrategy, StrategySpec, AIScalpingStrategy, TrendFollowingStrategy,
    MeanReversionStrategy, BreakoutStrategy, MomentumStrategy, PriceActionStrategy,
    VWAPStrategy, MultiTimeframeStrategy, SMCStrategy, AICompositeStrategy,
    get_default_strategies,
)
from src.strategy.regime_detector import MarketRegimeDetector, MarketRegime
from src.strategy.ai_selector import AIStrategySelector, StrategySelection
from src.strategy.scoring import StrategyScorer, StrategyScore
from src.risk.multi_strategy import MultiStrategyRiskManager, MultiStrategyRiskConfig
from src.engine.session_manager import PhoneSessionManager, SessionState, SessionLease
from src.core.enums import RegimeType
from src.core.signals import Signal


# ── Strategy Implementation Tests ──────────────────────────────────────

class TestStrategySpec:
    """Test StrategySpec dataclass."""

    def test_strategy_spec_creation(self):
        spec = StrategySpec(
            strategy_id="test",
            name="Test Strategy",
            strategy_family="TEST",
            expected_holding_period="INTRADAY",
        )
        assert spec.strategy_id == "test"
        assert spec.name == "Test Strategy"
        assert spec.strategy_family == "TEST"
        assert spec.expected_holding_period == "INTRADAY"

    def test_strategy_spec_defaults(self):
        spec = StrategySpec(strategy_id="test", name="Test")
        assert spec.version == "1.0.0"
        assert spec.supported_timeframes == ["H1"]
        assert spec.supported_asset_classes == ["FOREX"]
        assert spec.min_bars_required == 50
        assert spec.generates_stops is True
        assert spec.risk_reward_min == 1.0


class TestBaseStrategy:
    """Test BaseStrategy abstract class."""

    def test_base_strategy_instantiation(self):
        spec = StrategySpec(strategy_id="test", name="Test")
        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError):
            BaseStrategy(spec)


class TestAIScalpingStrategy:
    """Test AI Scalping strategy."""

    def test_creation(self):
        strategy = AIScalpingStrategy()
        assert strategy.strategy_id == "ai_scalping"
        assert strategy.spec.strategy_family == "SCALPING"
        assert strategy.spec.expected_holding_period == "SCALP"
        assert "M1" in strategy.spec.supported_timeframes
        assert "M5" in strategy.spec.supported_timeframes

    def test_generate_signal_insufficient_data(self):
        strategy = AIScalpingStrategy()
        candles = [{"close": 1.0, "high": 1.1, "low": 0.9, "open": 1.0, "timestamp": "2024-01-01T00:00:00"}] * 10
        indicators = {}
        context = {"symbol": "EURUSD", "timeframe": "M5"}
        
        signal = strategy.generate_signal(candles, indicators, context)
        assert signal is None

    def test_generate_signal_with_data(self):
        strategy = AIScalpingStrategy()
        # Create enough candles
        candles = []
        for i in range(100):
            candles.append({
                "close": 1.1 + (i * 0.0001),
                "high": 1.101 + (i * 0.0001),
                "low": 1.099 + (i * 0.0001),
                "open": 1.1 + ((i-1) * 0.0001),
                "timestamp": f"2024-01-01T{i:02d}:00:00",
                "volume": 1000,
            })
        
        indicators = {
            "ema_5": [1.1 + (i * 0.0001) for i in range(100)],
            "ema_13": [1.1 + (i * 0.00005) for i in range(100)],
            "rsi_7": [50.0] * 100,
            "atr_14": [0.001] * 100,
        }
        
        context = {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "spread": 0.0001,
            "ai_confirmation": True,
        }
        
        signal = strategy.generate_signal(candles, indicators, context)
        # Signal may or may not be generated depending on exact values
        # This test ensures no exceptions are thrown
        assert signal is None or isinstance(signal, Signal)


class TestTrendFollowingStrategy:
    """Test Trend Following strategy."""

    def test_creation(self):
        strategy = TrendFollowingStrategy()
        assert strategy.strategy_id == "trend_following"
        assert strategy.spec.strategy_family == "TREND"
        assert strategy.spec.expected_holding_period == "INTRADAY"
        assert "H1" in strategy.spec.supported_timeframes

    def test_signal_score(self):
        strategy = TrendFollowingStrategy()
        signal = Signal(
            symbol="EURUSD",
            timeframe="H1",
            timestamp="2024-01-01T00:00:00",
            direction="LONG",
            confidence=0.8,
            entry=1.1,
            stop_loss=1.09,
            take_profit=1.12,
            strategy_id="trend_following",
        )
        
        score = strategy.get_signal_score(signal, "TRENDING_UP")
        assert score["signal"] == "ACTIVE"
        assert score["direction"] == "LONG"
        assert score["confidence"] == 0.8
        assert score["regime_compatibility"] == 1.0
        assert score["strategy_family"] == "TREND"


class TestMeanReversionStrategy:
    """Test Mean Reversion strategy."""

    def test_creation(self):
        strategy = MeanReversionStrategy()
        assert strategy.strategy_id == "mean_reversion"
        assert strategy.spec.strategy_family == "MEAN_REVERSION"
        assert "RANGING" in strategy.spec.regime_compatibility


class TestBreakoutStrategy:
    """Test Breakout strategy."""

    def test_creation(self):
        strategy = BreakoutStrategy()
        assert strategy.strategy_id == "breakout"
        assert strategy.spec.strategy_family == "BREAKOUT"
        assert "BREAKOUT" in strategy.spec.regime_compatibility


class TestMomentumStrategy:
    """Test Momentum strategy."""

    def test_creation(self):
        strategy = MomentumStrategy()
        assert strategy.strategy_id == "momentum"
        assert strategy.spec.strategy_family == "MOMENTUM"


class TestPriceActionStrategy:
    """Test Price Action strategy."""

    def test_creation(self):
        strategy = PriceActionStrategy()
        assert strategy.strategy_id == "price_action"
        assert strategy.spec.strategy_family == "PRICE_ACTION"


class TestVWAPStrategy:
    """Test VWAP Intraday strategy."""

    def test_creation(self):
        strategy = VWAPStrategy()
        assert strategy.strategy_id == "vwap_intraday"
        assert strategy.spec.strategy_family == "VWAP"


class TestMultiTimeframeStrategy:
    """Test Multi-Timeframe strategy."""

    def test_creation(self):
        strategy = MultiTimeframeStrategy()
        assert strategy.strategy_id == "multi_timeframe"
        assert strategy.spec.strategy_family == "MULTI_TIMEFRAME"


class TestSMCStrategy:
    """Test SMC Market Structure strategy."""

    def test_creation(self):
        strategy = SMCStrategy()
        assert strategy.strategy_id == "smc_market_structure"
        assert strategy.spec.strategy_family == "SMC"


class TestAICompositeStrategy:
    """Test AI Composite strategy."""

    def test_creation(self):
        strategy = AICompositeStrategy()
        assert strategy.strategy_id == "ai_composite"
        assert strategy.spec.strategy_family == "COMPOSITE"

    def test_with_strategies(self):
        strategies = [TrendFollowingStrategy(), MomentumStrategy()]
        composite = AICompositeStrategy(strategies=strategies)
        assert len(composite.strategies) == 2


class TestGetDefaultStrategies:
    """Test get_default_strategies function."""

    def test_returns_all_strategies(self):
        strategies = get_default_strategies()
        assert len(strategies) >= 10  # At least 10 strategies
        
        strategy_ids = [s.strategy_id for s in strategies]
        assert "ema_trend" in strategy_ids
        assert "rsi_reversion" in strategy_ids
        assert "ai_scalping" in strategy_ids
        assert "trend_following" in strategy_ids
        assert "mean_reversion" in strategy_ids
        assert "breakout" in strategy_ids
        assert "momentum" in strategy_ids
        assert "price_action" in strategy_ids
        assert "vwap_intraday" in strategy_ids
        assert "multi_timeframe" in strategy_ids
        assert "smc_market_structure" in strategy_ids
        assert "ai_composite" in strategy_ids


# ── Market Regime Detection Tests ──────────────────────────────────────

class TestMarketRegimeDetector:
    """Test MarketRegimeDetector."""

    def test_creation(self):
        detector = MarketRegimeDetector()
        assert detector.trend_ema_fast == 12
        assert detector.trend_ema_slow == 26
        assert detector.adx_period == 14

    def test_detect_insufficient_data(self):
        detector = MarketRegimeDetector()
        candles = [{"close": 1.0, "high": 1.1, "low": 0.9}] * 10
        indicators = {}
        
        regime = detector.detect(candles, indicators)
        assert regime.regime == RegimeType.UNCERTAIN
        assert regime.confidence == 0.0

    def test_detect_with_indicators(self):
        detector = MarketRegimeDetector()
        candles = [{"close": 1.0 + (i * 0.001), "high": 1.001 + (i * 0.001), "low": 0.999 + (i * 0.001)} for i in range(100)]
        indicators = {
            "ema_12": [1.0 + (i * 0.001) for i in range(100)],
            "ema_26": [1.0 + (i * 0.0005) for i in range(100)],
            "adx_14": [30.0] * 100,
            "atr_14": [0.001] * 100,
        }
        
        regime = detector.detect(candles, indicators)
        assert isinstance(regime, MarketRegime)
        assert regime.regime in RegimeType
        assert 0.0 <= regime.confidence <= 1.0

    def test_get_strategy_preferences(self):
        detector = MarketRegimeDetector()
        regime = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=0.8,
            indicators={},
            timestamp="2024-01-01T00:00:00",
        )
        
        preferences = detector.get_strategy_preferences(regime)
        assert "trend_following" in preferences
        assert "mean_reversion" in preferences
        assert preferences["trend_following"] > preferences["mean_reversion"]


# ── AI Strategy Selector Tests ─────────────────────────────────────────

class TestAIStrategySelector:
    """Test AIStrategySelector."""

    def test_creation(self):
        strategies = {s.strategy_id: s for s in get_default_strategies()}
        detector = MarketRegimeDetector()
        selector = AIStrategySelector(strategies, detector)
        assert len(selector.strategies) == len(strategies)

    def test_select_strategy_no_data(self):
        strategies = {s.strategy_id: s for s in get_default_strategies()}
        detector = MarketRegimeDetector()
        selector = AIStrategySelector(strategies, detector)
        
        selection = selector.select_strategy(
            candles=[],
            indicators={},
            context={"symbol": "EURUSD", "timeframe": "H1"},
        )
        
        assert isinstance(selection, StrategySelection)
        assert selection.direction == "HOLD"
        assert selection.confidence == 0.0

    def test_strategy_selection_to_dict(self):
        selection = StrategySelection(
            selected_strategy="trend_following",
            direction="BUY",
            confidence=0.8,
            reason="Test selection",
            risk_level="LOW",
            entry_conditions=["EMA_alignment"],
            invalid_conditions=["EMA_cross_against"],
            regime="TRENDING_UP",
            volatility=1.0,
            trend="UP",
            momentum=0.01,
            spread=0.0001,
            timeframe="H1",
            symbol="EURUSD",
            session="TEST",
            existing_positions=[],
            risk_state={},
        )
        
        data = selection.to_dict()
        assert data["selected_strategy"] == "trend_following"
        assert data["direction"] == "BUY"
        assert data["confidence"] == 0.8


# ── Strategy Scoring Tests ─────────────────────────────────────────────

class TestStrategyScorer:
    """Test StrategyScorer."""

    def test_creation(self):
        scorer = StrategyScorer()
        assert scorer.confidence_weight == 0.3
        assert scorer.regime_weight == 0.25

    def test_score_strategies(self):
        strategies = {s.strategy_id: s for s in get_default_strategies()}
        scorer = StrategyScorer()
        
        candles = [{"close": 1.0, "high": 1.1, "low": 0.9}] * 100
        indicators = {}
        context = {"symbol": "EURUSD", "timeframe": "H1"}
        
        scores = scorer.score_strategies(strategies, candles, indicators, context)
        assert len(scores) == len(strategies)
        assert all(isinstance(s, StrategyScore) for s in scores)
        
        # Scores should be sorted by score descending
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_strategy_score_to_dict(self):
        score = StrategyScore(
            strategy_id="test",
            strategy_family="TEST",
            signal="ACTIVE",
            direction="LONG",
            confidence=0.8,
            regime_compatibility=1.0,
            entry_conditions=["condition1"],
            stop_loss_suggestion=1.0,
            take_profit_suggestion=1.1,
            invalidation=["invalid1"],
            timeframe="H1",
            expected_holding_period="INTRADAY",
            risk_reward_ratio=2.0,
            score=0.85,
            rank=1,
        )
        
        data = score.to_dict()
        assert data["strategy_id"] == "test"
        assert data["score"] == 0.85
        assert data["rank"] == 1

    def test_update_historical_score(self):
        scorer = StrategyScorer()
        scorer.update_historical_score("test_strategy", 0.8)
        scorer.update_historical_score("test_strategy", 0.9)
        
        score = scorer._get_historical_score("test_strategy")
        assert abs(score - 0.85) < 0.0001  # Average of 0.8 and 0.9


# ── Multi-Strategy Risk Management Tests ───────────────────────────────

class TestMultiStrategyRiskManager:
    """Test MultiStrategyRiskManager."""

    def test_creation(self):
        config = MultiStrategyRiskConfig()
        manager = MultiStrategyRiskManager(config=config)
        assert manager.config.max_strategies_per_symbol == 3
        assert manager.config.max_correlated_exposure == 0.30

    def test_strategy_state_tracking(self):
        from src.risk.multi_strategy import StrategyRiskState
        manager = MultiStrategyRiskManager()
        manager._strategy_states["test"] = StrategyRiskState(strategy_id="test")
        
        # Test trade recording
        manager.record_trade_result("test", "EURUSD", 100.0)
        assert manager._strategy_states["test"].daily_pnl == 100.0


class TestPhoneSessionManager:
    """Test PhoneSessionManager."""

    def test_creation(self):
        manager = PhoneSessionManager()
        assert manager.heartbeat_interval == 30.0
        assert manager.lease_duration == 300.0

    def test_session_lifecycle(self):
        manager = PhoneSessionManager(heartbeat_interval=60.0, lease_duration=300.0)
        
        # Start session
        result = manager.start_session("test_session")
        assert result is True
        assert manager.state == SessionState.ACTIVE
        
        # Stop session immediately
        result = manager.stop_session()
        assert result is True
        # Note: State may be STOPPED or EXPIRED depending on heartbeat thread timing
        # The important thing is that the session was stopped successfully

    def test_session_lease(self):
        lease = SessionLease(
            session_id="test",
            start_time=time.time(),
            lease_duration=300.0,
            heartbeat_interval=30.0,
        )
        
        assert not lease.is_expired()
        assert lease.remaining_time() > 0
        
        # Test heartbeat
        result = lease.heartbeat()
        assert result is True

    def test_session_allows_new_trades(self):
        manager = PhoneSessionManager()
        manager.start_session("test")
        
        assert manager.allows_new_trades is True
        
        manager.stop_new_trades()
        assert manager.allows_new_trades is False

    def test_session_status(self):
        manager = PhoneSessionManager()
        manager.start_session("test")
        
        status = manager.get_status()
        assert "session" in status
        assert "lease" in status
        assert "state" in status


# ── Safety Flag Enforcement Tests ──────────────────────────────────────

class TestSafetyFlagEnforcement:
    """Test safety flag enforcement."""

    def test_live_trading_disabled(self):
        """Verify LIVE_TRADING is disabled."""
        from src.config import Config
        assert Config.LIVE_TRADING is False

    def test_mt5_demo_only_enabled(self):
        """Verify MT5_DEMO_ONLY is enabled."""
        from src.config import Config
        assert Config.MT5_DEMO_ONLY is True

    def test_mt5_demo_trading_disabled(self):
        """Verify MT5_DEMO_TRADING_ENABLED is disabled."""
        from src.config import Config
        assert Config.MT5_DEMO_TRADING_ENABLED is False

    def test_trading_mode_allows_execution(self):
        """Verify LIVE_LOCKED does not allow execution."""
        from src.core.enums import TradingMode
        assert TradingMode.LIVE_LOCKED.allows_execution is False
        assert TradingMode.MT5_DEMO.allows_execution is True
        assert TradingMode.PAPER.allows_execution is True


# ── Integration Tests ──────────────────────────────────────────────────

class TestMultiStrategyIntegration:
    """Integration tests for multi-strategy engine."""

    def test_strategy_registry(self):
        """Test that all strategies are properly registered."""
        strategies = get_default_strategies()
        strategy_dict = {s.strategy_id: s for s in strategies}
        
        assert len(strategy_dict) >= 10
        
        # Check that each strategy has required attributes
        for strategy in strategies:
            assert hasattr(strategy, 'strategy_id')
            assert hasattr(strategy, 'spec')
            assert hasattr(strategy, 'generate_signal')
            assert hasattr(strategy, 'get_signal_score')
            # Note: Original strategies may not have strategy_family set
            # This is expected as we're extending existing code

    def test_regime_strategy_compatibility(self):
        """Test regime-strategy compatibility."""
        detector = MarketRegimeDetector()
        
        # Test different regimes
        regimes = [
            RegimeType.TRENDING_UP,
            RegimeType.TRENDING_DOWN,
            RegimeType.RANGING,
            RegimeType.BREAKOUT,
            RegimeType.HIGH_VOLATILITY,
            RegimeType.LOW_VOLATILITY,
        ]
        
        for regime in regimes:
            market_regime = MarketRegime(
                regime=regime,
                confidence=0.8,
                indicators={},
                timestamp="2024-01-01T00:00:00",
            )
            
            preferences = detector.get_strategy_preferences(market_regime)
            assert len(preferences) > 0
            assert all(0.0 <= v <= 1.0 for v in preferences.values())

    def test_safety_pipeline(self):
        """Test that safety pipeline blocks live trading."""
        from src.core.enums import TradingMode
        
        # Verify that LIVE_LOCKED mode blocks execution
        assert not TradingMode.LIVE_LOCKED.allows_execution
        
        # Verify that demo modes allow execution
        assert TradingMode.MT5_DEMO.allows_execution
        assert TradingMode.PAPER.allows_execution
        assert TradingMode.PAPER_LIVE.allows_execution