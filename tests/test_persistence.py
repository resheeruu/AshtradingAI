"""Tests for SQLite persistence layer."""
import tempfile
import pytest
from pathlib import Path
from src.persistence.database import Database


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    database = Database(db_path=path)
    database.connect()
    yield database
    database.close()
    path.unlink(missing_ok=True)


class TestDatabase:
    def test_log_trade(self, db):
        trade_id = db.log_trade(
            ai_id="test-ai", symbol="BTC/USDT", side="long",
            entry_price=50000.0, exit_price=55000.0, quantity=0.01,
            fee=5.0, slippage=2.5, pnl=492.5, balance=1492.5,
            experiment_id="exp-1",
        )
        assert trade_id
        assert db.get_trade_count(experiment_id="exp-1") == 1

    def test_log_decision(self, db):
        dec_id = db.log_decision(
            ai_id="test-ai", symbol="BTC/USDT", decision="BUY",
            confidence=0.85, reason="RSI oversold",
            suggested_position_size=0.05, stop_loss=49000.0,
            take_profit=56000.0, market_price=50000.0,
            experiment_id="exp-1",
        )
        assert dec_id
        assert db.get_decision_count(experiment_id="exp-1") == 1

    def test_log_backtest_run(self, db):
        run_id = db.log_backtest_run(
            ai_id="test-ai", symbol="BTC/USDT", timeframe="1h",
            starting_balance=1000.0, ending_balance=1500.0,
            return_percent=0.5, max_drawdown=0.1, win_rate=0.6,
            profit_factor=1.5, sharpe_ratio=1.2, sortino_ratio=1.8,
            trade_count=10, experiment_id="exp-1",
        )
        assert run_id
        results = db.get_experiment_results("exp-1")
        assert len(results) == 1
        assert results[0]["ai_id"] == "test-ai"

    def test_experiment_isolation(self, db):
        db.log_trade(ai_id="ai-1", symbol="BTC/USDT", side="long",
                     entry_price=50000, exit_price=55000, quantity=0.01,
                     fee=5, slippage=2.5, pnl=492.5, balance=1492.5,
                     experiment_id="exp-1")
        db.log_trade(ai_id="ai-2", symbol="ETH/USDT", side="long",
                     entry_price=3000, exit_price=3300, quantity=0.1,
                     fee=3, slippage=1.5, pnl=295.5, balance=1295.5,
                     experiment_id="exp-2")
        assert db.get_trade_count(experiment_id="exp-1") == 1
        assert db.get_trade_count(experiment_id="exp-2") == 1

    def test_leaderboard_data(self, db):
        db.log_backtest_run(ai_id="ai-1", symbol="BTC/USDT", timeframe="1h",
                            starting_balance=1000, ending_balance=1500,
                            return_percent=0.5, max_drawdown=0.1, win_rate=0.6,
                            profit_factor=1.5, sharpe_ratio=1.2, sortino_ratio=1.8,
                            trade_count=10, experiment_id="exp-1")
        db.log_backtest_run(ai_id="ai-2", symbol="BTC/USDT", timeframe="1h",
                            starting_balance=1000, ending_balance=1200,
                            return_percent=0.2, max_drawdown=0.05, win_rate=0.7,
                            profit_factor=2.0, sharpe_ratio=1.5, sortino_ratio=2.0,
                            trade_count=8, experiment_id="exp-1")
        lb = db.get_leaderboard_data("exp-1")
        assert len(lb) == 2
        # Should be sorted by sharpe_ratio
        assert lb[0]["sharpe_ratio"] >= lb[1]["sharpe_ratio"]

    def test_clear_experiment(self, db):
        db.log_trade(ai_id="ai-1", symbol="BTC/USDT", side="long",
                     entry_price=50000, exit_price=55000, quantity=0.01,
                     fee=5, slippage=2.5, pnl=492.5, balance=1492.5,
                     experiment_id="exp-1")
        db.log_decision(ai_id="ai-1", symbol="BTC/USDT", decision="BUY",
                        confidence=0.85, reason="test", suggested_position_size=0.05,
                        stop_loss=49000, take_profit=56000, market_price=50000,
                        experiment_id="exp-1")
        db.log_backtest_run(ai_id="ai-1", symbol="BTC/USDT", timeframe="1h",
                            starting_balance=1000, ending_balance=1500,
                            return_percent=0.5, max_drawdown=0.1, win_rate=0.6,
                            profit_factor=1.5, sharpe_ratio=1.2, sortino_ratio=1.8,
                            trade_count=10, experiment_id="exp-1")
        db.clear_experiment("exp-1")
        assert db.get_trade_count(experiment_id="exp-1") == 0
        assert db.get_decision_count(experiment_id="exp-1") == 0
        assert len(db.get_experiment_results("exp-1")) == 0

    def test_ai_filtering(self, db):
        db.log_trade(ai_id="ai-1", symbol="BTC/USDT", side="long",
                     entry_price=50000, exit_price=55000, quantity=0.01,
                     fee=5, slippage=2.5, pnl=492.5, balance=1492.5,
                     experiment_id="exp-1")
        db.log_trade(ai_id="ai-2", symbol="ETH/USDT", side="long",
                     entry_price=3000, exit_price=3300, quantity=0.1,
                     fee=3, slippage=1.5, pnl=295.5, balance=1295.5,
                     experiment_id="exp-1")
        assert db.get_trade_count(ai_id="ai-1") == 1
        assert db.get_trade_count(ai_id="ai-2") == 1
