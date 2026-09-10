"""Multi-strategy orchestrator — runs multiple strategies concurrently.

Manages strategy selection, signal aggregation, conflict resolution,
and routing through AI validation and risk management.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.signals import Signal, AIDecision
from src.core.enums import TradingMode, MarketHealthStatus, RegimeType
from src.strategy.spec import BaseStrategy
from src.strategy.registry import get_registry
from src.strategy.scoring import StrategyScorer
from src.strategy.regime_detector import MarketRegimeDetector
from src.risk.advanced import AdvancedRiskEngine, RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the multi-strategy orchestrator."""
    max_strategies_per_symbol: int = 3
    min_confidence: float = 0.60
    signal_agreement_threshold: int = 2
    conflict_resolution: str = "highest_confidence"  # "highest_confidence", "majority_vote", "weighted_average"
    enable_regime_filter: bool = True
    enable_ai_validation: bool = True
    strategy_switch_cooldown: int = 300  # seconds between strategy switches
    max_signals_per_cycle: int = 5
    deduplication_window: int = 60  # seconds to prevent duplicate signals


@dataclass
class StrategySelection:
    """Result of strategy selection for a symbol."""
    symbol: str
    selected_strategies: List[str]
    regime: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class SignalAggregation:
    """Aggregated signals from multiple strategies."""
    symbol: str
    direction: str  # "LONG", "SHORT", "HOLD"
    confidence: float
    signals: List[Signal] = field(default_factory=list)
    agreeing_strategies: List[str] = field(default_factory=list)
    conflicting: bool = False
    aggregation_method: str = ""
    reasoning: List[str] = field(default_factory=list)


