"""Strategy registry — central registry for all trading strategies.

Replaces hard-coded strategy lists with a dynamic registry.
Strategies register themselves and can be looked up by ID, family, or capability.
"""
import logging
from typing import Dict, List, Optional, Type

from src.strategy.spec import BaseStrategy, StrategySpec, get_default_strategies

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Central registry for all trading strategies.

    Provides:
    - Registration of new strategies
    - Lookup by ID, family, timeframe, regime
    - Strategy metadata and capabilities
    - Dynamic strategy loading
    """

    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
        self._families: Dict[str, List[str]] = {}
        self._timeframe_map: Dict[str, List[str]] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Initialize with default built-in strategies."""
        if self._initialized:
            return

        defaults = get_default_strategies()
        for strategy in defaults:
            self.register(strategy)

        self._initialized = True
        logger.info("Strategy registry initialized with %d strategies", len(self._strategies))

    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy."""
        sid = strategy.strategy_id
        if sid in self._strategies:
            logger.warning("Strategy %s already registered, overwriting", sid)

        self._strategies[sid] = strategy

        # Index by family
        family = strategy.spec.strategy_family
        if family:
            if family not in self._families:
                self._families[family] = []
            if sid not in self._families[family]:
                self._families[family].append(sid)

        # Index by timeframe
        for tf in strategy.spec.supported_timeframes:
            if tf not in self._timeframe_map:
                self._timeframe_map[tf] = []
            if sid not in self._timeframe_map[tf]:
                self._timeframe_map[tf].append(sid)

        logger.debug("Registered strategy: %s (family=%s)", sid, family)

    def unregister(self, strategy_id: str) -> bool:
        """Unregister a strategy. Returns True if found and removed."""
        if strategy_id not in self._strategies:
            return False

        strategy = self._strategies.pop(strategy_id)

        # Remove from family index
        family = strategy.spec.strategy_family
        if family in self._families:
            self._families[family] = [
                sid for sid in self._families[family] if sid != strategy_id
            ]
            if not self._families[family]:
                del self._families[family]

        # Remove from timeframe index
        for tf in strategy.spec.supported_timeframes:
            if tf in self._timeframe_map:
                self._timeframe_map[tf] = [
                    sid for sid in self._timeframe_map[tf] if sid != strategy_id
                ]
                if not self._timeframe_map[tf]:
                    del self._timeframe_map[tf]

        logger.debug("Unregistered strategy: %s", strategy_id)
        return True

    def get(self, strategy_id: str) -> Optional[BaseStrategy]:
        """Get strategy by ID."""
        return self._strategies.get(strategy_id)

    def get_spec(self, strategy_id: str) -> Optional[StrategySpec]:
        """Get strategy spec by ID."""
        strategy = self._strategies.get(strategy_id)
        return strategy.spec if strategy else None

    def list_all(self) -> List[BaseStrategy]:
        """List all registered strategies."""
        return list(self._strategies.values())

    def list_ids(self) -> List[str]:
        """List all strategy IDs."""
        return list(self._strategies.keys())

    def list_by_family(self, family: str) -> List[BaseStrategy]:
        """List strategies by family (SCALPING, TREND, etc.)."""
        sids = self._families.get(family, [])
        return [self._strategies[sid] for sid in sids if sid in self._strategies]

    def list_by_timeframe(self, timeframe: str) -> List[BaseStrategy]:
        """List strategies that support a timeframe."""
        sids = self._timeframe_map.get(timeframe, [])
        return [self._strategies[sid] for sid in sids if sid in self._strategies]

    def list_by_regime(self, regime: str) -> List[BaseStrategy]:
        """List strategies compatible with a market regime."""
        return [
            s for s in self._strategies.values()
            if s.supports_regime(regime)
        ]

    def list_families(self) -> List[str]:
        """List all strategy families."""
        return list(self._families.keys())

    def get_capabilities(self, strategy_id: str) -> Dict:
        """Get strategy capabilities as a dictionary."""
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return {}
        spec = strategy.spec
        return {
            "strategy_id": spec.strategy_id,
            "name": spec.name,
            "version": spec.version,
            "family": spec.strategy_family,
            "holding_period": spec.expected_holding_period,
            "timeframes": spec.supported_timeframes,
            "asset_classes": spec.supported_asset_classes,
            "regimes": spec.supported_regimes,
            "min_bars": spec.min_bars_required,
            "generates_stops": spec.generates_stops,
            "risk_reward_min": spec.risk_reward_min,
            "entry_conditions": spec.entry_conditions,
            "invalidation_conditions": spec.invalidation_conditions,
        }

    def get_registry_summary(self) -> Dict:
        """Get summary of all registered strategies."""
        return {
            "total_strategies": len(self._strategies),
            "families": {f: len(sids) for f, sids in self._families.items()},
            "timeframes": {tf: len(sids) for tf, sids in self._timeframe_map.items()},
            "strategies": [
                {
                    "id": s.strategy_id,
                    "name": s.spec.name,
                    "family": s.spec.strategy_family,
                    "holding_period": s.spec.expected_holding_period,
                }
                for s in self._strategies.values()
            ],
        }


# Global singleton
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get or create the global strategy registry."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
        _registry.initialize()
    return _registry


def register_strategy(strategy: BaseStrategy) -> None:
    """Convenience: register a strategy in the global registry."""
    get_registry().register(strategy)


def get_strategy(strategy_id: str) -> Optional[BaseStrategy]:
    """Convenience: get a strategy from the global registry."""
    return get_registry().get(strategy_id)
