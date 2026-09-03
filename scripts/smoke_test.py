"""Smoke test — runs without API credentials to verify basic functionality."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.ai.test_strategy import TestStrategy
from src.ai.manager import AIManager
from src.market.candles import generate_synthetic_candles
from src.indicators.technical import compute_all_indicators
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.backtest.engine import BacktestEngine


def test_config():
    print("[1] Config validation...")
    if Config.LIVE_TRADING:
        print("  FAIL: LIVE_TRADING is true")
        return False
    errors = Config.validate()
    live_errors = [e for e in errors if "LIVE_TRADING" in e]
    if live_errors:
        print(f"  FAIL: {live_errors}")
        return False
    print("  PASS")
    return True


def test_indicators():
    print("[2] Technical indicators...")
    candles = generate_synthetic_candles(periods=100)
    indicators = compute_all_indicators(candles)
    required = ["sma_20", "ema_12", "rsi_14", "macd", "atr_14", "bb_upper"]
    for key in required:
        if key not in indicators:
            print(f"  FAIL: missing indicator {key}")
            return False
    # Check lengths match
    if len(indicators["rsi_14"]) != 100:
        print(f"  FAIL: RSI length mismatch")
        return False
    print("  PASS")
    return True


def test_portfolio():
    print("[3] Portfolio accounting...")
    p = Portfolio("test", 1000.0)
    assert p.balance == 1000.0
    # Buy: cost = 100*1 + 0.1 = 100.1
    ok = p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    assert ok is True
    assert "BTC/USDT" in p.positions
    # Sell: proceeds = 110*1 - 0.11 = 109.89 => pnl > 0
    record = p.close_position("BTC/USDT", 110.0, fee=0.11)
    assert record is not None
    assert record.pnl > 0
    assert p.balance > 1000.0
    print("  PASS")
    return True


def test_paper_broker():
    print("[4] Paper broker...")
    broker = PaperBroker(fee=0.001, slippage=0.0005)
    p = Portfolio("test-broker", 1000.0)
    order = broker.execute_buy(p, "ETH/USDT", 3000.0, 0.1)
    assert order is not None
    assert order["status"] == "filled"
    order = broker.execute_sell(p, "ETH/USDT", 3100.0)
    assert order is not None
    assert order["pnl"] > 0
    print("  PASS")
    return True


def test_risk_manager():
    print("[5] Risk manager...")
    rm = RiskManager(max_position_size=0.10, max_open_positions=2, min_confidence=0.6)
    p = Portfolio("test-risk", 1000.0)
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.3)
    assert not r.allowed
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.8, requested_size=0.01)
    assert r.allowed
    rm.activate_kill_switch()
    r = rm.evaluate(p, "BUY", "BTC/USDT", 50000.0, confidence=0.9)
    assert not r.allowed
    rm.deactivate_kill_switch()
    print("  PASS")
    return True


def test_backtest():
    print("[6] Backtest engine...")
    ai = TestStrategy(ai_id="smoke-test")
    bt = BacktestEngine(starting_balance=1000.0, fee=0.001, slippage=0.0005)
    data = {"BTC/USDT": generate_synthetic_candles(periods=500)}
    metrics, portfolio = bt.run(ai, data, "1h")
    m = metrics.summary()
    assert m["starting_balance"] == 1000.0
    assert m["num_trades"] >= 0
    assert m["max_drawdown"] >= 0.0
    print(f"  Trades: {m['num_trades']}, Return: {m['return_pct']:.2%}, DD: {m['max_drawdown']:.2%}")
    print("  PASS")
    return True


def test_ai_manager():
    print("[7] AI manager competition...")
    manager = AIManager(starting_balance=1000.0)
    manager.register_ai(TestStrategy(ai_id="AI-A"))
    manager.register_ai(TestStrategy(ai_id="AI-B"))
    data = {"BTC/USDT": generate_synthetic_candles(periods=300)}
    results = manager.run_competition(data)
    assert len(results) == 2
    assert "ai_id" in results[0]
    print(f"  Winner: {results[0]['ai_id']}")
    print("  PASS")
    return True


def main():
    print("=== ASHTRADINGAI SMOKE TEST ===\n")
    tests = [
        test_config, test_indicators, test_portfolio,
        test_paper_broker, test_risk_manager, test_backtest, test_ai_manager,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            if t():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n=== RESULTS: {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
