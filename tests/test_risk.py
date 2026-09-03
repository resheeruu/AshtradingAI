"""Tests for risk management."""
import pytest
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager


def test_hold_always_allowed():
    rm = RiskManager()
    p = Portfolio("test", 1000.0)
    r = rm.evaluate(p, "HOLD", "BTC/USDT", 50000.0, 0.5)
    assert r.allowed


def test_low_confidence_rejected():
    rm = RiskManager(min_confidence=0.6)
    p = Portfolio("test", 1000.0)
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.3)
    assert not r.allowed
    assert "confidence" in r.reason


def test_high_confidence_allowed():
    rm = RiskManager(min_confidence=0.6)
    p = Portfolio("test", 1000.0)
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.8, requested_size=0.01)
    assert r.allowed


def test_drawdown_protection():
    rm = RiskManager(max_drawdown=0.10)
    p = Portfolio("test", 1000.0)
    p.balance = 850.0  # 15% drawdown
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.9)
    assert not r.allowed
    assert "drawdown" in r.reason


def test_daily_loss_limit():
    rm = RiskManager(max_daily_loss=0.03)
    p = Portfolio("test", 1000.0)
    p.daily_pnl = -50.0  # 5% daily loss
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.9)
    assert not r.allowed
    assert "daily loss" in r.reason


def test_position_size_capped():
    rm = RiskManager(max_position_size=0.10)
    p = Portfolio("test", 1000.0)
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.9, requested_size=0.1)
    assert r.allowed
    assert r.adjusted_size is not None
    assert r.adjusted_size < 0.1


def test_kill_switch():
    rm = RiskManager()
    p = Portfolio("test", 1000.0)
    rm.activate_kill_switch()
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.99)
    assert not r.allowed
    assert "kill_switch" in r.reason
    rm.deactivate_kill_switch()
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.99, requested_size=0.01)
    assert r.allowed


def test_max_open_positions():
    rm = RiskManager(max_open_positions=2)
    p = Portfolio("test", 100000.0)
    p.open_position("A/USDT", "long", 10.0, 1.0, fee=0.0)
    p.open_position("B/USDT", "long", 10.0, 1.0, fee=0.0)
    r = rm.evaluate(p, "BUY", "C/USDT", 50000.0, confidence=0.9, requested_size=0.01)
    assert not r.allowed
    assert "max_open" in r.reason
