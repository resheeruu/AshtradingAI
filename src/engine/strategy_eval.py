"""Strategy evaluation and leaderboard — ranks strategies holistically.

Do NOT rank purely by profit. Include overfit warnings, data sufficiency, stability.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.engine.analytics import PerformanceAnalyzer, PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class StrategyRating:
    strategy_id: str
    metrics: PerformanceMetrics
    oos_return: float = 0.0
    stability_score: float = 0.0
    regime_robustness: float = 0.0
    composite_score: float = 0.0
    warnings: List[str] = field(default_factory=list)
    rating: str = "UNRATED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "metrics": self.metrics.to_dict(),
            "oos_return": self.oos_return,
            "stability_score": self.stability_score,
            "regime_robustness": self.regime_robustness,
            "composite_score": self.composite_score,
            "warnings": self.warnings,
            "rating": self.rating,
        }


class StrategyEvaluator:
    """Evaluates and ranks strategies using multiple criteria."""

    def __init__(self, min_trades: int = 30):
        self.min_trades = min_trades
        self._analyzer = PerformanceAnalyzer()

    def evaluate(
        self,
        strategy_id: str,
        trades: List[Dict[str, Any]],
        oos_trades: Optional[List[Dict[str, Any]]] = None,
        regime_results: Optional[Dict[str, List[Dict]]] = None,
    ) -> StrategyRating:
        metrics = self._analyzer.analyze(trades)
        warnings = []

        if metrics.trade_count < self.min_trades:
            warnings.append("INSUFFICIENT_DATA")
        if metrics.profit_factor > 3.0 and metrics.trade_count < 100:
            warnings.append("OVERFIT_WARNING")
        if metrics.max_drawdown_pct > 0.20:
            warnings.append("HIGH_DRAWDOWN")

        stability = self._calculate_stability(trades)
        if stability < 0.3:
            warnings.append("UNSTABLE")

        regime_rob = self._calculate_regime_robustness(regime_results) if regime_results else 0.5
        if regime_rob < 0.3:
            warnings.append("REGIME_DEPENDENT")

        oos_return = 0.0
        if oos_trades:
            oos_m = self._analyzer.analyze(oos_trades)
            oos_return = oos_m.net_pnl / self._analyzer.starting_balance if self._analyzer.starting_balance > 0 else 0.0
            if oos_return < 0:
                warnings.append("DEGRADED_OOS")

        composite = self._composite_score(metrics, stability, regime_rob, oos_return)
        rating = self._classify(composite, warnings)

        return StrategyRating(
            strategy_id=strategy_id,
            metrics=metrics,
            oos_return=oos_return,
            stability_score=stability,
            regime_robustness=regime_rob,
            composite_score=composite,
            warnings=warnings,
            rating=rating,
        )

    def _calculate_stability(self, trades: List[Dict]) -> float:
        if len(trades) < 10:
            return 0.0
        pnls = [t.get("pnl", 0) or 0 for t in trades]
        chunk_size = max(1, len(pnls) // 4)
        chunks = [pnls[i:i + chunk_size] for i in range(0, len(pnls), chunk_size)]
        chunk_returns = [sum(c) for c in chunks if c]
        if len(chunk_returns) < 2:
            return 0.5
        positive = sum(1 for r in chunk_returns if r > 0)
        return positive / len(chunk_returns)

    def _calculate_regime_robustness(self, regime_results: Dict[str, List[Dict]]) -> float:
        if not regime_results:
            return 0.5
        regime_scores = []
        for regime, trades in regime_results.items():
            m = self._analyzer.analyze(trades)
            if m.trade_count > 0:
                regime_scores.append(1.0 if m.net_pnl > 0 else 0.0)
        return sum(regime_scores) / len(regime_scores) if regime_scores else 0.5

    def _composite_score(self, metrics, stability, regime_rob, oos_return) -> float:
        pf_score = min(metrics.profit_factor / 2.0, 1.0) if metrics.profit_factor < float("inf") else 1.0
        wr_score = metrics.win_rate
        dd_penalty = max(0, 1.0 - metrics.max_drawdown_pct * 3)
        sharpe_score = min(max(metrics.sharpe_ratio / 2.0, -1.0), 1.0)
        return (
            pf_score * 0.25
            + wr_score * 0.15
            + dd_penalty * 0.20
            + stability * 0.15
            + regime_rob * 0.10
            + sharpe_score * 0.10
            + min(max(oos_return * 10, -1.0), 1.0) * 0.05
        )

    def _classify(self, score: float, warnings: List[str]) -> str:
        if "OVERFIT_WARNING" in warnings:
            return "OVERFIT_WARNING"
        if "INSUFFICIENT_DATA" in warnings:
            return "INSUFFICIENT_DATA"
        if "UNSTABLE" in warnings:
            return "UNSTABLE"
        if score >= 0.7:
            return "ROBUST"
        if score >= 0.5:
            return "ACCEPTABLE"
        return "WEAK"


def rank_strategies(ratings: List[StrategyRating]) -> List[StrategyRating]:
    """Rank strategies by composite score, excluding those with critical warnings."""
    critical = [r for r in ratings if not any(w in r.warnings for w in ("INSUFFICIENT_DATA", "OVERFIT_WARNING"))]
    other = [r for r in ratings if r not in critical]
    critical.sort(key=lambda r: r.composite_score, reverse=True)
    other.sort(key=lambda r: r.composite_score, reverse=True)
    return critical + other
