"""Strategy Scoring for multi-strategy engine.

Provides deterministic strategy scoring before AI execution.
Each strategy exposes signal, direction, confidence, regime compatibility, etc.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.strategy.spec import BaseStrategy, StrategySpec
from src.core.signals import Signal

logger = logging.getLogger(__name__)


@dataclass
class StrategyScore:
    """Structured strategy scoring output."""
    strategy_id: str
    strategy_family: str
    signal: str  # "ACTIVE", "NONE", "HOLD"
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    confidence: float
    regime_compatibility: float
    entry_conditions: List[str]
    stop_loss_suggestion: Optional[float]
    take_profit_suggestion: Optional[float]
    invalidation: List[str]
    timeframe: str
    expected_holding_period: str
    risk_reward_ratio: Optional[float] = None
    score: float = 0.0
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "signal": self.signal,
            "direction": self.direction,
            "confidence": self.confidence,
            "regime_compatibility": self.regime_compatibility,
            "entry_conditions": self.entry_conditions,
            "stop_loss_suggestion": self.stop_loss_suggestion,
            "take_profit_suggestion": self.take_profit_suggestion,
            "invalidation": self.invalidation,
            "timeframe": self.timeframe,
            "expected_holding_period": self.expected_holding_period,
            "risk_reward_ratio": self.risk_reward_ratio,
            "score": self.score,
            "rank": self.rank,
        }


class StrategyScorer:
    """Deterministic strategy scoring system."""

    def __init__(
        self,
        confidence_weight: float = 0.3,
        regime_weight: float = 0.25,
        risk_reward_weight: float = 0.2,
        timeframe_weight: float = 0.15,
        historical_weight: float = 0.1,
    ):
        self.confidence_weight = confidence_weight
        self.regime_weight = regime_weight
        self.risk_reward_weight = risk_reward_weight
        self.timeframe_weight = timeframe_weight
        self.historical_weight = historical_weight
        self._historical_scores: Dict[str, List[float]] = {}

    def score_strategies(
        self,
        strategies: Dict[str, BaseStrategy],
        candles: List[Dict],
        indicators: Dict[str, Any],
        context: Dict[str, Any],
        regime: str = None,
    ) -> List[StrategyScore]:
        """Score all strategies and return sorted list."""
        scores = []

        for strategy_id, strategy in strategies.items():
            try:
                signal = strategy.generate_signal(candles, indicators, context)
                score = self._score_strategy(strategy, signal, regime, context)
                scores.append(score)
            except Exception as e:
                logger.warning(f"Failed to score strategy {strategy_id}: {e}")
                # Add a zero-score entry for failed strategies
                scores.append(StrategyScore(
                    strategy_id=strategy_id,
                    strategy_family=strategy.spec.strategy_family,
                    signal="ERROR",
                    direction="NEUTRAL",
                    confidence=0.0,
                    regime_compatibility=0.0,
                    entry_conditions=[],
                    stop_loss_suggestion=None,
                    take_profit_suggestion=None,
                    invalidation=[],
                    timeframe=strategy.spec.supported_timeframes[0] if strategy.spec.supported_timeframes else "H1",
                    expected_holding_period=strategy.spec.expected_holding_period,
                    score=0.0,
                ))

        # Sort by score descending
        scores.sort(key=lambda x: x.score, reverse=True)

        # Assign ranks
        for i, score in enumerate(scores):
            score.rank = i + 1

        return scores

    def _score_strategy(
        self,
        strategy: BaseStrategy,
        signal: Optional[Signal],
        regime: str,
        context: Dict[str, Any],
    ) -> StrategyScore:
        """Calculate score for a single strategy."""
        # Get base signal data
        if signal and signal.is_actionable:
            signal_status = "ACTIVE"
            direction = signal.direction
            confidence = signal.confidence
            stop_loss = signal.stop_loss
            take_profit = signal.take_profit
            risk_reward = signal.risk_reward
            timeframe = signal.timeframe
        else:
            signal_status = "HOLD"
            direction = "NEUTRAL"
            confidence = 0.0
            stop_loss = None
            take_profit = None
            risk_reward = None
            timeframe = strategy.spec.supported_timeframes[0] if strategy.spec.supported_timeframes else "H1"

        # Calculate regime compatibility
        regime_compatibility = 0.0
        if regime and strategy.spec.regime_compatibility:
            regime_compatibility = 1.0 if regime in strategy.spec.regime_compatibility else 0.3

        # Calculate individual scores
        confidence_score = confidence
        regime_score = regime_compatibility
        
        # Risk/reward score
        rr_score = 0.5
        if risk_reward:
            if risk_reward >= 2.0:
                rr_score = 1.0
            elif risk_reward >= 1.5:
                rr_score = 0.8
            elif risk_reward >= 1.0:
                rr_score = 0.6
            else:
                rr_score = 0.4

        # Timeframe score (prefer configured timeframe)
        timeframe_score = 1.0 if timeframe in strategy.spec.supported_timeframes else 0.5

        # Historical performance score
        historical_score = self._get_historical_score(strategy.strategy_id)

        # Calculate final score
        final_score = (
            confidence_score * self.confidence_weight +
            regime_score * self.regime_weight +
            rr_score * self.risk_reward_weight +
            timeframe_score * self.timeframe_weight +
            historical_score * self.historical_weight
        )

        return StrategyScore(
            strategy_id=strategy.strategy_id,
            strategy_family=strategy.spec.strategy_family,
            signal=signal_status,
            direction=direction,
            confidence=confidence,
            regime_compatibility=regime_compatibility,
            entry_conditions=strategy.spec.entry_conditions,
            stop_loss_suggestion=stop_loss,
            take_profit_suggestion=take_profit,
            invalidation=strategy.spec.invalidation_conditions,
            timeframe=timeframe,
            expected_holding_period=strategy.spec.expected_holding_period,
            risk_reward_ratio=risk_reward,
            score=final_score,
        )

    def _get_historical_score(self, strategy_id: str) -> float:
        """Get historical performance score for a strategy."""
        if strategy_id not in self._historical_scores:
            return 0.5  # Default score
        
        scores = self._historical_scores[strategy_id]
        if not scores:
            return 0.5
        
        # Return average of recent scores
        recent_scores = scores[-10:]  # Last 10 trades
        return sum(recent_scores) / len(recent_scores)

    def update_historical_score(self, strategy_id: str, score: float) -> None:
        """Update historical performance score for a strategy."""
        if strategy_id not in self._historical_scores:
            self._historical_scores[strategy_id] = []
        
        self._historical_scores[strategy_id].append(score)
        
        # Keep only last 100 scores
        if len(self._historical_scores[strategy_id]) > 100:
            self._historical_scores[strategy_id] = self._historical_scores[strategy_id][-100:]

    def get_leaderboard(
        self,
        strategies: Dict[str, BaseStrategy],
        candles: List[Dict],
        indicators: Dict[str, Any],
        context: Dict[str, Any],
        regime: str = None,
        limit: int = 10,
    ) -> List[StrategyScore]:
        """Get strategy leaderboard with scoring."""
        scores = self.score_strategies(strategies, candles, indicators, context, regime)
        return scores[:limit]

    def get_strategy_comparison(
        self,
        strategies: Dict[str, BaseStrategy],
        candles: List[Dict],
        indicators: Dict[str, Any],
        context: Dict[str, Any],
        regime: str = None,
    ) -> Dict[str, Any]:
        """Get detailed comparison of all strategies."""
        scores = self.score_strategies(strategies, candles, indicators, context, regime)
        
        # Group by family
        family_scores = {}
        for score in scores:
            family = score.strategy_family
            if family not in family_scores:
                family_scores[family] = []
            family_scores[family].append(score)
        
        # Calculate family averages
        family_averages = {}
        for family, family_score_list in family_scores.items():
            avg_score = sum(s.score for s in family_score_list) / len(family_score_list)
            family_averages[family] = {
                "average_score": avg_score,
                "strategy_count": len(family_score_list),
                "best_strategy": family_score_list[0].strategy_id if family_score_list else None,
            }
        
        return {
            "individual_scores": [s.to_dict() for s in scores],
            "family_averages": family_averages,
            "total_strategies": len(scores),
            "active_strategies": len([s for s in scores if s.signal == "ACTIVE"]),
        }