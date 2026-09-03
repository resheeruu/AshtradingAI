"""Unified market data interface using requests + CCXT REST API."""
import logging
import json
import time
from typing import Optional, List, Dict
import requests

logger = logging.getLogger(__name__)

CCXT_BASE = "https://api.ccxt.com"


class MarketData:
    """Fetch OHLCV data via CCXT public API (no auth needed for candles)."""

    def __init__(self, exchange_id: str = "binance"):
        self.exchange_id = exchange_id
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "AshtradingAI/0.1"})

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
    ) -> List[Dict]:
        """Fetch OHLCV candles via CCXT REST endpoint."""
        url = f"{CCXT_BASE}/{self.exchange_id}/fetchOHLCV"
        params = {"symbol": symbol, "timeframe": timeframe, "limit": limit}
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            candles = []
            for row in data:
                candles.append({
                    "timestamp": _ms_to_iso(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                })
            return candles
        except Exception as e:
            logger.error("Failed to fetch candles for %s: %s", symbol, e)
            return []

    def get_last_price(self, symbol: str) -> float:
        url = f"{CCXT_BASE}/{self.exchange_id}/fetchTicker"
        try:
            resp = self._session.get(url, params={"symbol": symbol}, timeout=15)
            resp.raise_for_status()
            return float(resp.json().get("last", 0.0))
        except Exception:
            return 0.0


class OfflineMarketData:
    """Market data provider for backtesting (no network needed)."""

    def __init__(self, data: Dict[str, List[Dict]]):
        self._data = data

    def fetch_candles(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> List[Dict]:
        candles = self._data.get(symbol, [])
        return candles[-limit:]

    def get_last_price(self, symbol: str) -> float:
        candles = self._data.get(symbol, [])
        if candles:
            return candles[-1]["close"]
        return 0.0


def _ms_to_iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
