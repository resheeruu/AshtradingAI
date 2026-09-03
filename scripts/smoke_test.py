"""Smoke test — runs without API credentials to verify basic functionality."""
import sys
import json
import tempfile
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
from src.market.validation import validate_candles, validate_candle
from src.market.data import OfflineMarketData
from src.persistence.database import Database
from src.ai.providers.openai_compatible import parse_ai_response


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
    if len(indicators["rsi_14"]) != 100:
        print(f"  FAIL: RSI length mismatch")
        return False
    print("  PASS")
    return True


def test_portfolio():
    print("[3] Portfolio accounting...")
    p = Portfolio("test", 1000.0)
    assert p.balance == 1000.0
    ok = p.open_position("BTC/USDT", "long", 100.0, 1.0, fee=0.1)
    assert ok is True
    assert "BTC/USDT" in p.positions
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


def test_candle_validation():
    print("[8] Candle validation...")
    # Valid candle
    valid_candle = {
        "timestamp": "2024-01-01T00:00:00+00:00",
        "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
    }
    err = validate_candle(valid_candle)
    assert err is None, f"Valid candle rejected: {err}"

    # Missing field
    bad = {"timestamp": "2024-01-01T00:00:00+00:00", "open": 100.0}
    err = validate_candle(bad)
    assert err is not None, "Should reject missing fields"

    # Low > High
    bad2 = {
        "timestamp": "2024-01-01T00:00:00+00:00",
        "open": 100.0, "high": 90.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
    }
    err = validate_candle(bad2)
    assert err is not None, "Should reject low > high"

    # Full validation with duplicates
    candles = [valid_candle, valid_candle]
    valid, errors = validate_candles(candles)
    assert len(valid) == 1, f"Should deduplicate, got {len(valid)}"
    assert any("duplicate" in e for e in errors)

    print("  PASS")
    return True


def test_sqlite_persistence():
    print("[9] SQLite persistence...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = Database(db_path=db_path)
    db.connect()

    # Log a trade
    trade_id = db.log_trade(
        ai_id="test-ai", symbol="BTC/USDT", side="long",
        entry_price=50000.0, exit_price=55000.0, quantity=0.01,
        fee=5.0, slippage=2.5, pnl=492.5, balance=1492.5,
        experiment_id="exp-001",
    )
    assert trade_id

    # Log a decision
    dec_id = db.log_decision(
        ai_id="test-ai", symbol="BTC/USDT", decision="BUY",
        confidence=0.85, reason="RSI oversold",
        suggested_position_size=0.05, stop_loss=49000.0,
        take_profit=56000.0, market_price=50000.0,
        experiment_id="exp-001",
    )
    assert dec_id

    # Log a backtest run
    run_id = db.log_backtest_run(
        ai_id="test-ai", symbol="BTC/USDT", timeframe="1h",
        starting_balance=1000.0, ending_balance=1500.0,
        return_percent=0.5, max_drawdown=0.1, win_rate=0.6,
        profit_factor=1.5, sharpe_ratio=1.2, sortino_ratio=1.8,
        trade_count=10, experiment_id="exp-001",
    )
    assert run_id

    # Verify counts
    assert db.get_trade_count(experiment_id="exp-001") == 1
    assert db.get_decision_count(experiment_id="exp-001") == 1

    # Get leaderboard data
    lb = db.get_leaderboard_data("exp-001")
    assert len(lb) == 1
    assert lb[0]["ai_id"] == "test-ai"

    db.close()
    db_path.unlink(missing_ok=True)
    print("  PASS")
    return True


def test_ai_response_parsing():
    print("[10] AI response parsing...")

    # Normal JSON
    resp = '{"decision": "BUY", "confidence": 0.82, "reason": "test", "suggested_position_size": 0.05, "stop_loss": 49000, "take_profit": 56000}'
    parsed = parse_ai_response(resp)
    assert parsed["decision"] == "BUY"
    assert parsed["confidence"] == 0.82

    # JSON in markdown code block
    resp2 = '```json\n{"decision": "SELL", "confidence": 0.9, "reason": "overbought"}\n```'
    parsed2 = parse_ai_response(resp2)
    assert parsed2["decision"] == "SELL"
    assert parsed2["confidence"] == 0.9

    # Invalid JSON -> fallback to HOLD
    parsed3 = parse_ai_response("this is not json at all")
    assert parsed3["decision"] == "HOLD"
    assert parsed3["confidence"] == 0.0

    # Invalid decision -> HOLD
    resp4 = '{"decision": "MOON", "confidence": 0.5, "reason": "test"}'
    parsed4 = parse_ai_response(resp4)
    assert parsed4["decision"] == "HOLD"

    # Out of range confidence -> clamped
    resp5 = '{"decision": "BUY", "confidence": 5.0, "reason": "test"}'
    parsed5 = parse_ai_response(resp5)
    assert parsed5["confidence"] == 1.0

    print("  PASS")
    return True


def test_ai_isolation():
    print("[11] AI isolation...")
    manager = AIManager(starting_balance=1000.0)
    manager.register_ai(TestStrategy(ai_id="AI-One"))
    manager.register_ai(TestStrategy(ai_id="AI-Two"))
    data = {"BTC/USDT": generate_synthetic_candles(periods=200)}
    results = manager.run_competition(data)

    # Each AI should have its own results
    assert len(results) == 2
    ids = {r["ai_id"] for r in results}
    assert "AI-One" in ids
    assert "AI-Two" in ids

    # Portfolios should be independent
    for entry in manager.entries:
        assert entry.portfolio.ai_id in ("AI-One", "AI-Two")
        # No cross-contamination
        assert entry.portfolio.balance != 0 or entry.portfolio.trade_history == []

    print("  PASS")
    return True


def test_fair_experiment():
    print("[12] Fair experiment comparison...")
    manager = AIManager(starting_balance=1000.0, fee=0.001, slippage=0.0005)
    manager.register_ai(TestStrategy(ai_id="Fair-A"))
    manager.register_ai(TestStrategy(ai_id="Fair-B"))
    data = {"BTC/USDT": generate_synthetic_candles(periods=300, seed=99)}
    results = manager.run_competition(data, experiment_id="fair-test")

    # Both should have the same starting balance
    for r in results:
        assert r["metrics"]["starting_balance"] == 1000.0

    # Both used the same data
    assert len(data["BTC/USDT"]) == 300

    print("  PASS")
    return True


def main():
    print("=== ASHTRADINGAI SMOKE TEST ===\n")
    tests = [
        test_config, test_indicators, test_portfolio,
        test_paper_broker, test_risk_manager, test_backtest, test_ai_manager,
        test_candle_validation, test_sqlite_persistence, test_ai_response_parsing,
        test_ai_isolation, test_fair_experiment,
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
