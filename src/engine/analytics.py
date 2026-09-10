"""Performance analytics — comprehensive trade and strategy performance metrics."""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PerformanceMetrics:
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    trade_count: int = 0
    avg_holding_time: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in self.__dict__.items()}


@dataclass
class SegmentPerformance:
    segment_key: str
    metrics: PerformanceMetrics
    trade_count: int = 0


class PerformanceAnalyzer:
    """Calculate comprehensive performance metrics from trade records."""

    def __init__(self, starting_balance: float = 1000.0):
        self.starting_balance = starting_balance

    def analyze(self, trades: List[Dict[str, Any]]) -> PerformanceMetrics:
        if not trades:
            return PerformanceMetrics()

        pnls = [t.get("pnl", 0.0) or 0.0 for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total = len(pnls)

        net_pnl = sum(pnls)
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = sum(losses) if losses else 0.0
        win_rate = len(wins) / total if total > 0 else 0.0
        loss_rate = len(losses) / total if total > 0 else 0.0
        avg_win = gross_profit / len(wins) if wins else 0.0
        avg_loss = gross_loss / len(losses) if losses else 0.0
        profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else float("inf")
        expectancy = net_pnl / total if total > 0 else 0.0

        # Drawdown
        balance = self.starting_balance
        peak = balance
        max_dd = 0.0
        max_dd_pct = 0.0
        for p in pnls:
            balance += p
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd / peak if peak > 0 else 0.0

        # Sharpe (annualized, assuming hourly)
        if len(pnls) > 1:
            mean_ret = sum(pnls) / len(pnls)
            std_ret = math.sqrt(sum((p - mean_ret) ** 2 for p in pnls) / (len(pnls) - 1))
            sharpe = (mean_ret / std_ret * math.sqrt(8760)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        # Sortino
        neg_returns = [p for p in pnls if p < 0]
        if neg_returns:
            downside_std = math.sqrt(sum(p ** 2 for p in neg_returns) / len(neg_returns))
            sortino = (sum(pnls) / len(pnls) / downside_std * math.sqrt(8760)) if downside_std > 0 else 0.0
        else:
            sortino = 0.0

        calmar = (net_pnl / max_dd_pct) if max_dd_pct > 0 else 0.0
        recovery = (net_pnl / max_dd) if max_dd > 0 else float("inf")

        total_fees = sum(t.get("fee", 0.0) or 0.0 for t in trades)
        total_slippage = sum(t.get("slippage", 0.0) or 0.0 for t in trades)

        return PerformanceMetrics(
            net_pnl=net_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            win_rate=win_rate,
            loss_rate=loss_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_win=avg_win,
            average_loss=avg_loss,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            recovery_factor=recovery,
            trade_count=total,
            largest_win=max(pnls) if pnls else 0.0,
            largest_loss=min(pnls) if pnls else 0.0,
            total_fees=total_fees,
            total_slippage=total_slippage,
        )

    def analyze_by_segment(
        self, trades: List[Dict[str, Any]], segment_key: str
    ) -> List[SegmentPerformance]:
        segments: Dict[str, List[Dict]] = {}
        for t in trades:
            key = t.get(segment_key, "unknown")
            segments.setdefault(key, []).append(t)
        results = []
        for key, seg_trades in sorted(segments.items()):
            metrics = self.analyze(seg_trades)
            results.append(SegmentPerformance(segment_key=key, metrics=metrics, trade_count=len(seg_trades)))
        return results
