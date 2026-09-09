"""MT5 market data adapter — converts MT5 rates into AshtradingAI candle format.

Uses MT5ConnectionManager wrappers for all MT5 API calls.
Never imports MetaTrader5 directly.

Preserves the existing candle format:
{
    "timestamp": "ISO8601 string",
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
}
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# AshtradingAI timeframe -> MT5 timeframe constant name
TIMEFRAME_MAP = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
    "1d": "TIMEFRAME_D1",
    "1w": "TIMEFRAME_W1",
    "1M": "TIMEFRAME_MN1",
}

# MT5 timeframe constants (numeric values)
TIMEFRAME_SECONDS = {
    "TIMEFRAME_M1": 60,
    "TIMEFRAME_M5": 300,
    "TIMEFRAME_M15": 900,
    "TIMEFRAME_M30": 1800,
    "TIMEFRAME_H1": 3600,
    "TIMEFRAME_H4": 14400,
    "TIMEFRAME_D1": 86400,
    "TIMEFRAME_W1": 604800,
    "TIMEFRAME_MN1": 2592000,
}


class MT5MarketData:
    """Retrieves candle data from MT5 and converts to AshtradingAI format.

    Uses MT5ConnectionManager for all MT5 API access.
    """

    def __init__(self, connection_manager, symbol_map: Optional[Dict[str, str]] = None):
        """
        Args:
            connection_manager: MT5ConnectionManager instance (must be connected).
            symbol_map: Optional mapping from AshtradingAI symbol to MT5 symbol.
                        e.g. {"BTCUSD": "BTCUSD."} for broker-specific suffixes.
        """
        self.connection = connection_manager
        self.symbol_map = symbol_map or {}

    def map_symbol(self, ash_symbol: str) -> str:
        """Map AshtradingAI symbol to MT5 broker symbol."""
        return self.symbol_map.get(ash_symbol, ash_symbol)

    def fetch_candles(
        self, symbol: str, timeframe: str = "1h", limit: int = 500
    ) -> List[Dict]:
        """Fetch OHLCV candles from MT5.

        Returns candles in standard AshtradingAI format.
        Returns empty list on failure.
        """
        if not self.connection.is_connected():
            logger.warning("MT5 not connected, cannot fetch candles for %s", symbol)
            return []

        mt5_symbol = self.map_symbol(symbol)
        mt5_tf_name = TIMEFRAME_MAP.get(timeframe)
        if mt5_tf_name is None:
            logger.error("Unsupported timeframe for MT5: %s", timeframe)
            return []

        try:
            # Use lazy import for MetaTrader5 (only needed for copy_rates_from_pos)
            from src.mt5.connection import _get_mt5
            mt5 = _get_mt5()

            # Verify symbol exists and is visible via connection manager
            sym_info = self.connection.symbol_info(mt5_symbol)
            if sym_info is None:
                logger.error("MT5 symbol not found: %s (mapped from %s)", mt5_symbol, symbol)
                return []

            if not sym_info.get("visible", False):
                if not self.connection.symbol_select(mt5_symbol, True):
                    logger.error("Failed to select MT5 symbol: %s", mt5_symbol)
                    return []

            # Get the numeric timeframe value
            mt5_tf_value = getattr(mt5, mt5_tf_name, None)
            if mt5_tf_value is None:
                logger.error("MT5 timeframe constant not found: %s", mt5_tf_name)
                return []

            # Copy rates from position 0 (most recent)
            rates = mt5.copy_rates_from_pos(mt5_symbol, mt5_tf_value, 0, limit)
            if rates is None or len(rates) == 0:
                logger.warning("No rates returned for %s %s", mt5_symbol, timeframe)
                return []

            # Convert MT5 rates to AshtradingAI candle format
            candles = []
            for rate in rates:
                try:
                    ts = datetime.fromtimestamp(
                        int(rate["time"]), tz=timezone.utc
                    ).isoformat()
                    candles.append({
                        "timestamp": ts,
                        "open": float(rate["open"]),
                        "high": float(rate["high"]),
                        "low": float(rate["low"]),
                        "close": float(rate["close"]),
                        "volume": float(rate["tick_volume"]),
                    })
                except (KeyError, TypeError, ValueError) as e:
                    logger.debug("Skipping malformed rate: %s", e)
                    continue

            logger.debug("Fetched %d candles for %s %s from MT5", len(candles), symbol, timeframe)
            return candles

        except ImportError:
            logger.error("MetaTrader5 package not installed")
            return []
        except Exception as e:
            logger.error("Error fetching MT5 candles for %s: %s", symbol, e)
            return []

    def get_last_price(self, symbol: str) -> float:
        """Get current bid price for a symbol."""
        if not self.connection.is_connected():
            return 0.0

        mt5_symbol = self.map_symbol(symbol)
        tick = self.connection.symbol_info_tick(mt5_symbol)
        if tick is None:
            return 0.0
        return float(tick.get("bid", 0.0))

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Get MT5 symbol information (point, digits, volume limits, etc.)."""
        if not self.connection.is_connected():
            return None

        mt5_symbol = self.map_symbol(symbol)
        return self.connection.symbol_info(mt5_symbol)
