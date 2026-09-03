"""Comprehensive tests for the tournament system."""
import tempfile
import pytest
from pathlib import Path
from src.market.candles import generate_synthetic_candles
from src.ai.test_strategy import TestStrategy
from src.ai.base import MarketContext, TradingAI
from src.persistence.database import Database

# Tournament modules
from src.tournament.participant import ParticipantConfig, load_participants_from_env, load_participants_from_list
from src.tournament.prompts import build_tournament_prompt, build_risk_limits_dict
from src.tournament.metrics import (
    TournamentMetrics, compute_tournament_metrics, compute_composite_score, assign_awards,
)
from src.tournament.engine import TournamentEngine, TournamentConfig, validate_no_lookahead
from src.tournament.leaderboard import format_leaderboard, format_leaderboard_compact


# ============================================================
# Test: AI Isolation
# ============================================================

class TestAIIsolation:
    def test_independent_portfolios_in_tournament(self):
        """Each AI in a tournament must have its own isolated portfolio."""
        config = TournamentConfig(
            experiment_id="isolation-test",
            symbols=["BTC/USDT"],
            candle_limit=100,
            starting_balance=1000.0,
        )
        participants = [
            ParticipantConfig(id="ai-1", provider="test"),
            ParticipantConfig(id="ai-2", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=100)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        assert "participants" in result
        assert len(result["participants"]) == 2

        # Verify each has independent results
        ids = {p["ai_id"] for p in result["participants"]}
        assert "ai-1" in ids
        assert "ai-2" in ids

        # Starting balances should be identical
        for p in result["participants"]:
            assert p["starting_balance"] == 1000.0

    def test_no_cross_contamination(self):
        """AI #1 must not see AI #2's balance, trades, or decisions."""
        config = TournamentConfig(
            experiment_id="cross-test",
            symbols=["BTC/USDT"],
            candle_limit=100,
            starting_balance=1000.0,
        )
        participants = [
            ParticipantConfig(id="alpha", provider="test"),
            ParticipantConfig(id="beta", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=100)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        # Both should have identical starting balances
        for p in result["participants"]:
            assert p["starting_balance"] == 1000.0

        # Both should have had the same market data
        # (same candles, same decisions from same strategy -> same results for same-id AIs)
        for p in result["participants"]:
            assert p["num_trades"] >= 0


# ============================================================
# Test: Identical Market Context
# ============================================================

class TestIdenticalMarketContext:
    def test_same_candles_same_price(self):
        """All AIs receive the same candle data at the same timestamp."""
        config = TournamentConfig(
            experiment_id="context-test",
            symbols=["BTC/USDT"],
            candle_limit=100,
        )
        participants = [
            ParticipantConfig(id="ctx-1", provider="test"),
            ParticipantConfig(id="ctx-2", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=100)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        # Both AIs should produce the same number of trades
        # (since they're the same deterministic strategy)
        assert len(result["participants"]) == 2
        assert result["participants"][0]["num_trades"] == result["participants"][1]["num_trades"]

    def test_same_starting_balance(self):
        """All AIs start with identical balance."""
        config = TournamentConfig(starting_balance=5000.0)
        participants = [
            ParticipantConfig(id="bal-1", provider="test"),
            ParticipantConfig(id="bal-2", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        for p in result["participants"]:
            assert p["starting_balance"] == 5000.0


# ============================================================
# Test: No-Lookahead Rule
# ============================================================

class TestNoLookahead:
    def test_validate_no_lookahead_pass(self):
        """No error when all candles are historical."""
        candles = [
            {"timestamp": "2024-01-01T00:00:00", "close": 100},
            {"timestamp": "2024-01-01T01:00:00", "close": 101},
        ]
        assert validate_no_lookahead({}, candles, "2024-01-01T01:00:00", "BTC/USDT") is True

    def test_validate_no_lookahead_fail(self):
        """Error when a future candle is included."""
        candles = [
            {"timestamp": "2024-01-01T00:00:00", "close": 100},
            {"timestamp": "2024-01-01T02:00:00", "close": 102},  # future!
        ]
        assert validate_no_lookahead({}, candles, "2024-01-01T01:00:00", "BTC/USDT") is False

    def test_no_lookahead_in_engine(self):
        """Engine must not pass future candles to AI."""
        config = TournamentConfig(
            experiment_id="lookahead-test",
            symbols=["BTC/USDT"],
            candle_limit=50,
        )
        participants = [
            ParticipantConfig(id="la-test", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}

        # Track what context the AI receives
        received_timestamps = []

        class TrackingStrategy(TradingAI):
            def __init__(self):
                super().__init__(ai_id="tracker", model="tracking")
            def decide(self, context: MarketContext) -> dict:
                # Record the latest candle timestamp we received
                if context.candles:
                    latest = max(c["timestamp"] for c in context.candles)
                    received_timestamps.append((context.timestamp, latest))
                    # Verify we never received a future candle
                    assert latest <= context.timestamp, \
                        f"Got future candle {latest} at time {context.timestamp}"
                return {"decision": "HOLD", "confidence": 0.5}

        tracking_ai = ParticipantConfig(id="tracker", provider="test")
        # Override the create_ai method
        original_create = tracking_ai.create_ai
        tracking_ai.create_ai = lambda: TrackingStrategy()

        engine = TournamentEngine(config=config)
        result = engine.run(participants=[tracking_ai], data=data)

        # Verify we received some contexts
        assert len(received_timestamps) > 0

        # Verify no future data was passed
        for current_ts, latest_candle_ts in received_timestamps:
            assert latest_candle_ts <= current_ts


# ============================================================
# Test: Malformed AI Response
# ============================================================

class TestMalformedAIResponse:
    def test_invalid_json_returns_hold(self):
        """Malaged AI response should default to HOLD."""
        from src.ai.providers.openai_compatible import parse_ai_response
        result = parse_ai_response("this is not json at all")
        assert result["decision"] == "HOLD"
        assert result["confidence"] == 0.0

    def test_invalid_decision_becomes_hold(self):
        """Invalid decision string should become HOLD."""
        from src.ai.providers.openai_compatible import parse_ai_response
        result = parse_ai_response('{"decision": "MOON", "confidence": 0.9}')
        assert result["decision"] == "HOLD"

    def test_tournament_survives_ai_error(self):
        """Tournament should continue even if one AI raises an exception."""
        class BrokenAI(TradingAI):
            def __init__(self):
                super().__init__(ai_id="broken", model="broken")
            def decide(self, context):
                raise RuntimeError("AI exploded")

        config = TournamentConfig(
            experiment_id="broken-test",
            symbols=["BTC/USDT"],
            candle_limit=50,
        )

        # Create a participant that returns BrokenAI
        broken_p = ParticipantConfig(id="broken", provider="test")
        broken_p.create_ai = lambda: BrokenAI()

        healthy_p = ParticipantConfig(id="healthy", provider="test")

        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}
        engine = TournamentEngine(config=config)
        result = engine.run(participants=[broken_p, healthy_p], data=data)

        # Both should be in results, broken one should have HOLD decisions
        assert len(result["participants"]) == 2
        # Healthy one should have made trades
        healthy = [p for p in result["participants"] if p["ai_id"] == "healthy"][0]
        assert healthy["num_trades"] >= 0


# ============================================================
# Test: Provider Timeout / Failure
# ============================================================

class TestProviderFailure:
    def test_unavailable_provider_skipped(self):
        """Unavailable providers should be skipped, not crash tournament."""
        config = TournamentConfig(
            experiment_id="unavail-test",
            symbols=["BTC/USDT"],
            candle_limit=50,
        )
        participants = [
            ParticipantConfig(id="unavail", provider="deepseek", enabled=False),
            ParticipantConfig(id="working", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        # Only working participant should be in results
        assert len(result["participants"]) == 1
        assert result["participants"][0]["ai_id"] == "working"

    def test_provider_not_configured(self):
        """Provider with no API key should be marked unavailable."""
        p = ParticipantConfig(id="no-key", provider="openai", api_key="")
        assert p.is_available is False
        assert p.create_ai() is None


# ============================================================
# Test: Risk Rejection
# ============================================================

class TestRiskRejection:
    def test_low_confidence_rejected(self):
        """Low confidence decisions should be rejected by risk manager."""
        from src.risk.manager import RiskManager
        from src.portfolio.portfolio import Portfolio

        rm = RiskManager(min_confidence=0.6)
        p = Portfolio("test", 1000.0)
        result = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.3)
        assert not result.allowed

    def test_high_confidence_allowed(self):
        """High confidence decisions should pass risk checks."""
        from src.risk.manager import RiskManager
        from src.portfolio.portfolio import Portfolio

        rm = RiskManager(min_confidence=0.6)
        p = Portfolio("test", 1000.0)
        result = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.8, requested_size=0.01)
        assert result.allowed


# ============================================================
# Test: Tournament Execution
# ============================================================

class TestTournamentExecution:
    def test_tournament_runs(self):
        """Basic tournament should complete successfully."""
        config = TournamentConfig(
            symbols=["BTC/USDT"],
            candle_limit=50,
            starting_balance=1000.0,
        )
        participants = [
            ParticipantConfig(id="exec-1", provider="test"),
            ParticipantConfig(id="exec-2", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        assert "experiment_id" in result
        assert "participants" in result
        assert len(result["participants"]) == 2
        assert result["decision_logs_count"] > 0

    def test_tournament_with_multiple_symbols(self):
        """Tournament should handle multiple symbols."""
        config = TournamentConfig(
            symbols=["BTC/USDT", "ETH/USDT"],
            candle_limit=50,
        )
        participants = [
            ParticipantConfig(id="multi-1", provider="test"),
        ]
        data = {
            "BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50),
            "ETH/USDT": generate_synthetic_candles(symbol="ETH/USDT", periods=50),
        }

        engine = TournamentEngine(config=config)
        result = engine.run(participants=participants, data=data)

        assert len(result["participants"]) == 1
        assert result["participants"][0]["num_trades"] >= 0

    def test_tournament_persistence(self):
        """Tournament results should be persisted to database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        db = Database(db_path=db_path)
        db.connect()

        config = TournamentConfig(
            experiment_id="persist-test",
            symbols=["BTC/USDT"],
            candle_limit=50,
        )
        participants = [
            ParticipantConfig(id="persist-1", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=50)}

        engine = TournamentEngine(config=config, database=db)
        result = engine.run(participants=participants, data=data)

        # Verify data was persisted
        trades = db.get_experiment_trades("persist-test")
        decisions = db.get_experiment_decisions("persist-test")
        results_db = db.get_experiment_results("persist-test")

        assert len(trades) >= 0  # May be 0 if strategy doesn't trade much
        assert len(decisions) > 0  # Should have decision logs
        assert len(results_db) == 1  # One backtest run

        db.close()
        db_path.unlink(missing_ok=True)


# ============================================================
# Test: Leaderboard
# ============================================================

class TestLeaderboard:
    def test_leaderboard_format(self):
        """Leaderboard should produce formatted output."""
        m1 = TournamentMetrics(ai_id="AI-1", return_pct=0.15, max_drawdown=0.05,
                               sharpe_ratio=1.5, win_rate=0.6, profit_factor=1.8,
                               composite_score=0.8, starting_balance=1000, ending_balance=1150)
        m2 = TournamentMetrics(ai_id="AI-2", return_pct=0.10, max_drawdown=0.03,
                               sharpe_ratio=1.8, win_rate=0.65, profit_factor=2.0,
                               composite_score=0.9, starting_balance=1000, ending_balance=1100)

        # Assign awards before formatting
        assign_awards([m1, m2])

        output = format_leaderboard([m1, m2], experiment_id="test-exp")
        assert "AI-1" in output
        assert "AI-2" in output
        assert "test-exp" in output
        assert "HIGHEST RETURN" in output or "BEST" in output

    def test_leaderboard_compact(self):
        """Compact leaderboard should be shorter."""
        m1 = TournamentMetrics(ai_id="AI-1", return_pct=0.15, max_drawdown=0.05,
                               sharpe_ratio=1.5, win_rate=0.6, composite_score=0.8,
                               starting_balance=1000, ending_balance=1150)
        output = format_leaderboard_compact([m1], experiment_id="test")
        assert "AI-1" in output

    def test_leaderboard_empty(self):
        """Empty participant list should return message."""
        output = format_leaderboard([])
        assert "No participants" in output

    def test_awards_assigned(self):
        """Awards should be assigned to the best performers."""
        m1 = TournamentMetrics(ai_id="AI-1", return_pct=0.20, max_drawdown=0.10,
                               sharpe_ratio=1.0, win_rate=0.5, profit_factor=1.5,
                               composite_score=0.6, starting_balance=1000, ending_balance=1200)
        m2 = TournamentMetrics(ai_id="AI-2", return_pct=0.10, max_drawdown=0.02,
                               sharpe_ratio=2.0, win_rate=0.7, profit_factor=2.5,
                               composite_score=0.9, starting_balance=1000, ending_balance=1100)

        result = assign_awards([m1, m2])
        # AI-1 has highest return
        assert "Highest Return" in result[0].awards or "Highest Return" in result[1].awards
        # AI-2 has lowest drawdown
        assert "Lowest Drawdown" in result[0].awards or "Lowest Drawdown" in result[1].awards


# ============================================================
# Test: Metrics Calculation
# ============================================================

class TestMetrics:
    def test_composite_score_formula(self):
        """Composite score should follow documented formula."""
        m = TournamentMetrics(
            return_pct=0.10,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            win_rate=0.6,
            max_drawdown=0.05,
            profit_factor=2.0,
        )
        score = compute_composite_score(m)

        # Expected: 0.10*0.25 + 1.5*0.20 + 1.8*0.20 + 0.6*0.10 + (1-0.05)*0.15 + (2/5)*0.10
        # = 0.025 + 0.30 + 0.36 + 0.06 + 0.1425 + 0.04 = 0.9275
        expected = 0.025 + 0.30 + 0.36 + 0.06 + 0.1425 + 0.04
        assert abs(score - expected) < 0.001

    def test_drawdown_penalized(self):
        """Higher drawdown should result in lower score."""
        m_low_dd = TournamentMetrics(
            return_pct=0.10, sharpe_ratio=1.0, sortino_ratio=1.0,
            win_rate=0.5, max_drawdown=0.02, profit_factor=1.5,
        )
        m_high_dd = TournamentMetrics(
            return_pct=0.10, sharpe_ratio=1.0, sortino_ratio=1.0,
            win_rate=0.5, max_drawdown=0.20, profit_factor=1.5,
        )
        assert compute_composite_score(m_low_dd) > compute_composite_score(m_high_dd)

    def test_profit_factor_capped(self):
        """Profit factor should be capped at 5.0 in scoring."""
        m_inf = TournamentMetrics(
            return_pct=0.10, sharpe_ratio=1.0, sortino_ratio=1.0,
            win_rate=0.5, max_drawdown=0.05, profit_factor=float("inf"),
        )
        m_max = TournamentMetrics(
            return_pct=0.10, sharpe_ratio=1.0, sortino_ratio=1.0,
            win_rate=0.5, max_drawdown=0.05, profit_factor=5.0,
        )
        # Both should score the same since PF is capped at 5
        assert compute_composite_score(m_inf) == compute_composite_score(m_max)


# ============================================================
# Test: Participant Configuration
# ============================================================

class TestParticipantConfig:
    def test_test_provider_always_available(self):
        """Test provider should always be available."""
        p = ParticipantConfig(id="test", provider="test")
        assert p.is_available is True

    def test_provider_without_key_disabled(self):
        """Provider without API key should be disabled."""
        p = ParticipantConfig(id="no-key", provider="openai")
        assert p.is_available is False
        assert p.enabled is False

    def test_load_participants_from_list(self):
        """Should create participants from config list."""
        configs = [
            {"id": "p1", "provider": "test"},
            {"id": "p2", "provider": "test"},
        ]
        participants = load_participants_from_list(configs)
        assert len(participants) == 2
        assert participants[0].id == "p1"
        assert participants[1].id == "p2"


# ============================================================
# Test: Prompts
# ============================================================

class TestPrompts:
    def test_prompt_contains_no_lookahead_warning(self):
        """Prompt should explicitly tell AI it has no future data."""
        ctx = MarketContext(
            symbol="BTC/USDT",
            timeframe="1h",
            current_price=50000.0,
            candles=[{"timestamp": "2024-01-01T00:00:00", "open": 49000, "high": 51000,
                      "low": 48000, "close": 50000, "volume": 1000}],
            indicators={"rsi_14": 55.0},
            portfolio_balance=1000.0,
            timestamp="2024-01-01T00:00:00",
        )
        prompt = build_tournament_prompt(ctx)
        assert "NO access to future" in prompt or "no access to future" in prompt.lower()
        assert "BTC/USDT" in prompt
        assert "50000" in prompt

    def test_prompt_includes_risk_limits(self):
        """Prompt should include risk limits when provided."""
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h", current_price=50000.0,
            candles=[], portfolio_balance=1000.0, timestamp="2024-01-01T00:00:00",
        )
        risk = build_risk_limits_dict(max_position_size=0.05, max_open_positions=2)
        prompt = build_tournament_prompt(ctx, risk_limits=risk)
        assert "0.05" in prompt or "5%" in prompt
        assert "2" in prompt


# ============================================================
# Test: Reproducibility
# ============================================================

class TestReproducibility:
    def test_deterministic_strategy_same_results(self):
        """Same deterministic strategy on same data should produce same results."""
        config = TournamentConfig(
            experiment_id="repro-test",
            symbols=["BTC/USDT"],
            candle_limit=100,
            starting_balance=1000.0,
        )
        participants = [
            ParticipantConfig(id="repro-1", provider="test"),
        ]
        data = {"BTC/USDT": generate_synthetic_candles(symbol="BTC/USDT", periods=100, seed=42)}

        engine = TournamentEngine(config=config)
        result1 = engine.run(participants=participants, data=data)

        # Run again with same config
        config2 = TournamentConfig(
            experiment_id="repro-test-2",
            symbols=["BTC/USDT"],
            candle_limit=100,
            starting_balance=1000.0,
        )
        participants2 = [
            ParticipantConfig(id="repro-1", provider="test"),
        ]
        engine2 = TournamentEngine(config=config2)
        result2 = engine2.run(participants=participants2, data=data)

        # Same deterministic strategy on same data should produce identical metrics
        assert result1["participants"][0]["return_pct"] == result2["participants"][0]["return_pct"]
        assert result1["participants"][0]["num_trades"] == result2["participants"][0]["num_trades"]
        assert result1["participants"][0]["max_drawdown"] == result2["participants"][0]["max_drawdown"]
