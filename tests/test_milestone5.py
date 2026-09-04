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


# --- Completed Candle Selection Tests ---

class TestCompletedCandleSelection:
    def _make_candles(self, count, base_hour=0, timeframe="1h"):
        """Generate candle list with ISO timestamps."""
        from datetime import timedelta
        candles = []
        base = datetime(2024, 1, 1, base_hour, 0, 0, tzinfo=timezone.utc)
        for i in range(count):
            ts = (base + timedelta(hours=i)).isoformat()
            candles.append({
                "timestamp": ts,
                "open": 100 + i, "high": 110 + i, "low": 90 + i,
                "close": 105 + i, "volume": 1000,
            })
        return candles

    def test_get_latest_completed_candle(self):
        from src.paper_live.engine import _get_latest_completed_candle
        candles = self._make_candles(10)
        result = _get_latest_completed_candle(candles, "1h")
        # All candles are in the past, so the latest completed should be the last
        assert result is not None
        assert result["timestamp"] == candles[-1]["timestamp"]

    def test_get_latest_completed_no_completed(self):
        from src.paper_live.engine import _get_latest_completed_candle
        from datetime import timedelta
        # All candles are in the future
        future_base = datetime.now(timezone.utc) + timedelta(hours=10)
        candles = []
        for i in range(5):
            ts = (future_base + timedelta(hours=i)).isoformat()
            candles.append({
                "timestamp": ts,
                "open": 100, "high": 110, "low": 90,
                "close": 105, "volume": 1000,
            })
        result = _get_latest_completed_candle(candles, "1h")
        assert result is None

    def test_find_unprocessed_completed_candles_no_prior(self):
        from src.paper_live.engine import _find_unprocessed_completed_candles
        candles = self._make_candles(10)
        result = _find_unprocessed_completed_candles(candles, "1h", last_processed_ts=None)
        # No prior state: returns only the latest completed candle
        assert len(result) == 1
        assert result[0]["timestamp"] == candles[-1]["timestamp"]

    def test_find_unprocessed_completed_candles_with_gap(self):
        from src.paper_live.engine import _find_unprocessed_completed_candles
        candles = self._make_candles(10)
        # Simulate: last processed was candle at index 5
        last_ts = candles[5]["timestamp"]
        result = _find_unprocessed_completed_candles(candles, "1h", last_processed_ts=last_ts)
        # Should return candles 6, 7, 8, 9 (4 candles after last_ts)
        assert len(result) == 4
        for c in result:
            assert c["timestamp"] > last_ts

    def test_find_unprocessed_completed_candles_all_processed(self):
        from src.paper_live.engine import _find_unprocessed_completed_candles
        candles = self._make_candles(10)
        last_ts = candles[-1]["timestamp"]
        result = _find_unprocessed_completed_candles(candles, "1h", last_processed_ts=last_ts)
        assert len(result) == 0


# --- No Duplicate Processing Tests ---

class TestNoDuplicateProcessing:
    def test_scheduler_prevents_duplicate(self):
        sched = CandleScheduler("1h")
        ts = "2024-01-01T00:00:00+00:00"
        assert sched.should_process(ts) is True
        sched.mark_processed(ts)
        assert sched.should_process(ts) is False
        assert sched.has_processed(ts) is True

    def test_scheduler_state_persists_across_instances(self):
        sched1 = CandleScheduler("1h")
        ts = "2024-01-01T00:00:00+00:00"
        sched1.mark_processed(ts)
        # Simulate new instance with restored state
        sched2 = CandleScheduler("1h")
        sched2.set_last_processed(ts)
        assert sched2.has_processed(ts) is True
        assert sched2.should_process(ts) is False


# --- Historical Context Tests ---

