"""Formal broker protocol/ABC for type-safe broker abstractions.

Defines the interface that all broker adapters must implement.
PaperBroker, MT5DemoBroker, and future LiveBroker all conform to this.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class BrokerProtocol(Protocol):
    """Runtime-checkable protocol for broker duck-typing validation."""

    def execute_buy(
        self,
        portfolio: Any,
        symbol: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ...

    def execute_sell(
        self,
        portfolio: Any,
        symbol: str,
        price: float,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ...

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        ...


class BrokerAdapter(ABC):
    """Abstract base class for all broker adapters.

    Provides standardized interface for:
    - Account information
    - Position management
    - Order execution
    - Market data
    - Health checks
    """

    @property
    @abstractmethod
    def broker_id(self) -> str:
        """Unique broker identifier."""
        ...

    @property
    @abstractmethod
    def broker_type(self) -> str:
        """Broker type: 'paper', 'mt5_demo', 'mt5_live', 'crypto', etc."""
        ...

    @property
    @abstractmethod
    def is_demo(self) -> bool:
        """Whether this is a demo/simulation broker."""
        ...

    @property
    @abstractmethod
    def is_live(self) -> bool:
        """Whether this is a live trading broker."""
        ...

    @abstractmethod
    def get_account(self) -> Dict[str, Any]:
        """Get account information: balance, equity, margin, free_margin, etc."""
        ...

    @abstractmethod
    def get_balance(self) -> float:
        """Get account balance."""
        ...

    @abstractmethod
    def get_equity(self) -> float:
        """Get account equity (balance + floating P/L)."""
        ...

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol."""
        ...

    @abstractmethod
    def get_symbols(self) -> List[str]:
        """Get list of available trading symbols."""
        ...

    @abstractmethod
    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current bid/ask price for a symbol."""
        ...

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV candles."""
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Place an order. Returns order dict or None on failure."""
        ...

    @abstractmethod
    def modify_order(
        self,
        order_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        price: Optional[float] = None,
    ) -> bool:
        """Modify an existing order. Returns success."""
        ...

    @abstractmethod
    def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Close position for a symbol. Returns fill info or None."""
        ...

    @abstractmethod
    def close_all(self) -> List[Dict[str, Any]]:
        """Close all open positions. Returns list of fill info."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns success."""
        ...

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Check broker connection health. Returns status dict."""
        ...

    def supports_symbol(self, symbol: str) -> bool:
        """Check if broker supports a symbol. Default: True."""
        return True

    def get_spread(self, symbol: str) -> float:
        """Get current spread for a symbol. Default: 0."""
        return 0.0

    def get_margin_required(self, symbol: str, quantity: float) -> float:
        """Get margin required for a position. Default: 0."""
        return 0.0


@dataclass
class BrokerCapabilities:
    """Describe broker capabilities for strategy selection."""
    supports_leverage: bool = False
    supports_short_selling: bool = False
    supports_limit_orders: bool = False
    supports_stop_orders: bool = False
    supports_trailing_stop: bool = False
    supports_partial_close: bool = False
    max_position_size: float = 0.0
    min_position_size: float = 0.0
    max_open_positions: int = 0
    supported_timeframes: List[str] = field(default_factory=list)
    supported_asset_classes: List[str] = field(default_factory=list)
    commission_model: str = "spread"  # "spread", "fixed", "percentage"
    execution_model: str = "market"  # "market", "instant", "pending"
