"""Unified market data interface with retry, backoff, pagination, and rate-limiting."""
import logging
import time
import json
from typing import Optional, List, Dict
import requests

from src.market.validation import validate_candles

logger = logging.getLogger(__name__)

CCXT_BASE = "https://api.ccxt.com"


class MarketData:
    """Fetch OHLCV data via CCXT public API with retry/backoff/rate-limiting."""

    def __init__(
        self,
        exchange_id: str = "binance",
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: int = 30,
    ):
        self.exchange_id = exchange_id
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "AshtradingAI/0.2"})

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
    ) -> List[Dict]:
        """Fetch OHLCV candles via CCXT REST endpoint with retry and validation.

        Supports pagination when limit > exchange max. Uses exponential backoff
        on transient failures.
        """
        all_candles: List[Dict] = []
        exchange_max = 1000  # Most exchanges cap at 1000 per request
        remaining = limit
        since = None  # CCXT uses 'since' for pagination (ms timestamp)

        while remaining > 0:
            batch_size = min(remaining, exchange_max)
            batch = self._fetch_batch(symbol, timeframe, batch_size, since)
            if not batch:
                break

            all_candles.extend(batch)
            remaining -= len(batch)

            if len(batch) < batch_size:
                break  # No more data available

            # Set 'since' for next page: last candle timestamp + 1ms
            last_ts = batch[-1].get("timestamp", "")
            since = _iso_to_ms(last_ts) + 1 if last_ts else None
            if since is None:
                break

            # Rate-limit pause between pages
            time.sleep(self.base_delay)

        # Validate the full result
        valid, errors = validate_candles(all_candles)
        if errors:
            logger.warning("Candle validation warnings for %s: %d issues", symbol, len(errors))
        return valid

    def _fetch_batch(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        since: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch a single batch with retry/backoff."""
        url = f"{CCXT_BASE}/{self.exchange_id}/fetchOHLCV"
        params: Dict = {"symbol": symbol, "timeframe": timeframe, "limit": limit}
        if since is not None:
            params["since"] = since

        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)

                # Handle rate limiting (429)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", self.base_delay * (2 ** attempt)))
                    logger.warning("Rate limited, waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, list):
                    logger.error("Unexpected response type for %s: %s", symbol, type(data).__name__)
                    return []

                candles = []
                for row in data:
                    if not isinstance(row, list) or len(row) < 6:
                        continue
                    try:
                        candles.append({
                            "timestamp": _ms_to_iso(int(row[0])),
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]),
                        })
                    except (ValueError, TypeError, IndexError) as e:
                        logger.debug("Skipping malformed row: %s", e)
                        continue
                return candles

            except requests.exceptions.Timeout:
                last_err = "timeout"
                logger.warning("Timeout fetching %s (attempt %d/%d)", symbol, attempt + 1, self.max_retries)
            except requests.exceptions.ConnectionError as e:
                last_err = f"connection_error: {e}"
                logger.warning("Connection error fetching %s (attempt %d/%d)", symbol, attempt + 1, self.max_retries)
            except requests.exceptions.HTTPError as e:
                status = getattr(e.response, "status_code", 0) if e.response is not None else 0
                if status >= 500:
                    last_err = f"server_error_{status}"
                    logger.warning("Server error %d for %s (attempt %d/%d)", status, symbol, attempt + 1, self.max_retries)
                else:
                    logger.error("HTTP error %d for %s: %s", status, symbol, e)
                    return []
            except Exception as e:
                last_err = str(e)
                logger.error("Unexpected error fetching %s: %s", symbol, e)
                return []

            # Exponential backoff
            delay = self.base_delay * (2 ** attempt)
            time.sleep(delay)

        logger.error("All %d retries exhausted for %s: %s", self.max_retries, symbol, last_err)
        return []

    def get_last_price(self, symbol: str) -> float:
        url = f"{CCXT_BASE}/{self.exchange_id}/fetchTicker"
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params={"symbol": symbol}, timeout=15)
                if resp.status_code == 429:
                    time.sleep(self.base_delay * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return float(resp.json().get("last", 0.0))
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
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


def _iso_to_ms(iso_str: str) -> Optional[int]:
    """Convert ISO 8601 string to milliseconds timestamp. Returns None on failure."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError, OSError):
        return None
