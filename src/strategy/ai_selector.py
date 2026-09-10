"""AI Strategy Selector for multi-strategy engine.

Evaluates market conditions and selects appropriate strategy.
Returns structured data for trading decisions.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.strategy.regime_detector import MarketRegime, MarketRegimeDetector
from src.strategy.spec import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class StrategySelection:
    """Structured AI strategy selection output."""
    selected_strategy: str
    direction: str  # "BUY", "SELL", "HOLD"
    confidence: float
    reason: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    entry_conditions: List[str]
    invalid_conditions: List[str]
    regime: str
    volatility: float
    trend: str
    momentum: float
    spread: float
    timeframe: str
    symbol: str
    session: str
    existing_positions: List[str]
    risk_state: Dict[str, Any]
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_strategy": self.selected_strategy,
            "direction": self.direction,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "entry_conditions": self.entry_conditions,
            "invalid_conditions": self.invalid_conditions,
            "regime": self.regime,
            "volatility": self.volatility,
            "trend": self.trend,
            "momentum": self.momentum,
            "spread": self.spread,
            "timeframe": self.timeframe,
            "symbol": self.symbol,
            "session": self.session,
            "existing_positions": self.existing_positions,
            "risk_state": self.risk_state,
            "timestamp": self.timestamp,
        }


class AIStrategySelector:
    """AI-powered strategy selection based on market conditions."""

    def __init__(
        self,
        strategies: Dict[str, BaseStrategy],
        regime_detector: MarketRegimeDetector,
        min_confidence: float = 0.6,
        strategy_switch_cooldown: int = 300,  # seconds
    ):
        self.strategies = strategies
        self.regime_detector = regime_detector
        self.min_confidence = min_confidence
        self.strategy_switch_cooldown = strategy_switch_cooldown
        self._last_strategy_switch: Dict[str, float] = {}  # symbol -> timestamp
        self._current_strategy: Dict[str, str] = {}  # symbol -> strategy_id

    def select_strategy(
        self,
        candles: List[Dict],
        indicators: Dict[str, Any],
        context: Dict[str, Any],
    ) -> StrategySelection:
        """Select best strategy based on market conditions."""
        symbol = context.get("symbol", "")
        timeframe = context.get("timeframe", "H1")
        timestamp = candles[-1].get("timestamp", "") if candles else ""

        # Detect market regime
        regime = self.regime_detector.detect(candles, indicators, timestamp)
        
        # Get strategy preferences
        preferences = self.regime_detector.get_strategy_preferences(regime)

        # Evaluate each strategy
        strategy_scores = {}
        for strategy_id, strategy in self.strategies.items():
            try:
                signal = strategy.generate_signal(candles, indicators, context)
                if signal and signal.is_actionable:
                    score = self._calculate_strategy_score(
                        strategy, signal, regime, preferences.get(strategy_id, 0.5), context
                    )
                    strategy_scores[strategy_id] = {
                        "signal": signal,
                        "score": score,
                        "strategy": strategy,
                    }
            except Exception as e:
                logger.warning(f"Strategy {strategy_id} failed: {e}")
                continue

        # Select best strategy
        if not strategy_scores:
            return self._create_hold_selection(
                symbol, timeframe, timestamp, regime, context, "No strategies generated signals"
            )

        # Sort by score
        sorted_strategies = sorted(
            strategy_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )

        best_strategy_id, best_data = sorted_strategies[0]
        best_signal = best_data["signal"]
        best_score = best_data["score"]

        # Check cooldown
        import time
        current_time = time.time()
        last_switch = self._last_strategy_switch.get(symbol, 0)
        if current_time - last_switch < self.strategy_switch_cooldown:
            # Check if we're switching strategies
            current_strategy = self._current_strategy.get(symbol)
            if current_strategy and current_strategy != best_strategy_id:
                # Cooldown active, prefer current strategy
                if current_strategy in strategy_scores:
                    current_data = strategy_scores[current_strategy]
                    if current_data["score"] > best_score * 0.8:  # Allow 20% degradation
                        best_strategy_id = current_strategy
                        best_data = current_data
                        best_signal = current_data["signal"]
                        best_score = current_data["score"]

        # Update tracking
        self._last_strategy_switch[symbol] = current_time
        self._current_strategy[symbol] = best_strategy_id

        # Calculate risk level
        risk_level = self._calculate_risk_level(best_score, regime, context)

        # Get entry/invalidation conditions
        strategy = best_data["strategy"]
        entry_conditions = strategy.spec.entry_conditions
        invalid_conditions = strategy.spec.invalidation_conditions

        # Calculate market metrics
        volatility = regime.indicators.get("volatility_ratio", 1.0)
        trend = regime.indicators.get("trend_direction", "NEUTRAL")
        momentum = self._calculate_momentum(candles)
        spread = context.get("spread", 0.0)

        # Determine direction
        direction = "BUY" if best_signal.direction == "LONG" else "SELL" if best_signal.direction == "SHORT" else "HOLD"

        # Create selection
        return StrategySelection(
            selected_strategy=best_strategy_id,
            direction=direction,
            confidence=best_signal.confidence,
            reason=f"AI selected {best_strategy_id} with score {best_score:.2f} for {regime.regime.value}",
            risk_level=risk_level,
            entry_conditions=entry_conditions,
            invalid_conditions=invalid_conditions,
            regime=regime.regime.value,
            volatility=volatility,
            trend=trend,
            momentum=momentum,
            spread=spread,
            timeframe=timeframe,
            symbol=symbol,
            session=context.get("session", "UNKNOWN"),
            existing_positions=context.get("open_positions", []),
            risk_state=context.get("risk_state", {}),
            timestamp=timestamp,
        )

    def _calculate_strategy_score(
        self,
        strategy: BaseStrategy,
        signal: Any,
        regime: MarketRegime,
        preference: float,
        context: Dict[str, Any],
    ) -> float:
        """Calculate strategy score based on multiple factors."""
        # Base score from signal confidence
        base_score = signal.confidence

        # Regime compatibility
        regime_compat = 1.0 if regime.regime.value in strategy.spec.regime_compatibility else 0.3

        # Preference from regime detector
        preference_score = preference

        # Timeframe compatibility
        timeframe_compat = 1.0 if signal.timeframe in strategy.spec.supported_timeframes else 0.5

        # Risk/reward ratio
        rr_score = 1.0
        if signal.risk_reward:
            if signal.risk_reward >= 2.0:
                rr_score = 1.2
            elif signal.risk_reward >= 1.5:
                rr_score = 1.0
            elif signal.risk_reward >= 1.0:
                rr_score = 0.8
            else:
                rr_score = 0.6

        # Combine scores
        final_score = (
            base_score * 0.3 +
            regime_compat * 0.25 +
            preference_score * 0.2 +
            timeframe_compat * 0.1 +
            rr_score * 0.15
        )

        return final_score

    def _calculate_risk_level(self, score: float, regime: MarketRegime, context: Dict[str, Any]) -> str:
        """Calculate risk level based on score and market conditions."""
        # Base risk from score
        if score > 0.8:
            risk = "LOW"
        elif score > 0.6:
            risk = "MEDIUM"
        else:
            risk = "HIGH"

        # Adjust for volatility
        volatility = regime.indicators.get("volatility_ratio", 1.0)
        if volatility > 1.5:
            if risk == "LOW":
                risk = "MEDIUM"
            elif risk == "MEDIUM":
                risk = "HIGH"

        # Adjust for spread
        spread = context.get("spread", 0.0)
        if spread > 0.002:
            if risk == "LOW":
                risk = "MEDIUM"

        return risk

    def _calculate_momentum(self, candles: List[Dict]) -> float:
        """Calculate simple momentum from price action."""
        if len(candles) < 10:
            return 0.0
        
        recent_close = candles[-1]["close"]
        past_close = candles[-10]["close"]
        
        if past_close == 0:
            return 0.0
            
        return (recent_close - past_close) / past_close

    def _create_hold_selection(
        self,
        symbol: str,
        timeframe: str,
        timestamp: str,
        regime: MarketRegime,
        context: Dict[str, Any],
        reason: str,
    ) -> StrategySelection:
        """Create a HOLD selection when no strategy is suitable."""
        return StrategySelection(
            selected_strategy="none",
            direction="HOLD",
            confidence=0.0,
            reason=reason,
            risk_level="HIGH",
            entry_conditions=[],
            invalid_conditions=[],
            regime=regime.regime.value,
            volatility=regime.indicators.get("volatility_ratio", 1.0),
            trend=regime.indicators.get("trend_direction", "NEUTRAL"),
            momentum=0.0,
            spread=context.get("spread", 0.0),
            timeframe=timeframe,
            symbol=symbol,
            session=context.get("session", "UNKNOWN"),
            existing_positions=context.get("open_positions", []),
            risk_state=context.get("risk_state", {}),
            timestamp=timestamp,
        )

    def get_strategy_performance(self, symbol: str) -> Dict[str, Any]:
        """Get strategy performance metrics for adaptive selection."""
        # In real implementation, would track historical performance
        return {
            "symbol": symbol,
            "strategies": {},
            "last_update": "",
        }