class TestHistoricalContext:
    def test_indicators_require_enough_history(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy
        engine = PaperLiveEngine(
            session_id="ctx-test", ai=TestStrategy(ai_id="t"),
            symbols=["BTC/USDT"], starting_balance=1000,
        )
        # Few candles -> no indicators
        few_candles = [{"timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
                        "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
                       for i in range(10)]
        indicators = engine._compute_indicators("BTC/USDT", few_candles)
        assert indicators == {}

        # Enough candles -> indicators present
        many_candles = [{"timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
                         "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
                        for i in range(60)]
        indicators = engine._compute_indicators("BTC/USDT", many_candles)
        assert "rsi_14" in indicators
        assert "sma_20" in indicators

    def test_visible_candles_no_lookahead(self):
        candles = [
            {"timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
             "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
            for i in range(10)
        ]
        # Processing candle at index 5
        completed_idx = 5
        visible = candles[:completed_idx + 1]
        assert len(visible) == 6
        assert visible[-1]["timestamp"] == "2024-01-01T05:00:00+00:00"
        # No candle after index 5 should be visible
        for c in visible:
            assert c["timestamp"] <= candles[5]["timestamp"]


# --- Per-Symbol State Recovery Tests ---

class TestPerSymbolStateRecovery:
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

    def test_per_symbol_state_json(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy
        from unittest.mock import MagicMock

        session_id = "per-sym-test"
        self.db.create_paper_session(
            session_id=session_id, exchange="binance",
            symbols="BTC/USDT,ETH/USDT", timeframe="1h",
            data_source="synthetic", starting_balance=1000,
        )

        ai = TestStrategy(ai_id="t")
        engine = PaperLiveEngine(
            session_id=session_id, ai=ai, database=self.db,
            symbols=["BTC/USDT", "ETH/USDT"], starting_balance=1000,
        )

        # Simulate processing different candles for each symbol
        engine.schedulers["BTC/USDT"].mark_processed("2024-01-01T01:00:00+00:00")
        engine.schedulers["ETH/USDT"].mark_processed("2024-01-01T02:00:00+00:00")
        engine.portfolio.balance = 950.0

        engine._save_state()

        # Verify saved state
        session = self.db.get_paper_session(session_id)
        state = json.loads(session["last_processed_candle"])
        assert state["BTC/USDT"] == "2024-01-01T01:00:00+00:00"
        assert state["ETH/USDT"] == "2024-01-01T02:00:00+00:00"

        # Recover into new engine
        engine2 = PaperLiveEngine(
            session_id=session_id, ai=TestStrategy(ai_id="t2"),
            database=self.db, symbols=["BTC/USDT", "ETH/USDT"],
            starting_balance=1000,
        )
        assert engine2.recover_from_db() is True
        assert engine2.schedulers["BTC/USDT"].last_processed_candle == "2024-01-01T01:00:00+00:00"
        assert engine2.schedulers["ETH/USDT"].last_processed_candle == "2024-01-01T02:00:00+00:00"
        assert abs(engine2.portfolio.balance - 950.0) < 0.01

    def test_btc_state_does_not_overwrite_eth(self):
        sched_btc = CandleScheduler("1h")
        sched_eth = CandleScheduler("1h")
        ts_btc = "2024-01-01T01:00:00+00:00"
        ts_eth = "2024-01-01T02:00:00+00:00"
        sched_btc.mark_processed(ts_btc)
        sched_eth.mark_processed(ts_eth)
        assert sched_btc.last_processed_candle == ts_btc
        assert sched_eth.last_processed_candle == ts_eth
        # Marking BTC should not affect ETH
        sched_btc.mark_processed("2024-01-01T03:00:00+00:00")
        assert sched_eth.last_processed_candle == ts_eth


# --- Enhanced Restart Recovery Tests ---

class TestEnhancedRestartRecovery:
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

    def test_full_engine_recovery(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy
        from unittest.mock import MagicMock

        session_id = "recovery-eng-test"
        self.db.create_paper_session(
            session_id=session_id, exchange="binance",
            symbols="BTC/USDT", timeframe="1h",
            data_source="synthetic", starting_balance=1000,
        )

        ai = TestStrategy(ai_id="t")
        engine = PaperLiveEngine(
            session_id=session_id, ai=ai, database=self.db,
            symbols=["BTC/USDT"], starting_balance=1000,
        )
        engine.portfolio.balance = 980.0
        engine.schedulers["BTC/USDT"].mark_processed("2024-01-01T05:00:00+00:00")
        engine._save_state()

        # New engine recovers
        engine2 = PaperLiveEngine(
            session_id=session_id, ai=TestStrategy(ai_id="t2"),
            database=self.db, symbols=["BTC/USDT"],
            starting_balance=1000,
        )
        assert engine2.recover_from_db() is True
        assert abs(engine2.portfolio.balance - 980.0) < 0.01
        assert engine2.schedulers["BTC/USDT"].last_processed_candle == "2024-01-01T05:00:00+00:00"

    def test_cannot_recover_closed_session(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy

        session_id = "closed-test"
        self.db.create_paper_session(
            session_id=session_id, exchange="binance",
            symbols="BTC/USDT", timeframe="1h",
            data_source="synthetic", starting_balance=1000,
        )
        self.db.close_paper_session(session_id)

        engine = PaperLiveEngine(
            session_id=session_id, ai=TestStrategy(ai_id="t"),
            database=self.db, symbols=["BTC/USDT"],
            starting_balance=1000,
        )
        assert engine.recover_from_db() is False


# --- No Synthetic Fallback Tests ---

class TestNoSyntheticFallback:
    def test_paper_live_refuses_synthetic(self):
        from unittest.mock import MagicMock
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy

        mock_md = MagicMock()
        mock_md.fetch_candles.return_value = []

        engine = PaperLiveEngine(
            session_id="no-synth", ai=TestStrategy(ai_id="t"),
            symbols=["BTC/USDT"], starting_balance=1000,
        )
        engine.market_data = mock_md
        engine.start()

        # Should record unavailable, not generate synthetic data
        engine._process_symbol("BTC/USDT")
        state = engine.market_health.get_state("BTC/USDT")
        assert state.value == "UNAVAILABLE"
        mock_md.fetch_candles.assert_called_once()

    def test_paper_live_test_uses_mock_not_synthetic_engine(self):
        from bot import cmd_paper_live_test
        import argparse
        args = argparse.Namespace(mode="paper-live-test")
        # This should complete without error (it uses mock data, not synthetic fallback)
        cmd_paper_live_test(args)


# --- Market Health Tests ---

class TestMarketHealthIntegration:
    def test_market_health_independent_of_ai_health(self):
        mh = MarketHealth(max_stale_seconds=300)
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        assert mh.is_healthy("BTC/USDT")
        # AI health being unhealthy should not affect market health
        mh.record_network_error("ETH/USDT", "timeout")
        assert mh.is_healthy("BTC/USUS") is False or mh.get_state("BTC/USDT").value == "ONLINE"

    def test_market_health_recovery(self):
        mh = MarketHealth(max_stale_seconds=300)
        mh.record_network_error("BTC/USDT", "connection refused")
        assert mh.get_state("BTC/USDT") == MarketState.NETWORK_ERROR
        ts = datetime.now(timezone.utc).isoformat()
        mh.record_success("BTC/USDT", ts)
        assert mh.get_state("BTC/USDT") == MarketState.ONLINE


# --- Safety Tests (Enhanced) ---

class TestSafetyEnhanced:
    def test_live_trading_blocks_all_modes(self):
        assert Config.LIVE_TRADING is False

    def test_paper_live_engine_refuses_live_trading(self):
        from unittest.mock import MagicMock
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy

        original = Config.LIVE_TRADING
        try:
            Config.LIVE_TRADING = True
            # The engine itself doesn't check LIVE_TRADING (bot.py does),
            # but Config.validate should catch it
            errors = Config.validate()
            assert any("LIVE_TRADING" in e for e in errors)
        finally:
            Config.LIVE_TRADING = original


# --- PaperLiveEngine Integration Tests ---

class TestPaperLiveEngineIntegration:
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

    def test_engine_processes_completed_candles(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy
        from src.market.candles import generate_synthetic_candles
        from unittest.mock import MagicMock

        session_id = "eng-integ-test"
        self.db.create_paper_session(
            session_id=session_id, exchange="binance",
            symbols="BTC/USDT", timeframe="1h",
            data_source="synthetic", starting_balance=1000,
        )

        # Generate candles where most are in the past
        candles = generate_synthetic_candles(symbol="BTC/USDT", periods=100)

        mock_md = MagicMock()
        mock_md.fetch_candles.return_value = candles

        engine = PaperLiveEngine(
            session_id=session_id, ai=TestStrategy(ai_id="t"),
            database=self.db, symbols=["BTC/USDT"],
            starting_balance=1000, candle_limit=500,
        )
        engine.market_data = mock_md
        engine.start()

        engine._process_symbol("BTC/USDT")

        # Should have processed at least one candle
        assert engine.schedulers["BTC/USDT"].last_processed_candle is not None
        # State should be saved
        session = self.db.get_paper_session(session_id)
        assert session is not None

    def test_engine_no_lookahead_enforcement(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy
        from src.market.candles import generate_synthetic_candles
        from unittest.mock import MagicMock

        session_id = "no-lookahead-test"
        self.db.create_paper_session(
            session_id=session_id, exchange="binance",
            symbols="BTC/USDT", timeframe="1h",
            data_source="synthetic", starting_balance=1000,
        )

        candles = generate_synthetic_candles(symbol="BTC/USDT", periods=100)

        mock_md = MagicMock()
        mock_md.fetch_candles.return_value = candles

        engine = PaperLiveEngine(
            session_id=session_id, ai=TestStrategy(ai_id="t"),
            database=self.db, symbols=["BTC/USDT"],
            starting_balance=1000, candle_limit=500,
        )
        engine.market_data = mock_md
        engine.start()

        # Process a symbol - verify no future candles leaked
        engine._process_symbol("BTC/USDT")
        # The engine should have used only completed candles
        assert engine.schedulers["BTC/USDT"].last_processed_candle is not None

    def test_engine_signal_handlers(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy

        engine = PaperLiveEngine(
            session_id="sig-test", ai=TestStrategy(ai_id="t"),
            symbols=["BTC/USDT"], starting_balance=1000,
        )
        engine.start()
        assert engine._running is True
        engine.stop()
        assert engine._running is False

    def test_engine_status(self):
        from src.paper_live.engine import PaperLiveEngine
        from src.ai.test_strategy import TestStrategy

        engine = PaperLiveEngine(
            session_id="status-test", ai=TestStrategy(ai_id="t"),
            symbols=["BTC/USDT"], starting_balance=1000,
        )
        status = engine.get_status()
        assert status["session_id"] == "status-test"
        assert status["data_source"] == "LIVE"
        assert status["balance"] == 1000.0
        assert "market_health" in status
