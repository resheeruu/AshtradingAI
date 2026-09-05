"""Coins.ph market data adapter tests — parsing, symbol handling, safety, candle logic."""
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, Mock

import pytest

from src.market.coinsph import (
    CoinsPhMarketData,
    normalize_symbol,
    denormalize_symbol,
    parse_kline_to_candle,
    parse_ticker_response,
    SUPPORTED_INTERVALS,
    COINSPH_BASE_URL,
)


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------

class TestSymbolNormalization:
    def test_slash_removal(self):
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_already_normalized(self):
        assert normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_lowercase(self):
        assert normalize_symbol("btc/usdt") == "BTCUSDT"

    def test_php_pair(self):
        assert normalize_symbol("BTC/PHP") == "BTCPHP"

    def test_dash_separator(self):
        assert normalize_symbol("BTC-USDT") == "BTCUSDT"

    def test_mixed_case(self):
        assert normalize_symbol("BtC/UsDt") == "BTCUSDT"

    def test_denormalize_btcusdt(self):
        assert denormalize_symbol("BTCUSDT") == "BTC/USDT"

    def test_denormalize_btcpHP(self):
        assert denormalize_symbol("BTCPHP") == "BTC/PHP"

    def test_denormalize_ethusdt(self):
        assert denormalize_symbol("ETHUSDT") == "ETH/USDT"

    def test_denormalize_unknown_quote(self):
        assert denormalize_symbol("XYZABC") == "XYZABC"

    def test_roundtrip(self):
        original = "BTC/USDT"
        assert denormalize_symbol(normalize_symbol(original)) == original


# ---------------------------------------------------------------------------
# Kline parsing
# ---------------------------------------------------------------------------

class TestKlineParsing:
    def _make_kline(self, open_time_ms=1499040000000, open_p="0.01634790",
                    high_p="0.80000000", low_p="0.01575800",
                    close_p="0.01577100", volume="148976.11427815",
                    close_time_ms=1499644799999):
        return [
            open_time_ms, open_p, high_p, low_p, close_p, volume,
            close_time_ms, "2434.19055334", 308,
            "1756.87402397", "28.46694368",
        ]

    def test_valid_kline(self):
        kline = self._make_kline()
        candle = parse_kline_to_candle(kline)
        assert candle is not None
        assert candle["open"] == pytest.approx(0.01634790, abs=1e-8)
        assert candle["high"] == pytest.approx(0.8, abs=1e-8)
        assert candle["low"] == pytest.approx(0.01575800, abs=1e-8)
        assert candle["close"] == pytest.approx(0.01577100, abs=1e-8)
        assert candle["volume"] == pytest.approx(148976.11427815, abs=1e-6)
        assert "timestamp" in candle
        assert candle["timestamp"].endswith("+00:00")

    def test_timestamp_is_iso(self):
        kline = self._make_kline(open_time_ms=1609459200000)
        candle = parse_kline_to_candle(kline)
        assert candle is not None
        dt = datetime.fromisoformat(candle["timestamp"])
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1

    def test_malformed_kline_not_enough_elements(self):
        assert parse_kline_to_candle([1499040000000, "0.01", "0.02"]) is None

    def test_malformed_kline_non_numeric_prices(self):
        kline = [1499040000000, "abc", "0.8", "0.01", "0.02", "100", 1499644799999]
        assert parse_kline_to_candle(kline) is None

    def test_malformed_kline_negative_timestamp(self):
        kline = self._make_kline(open_time_ms=-1)
        assert parse_kline_to_candle(kline) is None

    def test_malformed_kline_zero_timestamp(self):
        kline = self._make_kline(open_time_ms=0)
        assert parse_kline_to_candle(kline) is None

    def test_low_greater_than_high(self):
        kline = self._make_kline(low_p="0.80", high_p="0.01")
        assert parse_kline_to_candle(kline) is None

    def test_open_outside_range(self):
        kline = self._make_kline(open_p="0.90")
        assert parse_kline_to_candle(kline) is None

    def test_close_outside_range(self):
        kline = self._make_kline(close_p="0.90")
        assert parse_kline_to_candle(kline) is None

    def test_not_a_list(self):
        assert parse_kline_to_candle("not a list") is None

    def test_empty_list(self):
        assert parse_kline_to_candle([]) is None

    def test_none_input(self):
        assert parse_kline_to_candle(None) is None


# ---------------------------------------------------------------------------
# Ticker parsing
# ---------------------------------------------------------------------------

