"""Tests for market data validation."""
import pytest
from src.market.validation import validate_candle, validate_candles


class TestValidateCandle:
    def test_valid_candle(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        assert validate_candle(candle) is None

    def test_missing_key(self):
        candle = {"timestamp": "2024-01-01T00:00:00+00:00", "open": 100.0}
        err = validate_candle(candle)
        assert err is not None
        assert "missing key" in err

    def test_non_numeric_field(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": "abc", "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None
        assert "not numeric" in err

    def test_nan_field(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": float("nan"), "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None
        assert "NaN" in err

    def test_low_greater_than_high(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0, "high": 90.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None
        assert "low" in err and "high" in err

    def test_open_outside_range(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 120.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None
        assert "open" in err

    def test_close_outside_range(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 90.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None
        assert "close" in err

    def test_negative_price(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": -100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None

    def test_zero_volume_ok(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 0.0,
        }
        assert validate_candle(candle) is None

    def test_negative_volume(self):
        candle = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": -100.0,
        }
        err = validate_candle(candle)
        assert err is not None

    def test_empty_timestamp(self):
        candle = {
            "timestamp": "",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        }
        err = validate_candle(candle)
        assert err is not None


class TestValidateCandles:
    def test_empty_list(self):
        valid, errors = validate_candles([])
        assert valid == []
        assert len(errors) > 0

    def test_all_valid(self):
        candles = [
            {"timestamp": f"2024-01-01T{i:02d}:00:00+00:00", "open": 100.0, "high": 110.0,
             "low": 95.0, "close": 105.0, "volume": 1000.0}
            for i in range(5)
        ]
        valid, errors = validate_candles(candles)
        assert len(valid) == 5
        assert len(errors) == 0

    def test_removes_invalid(self):
        good = {"timestamp": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 110.0,
                "low": 95.0, "close": 105.0, "volume": 1000.0}
        bad = {"timestamp": "2024-01-01T01:00:00+00:00", "open": "bad", "high": 110.0,
               "low": 95.0, "close": 105.0, "volume": 1000.0}
        valid, errors = validate_candles([good, bad])
        assert len(valid) == 1
        assert len(errors) == 1

    def test_deduplicates_timestamps(self):
        candle = {"timestamp": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 110.0,
                  "low": 95.0, "close": 105.0, "volume": 1000.0}
        valid, errors = validate_candles([candle, candle])
        assert len(valid) == 1
        assert any("duplicate" in e for e in errors)

    def test_rejects_out_of_order(self):
        c1 = {"timestamp": "2024-01-01T01:00:00+00:00", "open": 100.0, "high": 110.0,
              "low": 95.0, "close": 105.0, "volume": 1000.0}
        c2 = {"timestamp": "2024-01-01T00:00:00+00:00", "open": 100.0, "high": 110.0,
              "low": 95.0, "close": 105.0, "volume": 1000.0}
        valid, errors = validate_candles([c1, c2])
        assert len(valid) == 1
        assert any("out of order" in e for e in errors)
