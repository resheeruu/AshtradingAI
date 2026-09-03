"""Tests for AI validation and isolation."""
import pytest
from src.ai.base import TradingAI, MarketContext, AIDecision
from src.ai.test_strategy import TestStrategy
from src.ai.manager import AIManager
from src.market.candles import generate_synthetic_candles


def test_invalid_decision_becomes_hold():
    ai = TestStrategy()
    validated = ai.validate_decision({"decision": "INVALID"})
    assert validated.decision == "HOLD"


def test_confidence_clamped():
    ai = TestStrategy()
    v = ai.validate_decision({"decision": "BUY", "confidence": 2.0})
    assert v.confidence == 1.0
    v = ai.validate_decision({"decision": "BUY", "confidence": -1.0})
    assert v.confidence == 0.0


def test_ai_isolation():
    manager = AIManager(starting_balance=1000.0)
    manager.register_ai(TestStrategy(ai_id="AI-1"))
    manager.register_ai(TestStrategy(ai_id="AI-2"))
    data = {"BTC/USDT": generate_synthetic_candles(periods=200)}
    results = manager.run_competition(data)
    assert len(results) == 2
    balances = [r["metrics"]["ending_balance"] for r in results]
    assert all(isinstance(b, float) for b in balances)


def test_test_strategy_decision():
    ai = TestStrategy()
    candles = generate_synthetic_candles(periods=100)
    ctx = MarketContext(
        symbol="BTC/USDT",
        timeframe="1h",
        current_price=candles[-1]["close"],
        candles=candles,
        portfolio_balance=1000.0,
    )
    decision = ai.decide(ctx)
    assert "decision" in decision
    assert decision["decision"] in ("BUY", "SELL", "HOLD")


def test_manager_leaderboard():
    manager = AIManager(starting_balance=1000.0)
    manager.register_ai(TestStrategy(ai_id="A"))
    data = {"BTC/USDT": generate_synthetic_candles(periods=100)}
    manager.run_competition(data)
    lb = manager.get_leaderboard()
    assert "A" in lb