class TestTickerParsing:
    def test_valid_ticker(self):
        data = {
            "lastPrice": "50000.50",
            "bidPrice": "49999.00",
            "askPrice": "50001.00",
            "volume": "1234.56",
            "quoteVolume": "61728000.00",
            "priceChangePercent": "2.5",
            "highPrice": "51000.00",
            "lowPrice": "48000.00",
        }
        result = parse_ticker_response(data)
        assert result is not None
        assert result["last"] == pytest.approx(50000.50)
        assert result["bid"] == pytest.approx(49999.00)
        assert result["ask"] == pytest.approx(50001.00)
        assert result["volume_24h"] == pytest.approx(1234.56)
        assert result["change_24h"] == pytest.approx(2.5)

    def test_missing_fields(self):
        result = parse_ticker_response({})
        assert result is None

    def test_zero_last_price(self):
        data = {"lastPrice": "0", "bidPrice": "0", "askPrice": "0"}
        result = parse_ticker_response(data)
        assert result is None

    def test_not_a_dict(self):
        assert parse_ticker_response("not a dict") is None

    def test_none_input(self):
        assert parse_ticker_response(None) is None

    def test_non_numeric_values(self):
        data = {"lastPrice": "abc"}
        assert parse_ticker_response(data) is None


# ---------------------------------------------------------------------------
# CoinsPhMarketData class
# ---------------------------------------------------------------------------

class TestCoinsPhMarketData:
    def test_init_default(self):
        md = CoinsPhMarketData()
        assert md.base_url == COINSPH_BASE_URL
        assert md.max_retries == 3
        assert md.timeout == 30

    def test_init_custom(self):
        md = CoinsPhMarketData(base_url="https://custom.api.test", max_retries=5, timeout=10)
        assert md.base_url == "https://custom.api.test"
        assert md.max_retries == 5
        assert md.timeout == 10

    def test_init_strips_trailing_slash(self):
        md = CoinsPhMarketData(base_url="https://api.test/")
        assert md.base_url == "https://api.test"

    def test_supported_intervals(self):
        assert "1h" in SUPPORTED_INTERVALS
        assert "1m" in SUPPORTED_INTERVALS
        assert "1d" in SUPPORTED_INTERVALS
        assert "1w" in SUPPORTED_INTERVALS

    def test_unsupported_interval_returns_empty(self):
        md = CoinsPhMarketData()
        candles = md.fetch_candles("BTCUSDT", "7h")
        assert candles == []


