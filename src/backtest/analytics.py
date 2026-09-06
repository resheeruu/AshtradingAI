"""AI Decision Quality Analytics.

Answers:
- How often did AI agree with M7 setup direction?
- How often did AI reject a setup?
- How often did AI choose HOLD?
- What happened after AI confirmation?
- Performance by confidence bucket, regime, symbol, session, long/short.

Research only — does NOT auto-change strategy thresholds.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DecisionEvent:
    """A single AI decision event for analytics."""
    timestamp: str = ""
    symbol: str = ""
    direction: str = ""  # LONG/SHORT from M7
    ai_decision: str = ""  # BUY/SELL/HOLD from AI
    confidence: float = 0.0
    confirmed: bool = False  # Did AI agree with direction?
    regime: str = "UNKNOWN"
    pnl: float = 0.0  # P&L of resulting trade (0 if no trade)
    was_trade: bool = False
    filter_states: Dict[str, bool] = field(default_factory=dict)


class DecisionAnalytics:
    """Collects and analyzes AI decision quality metrics."""

    def __init__(self):
        self.events: List[DecisionEvent] = []

    def record(self, event: DecisionEvent) -> None:
        self.events.append(event)

    def agreement_rate(self) -> float:
        """How often AI confirmed the M7 direction."""
        signals = [e for e in self.events if e.direction]
        if not signals:
            return 0.0
        confirmed = sum(1 for e in signals if e.confirmed)
        return confirmed / len(signals)

    def rejection_rate(self) -> float:
        """How often AI rejected (confidence=0) a setup."""
        signals = [e for e in self.events if e.direction]
        if not signals:
            return 0.0
        rejected = sum(1 for e in signals if not e.confirmed)
        return rejected / len(signals)

    def hold_rate(self) -> float:
        """How often AI chose HOLD."""
        if not self.events:
            return 0.0
        holds = sum(1 for e in self.events if e.ai_decision == "HOLD")
        return holds / len(self.events)

    def performance_by_confidence_bucket(
        self, n_buckets: int = 5
    ) -> Dict[str, Dict[str, float]]:
        """Performance metrics grouped by confidence buckets."""
        trade_events = [e for e in self.events if e.was_trade]
        if not trade_events:
            return {}

        min_conf = min(e.confidence for e in trade_events)
        max_conf = max(e.confidence for e in trade_events)
        if max_conf <= min_conf:
            return {"all": _compute_bucket_stats(trade_events)}

        step = (max_conf - min_conf) / n_buckets
        buckets: Dict[str, List[DecisionEvent]] = {}

        for e in trade_events:
            bucket_idx = min(int((e.confidence - min_conf) / step), n_buckets - 1)
            lo = min_conf + bucket_idx * step
            hi = lo + step
            key = f"{lo:.2f}-{hi:.2f}"
            buckets.setdefault(key, []).append(e)

        return {k: _compute_bucket_stats(v) for k, v in buckets.items()}

    def performance_by_regime(self) -> Dict[str, Dict[str, float]]:
        """Performance metrics grouped by market regime."""
        trade_events = [e for e in self.events if e.was_trade]
        by_regime: Dict[str, List[DecisionEvent]] = {}
        for e in trade_events:
            by_regime.setdefault(e.regime, []).append(e)
        return {k: _compute_bucket_stats(v) for k, v in by_regime.items()}

    def performance_by_symbol(self) -> Dict[str, Dict[str, float]]:
        """Performance metrics grouped by symbol."""
        trade_events = [e for e in self.events if e.was_trade]
        by_sym: Dict[str, List[DecisionEvent]] = {}
        for e in trade_events:
            by_sym.setdefault(e.symbol, []).append(e)
        return {k: _compute_bucket_stats(v) for k, v in by_sym.items()}

    def performance_by_direction(self) -> Dict[str, Dict[str, float]]:
        """Performance metrics for long vs short."""
        trade_events = [e for e in self.events if e.was_trade]
        by_dir: Dict[str, List[DecisionEvent]] = {}
        for e in trade_events:
            key = "long" if e.direction == "LONG" else "short"
            by_dir.setdefault(key, []).append(e)
        return {k: _compute_bucket_stats(v) for k, v in by_dir.items()}

    def performance_by_filter_combination(self) -> Dict[str, Dict[str, float]]:
        """Performance grouped by which filters were active."""
        trade_events = [e for e in self.events if e.was_trade]
        by_combo: Dict[str, List[DecisionEvent]] = {}
        for e in trade_events:
            # Create a key from active filters
            active = sorted(k for k, v in e.filter_states.items() if v)
            key = "+".join(active) if active else "none"
            by_combo.setdefault(key, []).append(e)
        return {k: _compute_bucket_stats(v) for k, v in by_combo.items()}

    def summary(self) -> dict:
        """Complete analytics summary."""
        total = len(self.events)
        signals = [e for e in self.events if e.direction]
        trades = [e for e in self.events if e.was_trade]

        return {
            "total_events": total,
            "total_signals": len(signals),
            "total_trades": len(trades),
            "agreement_rate": round(self.agreement_rate(), 4),
            "rejection_rate": round(self.rejection_rate(), 4),
            "hold_rate": round(self.hold_rate(), 4),
            "performance_by_confidence": self.performance_by_confidence_bucket(),
            "performance_by_regime": self.performance_by_regime(),
            "performance_by_symbol": self.performance_by_symbol(),
            "performance_by_direction": self.performance_by_direction(),
            "performance_by_filter_combination": self.performance_by_filter_combination(),
        }


def _compute_bucket_stats(events: List[DecisionEvent]) -> Dict[str, float]:
    if not events:
        return {"count": 0}
    pnls = [e.pnl for e in events]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "count": len(events),
        "total_pnl": round(sum(pnls), 4),
        "avg_pnl": round(sum(pnls) / len(pnls), 4),
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0.0,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
    }
