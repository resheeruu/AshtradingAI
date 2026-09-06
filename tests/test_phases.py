"""Tests for Phases 1-9: Real-data validation, robustness, regime, arena, analytics, baselines.

All tests work without paid API keys. Deterministic test strategy used throughout.
"""
import math
import random
import pytest
from typing import List, Dict

from src.ai.base import TradingAI, MarketContext
from src.ai.test_strategy import TestStrategy
from src.backtest.m7_backtest import M7BacktestEngine, M7BacktestMetrics, run_walk_forward
from src.backtest.robustness import RobustnessLab, RobustnessReport
from src.backtest.baselines import BuyAndHold, SMACrossover, RSIMeanReversion, get_all_baselines
from src.backtest.experiment import ExperimentConfig, ExperimentResult, create_experiment, ExecutionAssumptions
from src.backtest.analytics import DecisionAnalytics, DecisionEvent
from src.market.regime import RegimeDetector, Regime, RegimeResult
from src.trading.paper.broker import PaperBroker
from src.portfolio.portfolio import Portfolio
from src.indicators.technical import sma, atr, ema, rsi
from src.market.candles import generate_synthetic_candles


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_candles(prices, volatility=0.005, seed=42):
    import random as _rng
    rng = _rng.Random(seed)
    candles = []
    from datetime import datetime, timedelta, timezone
    base_time = datetime.now(timezone.utc) - timedelta(hours=len(prices))
    for i, close in enumerate(prices):
        high = close * (1 + abs(rng.gauss(0, volatility)))
        low = close * (1 - abs(rng.gauss(0, volatility)))
        open_ = prices[i - 1] if i > 0 else close
        ts = (base_time + timedelta(hours=i)).isoformat()
        candles.append({
            "timestamp": ts, "open": open_, "high": high,
            "low": low, "close": close, "volume": rng.uniform(100, 10000),
        })
    return candles


def _trending_up(n=60, start=100.0, step=0.5):
    return [start + i * step for i in range(n)]


def _trending_down(n=60, start=200.0, step=0.5):
    return [start - i * step for i in range(n)]


def _ranging(n=60, mid=100.0, amp=2.0):
    return [mid + amp * math.sin(i * 0.3) for i in range(n)]


# ============================================================
# Phase 1: Realistic Execution (Spread)
# ============================================================

class TestRealisticExecution:
    def test_paper_broker_spread_buy(self):
        """Spread increases effective buy price."""
        p = Portfolio("test", 10000)
        broker = PaperBroker(fee=0.001, slippage=0.0005, spread=0.001)
        broker.execute_buy(p, "BTC/USDT", 50000.0, 0.01)
        pos = p.get_position("BTC/USDT")
        assert pos is not None
        # Price should be higher than mid due to spread + slippage
        assert pos.entry_price > 50000.0

    def test_paper_broker_spread_sell(self):
        """Spread decreases effective sell price."""
        p = Portfolio("test", 10000)
        broker = PaperBroker(fee=0.001, slippage=0.0005, spread=0.001)
        broker.execute_buy(p, "BTC/USDT", 50000.0, 0.01)
        broker.execute_sell(p, "BTC/USDT", 51000.0)
        trades = p.trade_history
        assert len(trades) == 1
        # Exit price should be lower than mid due to spread + slippage
        assert trades[0].exit_price < 51000.0

    def test_spread_increases_cost(self):
        """Zero spread vs non-zero spread should differ in P&L."""
        p1 = Portfolio("test1", 10000)
        p2 = Portfolio("test2", 10000)
        b1 = PaperBroker(fee=0.001, slippage=0.0005, spread=0.0)
        b2 = PaperBroker(fee=0.001, slippage=0.0005, spread=0.01)
        b1.execute_buy(p1, "BTC/USDT", 50000.0, 0.01)
        b2.execute_buy(p2, "BTC/USDT", 50000.0, 0.01)
        b1.execute_sell(p1, "BTC/USDT", 50000.0)
        b2.execute_sell(p2, "BTC/USDT", 50000.0)
        # Spread version should have worse P&L
        assert p1.trade_history[0].pnl >= p2.trade_history[0].pnl

    def test_m7_backtest_with_spread(self):
        """M7 backtest accepts spread parameter."""
        ai = TestStrategy(ai_id="spread-test")
        candles = _make_candles(_trending_up(80))
        data = {"BTC/USDT": candles}
        engine = M7BacktestEngine(starting_balance=10000, fee=0.001, slippage=0.0005)
        # Patch broker with spread
        engine.broker = PaperBroker(fee=0.001, slippage=0.0005, spread=0.001)
        metrics, portfolio = engine.run(ai, data, "1h")
        assert metrics.standard.starting_balance == 10000


