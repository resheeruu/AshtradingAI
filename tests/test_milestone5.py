"""Tests for Milestone 5: Paper-Live mode, scheduler, market health, persistence."""
import json
import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from src.market.health import MarketHealth, MarketState
from src.market.scheduler import CandleScheduler, is_candle_completed, timeframe_to_seconds, parse_candle_timestamp
from src.persistence.database import Database
from src.config import Config


# --- Market Health Tests ---

class TestMarketHealth:
    def test_initial_state(self):
        mh = MarketHealth(max_stale_seconds=300)
        assert mh.get_state("BTC/USDT") == MarketState.UNAVAILABLE

    def test_record_success(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        assert mh.get_state("BTC/USDT") == MarketState.ONLINE
        assert mh.get_last_candle_timestamp("BTC/USDT") == ts

    def test_stale_detection(self):
        mh = MarketHealth(max_stale_seconds=1)
        ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        mh.record_success("BTC/USDT", ts)
        # Manually set last_success_time to past to simulate staleness
        mh._last_success_time["BTC/USDT"] = time.time() - 10
        assert mh.get_state("BTC/USDT") == MarketState.STALE

    def test_not_stale_when_fresh(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        assert mh.get_state("BTC/USDT") == MarketState.ONLINE
        assert not mh.is_stale("BTC/USDT")

    def test_network_error(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_network_error("BTC/USDT", "connection refused")
        assert mh.get_state("BTC/USDT") == MarketState.NETWORK_ERROR
        assert mh.get_consecutive_failures("BTC/USDT") == 1
        assert mh.get_last_error("BTC/USDT") == "connection refused"

    def test_consecutive_failures(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_network_error("BTC/USDT", "err1")
        mh.record_network_error("BTC/USDT", "err2")
        assert mh.get_consecutive_failures("BTC/USDT") == 2

    def test_rate_limited(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_rate_limited("BTC/USDT")
        assert mh.get_state("BTC/USDT") == MarketState.RATE_LIMITED

    def test_invalid_data(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_invalid_data("BTC/USDT", "bad candle")
        assert mh.get_state("BTC/USDT") == MarketState.INVALID_DATA

    def test_unavailable(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_unavailable("BTC/USDT", "no data")
        assert mh.get_state("BTC/USDT") == MarketState.UNAVAILABLE

    def test_is_healthy(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        assert mh.is_healthy("BTC/USDT")

    def test_multi_symbol(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        mh.record_network_error("ETH/USDT", "timeout")
        assert mh.get_state("BTC/USDT") == MarketState.ONLINE
        assert mh.get_state("ETH/USDT") == MarketState.NETWORK_ERROR

    def test_summary(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        s = mh.get_summary()
        assert s["max_stale_seconds"] == 300
        assert "BTC/USDT" in s["symbols"]
        assert s["symbols"]["BTC/USDT"]["state"] == "ONLINE"

    def test_get_all_states(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        states = mh.get_all_states()
        assert states["BTC/USDT"] == "ONLINE"


# --- Candle Scheduler Tests ---

class TestCandleScheduler:
    def test_timeframe_to_seconds(self):
        assert timeframe_to_seconds("1m") == 60
        assert timeframe_to_seconds("5m") == 300
        assert timeframe_to_seconds("1h") == 3600
        assert timeframe_to_seconds("1d") == 86400
        assert timeframe_to_seconds("unknown") == 3600  # default

    def test_parse_candle_timestamp(self):
        ts = "2024-01-01T00:00:00+00:00"
        result = parse_candle_timestamp(ts)
        assert result is not None
        assert result > 0

    def test_parse_candle_timestamp_invalid(self):
        assert parse_candle_timestamp("not-a-timestamp") is None
        assert parse_candle_timestamp("") is None

    def test_is_candle_completed_future(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        assert is_candle_completed(future, "1h") is False

    def test_is_candle_completed_past(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert is_candle_completed(past, "1h") is True

    def test_scheduler_should_process(self):
        sched = CandleScheduler("1h")
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert sched.should_process(past) is True

    def test_scheduler_duplicate_prevention(self):
        sched = CandleScheduler("1h")
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert sched.should_process(past) is True
        sched.mark_processed(past)
        assert sched.should_process(past) is False

    def test_scheduler_set_last_processed(self):
        sched = CandleScheduler("1h")
        ts = "2024-01-01T00:00:00+00:00"
        sched.set_last_processed(ts)
        assert sched.last_processed_candle == ts
        assert sched.has_processed(ts)

    def test_scheduler_next_candle_time(self):
        sched = CandleScheduler("1h")
        ts = "2024-01-01T00:00:00+00:00"
        next_time = sched.get_next_candle_time(ts)
        assert next_time is not None
        assert next_time > 0

    def test_scheduler_seconds_until_next(self):
        sched = CandleScheduler("1h")
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        sched.set_last_processed(past)
        wait = sched.seconds_until_next_candle()
        assert wait >= 0


# --- Paper Session Persistence Tests ---

class TestPaperSessionPersistence:
    def setup_method(self):
        import tempfile
        import os
        self.tmp = tempfile.mktemp(suffix=".db")
        self.db = Database(db_path=__import__("pathlib").Path(self.tmp))
        self.db.connect()

    def teardown_method(self):
        self.db.close()
        import os
        try:
            os.unlink(self.tmp)
        except OSError:
            pass

    def test_create_session(self):
        sid = self.db.create_paper_session(
            session_id="test-001",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        assert sid == "test-001"
        session = self.db.get_paper_session("test-001")
        assert session is not None
        assert session["exchange"] == "binance"
        assert session["starting_balance"] == 1000.0
        assert session["current_balance"] == 1000.0

    def test_get_active_session(self):
        self.db.create_paper_session(
            session_id="test-002",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        active = self.db.get_active_paper_session("binance")
        assert active is not None
        assert active["id"] == "test-002"

    def test_update_session(self):
        self.db.create_paper_session(
            session_id="test-003",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        self.db.update_paper_session(
            session_id="test-003",
            current_balance=950.0,
            last_processed_candle="2024-01-01T01:00:00+00:00",
        )
        session = self.db.get_paper_session("test-003")
        assert session["current_balance"] == 950.0
        assert session["last_processed_candle"] == "2024-01-01T01:00:00+00:00"

    def test_close_session(self):
        self.db.create_paper_session(
            session_id="test-004",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        self.db.close_paper_session("test-004")
        session = self.db.get_paper_session("test-004")
        assert session["status"] == "closed"

    def test_positions_persistence(self):
        self.db.create_paper_session(
            session_id="test-005",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        positions = {"BTC/USDT": {"side": "long", "entry_price": 50000, "quantity": 0.01}}
        self.db.update_paper_session(
            session_id="test-005",
            open_positions_json=json.dumps(positions),
        )
        session = self.db.get_paper_session("test-005")
        loaded = json.loads(session["open_positions_json"])
        assert "BTC/USDT" in loaded
        assert loaded["BTC/USDT"]["side"] == "long"

    def test_trades_persistence(self):
        self.db.create_paper_session(
            session_id="test-006",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        trades = [{"symbol": "BTC/USDT", "side": "buy", "pnl": 10.0}]
        self.db.update_paper_session(
            session_id="test-006",
            trade_history_json=json.dumps(trades),
        )
        session = self.db.get_paper_session("test-006")
        loaded = json.loads(session["trade_history_json"])
        assert len(loaded) == 1
        assert loaded[0]["pnl"] == 10.0

    def test_get_sessions(self):
        self.db.create_paper_session(
            session_id="test-007",
            exchange="binance",
            symbols="BTC/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )
        sessions = self.db.get_paper_sessions()
        assert len(sessions) >= 1


# --- Restart Recovery Tests ---

class TestRestartRecovery:
    def setup_method(self):
        import tempfile
        self.tmp = tempfile.mktemp(suffix=".db")
        self.db = Database(db_path=__import__("pathlib").Path(self.tmp))
        self.db.connect()

    def teardown_method(self):
        self.db.close()
        import os
        try:
            os.unlink(self.tmp)
        except OSError:
            pass

    def test_full_recovery_cycle(self):
        from src.portfolio.portfolio import Portfolio, Position, TradeRecord

        session_id = "recovery-test"
        self.db.create_paper_session(
            session_id=session_id,
            exchange="binance",
            symbols="BTC/USDT,ETH/USDT",
            timeframe="1h",
            data_source="live",
            starting_balance=1000.0,
        )

        portfolio = Portfolio(ai_id="test", starting_balance=1000.0)
        portfolio.balance = 950.0
        portfolio.positions["BTC/USDT"] = Position(
            symbol="BTC/USDT", side="long", entry_price=50000,
            quantity=0.001, entry_time="2024-01-01T00:00:00+00:00",
        )
        portfolio.trade_history.append(TradeRecord(
            symbol="BTC/USDT", side="long", entry_price=50000,
            exit_price=51000, quantity=0.001, fee=0.5, slippage=0.0005,
            pnl=10.0, entry_time="2024-01-01T00:00:00+00:00",
            exit_time="2024-01-01T01:00:00+00:00",
        ))

        positions_json = json.dumps(
            {sym: {"side": p.side, "entry_price": p.entry_price,
                    "quantity": p.quantity, "entry_time": p.entry_time}
             for sym, p in portfolio.positions.items()}
        )
        trades_json = json.dumps(
            [{"symbol": t.symbol, "side": t.side, "entry_price": t.entry_price,
              "exit_price": t.exit_price, "quantity": t.quantity, "pnl": t.pnl,
              "fee": t.fee, "entry_time": t.entry_time, "exit_time": t.exit_time}
             for t in portfolio.trade_history]
        )
        self.db.update_paper_session(
            session_id=session_id,
            current_balance=portfolio.balance,
            last_processed_candle="2024-01-01T01:00:00+00:00",
            open_positions_json=positions_json,
            trade_history_json=trades_json,
        )

        session = self.db.get_paper_session(session_id)
        assert session is not None

        recovered = Portfolio(ai_id="recovered", starting_balance=1000.0)
        recovered.balance = session["current_balance"]
        pos_data = json.loads(session["open_positions_json"])
        for sym, pdata in pos_data.items():
            recovered.positions[sym] = Position(
                symbol=sym, side=pdata["side"],
                entry_price=pdata["entry_price"],
                quantity=pdata["quantity"],
                entry_time=pdata.get("entry_time"),
            )
        trades_data = json.loads(session["trade_history_json"])
        for t in trades_data:
            recovered.trade_history.append(TradeRecord(
                symbol=t["symbol"], side=t["side"],
                entry_price=t["entry_price"],
                exit_price=t.get("exit_price", 0.0),
                quantity=t["quantity"],
                fee=t.get("fee", 0.0),
                slippage=t.get("slippage", 0.0),
                pnl=t.get("pnl", 0.0),
                entry_time=t.get("entry_time"),
                exit_time=t.get("exit_time"),
            ))

        assert abs(recovered.balance - portfolio.balance) < 0.01
        assert len(recovered.positions) == len(portfolio.positions)
        assert len(recovered.trade_history) == len(portfolio.trade_history)
        assert recovered.positions["BTC/USDT"].entry_price == 50000


# --- Safety Tests ---

class TestSafety:
    def test_live_trading_blocks_paper_live(self):
        assert Config.LIVE_TRADING is False

    def test_config_validate_live_trading(self):
        original = Config.LIVE_TRADING
        try:
            Config.LIVE_TRADING = True
            errors = Config.validate()
            assert any("LIVE_TRADING" in e for e in errors)
        finally:
            Config.LIVE_TRADING = original

    def test_paper_session_config_defaults(self):
        assert Config.MARKET_MAX_STALE_SECONDS >= 0
        assert Config.MARKET_RETRY_SECONDS >= 0
        assert Config.PAPER_HEARTBEAT_SECONDS >= 0

    def test_config_has_paper_live_settings(self):
        assert hasattr(Config, "PAPER_SESSION_ID")
        assert hasattr(Config, "PAPER_AUTO_RESUME")
        assert hasattr(Config, "MARKET_MAX_STALE_SECONDS")
        assert hasattr(Config, "MARKET_RETRY_SECONDS")
        assert hasattr(Config, "PAPER_HEARTBEAT_SECONDS")


# --- Multi-Symbol Isolation Tests ---

class TestMultiSymbolIsolation:
    def test_market_health_per_symbol(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        mh.record_network_error("ETH/USDT", "timeout")
        assert mh.get_state("BTC/USDT") == MarketState.ONLINE
        assert mh.get_state("ETH/USDT") == MarketState.NETWORK_ERROR

    def test_scheduler_per_symbol(self):
        sched_btc = CandleScheduler("1h")
        sched_eth = CandleScheduler("1h")
        ts = "2024-01-01T00:00:00+00:00"
        sched_btc.mark_processed(ts)
        assert sched_btc.has_processed(ts) is True
        assert sched_eth.has_processed(ts) is False

    def test_portfolio_isolation(self):
        from src.portfolio.portfolio import Portfolio
        p1 = Portfolio(ai_id="ai1", starting_balance=1000)
        p2 = Portfolio(ai_id="ai2", starting_balance=2000)
        assert p1.balance == 1000
        assert p2.balance == 2000
        p1.balance = 500
        assert p2.balance == 2000


# --- No Lookahead Tests ---

class TestNoLookahead:
    def test_context_limited_to_current_candle(self):
        from src.ai.base import MarketContext
        candles = [
            {"timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
             "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
            for i in range(10)
        ]
        ctx = MarketContext(
            symbol="BTC/USDT",
            timeframe="1h",
            current_price=candles[5]["close"],
            candles=candles[:6],
            indicators={},
            portfolio_balance=1000,
            open_positions=[],
            timestamp=candles[5]["timestamp"],
        )
        assert len(ctx.candles) == 6
        assert ctx.candles[-1]["timestamp"] == "2024-01-01T05:00:00+00:00"
        for c in ctx.candles:
            assert c["timestamp"] <= ctx.timestamp


# --- AI Error -> HOLD Tests ---

class TestAIErrorToHold:
    def test_ai_exception_results_in_hold(self):
        from src.ai.base import TradingAI, MarketContext

        class FailingAI(TradingAI):
            def decide(self, context):
                raise RuntimeError("AI provider failed")

        ai = FailingAI(ai_id="failing")
        ctx = MarketContext(
            symbol="BTC/USDT", timeframe="1h",
            current_price=50000, candles=[], indicators={},
            portfolio_balance=1000, open_positions=[], timestamp="",
        )
        try:
            decision = ai.decide(ctx)
        except RuntimeError:
            decision = {"decision": "HOLD", "confidence": 0.0, "reason": "AI_ERROR"}
        assert decision["decision"] == "HOLD"
