"""Tests for backtesting engine."""
import pytest
from src.ai.test_strategy import TestStrategy
from src.backtest.engine import BacktestEngine
from src.market.candles import generate_synthetic_candles


def test_backtest_runs():
    ai = TestStrategy(ai_id="test-bt")
    bt = BacktestEngine(starting_balance=1000.0)
    data = {"BTC/USDT": generate_synthetic_candles(periods=300)}
    metrics, portfolio = bt.run(ai, data)
    assert metrics.starting_balance == 1000.0
    assert metrics.num_trades >= 0


def test_backtest_reproducible():
    ai = TestStrategy(ai_id="repro")
    data = {"BTC/USDT": generate_synthetic_candles(periods=200)}
    bt1 = BacktestEngine(starting_balance=1000.0)
    m1, _ = bt1.run(ai, data)
    bt2 = BacktestEngine(starting_balance=1000.0)
    m2, _ = bt2.run(ai, data)
    assert m1.summary()["ending_balance"] == m2.summary()["ending_balance"]
    assert m1.summary()["num_trades"] == m2.summary()["num_trades"]


def test_backtest_with_fees():
    ai = TestStrategy(ai_id="fees")
    data = {"BTC/USDT": generate_synthetic_candles(periods=200)}
    bt = BacktestEngine(starting_balance=1000.0, fee=0.01)
    metrics, _ = bt.run(ai, data)
    assert metrics.fees_paid >= 0


def test_metrics_max_drawdown():
    ai = TestStrategy(ai_id="dd")
    data = {"BTC/USDT": generate_synthetic_candles(periods=200, volatility=0.05)}
    bt = BacktestEngine(starting_balance=1000.0)
    metrics, _ = bt.run(ai, data)
    assert 0.0 <= metrics.max_drawdown <= 1.0


def test_metrics_summary_dict():
    ai = TestStrategy(ai_id="dict")
    data = {"BTC/USDT": generate_synthetic_candles(periods=100)}
    bt = BacktestEngine(starting_balance=1000.0)
    metrics, _ = bt.run(ai, data)
    s = metrics.summary()
    assert isinstance(s, dict)
    assert "return_pct" in s
    assert "sharpe_ratio" in s