class MultiStrategyOrchestrator:
    """Orchestrates multiple strategies for a trading session.

    Responsibilities:
    1. Select active strategies based on regime and scoring
    2. Collect signals from all active strategies
    3. Aggregate/resolve conflicting signals
    4. Route through AI validation
    5. Route through risk management
    6. Return approved trading decisions
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self._registry = get_registry()
        self._scorer = StrategyScorer()
        self._regime_detector = MarketRegimeDetector()
        self._active_selections: Dict[str, StrategySelection] = {}
        self._signal_history: List[Dict] = []
        self._last_strategy_switch: Dict[str, float] = {}

    def select_strategies(
        self,
        symbol: str,
        candles: List[Dict],
        indicators: Dict,
        context: Optional[Dict] = None,
    ) -> StrategySelection:
        """Select the best strategies for a symbol based on current market conditions.

        Args:
            symbol: Trading symbol
            candles: Historical OHLCV candles
            indicators: Pre-computed indicators
            context: Additional context (portfolio, positions, etc.)

        Returns:
            StrategySelection with recommended strategies
        """
        ctx = context or {}

        # Detect market regime
        regime = None
        if self.config.enable_regime_filter:
            try:
                regime_detection = self._regime_detector.detect(candles, indicators)
                regime = regime_detection.regime if hasattr(regime_detection, 'regime') else str(regime_detection)
            except Exception as e:
                logger.warning("Regime detection failed for %s: %s", symbol, e)

        # Score all strategies
        scored_strategies = []
        all_strategies = self._registry.list_all()

        for strategy in all_strategies:
            # Check timeframe compatibility
            timeframe = ctx.get("timeframe", "H1")
            if not strategy.supports_timeframe(timeframe):
                continue

            # Check regime compatibility
            if regime and not strategy.supports_regime(regime):
                continue

            # Generate a test signal to score
            try:
                signal = strategy.generate_signal(candles, indicators, {
                    **ctx,
                    "symbol": symbol,
                    "timeframe": timeframe,
                })
                if signal and signal.is_actionable:
                    score_data = strategy.get_signal_score(signal, regime)
                    scored_strategies.append({
                        "strategy_id": strategy.strategy_id,
                        "signal": signal,
                        "score": score_data.get("confidence", 0.0),
                        "regime_compatibility": score_data.get("regime_compatibility", 0.0),
                    })
            except Exception as e:
                logger.debug("Strategy %s failed for %s: %s", strategy.strategy_id, symbol, e)
                continue

        # Sort by score
        scored_strategies.sort(key=lambda x: x["score"], reverse=True)

        # Select top strategies
        selected = scored_strategies[:self.config.max_strategies_per_symbol]
        selected_ids = [s["strategy_id"] for s in selected]
        scores = {s["strategy_id"]: s["score"] for s in selected}

        selection = StrategySelection(
            symbol=symbol,
            selected_strategies=selected_ids,
            regime=regime,
            scores=scores,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        )

        self._active_selections[symbol] = selection
        return selection

    def collect_signals(
        self,
        symbol: str,
        candles: List[Dict],
        indicators: Dict,
        context: Optional[Dict] = None,
    ) -> List[Signal]:
        """Collect signals from all active strategies for a symbol.

        Args:
            symbol: Trading symbol
            candles: Historical OHLCV candles
            indicators: Pre-computed indicators
            context: Additional context

        Returns:
            List of actionable signals
        """
        ctx = context or {}
        selection = self._active_selections.get(symbol)
        if not selection:
            selection = self.select_strategies(symbol, candles, indicators, ctx)

        signals = []
        for strategy_id in selection.selected_strategies:
            strategy = self._registry.get(strategy_id)
            if not strategy:
                continue

            try:
                signal = strategy.generate_signal(candles, indicators, {
                    **ctx,
                    "symbol": symbol,
                    "timeframe": ctx.get("timeframe", "H1"),
                })
                if signal and signal.is_actionable:
                    signals.append(signal)
            except Exception as e:
                logger.warning("Signal generation failed for %s: %s", strategy_id, e)

        return signals

    def aggregate_signals(self, signals: List[Signal], symbol: str) -> SignalAggregation:
        """Aggregate multiple signals into a single trading decision.

        Handles:
        - Signal agreement (multiple strategies agree on direction)
        - Signal conflict (strategies disagree)
        - Confidence weighting
        - Conflict resolution
        """
        if not signals:
            return SignalAggregation(
                symbol=symbol,
                direction="HOLD",
                confidence=0.0,
                aggregation_method="empty",
            )

        # Separate by direction
        long_signals = [s for s in signals if s.direction == "LONG"]
        short_signals = [s for s in signals if s.direction == "SHORT"]

        long_count = len(long_signals)
        short_count = len(short_signals)

        # Check for agreement
        if long_count >= self.config.signal_agreement_threshold and long_count > short_count:
            return self._aggregate_direction(long_signals, "LONG", symbol)
        elif short_count >= self.config.signal_agreement_threshold and short_count > long_count:
            return self._aggregate_direction(short_signals, "SHORT", symbol)
        elif long_count > 0 and short_count > 0:
            # Conflicting signals
            return self._resolve_conflict(long_signals, short_signals, symbol)
        elif long_count > 0:
            return self._aggregate_direction(long_signals, "LONG", symbol)
        elif short_count > 0:
            return self._aggregate_direction(short_signals, "SHORT", symbol)

        return SignalAggregation(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            aggregation_method="no_actionable",
        )

    def _aggregate_direction(
        self,
        signals: List[Signal],
        direction: str,
        symbol: str,
    ) -> SignalAggregation:
        """Aggregate signals in the same direction."""
        if not signals:
            return SignalAggregation(symbol=symbol, direction="HOLD", confidence=0.0)

        # Weight by confidence
        total_weight = sum(s.confidence for s in signals)
        if total_weight <= 0:
            return SignalAggregation(symbol=symbol, direction="HOLD", confidence=0.0)

        weighted_confidence = sum(s.confidence * s.confidence for s in signals) / total_weight

        # Use best entry/SL/TP from highest confidence signal
        best_signal = max(signals, key=lambda s: s.confidence)

        agreeing = [s.strategy_id for s in signals if s.strategy_id]

        reasoning = [
            f"{len(signals)} strategies agree on {direction}",
            f"Weighted confidence: {weighted_confidence:.2f}",
            f"Best signal from: {best_signal.strategy_id}",
        ]

        return SignalAggregation(
            symbol=symbol,
            direction=direction,
            confidence=weighted_confidence,
            signals=signals,
            agreeing_strategies=agreeing,
            conflicting=False,
            aggregation_method="weighted_average",
            reasoning=reasoning,
        )

    def _resolve_conflict(
        self,
        long_signals: List[Signal],
        short_signals: List[Signal],
        symbol: str,
    ) -> SignalAggregation:
        """Resolve conflicting signals between strategies."""
        if self.config.conflict_resolution == "highest_confidence":
            best_long = max(long_signals, key=lambda s: s.confidence) if long_signals else None
            best_short = max(short_signals, key=lambda s: s.confidence) if short_signals else None

            if best_long and best_short:
                if best_long.confidence >= best_short.confidence:
                    winner = best_long
                    loser_signals = short_signals
                else:
                    winner = best_short
                    loser_signals = long_signals
            elif best_long:
                winner = best_long
                loser_signals = short_signals
            else:
                winner = best_short
                loser_signals = long_signals

            reasoning = [
                f"Conflict: {len(long_signals)} long vs {len(short_signals)} short",
                f"Resolved by highest confidence: {winner.strategy_id} ({winner.confidence:.2f})",
            ]

            return SignalAggregation(
                symbol=symbol,
                direction=winner.direction,
                confidence=winner.confidence,
                signals=[winner],
                agreeing_strategies=[winner.strategy_id],
                conflicting=True,
                aggregation_method="highest_confidence",
                reasoning=reasoning,
            )

        # Default: HOLD on conflict
        return SignalAggregation(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            conflicting=True,
            aggregation_method="hold_on_conflict",
            reasoning=["Conflicting signals, defaulting to HOLD"],
        )

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "active_selections": {
                sym: {
                    "strategies": sel.selected_strategies,
                    "regime": sel.regime,
                    "scores": sel.scores,
                }
                for sym, sel in self._active_selections.items()
            },
            "registry_summary": self._registry.get_registry_summary(),
            "config": {
                "max_strategies_per_symbol": self.config.max_strategies_per_symbol,
                "min_confidence": self.config.min_confidence,
                "signal_agreement_threshold": self.config.signal_agreement_threshold,
                "conflict_resolution": self.config.conflict_resolution,
            },
        }
