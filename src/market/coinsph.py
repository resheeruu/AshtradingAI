"""Coins.ph market data adapter — real market data for paper-live trading.

This module provides a market-data-only adapter compatible with the existing
MarketData contract. It uses the official Coins.ph REST API for public market
data (OHLCV/klines, ticker). No order placement or authenticated endpoints
are used in this milestone.

Coins.ph API docs: https://docs.coins.ph/rest-api/
Base URL: https://api.pro.coins.ph
"""
import logging
import time
from typing import Optional, List, Dict

import requests

from src.market.validation import validate_candles

logger = logging.getLogger(__name__)

COINSPH_BASE_URL = "https://api.pro.coins.ph"
COINSPH_KLINE_ENDPOINT = "/openapi/quote/v1/klines"
COINSPH_TICKER_ENDPOINT = "/openapi/quote/v1/ticker/24hr"
COINSPH_PRICE_ENDPOINT = "/openapi/quote/v1/ticker/price"

# Coins.ph kline array index constants
KLINE_OPEN_TIME = 0
KLINE_OPEN = 1
KLINE_HIGH = 2
KLINE_LOW = 3
KLINE_CLOSE = 4
KLINE_VOLUME = 5
KLINE_CLOSE_TIME = 6

# Supported Coins.ph intervals (matches API documentation)
SUPPORTED_INTERVALS = frozenset({
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
})


def normalize_symbol(symbol: str) -> str:
    """Normalize a symbol to Coins.ph format (no separators).

    Examples:
        BTC/USDT -> BTCUSDT
        BTCUSDT  -> BTCUSDT
        BTC/PHP  -> BTCPHP
    """
    return symbol.replace("/", "").replace("-", "").upper()


def denormalize_symbol(coinsph_symbol: str) -> str:
    """Convert a Coins.ph symbol back to slash-separated format.

    Examples:
        BTCUSDT -> BTC/USDT
        BTCPHP  -> BTC/PHP
    """
    # Common quote currencies on Coins.ph
    quote_currencies = ("USDT", "USDC", "PHP", "BTC", "ETH", "BNB")
    upper = coinsph_symbol.upper()
    for quote in quote_currencies:
        if upper.endswith(quote) and len(upper) > len(quote):
            base = upper[: -len(quote)]
            return f"{base}/{quote}"
    return upper


def parse_kline_to_candle(kline_data: list) -> Optional[Dict]:
    """Parse a Coins.ph kline array into the standard candle dict.

    Coins.ph kline format (11 elements):
        [0] Open Time (ms)
        [1] Open (string)
        [2] High (string)
        [3] Low (string)
        [4] Close (string)
        [5] Volume (string)
        [6] Close Time (ms)
        [7] Quote Asset Volume (string)
        [8] Number of Trades (int)
        [9] Taker Buy Base Volume (string)
        [10] Taker Buy Quote Volume (string)

    Returns the standard candle dict or None if parsing fails.
    """
    if not isinstance(kline_data, list) or len(kline_data) < 6:
        return None

    try:
        open_time_ms = int(kline_data[KLINE_OPEN_TIME])
        open_price = float(kline_data[KLINE_OPEN])
        high_price = float(kline_data[KLINE_HIGH])
        low_price = float(kline_data[KLINE_LOW])
        close_price = float(kline_data[KLINE_CLOSE])
        volume = float(kline_data[KLINE_VOLUME])
    except (ValueError, TypeError, IndexError):
        return None

    if open_time_ms <= 0:
        return None

    # Validate OHLC logic
    if low_price > high_price:
        return None
    if open_price < low_price or open_price > high_price:
        return None
    if close_price < low_price or close_price > high_price:
        return None

    from datetime import datetime, timezone
    timestamp = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).isoformat()

    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


def parse_ticker_response(data: dict) -> Optional[Dict]:
    """Parse a Coins.ph 24hr ticker response into standard ticker dict.

    Returns dict with 'last', 'bid', 'ask', 'volume_24h', 'change_24h' or None.
    """
    if not isinstance(data, dict):
        return None

    try:
        result = {
            "last": float(data.get("lastPrice", 0)),
            "bid": float(data.get("bidPrice", 0)),
            "ask": float(data.get("askPrice", 0)),
            "volume_24h": float(data.get("volume", 0)),
            "quote_volume_24h": float(data.get("quoteVolume", 0)),
            "change_24h": float(data.get("priceChangePercent", 0)),
            "high_24h": float(data.get("highPrice", 0)),
            "low_24h": float(data.get("lowPrice", 0)),
        }
        if result["last"] <= 0:
            return None
        return result
    except (ValueError, TypeError):
        return None


