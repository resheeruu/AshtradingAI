"""Tests for paper broker."""
import pytest
from src.portfolio.portfolio import Portfolio
from src.trading.paper.broker import PaperBroker


def test_buy_order():
    broker = PaperBroker(fee=0.001, slippage=0.0005)
    p = Portfolio("test", 10000.0)
    order = broker.execute_buy(p, "BTC/USDT", 50000.0, 0.01)
    assert order is not None
    assert order["status"] == "filled"
    assert order["side"] == "buy"
    assert order["fee"] > 0
    assert "BTC/USDT" in p.positions


def test_sell_order():
    broker = PaperBroker(fee=0.001, slippage=0.0005)
    p = Portfolio("test", 10000.0)
    broker.execute_buy(p, "BTC/USDT", 50000.0, 0.01)
    order = broker.execute_sell(p, "BTC/USDT", 51000.0)
    assert order is not None
    assert order["side"] == "sell"
    assert "BTC/USDT" not in p.positions


def test_sell_no_position():
    broker = PaperBroker()
    p = Portfolio("test", 1000.0)
    order = broker.execute_sell(p, "BTC/USDT", 50000.0)
    assert order is None


def test_fee_calculation():
    broker = PaperBroker(fee=0.01, slippage=0.0)
    p = Portfolio("test", 10000.0)
    order = broker.execute_buy(p, "BTC/USDT", 1000.0, 1.0)
    # fee = price * qty * fee_rate = 1000 * 1 * 0.01 = 10
    assert order["fee"] == pytest.approx(10.0, abs=0.01)


def test_slippage_applied():
    broker = PaperBroker(fee=0.0, slippage=0.01)
    p = Portfolio("test", 10000.0)
    order = broker.execute_buy(p, "BTC/USDT", 1000.0, 1.0)
    assert order["price"] > 1000.0


def test_insufficient_balance():
    broker = PaperBroker()
    p = Portfolio("test", 50.0)
    order = broker.execute_buy(p, "BTC/USDT", 50000.0, 0.01)
    assert order is None


def test_order_retrieval():
    broker = PaperBroker()
    p = Portfolio("test", 10000.0)
    order = broker.execute_buy(p, "ETH/USDT", 3000.0, 0.1)
    retrieved = broker.get_order(order["id"])
    assert retrieved is not None
    assert retrieved["symbol"] == "ETH/USDT"
