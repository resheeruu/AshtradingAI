"""Candle helpers and synthetic candle generation for testing."""
import math
import random
from typing import List, Dict
from datetime import datetime, timedelta, timezone


def generate_synthetic_candles(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    periods: int = 500,
    start_price: float = 50000.0,
    volatility: float = 0.02,
    seed: int = 42,
) -> List[Dict]:
    """Generate reproducible synthetic OHLCV data."""
    rng = random.Random(seed)
    candles: List[Dict] = []
    price = start_price
    base_time = datetime.now(timezone.utc) - timedelta(hours=periods)

    for i in range(periods):
        change = rng.gauss(0, volatility)
        close = price * (1 + change)
        high = close * (1 + abs(rng.gauss(0, volatility / 2)))
        low = close * (1 - abs(rng.gauss(0, volatility / 2)))
        open_ = price
        volume = rng.uniform(100, 10000)
        ts = base_time + timedelta(hours=i)
        candles.append({
            "timestamp": ts.isoformat(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        price = close
    return candles


def generate_candle_series(
    prices: List[float],
    timeframe: str = "1h",
    volatility: float = 0.005,
    seed: int = 42,
) -> List[Dict]:
    """Generate candles that follow a specific price path."""
    rng = random.Random(seed)
    periods = len(prices)
    base_time = datetime.now(timezone.utc) - timedelta(hours=periods)
    candles: List[Dict] = []

    for i in range(periods):
        close = prices[i]
        high = close * (1 + abs(rng.gauss(0, volatility)))
        low = close * (1 - abs(rng.gauss(0, volatility)))
        open_ = prices[i - 1] if i > 0 else close
        volume = rng.uniform(100, 10000)
        ts = base_time + timedelta(hours=i)
        candles.append({
            "timestamp": ts.isoformat(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    return candles