class CoinsPhMarketData:
    """Fetch OHLCV data via Coins.ph REST API with retry/backoff/rate-limiting.

    This adapter implements the same interface as MarketData (CCXT) but uses
    the native Coins.ph API directly. No authentication is required for
    public market data endpoints.

    Usage:
        md = CoinsPhMarketData()
        candles = md.fetch_candles("BTC/USDT", "1h", limit=500)
        price = md.get_last_price("BTC/USDT")
    """

    def __init__(
        self,
        base_url: str = COINSPH_BASE_URL,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "AshtradingAI/0.2",
            "Accept": "application/json",
        })
        self._supported_pairs: Optional[set] = None

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
    ) -> List[Dict]:
        """Fetch OHLCV candles via Coins.ph REST endpoint with retry and validation.

        Supports pagination when limit > 1000 (Coins.ph max per request).
        Uses exponential backoff on transient failures.
        """
        coinsph_symbol = normalize_symbol(symbol)

        if timeframe not in SUPPORTED_INTERVALS:
            logger.warning(
                "Unsupported Coins.ph interval '%s'. Supported: %s",
                timeframe, ", ".join(sorted(SUPPORTED_INTERVALS)),
            )
            return []

        all_candles: List[Dict] = []
        exchange_max = 1000
        remaining = limit
        since = None

        while remaining > 0:
            batch_size = min(remaining, exchange_max)
            batch = self._fetch_klines_batch(coinsph_symbol, timeframe, batch_size, since)
            if not batch:
                break

            all_candles.extend(batch)
            remaining -= len(batch)

            if len(batch) < batch_size:
                break

            # Set 'since' for next page: last candle close_time + 1ms
            last_ts = batch[-1].get("timestamp", "")
            since = _iso_to_ms(last_ts) + 1 if last_ts else None
            if since is None:
                break

            time.sleep(self.base_delay)

        valid, errors = validate_candles(all_candles)
        if errors:
            logger.warning("Candle validation warnings for %s: %d issues", symbol, len(errors))
        return valid

    def _fetch_klines_batch(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        since: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch a single batch of klines with retry/backoff."""
        url = f"{self.base_url}{COINSPH_KLINE_ENDPOINT}"
        params: Dict = {
            "symbol": symbol,
            "interval": timeframe,
            "limit": limit,
        }
        if since is not None:
            params["startTime"] = since

        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get(
                        "Retry-After", self.base_delay * (2 ** attempt)
                    ))
                    logger.warning("Rate limited, waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, list):
                    logger.error("Unexpected klines response type for %s: %s", symbol, type(data).__name__)
                    return []

                candles = []
                for kline in data:
                    candle = parse_kline_to_candle(kline)
                    if candle is not None:
                        candles.append(candle)
                return candles

            except requests.exceptions.Timeout:
                last_err = "timeout"
                logger.warning("Timeout fetching klines for %s (attempt %d/%d)",
                               symbol, attempt + 1, self.max_retries)
            except requests.exceptions.ConnectionError as e:
                last_err = f"connection_error: {e}"
                logger.warning("Connection error fetching klines for %s (attempt %d/%d)",
                               symbol, attempt + 1, self.max_retries)
            except requests.exceptions.HTTPError as e:
                status = getattr(e.response, "status_code", 0) if e.response is not None else 0
                if status >= 500:
                    last_err = f"server_error_{status}"
                    logger.warning("Server error %d for %s (attempt %d/%d)",
                                   status, symbol, attempt + 1, self.max_retries)
                else:
                    logger.error("HTTP error %d for %s: %s", status, symbol, e)
                    return []
            except Exception as e:
                last_err = str(e)
                logger.error("Unexpected error fetching klines for %s: %s", symbol, e)
                return []

            delay = self.base_delay * (2 ** attempt)
            time.sleep(delay)

        logger.error("All %d retries exhausted for %s: %s", self.max_retries, symbol, last_err)
        return []

    def get_last_price(self, symbol: str) -> float:
        """Fetch the latest price for a symbol via Coins.ph price ticker."""
        coinsph_symbol = normalize_symbol(symbol)
        url = f"{self.base_url}{COINSPH_PRICE_ENDPOINT}"

        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(
                    url, params={"symbol": coinsph_symbol}, timeout=15
                )
                if resp.status_code == 429:
                    time.sleep(self.base_delay * (2 ** attempt))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return float(data.get("price", 0.0))
                return 0.0
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        return 0.0

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Fetch 24hr ticker statistics for a symbol."""
        coinsph_symbol = normalize_symbol(symbol)
        url = f"{self.base_url}{COINSPH_TICKER_ENDPOINT}"

        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(
                    url, params={"symbol": coinsph_symbol}, timeout=15
                )
                if resp.status_code == 429:
                    time.sleep(self.base_delay * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return parse_ticker_response(resp.json())
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        return None

    def get_supported_pairs(self) -> set:
        """Fetch supported trading pairs from Coins.ph exchange info.

        Caches the result for the lifetime of this instance.
        Requires API key (MARKET_DATA security type on Coins.ph).
        Returns empty set if unavailable.
        """
        if self._supported_pairs is not None:
            return self._supported_pairs

        try:
            url = f"{self.base_url}/openapi/v1/exchangeInfo"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            symbols = data.get("symbols", [])
            self._supported_pairs = {
                s["symbol"] for s in symbols
                if isinstance(s, dict) and s.get("status") == "TRADING"
            }
        except Exception as e:
            logger.debug("Could not fetch supported pairs: %s", e)
            self._supported_pairs = set()

        return self._supported_pairs

    def validate_symbol(self, symbol: str) -> bool:
        """Check if a symbol is supported on Coins.ph.

        If the pairs list cannot be fetched, returns True (optimistic).
        """
        coinsph_symbol = normalize_symbol(symbol)
        pairs = self.get_supported_pairs()
        if not pairs:
            return True
        return coinsph_symbol in pairs


def _iso_to_ms(iso_str: str) -> Optional[int]:
    """Convert ISO 8601 string to milliseconds timestamp."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError, OSError):
        return None
