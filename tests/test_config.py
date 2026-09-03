"""Tests for configuration."""
import pytest
from src.config import Config


def test_config_loads():
    assert Config.EXCHANGE == "binance"
    assert Config.TIMEFRAME == "1h"
    assert Config.STARTING_BALANCE > 0


def test_live_trading_disabled():
    assert Config.LIVE_TRADING is False


def test_config_validation():
    errors = Config.validate()
    # Should have no errors with defaults
    live_errors = [e for e in errors if "LIVE_TRADING" in e]
    assert len(live_errors) == 0


def test_config_as_dict():
    d = Config.as_dict()
    assert "SYMBOLS" in d
    assert "TRADING_FEE" in d


def test_symbols_parsed():
    assert isinstance(Config.SYMBOLS, list)
    assert len(Config.SYMBOLS) >= 1