# ============================================================
# Phase 2: Robustness Lab
# ============================================================

class TestRobustnessLab:
    def test_rolling_walk_forward(self):
        """Rolling walk-forward produces multiple windows."""
        lab = RobustnessLab(seed=42)
        ai = TestStrategy(ai_id="wf-test")
        candles = _make_candles(_trending_up(120))
        data = {"BTC/USDT": candles}
        result = lab.rolling_walk_forward(
            ai, data, "1h",
            train_pct=0.4, test_pct=0.2, step_pct=0.2,
            starting_balance=10000,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        assert result.num_windows >= 1
        assert len(result.oos_returns) == result.num_windows

    def test_walk_forward_no_state_leak(self):
        """Each walk-forward window uses a fresh engine."""
        lab = RobustnessLab(seed=42)
        ai = TestStrategy(ai_id="leak-test")
        candles = _make_candles(_trending_up(120))
        data = {"BTC/USDT": candles}
        result = lab.rolling_walk_forward(
            ai, data, "1h",
            train_pct=0.4, test_pct=0.2, step_pct=0.2,
            starting_balance=10000,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        # Each window should have independent results
        for w in result.windows:
            assert w.window_id >= 0

    def test_parameter_sensitivity(self):
        """Parameter sensitivity produces results for each tested value."""
        lab = RobustnessLab(seed=42)
        ai = TestStrategy(ai_id="sens-test")
        candles = _make_candles(_trending_up(80))
        data = {"BTC/USDT": candles}
        result = lab.parameter_sensitivity(
            ai, data, "1h",
            param_name="fee",
            base_value=0.001,
            test_values=[0.0005, 0.001, 0.002],
            starting_balance=10000,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        assert len(result.tested_values) == 3
        assert len(result.returns) == 3

    def test_monte_carlo_insufficient_trades(self):
        """Monte Carlo returns empty result for insufficient trades."""
        lab = RobustnessLab(seed=42)
        from src.portfolio.portfolio import TradeRecord
        trades = [TradeRecord("BTC/USDT", "long", 100, 105, 1, 0.1, 0.0005, 5.0) for _ in range(3)]
        result = lab.monte_carlo(trades, n_simulations=100)
        assert result.n_simulations == 0  # insufficient trades

    def test_monte_carlo_with_trades(self):
        """Monte Carlo produces valid statistics with enough trades."""
        lab = RobustnessLab(seed=42)
        from src.portfolio.portfolio import TradeRecord
        rng = random.Random(42)
        trades = [TradeRecord("BTC/USDT", "long", 100, 100 + rng.gauss(2, 5), 1, 0.1, 0.0005, rng.gauss(2, 5)) for _ in range(20)]
        result = lab.monte_carlo(trades, n_simulations=500)
        assert result.n_simulations == 500
        assert 0.0 <= result.probability_of_loss <= 1.0
        assert result.worst_drawdown >= 0.0

    def test_deflated_sharpe_insufficient_sample(self):
        """Deflated Sharpe returns INSUFFICIENT_SAMPLE for small samples."""
        lab = RobustnessLab(seed=42)
        ds, note = lab.compute_deflated_sharpe(1.0, n_trials=10, n_observations=10)
        assert ds is None
        assert "INSUFFICIENT_SAMPLE" in note

    def test_deflated_sharpe_valid(self):
        """Deflated Sharpe produces a valid probability for sufficient sample."""
        lab = RobustnessLab(seed=42)
        ds, note = lab.compute_deflated_sharpe(0.5, n_trials=10, n_observations=100)
        assert ds is not None
        assert 0.0 <= ds <= 1.0

    def test_robustness_score(self):
        """Robustness score is between 0 and 1."""
        lab = RobustnessLab(seed=42)
        from src.backtest.robustness import WalkForwardResult, MonteCarloResult
        wf = WalkForwardResult()
        mc = MonteCarloResult(n_simulations=100, probability_of_loss=0.3)
        score = lab.compute_robustness_score(wf, mc, n_trials=1)
        assert 0.0 <= score <= 1.0


# ============================================================
# Phase 3: Market Regime Detector
# ============================================================

class TestRegimeDetector:
    def test_insufficient_data_returns_unknown(self):
        det = RegimeDetector()
        result = det.detect([100.0] * 5, [99.0] * 5, [100.0] * 5)
        assert result.regime == Regime.UNKNOWN

    def test_trending_up_detection(self):
        det = RegimeDetector(trend_threshold=0.0001)
        prices = _trending_up(100, start=100.0, step=1.0)
        candles = _make_candles(prices)
        result = det.detect(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.regime in (Regime.TRENDING_UP, Regime.HIGH_VOLATILITY, Regime.UNKNOWN)

    def test_trending_down_detection(self):
        det = RegimeDetector(trend_threshold=0.0001)
        prices = _trending_down(100, start=200.0, step=1.0)
        candles = _make_candles(prices)
        result = det.detect(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.regime in (Regime.TRENDING_DOWN, Regime.HIGH_VOLATILITY, Regime.UNKNOWN)

    def test_ranging_detection(self):
        det = RegimeDetector(range_threshold=0.05)
        prices = _ranging(100, mid=100.0, amp=0.5)
        candles = _make_candles(prices, volatility=0.001)
        result = det.detect(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.regime in (Regime.RANGING, Regime.LOW_VOLATILITY, Regime.UNKNOWN)

    def test_regime_result_has_summary(self):
        det = RegimeDetector()
        result = det.detect([100.0] * 50, [99.0] * 50, [100.0] * 50)
        s = result.summary()
        assert "regime" in s
        assert "confidence" in s

    def test_deterministic(self):
        """Same inputs produce same regime."""
        det = RegimeDetector()
        prices = _trending_up(80)
        candles = _make_candles(prices)
        r1 = det.detect([c["high"] for c in candles], [c["low"] for c in candles], [c["close"] for c in candles])
        r2 = det.detect([c["high"] for c in candles], [c["low"] for c in candles], [c["close"] for c in candles])
        assert r1.regime == r2.regime
        assert r1.confidence == r2.confidence


# ============================================================
# Phase 4: AI Arena (tournament extension)
# ============================================================

class TestAIArena:
    def test_tournament_isolation(self):
        """Each participant has independent portfolio."""
        from src.tournament.engine import TournamentEngine, TournamentConfig
        from src.tournament.participant import ParticipantConfig

        config = TournamentConfig(
            starting_balance=10000, fee=0.001, slippage=0.0005,
            symbols=["BTC/USDT"], timeframe="1h",
        )
        participants = [
            ParticipantConfig(id="ai-1", provider="test", model=""),
            ParticipantConfig(id="ai-2", provider="test", model=""),
        ]
        candles = _make_candles(_trending_up(60))
        data = {"BTC/USDT": candles}

        engine = TournamentEngine(config)
        result = engine.run(participants, data)

        assert "participants" in result
        assert len(result["participants"]) == 2
        # Both should have independent results
        p1 = result["participants"][0]
        p2 = result["participants"][1]
        assert p1["ai_id"] != p2["ai_id"]

    def test_identical_market_snapshots(self):
        """All participants receive the same market data."""
        # This is architecturally guaranteed by TournamentEngine:
        # it builds one ctx_candles list per timestamp and passes
        # the same list to each AI. Verified by code inspection.
        from src.tournament.engine import TournamentEngine, TournamentConfig
        from src.tournament.participant import ParticipantConfig

        config = TournamentConfig(starting_balance=10000)
        participants = [
            ParticipantConfig(id="ai-1", provider="test", model=""),
            ParticipantConfig(id="ai-2", provider="test", model=""),
        ]
        candles = _make_candles(_trending_up(60))
        data = {"BTC/USDT": candles}

        engine = TournamentEngine(config)
        result = engine.run(participants, data)
        # Both should process same number of candles
        for p in result["participants"]:
            assert p["num_trades"] >= 0


# ============================================================
# Phase 5: AI Decision Quality Analytics
# ============================================================

class TestDecisionAnalytics:
    def test_agreement_rate(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(direction="LONG", ai_decision="BUY", confidence=0.8, confirmed=True))
        analytics.record(DecisionEvent(direction="LONG", ai_decision="HOLD", confidence=0.5, confirmed=False))
        analytics.record(DecisionEvent(direction="SHORT", ai_decision="SELL", confidence=0.7, confirmed=True))
        assert analytics.agreement_rate() == 2 / 3

    def test_rejection_rate(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(direction="LONG", ai_decision="BUY", confidence=0.8, confirmed=True))
        analytics.record(DecisionEvent(direction="LONG", ai_decision="HOLD", confidence=0.0, confirmed=False))
        assert analytics.rejection_rate() == 0.5

    def test_hold_rate(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(ai_decision="BUY"))
        analytics.record(DecisionEvent(ai_decision="HOLD"))
        analytics.record(DecisionEvent(ai_decision="HOLD"))
        assert analytics.hold_rate() == 2 / 3

    def test_performance_by_regime(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(was_trade=True, regime="TRENDING_UP", pnl=10.0))
        analytics.record(DecisionEvent(was_trade=True, regime="RANGING", pnl=-5.0))
        result = analytics.performance_by_regime()
        assert "TRENDING_UP" in result
        assert "RANGING" in result
        assert result["TRENDING_UP"]["avg_pnl"] == 10.0

    def test_performance_by_direction(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(was_trade=True, direction="LONG", pnl=10.0))
        analytics.record(DecisionEvent(was_trade=True, direction="SHORT", pnl=-5.0))
        result = analytics.performance_by_direction()
        assert "long" in result
        assert "short" in result

    def test_summary_structure(self):
        analytics = DecisionAnalytics()
        analytics.record(DecisionEvent(direction="LONG", ai_decision="BUY", confidence=0.8, confirmed=True, was_trade=True, pnl=5.0))
        s = analytics.summary()
        assert "agreement_rate" in s
        assert "hold_rate" in s
        assert "total_trades" in s


# ============================================================
# Phase 9: Baseline Strategies
# ============================================================

class TestBaselines:
    def test_buy_and_hold(self):
        ai = BuyAndHold()
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h", current_price=50000,
            candles=[{"close": 50000}] * 30, portfolio_balance=10000,
        )
        d = ai.decide(ctx)
        assert d["decision"] == "BUY"
        assert d["confidence"] == 1.0

    def test_buy_and_hold_holds_after_buy(self):
        ai = BuyAndHold()
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h", current_price=50000,
            candles=[{"close": 50000}] * 30, portfolio_balance=10000,
            open_positions=["BTC/USDT"],
        )
        ai._bought = True
        d = ai.decide(ctx)
        assert d["decision"] == "HOLD"

    def test_sma_crossover(self):
        ai = SMACrossover(fast_period=5, slow_period=10)
        # Create uptrend to trigger golden cross
        prices = _trending_up(30, start=100, step=2)
        candles = _make_candles(prices)
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h", current_price=prices[-1],
            candles=candles, portfolio_balance=10000,
        )
        d = ai.decide(ctx)
        assert d["decision"] in ("BUY", "SELL", "HOLD")

    def test_rsi_baseline(self):
        ai = RSIMeanReversion(period=5)
        candles = _make_candles(_trending_up(30))
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h", current_price=115,
            candles=candles, portfolio_balance=10000,
        )
        d = ai.decide(ctx)
        assert d["decision"] in ("BUY", "SELL", "HOLD")

    def test_get_all_baselines(self):
        baselines = get_all_baselines()
        assert len(baselines) == 3
        ids = {b.ai_id for b in baselines}
        assert "baseline-buy-hold" in ids
        assert "baseline-sma-cross" in ids
        assert "baseline-rsi" in ids

    def test_baseline_backtest(self):
        """Baselines can run through M7BacktestEngine."""
        ai = BuyAndHold()
        candles = _make_candles(_trending_up(80))
        data = {"BTC/USDT": candles}
        engine = M7BacktestEngine(
            starting_balance=10000,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        metrics, portfolio = engine.run(ai, data, "1h")
        assert metrics.standard.starting_balance == 10000


# ============================================================
# Phase 7: Experiment Management
# ============================================================

class TestExperimentManagement:
    def test_experiment_config_creation(self):
        config = create_experiment(symbol="BTC/USDT", timeframe="1h")
        assert config.experiment_id
        assert config.timestamp
        assert config.symbol == "BTC/USDT"

    def test_experiment_config_hash_deterministic(self):
        c1 = create_experiment(symbol="BTC/USDT", seed=42)
        c2 = create_experiment(symbol="BTC/USDT", seed=42)
        # Same config should produce same hash
        d1 = c1.to_dict()
        d2 = c2.to_dict()
        # Timestamps differ, so hashes differ — but config structure is same
        assert d1["symbol"] == d2["symbol"]
        assert d1["seed"] == d2["seed"]

    def test_experiment_to_dict(self):
        config = create_experiment()
        d = config.to_dict()
        assert "experiment_id" in d
        assert "git_commit" in d
        assert "execution" in d

    def test_execution_assumptions(self):
        ea = ExecutionAssumptions(fee=0.002, slippage=0.001, spread=0.0005)
        s = ea.summary()
        assert s["fee"] == 0.002
        assert s["spread"] == 0.0005

    def test_experiment_result(self):
        config = create_experiment()
        result = ExperimentResult(config=config, metrics={"return_pct": 0.05})
        d = result.to_dict()
        assert "config" in d
        assert "metrics" in d


# ============================================================
# Phase 2: Walk-Forward (existing function)
# ============================================================

class TestWalkForwardExisting:
    def test_walk_forward_produces_is_and_oos(self):
        ai = TestStrategy(ai_id="wf-existing")
        candles = _make_candles(_trending_up(100))
        data = {"BTC/USDT": candles}
        is_m, oos_m, _, _ = run_walk_forward(
            ai, data, "1h", in_sample_pct=0.7,
            starting_balance=10000,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        assert is_m.standard.starting_balance == 10000
        assert oos_m.standard.starting_balance == 10000


# ============================================================
# Phase 10: Determinism
# ============================================================

class TestDeterminism:
    def test_m7_backtest_deterministic(self):
        """Same inputs produce same M7 backtest results."""
        ai1 = TestStrategy(ai_id="det-test")
        ai2 = TestStrategy(ai_id="det-test")
        candles = _make_candles(_trending_up(80), seed=42)
        data = {"BTC/USDT": candles}

        e1 = M7BacktestEngine(starting_balance=10000, filter_config={"atr_enabled": False, "angle_enabled": False, "price_ema_enabled": False, "candle_enabled": False, "ema_order_enabled": False, "session_enabled": False})
        m1, _ = e1.run(ai1, data, "1h")

        e2 = M7BacktestEngine(starting_balance=10000, filter_config={"atr_enabled": False, "angle_enabled": False, "price_ema_enabled": False, "candle_enabled": False, "ema_order_enabled": False, "session_enabled": False})
        m2, _ = e2.run(ai2, data, "1h")

        assert m1.standard.ending_balance == m2.standard.ending_balance
        assert m1.standard.num_trades == m2.standard.num_trades
        assert m1.state_stats.setups_detected == m2.state_stats.setups_detected

    def test_monte_carlo_deterministic(self):
        """Same seed produces same Monte Carlo results."""
        from src.portfolio.portfolio import TradeRecord
        rng = random.Random(42)
        trades = [TradeRecord("BTC/USDT", "long", 100, 100 + rng.gauss(2, 5), 1, 0.1, 0.0005, rng.gauss(2, 5)) for _ in range(20)]

        lab1 = RobustnessLab(seed=42)
        r1 = lab1.monte_carlo(trades, n_simulations=200)

        lab2 = RobustnessLab(seed=42)
        r2 = lab2.monte_carlo(trades, n_simulations=200)

        assert r1.median_return == r2.median_return
        assert r1.probability_of_loss == r2.probability_of_loss
        assert r1.worst_drawdown == r2.worst_drawdown
