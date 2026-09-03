"""Tests for portfolio accounting."""
import pytest
from src.portfolio.portfolio import Portfolio


def test_portfolio_initialization():
    p = Portfolio("test-ai", 1000.0)
    assert p.ai_id == "test-ai"
    assert p.balance == 1000.0
    assert p.starting_balance == 1000.0
    assert len(p.positions) == 0
    assert len(p.trade_history) == 0


def test_open_position():
    p = Portfolio("test-ai", 1000.0)
    ok = p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    assert ok is True
    assert "BTC/USDT" in p.positions
    assert p.positions["BTC/USDT"].quantity == 1.0
    assert p.balance < 1000.0


def test_open_position_insufficient_funds():
    p = Portfolio("test-ai", 10.0)
    ok = p.open_position("BTC/USDT", "long", 50000.0, 1.0)
    assert ok is False
    assert "BTC/USDT" not in p.positions


def test_close_position_profit():
    p = Portfolio("test-ai", 1000.0)
    p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    record = p.close_position("BTC/USDT", 110.0, fee=0.11)
    assert record is not None
    assert record.pnl > 0
    assert p.balance > 1000.0


def test_close_position_loss():
    p = Portfolio("test-ai", 1000.0)
    p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    record = p.close_position("BTC/USDT", 80.0, fee=0.08)
    assert record is not None
    assert record.pnl < 0


def test_close_nonexistent_position():
    p = Portfolio("test-ai", 1000.0)
    record = p.close_position("FAKE/USDT", 100.0)
    assert record is None


def test_daily_pnl_tracking():
    p = Portfolio("test-ai", 1000.0)
    assert p.daily_pnl == 0.0
    p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    p.close_position("BTC/USDT", 110.0, fee=0.11)
    assert p.daily_pnl > 0
    p.reset_daily_pnl()
    assert p.daily_pnl == 0.0


def test_summary():
    p = Portfolio("test-ai", 1000.0)
    s = p.summary()
    assert s["ai_id"] == "test-ai"
    assert s["balance"] == 1000.0


def test_position_count():
    p = Portfolio("test-ai", 100000.0)
    for sym in ["A/USDT", "B/USDT", "C/USDT"]:
        p.open_position(sym, "long", 10.0, 1.0, fee=0.0)
    assert len(p.positions) == 3