# ---------------------------------------------------------------------------
# Market data fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestMarketDataFetch:
    def _mock_response(self, json_data, status_code=200, headers=None):
        mock_resp = MagicMock()
        mock_resp.json.return_value = json_data
        mock_resp.status_code = status_code
        mock_resp.headers = headers or {}
        mock_resp.raise_for_status = Mock()
        if status_code >= 400:
            from requests.exceptions import HTTPError
            mock_resp.raise_for_status.side_effect = HTTPError(response=mock_resp)
        return mock_resp

    def test_fetch_candles_success(self):
        klines = [
            [1609459200000, "29000.00", "29500.00", "28500.00", "29200.00", "100.5",
             1609462799999, "2900000", 500, "50.25", "1450000"],
            [1609462800000, "29200.00", "29800.00", "29000.00", "29600.00", "120.3",
             1609466399999, "3500000", 600, "60.15", "1750000"],
        ]
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response(klines)

        candles = md.fetch_candles("BTC/USDT", "1h", limit=2)
        assert len(candles) == 2
        assert candles[0]["open"] == pytest.approx(29000.0)
        assert candles[1]["close"] == pytest.approx(29600.0)

    def test_fetch_candles_pagination(self):
        """When first batch returns full batch_size, pagination continues."""
        # Create compact kline data (just enough for validation)
        def _make_kline(ms):
            return [ms, "29000", "29500", "28500", "29200", "100",
                    ms + 3599999, "2900000", 500, "50", "1450000"]

        # First batch returns 1000 candles (full exchange_max)
        batch1 = [_make_kline(1609459200000 + i * 3600000) for i in range(1000)]
        # Second batch returns 1 candle (end of data)
        batch2 = [_make_kline(1609459200000 + 1000 * 3600000)]

        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = [
            self._mock_response(batch1),
            self._mock_response(batch2),
        ]

        candles = md.fetch_candles("BTCUSDT", "1h", limit=1001)
        assert len(candles) == 1001
        assert md._session.get.call_count == 2

    def test_fetch_candles_no_pagination_when_partial_batch(self):
        """When first batch returns fewer than batch_size, no second request."""
        kline = [1609459200000, "29000", "29500", "28500", "29200", "100",
                 1609462799999, "2900000", 500, "50", "1450000"]
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response([kline])

        candles = md.fetch_candles("BTCUSDT", "1h", limit=500)
        assert len(candles) == 1
        # Only one request because batch < limit
        assert md._session.get.call_count == 1

    def test_fetch_candles_empty_response(self):
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response([])

        candles = md.fetch_candles("BTCUSDT", "1h", limit=500)
        assert candles == []

    def test_fetch_candles_timeout_retries(self):
        md = CoinsPhMarketData(max_retries=2, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = [
            self._mock_response([], 200),  # First call returns empty (after timeout)
        ]
        # Simulate timeout on first attempt, success on second
        from requests.exceptions import Timeout
        md._session.get.side_effect = [Timeout("timeout"), self._mock_response([])]

        candles = md.fetch_candles("BTCUSDT", "1h", limit=100)
        assert candles == []
        assert md._session.get.call_count == 2

    def test_fetch_candles_connection_error_retries(self):
        from requests.exceptions import ConnectionError
        md = CoinsPhMarketData(max_retries=2, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = [ConnectionError("refused"), self._mock_response([])]

        candles = md.fetch_candles("BTCUSDT", "1h", limit=100)
        assert candles == []
        assert md._session.get.call_count == 2

    def test_fetch_candles_rate_limit_retry(self):
        rate_limit_resp = self._mock_response([], 429, headers={"Retry-After": "1"})
        success_resp = self._mock_response([
            [1609459200000, "29000", "29500", "28500", "29200", "100",
             1609462799999, "2900000", 500, "50", "1450000"],
        ])
        md = CoinsPhMarketData(max_retries=3, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = [rate_limit_resp, success_resp]

        candles = md.fetch_candles("BTCUSDT", "1h", limit=1)
        assert len(candles) == 1

    def test_fetch_candles_server_error_retries(self):
        error_resp = self._mock_response([], 500)
        success_resp = self._mock_response([
            [1609459200000, "29000", "29500", "28500", "29200", "100",
             1609462799999, "2900000", 500, "50", "1450000"],
        ])
        md = CoinsPhMarketData(max_retries=3, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = [error_resp, success_resp]

        candles = md.fetch_candles("BTCUSDT", "1h", limit=1)
        assert len(candles) == 1

    def test_fetch_candles_client_error_no_retry(self):
        error_resp = self._mock_response([], 400)
        md = CoinsPhMarketData(max_retries=3, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = error_resp

        candles = md.fetch_candles("BTCUSDT", "1h", limit=1)
        assert candles == []
        assert md._session.get.call_count == 1

    def test_fetch_candles_unexpected_response_type(self):
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response({"error": "bad"})

        candles = md.fetch_candles("BTCUSDT", "1h", limit=100)
        assert candles == []

    def test_get_last_price_success(self):
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response({"price": "50000.50"})

        price = md.get_last_price("BTC/USDT")
        assert price == pytest.approx(50000.50)

    def test_get_last_price_failure(self):
        from requests.exceptions import ConnectionError
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = ConnectionError("refused")

        price = md.get_last_price("BTCUSDT")
        assert price == 0.0

    def test_get_ticker_success(self):
        ticker_data = {
            "lastPrice": "50000.50",
            "bidPrice": "49999.00",
            "askPrice": "50001.00",
            "volume": "1234.56",
            "quoteVolume": "61728000",
            "priceChangePercent": "2.5",
            "highPrice": "51000",
            "lowPrice": "48000",
        }
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.return_value = self._mock_response(ticker_data)

        ticker = md.get_ticker("BTC/USDT")
        assert ticker is not None
        assert ticker["last"] == pytest.approx(50000.50)

    def test_get_ticker_failure(self):
        md = CoinsPhMarketData(max_retries=1, base_delay=0.01)
        md._session = MagicMock()
        md._session.get.side_effect = Exception("network error")

        ticker = md.get_ticker("BTCUSDT")
        assert ticker is None


# ---------------------------------------------------------------------------
# Paper safety — verify no order endpoints are called
# ---------------------------------------------------------------------------

class TestPaperSafety:
    def test_coinsph_market_data_has_no_order_methods(self):
        """CoinsPhMarketData should NOT have order placement methods."""
        md = CoinsPhMarketData()
        assert not hasattr(md, "create_order")
        assert not hasattr(md, "place_order")
        assert not hasattr(md, "cancel_order")
        assert not hasattr(md, "new_order")
        assert not hasattr(md, "withdraw")

    def test_live_trading_false_by_default(self):
        """LIVE_TRADING must be false for paper-live mode."""
        from src.config import Config
        assert Config.LIVE_TRADING is False

    def test_config_validates_coinsph_safety(self):
        """Config validation should reject COINSPH_ENABLED + LIVE_TRADING."""
        from src.config import Config
        errors = Config.validate()
        # LIVE_TRADING=false is set, so no safety error
        assert not any("COINSPH_ENABLED" in e for e in errors)

    def test_paper_live_engine_uses_paper_broker(self):
        """PaperLiveEngine must always use PaperBroker, never a CoinsBroker."""
        from src.paper_live.engine import PaperLiveEngine
        from src.trading.paper.broker import PaperBroker
        from src.ai.test_strategy import TestStrategy

        ai = TestStrategy(ai_id="test")
        engine = PaperLiveEngine(
            session_id="test-session",
            ai=ai,
            exchange="coinsph",
        )
        assert isinstance(engine.broker, PaperBroker)
        assert not hasattr(engine.broker, "place_real_order")


# ---------------------------------------------------------------------------
# Candle safety — completed vs incomplete
# ---------------------------------------------------------------------------

class TestCandleSafety:
    def test_completed_candle_is_processed(self):
        """A candle whose timestamp + timeframe < now should be processed."""
        from src.market.scheduler import is_candle_completed
        # 2 hours ago, 1h candle = completed
        ts = datetime.now(timezone.utc).timestamp() - 7200
        candle_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        assert is_candle_completed(candle_ts, "1h") is True

    def test_incomplete_candle_is_ignored(self):
        """A candle from 10 seconds ago, 1h candle = not completed."""
        from src.market.scheduler import is_candle_completed
        ts = datetime.now(timezone.utc).timestamp() - 10
        candle_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        assert is_candle_completed(candle_ts, "1h") is False

    def test_find_unprocessed_completed_candles(self):
        """Only completed candles after last_processed_ts should be returned."""
        from src.paper_live.engine import _find_unprocessed_completed_candles

        now = datetime.now(timezone.utc)
        # 3 hours ago (completed)
        ts1 = datetime.fromtimestamp(now.timestamp() - 10800, tz=timezone.utc).isoformat()
        # 2 hours ago (completed)
        ts2 = datetime.fromtimestamp(now.timestamp() - 7200, tz=timezone.utc).isoformat()
        # 5 minutes ago (not completed)
        ts3 = datetime.fromtimestamp(now.timestamp() - 300, tz=timezone.utc).isoformat()

        candles = [
            {"timestamp": ts1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"timestamp": ts2, "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 200},
            {"timestamp": ts3, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 300},
        ]

        # Last processed was ts1, so only ts2 should be returned (ts3 not completed)
        result = _find_unprocessed_completed_candles(candles, "1h", ts1)
        assert len(result) == 1
        assert result[0]["timestamp"] == ts2

    def test_no_duplicate_processing(self):
        """Candles should not be processed twice."""
        from src.market.scheduler import CandleScheduler

        now = datetime.now(timezone.utc)
        ts = datetime.fromtimestamp(now.timestamp() - 7200, tz=timezone.utc).isoformat()

        scheduler = CandleScheduler("1h")
        assert scheduler.should_process(ts) is True
        scheduler.mark_processed(ts)
        assert scheduler.should_process(ts) is False

    def test_get_latest_completed_candle(self):
        """Should return the newest completed candle."""
        from src.paper_live.engine import _get_latest_completed_candle

        now = datetime.now(timezone.utc)
        ts1 = datetime.fromtimestamp(now.timestamp() - 10800, tz=timezone.utc).isoformat()
        ts2 = datetime.fromtimestamp(now.timestamp() - 7200, tz=timezone.utc).isoformat()
        ts3 = datetime.fromtimestamp(now.timestamp() - 300, tz=timezone.utc).isoformat()

        candles = [
            {"timestamp": ts1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"timestamp": ts2, "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 200},
            {"timestamp": ts3, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 300},
        ]

        latest = _get_latest_completed_candle(candles, "1h")
        assert latest is not None
        assert latest["timestamp"] == ts2  # ts3 is not completed


# ---------------------------------------------------------------------------
# Regression — existing tests still pass
# ---------------------------------------------------------------------------

class TestRegression:
    def test_market_data_imports(self):
        """Existing MarketData import still works."""
        from src.market.data import MarketData
        md = MarketData(exchange_id="binance")
        assert md.exchange_id == "binance"

    def test_offline_market_data_imports(self):
        """OfflineMarketData import still works."""
        from src.market.data import OfflineMarketData
        data = {"BTC/USDT": [{"timestamp": "2024-01-01T00:00:00+00:00",
                               "open": 100, "high": 110, "low": 90,
                               "close": 105, "volume": 1000}]}
        md = OfflineMarketData(data)
        assert md.get_last_price("BTC/USDT") == 105

    def test_paper_broker_imports(self):
        """PaperBroker import still works."""
        from src.trading.paper.broker import PaperBroker
        broker = PaperBroker()
        assert broker.fee == 0.001

    def test_config_imports(self):
        """Config import still works."""
        from src.config import Config
        assert hasattr(Config, "EXCHANGE")
        assert hasattr(Config, "COINSPH_ENABLED")

    def test_paper_live_engine_imports(self):
        """PaperLiveEngine import still works."""
        from src.paper_live.engine import PaperLiveEngine
        assert PaperLiveEngine is not None
