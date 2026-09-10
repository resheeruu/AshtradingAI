"""Dynamic symbol discovery and broker metadata.

Symbols are discovered from the broker, not hardcoded.
Supports broker suffixes like BTCUSDm, EURUSD.a, XAUUSD.pro.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.enums import AssetClass

logger = logging.getLogger(__name__)


@dataclass
class BrokerSymbol:
    """Full broker-specific symbol metadata."""
    name: str
    description: str = ""
    category: str = ""
    asset_class: str = ""
    currency_base: str = ""
    currency_profit: str = ""
    digits: int = 2
    point: float = 0.0001
    tick_size: float = 0.0001
    tick_value: float = 0.0
    contract_size: float = 1.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    spread: float = 0.0
    trade_mode: str = "FULL"
    session_open: str = ""
    session_close: str = ""
    timezone: str = "UTC"
    available: bool = True
    suffix: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def base_name(self) -> str:
        """Return the symbol without broker suffix (e.g., BTCUSD from BTCUSDm)."""
        if self.suffix and self.name.endswith(self.suffix):
            return self.name[: -len(self.suffix)]
        return self.name

    def matches(self, target: str) -> bool:
        """Check if this symbol matches a target, accounting for suffixes."""
        t = target.upper().replace("/", "")
        n = self.name.upper().replace("/", "")
        if n == t:
            return True
        base = self.base_name.upper().replace("/", "")
        return base == t

    @property
    def is_tradeable(self) -> bool:
        return self.available and self.trade_mode in ("FULL", "LONGONLY", "SHORTONLY")

    def to_risk_metadata(self) -> Dict[str, Any]:
        return {
            "tick_value": self.tick_value,
            "tick_size": self.tick_size,
            "point": self.point,
            "contract_size": self.contract_size,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "digits": self.digits,
        }


@dataclass
class AssetClassConfig:
    """Asset-specific risk and trading configuration."""
    asset_class: str
    volatility_model: str = "fixed"
    trading_sessions: List[str] = field(default_factory=list)
    spread_limit: float = 0.05
    risk_multiplier: float = 1.0
    min_stop_distance: float = 0.0
    max_exposure: float = 0.20
    correlation_group: str = ""


DEFAULT_ASSET_CONFIGS = {
    AssetClass.FOREX.value: AssetClassConfig(
        asset_class="FOREX",
        volatility_model="atr",
        trading_sessions=["london", "new_york"],
        spread_limit=0.0002,
        risk_multiplier=1.0,
        min_stop_distance=0.0005,
        max_exposure=0.30,
        correlation_group="forex_major",
    ),
    AssetClass.METALS.value: AssetClassConfig(
        asset_class="METALS",
        volatility_model="atr",
        trading_sessions=["london", "new_york"],
        spread_limit=0.50,
        risk_multiplier=0.8,
        min_stop_distance=0.50,
        max_exposure=0.20,
        correlation_group="metals",
    ),
    AssetClass.CRYPTO.value: AssetClassConfig(
        asset_class="CRYPTO",
        volatility_model="atr",
        trading_sessions=["24/7"],
        spread_limit=0.01,
        risk_multiplier=0.6,
        min_stop_distance=0.005,
        max_exposure=0.15,
        correlation_group="crypto",
    ),
    AssetClass.INDICES.value: AssetClassConfig(
        asset_class="INDICES",
        volatility_model="atr",
        trading_sessions=["london", "new_york"],
        spread_limit=2.0,
        risk_multiplier=0.7,
        min_stop_distance=5.0,
        max_exposure=0.20,
        correlation_group="indices",
    ),
    AssetClass.ENERGY.value: AssetClassConfig(
        asset_class="ENERGY",
        volatility_model="atr",
        trading_sessions=["london", "new_york"],
        spread_limit=0.05,
        risk_multiplier=0.7,
        min_stop_distance=0.10,
        max_exposure=0.15,
        correlation_group="energy",
    ),
}


class SymbolDiscovery:
    """Centralized symbol registry. Discovers and validates broker symbols."""

    def __init__(self):
        self._symbols: Dict[str, BrokerSymbol] = {}
        self._asset_configs: Dict[str, AssetClassConfig] = dict(DEFAULT_ASSET_CONFIGS)

    def register_symbol(self, symbol: BrokerSymbol) -> None:
        self._symbols[symbol.name.upper()] = symbol

    def register_symbols(self, symbols: List[BrokerSymbol]) -> None:
        for s in symbols:
            self.register_symbol(s)

    def find_symbol(self, target: str) -> Optional[BrokerSymbol]:
        """Find a symbol by name, supporting suffix matching."""
        t = target.upper().replace("/", "")
        for sym in self._symbols.values():
            if sym.matches(t):
                return sym
        return None

    def find_available(self, target: str) -> Optional[BrokerSymbol]:
        sym = self.find_symbol(target)
        if sym and sym.is_tradeable:
            return sym
        return None

    def get_all_symbols(self) -> List[BrokerSymbol]:
        return list(self._symbols.values())

    def get_available_symbols(self) -> List[BrokerSymbol]:
        return [s for s in self._symbols.values() if s.is_tradeable]

    def get_symbols_by_asset_class(self, asset_class: str) -> List[BrokerSymbol]:
        return [
            s for s in self._symbols.values()
            if s.asset_class.upper() == asset_class.upper() and s.is_tradeable
        ]

    def get_asset_config(self, asset_class: str) -> AssetClassConfig:
        return self._asset_configs.get(
            asset_class.upper(),
            DEFAULT_ASSET_CONFIGS.get(AssetClass.OTHER.value, AssetClassConfig(asset_class=asset_class)),
        )

    def set_asset_config(self, config: AssetClassConfig) -> None:
        self._asset_configs[config.asset_class.upper()] = config

    def mark_unavailable(self, symbol_name: str) -> None:
        sym = self.find_symbol(symbol_name)
        if sym:
            sym.available = False
            logger.warning("Symbol marked UNAVAILABLE: %s", symbol_name)

    def from_mt5_symbols(self, mt5_symbols: List[Dict[str, Any]]) -> List[BrokerSymbol]:
        """Convert MT5 symbol info dicts to BrokerSymbol objects."""
        result = []
        for info in mt5_symbols:
            name = info.get("name", "")
            if not name:
                continue
            sym = BrokerSymbol(
                name=name,
                description=info.get("description", ""),
                category=info.get("category", ""),
                currency_base=info.get("currency_base", ""),
                currency_profit=info.get("currency_profit", ""),
                digits=info.get("digits", 2),
                point=info.get("point", 0.0001),
                tick_size=info.get("trade_tick_size", 0.0001),
                tick_value=info.get("trade_tick_value", 0.0),
                contract_size=info.get("trade_contract_size", 1.0),
                volume_min=info.get("volume_min", 0.01),
                volume_max=info.get("volume_max", 100.0),
                volume_step=info.get("volume_step", 0.01),
                spread=info.get("spread", 0),
                trade_mode="FULL" if info.get("trade_mode", 0) == 4 else "DISABLED",
                available=info.get("trade_mode", 0) != 0,
                raw_data=info,
            )
            sym.asset_class = self._classify_symbol(name, info)
            result.append(sym)
        return result

    def _classify_symbol(self, name: str, info: Dict[str, Any]) -> str:
        n = name.upper()
        category = info.get("category", "").upper()
        if any(p in n for p in ("BTC", "ETH", "SOL", "ADA", "DOGE", "XRP")):
            return AssetClass.CRYPTO.value
        if any(p in n for p in ("XAU", "XAG", "GOLD", "SILVER")):
            return AssetClass.METALS.value
        if any(p in n for p in ("US30", "NAS100", "SPX500", "DAX", "FTSE", "NIKKEI")):
            return AssetClass.INDICES.value
        if any(p in n for p in ("OIL", "CRUDE", "NGAS", "NATGAS")):
            return AssetClass.ENERGY.value
        if any(p in n for p in ("EUR", "GBP", "USD", "JPY", "CHF", "AUD", "NZD", "CAD")) and len(n) == 6:
            return AssetClass.FOREX.value
        return AssetClass.OTHER.value
