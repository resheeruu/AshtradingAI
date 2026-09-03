"""Enhanced performance metrics for tournament results."""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TournamentMetrics:
    """Full performance metrics for a tournament participant."""
    ai_id: str = ""
    starting_balance: float = 0.0
    ending_balance: float = 0.0
    net_profit: float = 0.0
    return_pct: float = 0.0
    num_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    fees_paid: float = 0.0
    total_slippage: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    longest_losing_streak: int = 0
    long_trades: int = 0
    short_trades: int = 0
    daily_returns: List[float] = field(default_factory=list)
    composite_score: float = 0.0
    awards: List[str] = field(default_factory=list)

    def summary(self) -> Dict:
        return {
            "ai_id": self.ai_id,
            "starting_balance": round(self.starting_balance, 2),
            "ending_balance": round(self.ending_balance, 2),
            "net_profit": round(self.net_profit, 2),
            "return_pct": round(self.return_pct, 4),
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "profit_factor": round(self.profit_factor, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "fees_paid": round(self.fees_paid, 4),
            "total_slippage": round(self.total_slippage, 4),
            "largest_win": round(self.largest_win, 4),
            "largest_loss": round(self.largest_loss, 4),
            "longest_losing_streak": self.longest_losing_streak,
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
            "composite_score": round(self.composite_score, 6),
            "awards": self.awards,
        }


def compute_tournament_metrics(
    ai_id: str,
    starting_balance: float,
    ending_balance: float,
    trades: list,
    trading_returns: List[float],
) -> TournamentMetrics:
    """Compute comprehensive metrics from trade history and returns."""
    m = TournamentMetrics()
    m.ai_id = ai_id
    m.starting_balance = starting_balance
    m.ending_balance = ending_balance
    m.net_profit = ending_balance - starting_balance
    m.return_pct = m.net_profit / starting_balance if starting_balance > 0 else 0.0

    m.num_trades = len(trades)
    m.winning_trades = sum(1 for t in trades if t.pnl > 0)
    m.losing_trades = sum(1 for t in trades if t.pnl <= 0)
    m.win_rate = m.winning_trades / m.num_trades if m.num_trades > 0 else 0.0

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [abs(t.pnl) for t in trades if t.pnl <= 0]
    m.avg_win = sum(wins) / len(wins) if wins else 0.0
    m.avg_loss = sum(losses) / len(losses) if losses else 0.0
    m.largest_win = max(wins) if wins else 0.0
    m.largest_loss = -max(losses) if losses else 0.0

    m.fees_paid = sum(t.fee for t in trades)
    m.total_slippage = sum(t.slippage for t in trades)
    m.long_trades = sum(1 for t in trades if t.side == "long")
    m.short_trades = sum(1 for t in trades if t.side == "short")

    total_wins = sum(wins)
    total_losses = sum(losses)
    m.profit_factor = total_wins / total_losses if total_losses > 0 else (float("inf") if total_wins > 0 else 0.0)

    # Longest losing streak
    streak = 0
    max_streak = 0
    for t in trades:
        if t.pnl <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    m.longest_losing_streak = max_streak

    # Max drawdown
    if starting_balance > 0:
        balances = [starting_balance]
        running = starting_balance
        for t in trades:
            running += t.pnl
            balances.append(running)
        peak = balances[0]
        max_dd = 0.0
        for b in balances:
            if b > peak:
                peak = b
            dd = (peak - b) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = max_dd

    # Sharpe and Sortino (annualised, risk-free rate assumed 0)
    MIN_STD = 1e-10
    if trading_returns and len(trading_returns) > 1:
        n = len(trading_returns)
        mean_r = sum(trading_returns) / n
        variance = sum((r - mean_r) ** 2 for r in trading_returns) / (n - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        if std_r > MIN_STD:
            m.sharpe_ratio = max(-10.0, min(10.0, mean_r / std_r * math.sqrt(252)))

        downside = [r for r in trading_returns if r < 0]
        if len(downside) > 1:
            d_mean = sum(downside) / len(downside)
            d_var = sum((r - d_mean) ** 2 for r in downside) / (len(downside) - 1)
            d_std = math.sqrt(d_var) if d_var > 0 else 0.0
            if d_std > MIN_STD:
                m.sortino_ratio = max(-10.0, min(10.0, mean_r / d_std * math.sqrt(252)))

    m.daily_returns = trading_returns

    return m


def compute_composite_score(m: TournamentMetrics) -> float:
    """Compute transparent composite score.

    Formula (documented):
    - Return: 25% weight (raw return_pct)
    - Sharpe: 20% weight (raw sharpe_ratio, clamped to [-10,10])
    - Sortino: 20% weight (raw sortino_ratio, clamped to [-10,10])
    - Win Rate: 10% weight (raw win_rate 0-1)
    - Drawdown: 15% weight (penalized: 1 - max_drawdown, so lower DD = higher score)
    - Profit Factor: 10% weight (capped at 5.0, normalized to 0-1)

    Score range: approximately -5 to +3 (higher is better).
    Drawdown is penalized: a 0% drawdown gives full 0.15 points,
    a 15% drawdown gives 0 points.
    """
    pf = min(m.profit_factor, 5.0)
    score = (
        m.return_pct * 0.25
        + m.sharpe_ratio * 0.20
        + m.sortino_ratio * 0.20
        + m.win_rate * 0.10
        + (1.0 - m.max_drawdown) * 0.15
        + (pf / 5.0) * 0.10
    )
    return round(score, 6)


def assign_awards(participants: List[TournamentMetrics]) -> List[TournamentMetrics]:
    """Assign special awards to participants.

    Awards:
    - Highest Return
    - Lowest Drawdown
    - Best Sharpe
    - Highest Win Rate
    - Best Risk-Adjusted (composite score)
    """
    if not participants:
        return participants

    # Find winners for each category
    highest_return = max(participants, key=lambda p: p.return_pct)
    lowest_dd = min(participants, key=lambda p: p.max_drawdown)
    best_sharpe = max(participants, key=lambda p: p.sharpe_ratio)
    best_winrate = max(participants, key=lambda p: p.win_rate)
    best_risk_adj = max(participants, key=lambda p: p.composite_score)

    # Clear existing awards
    for p in participants:
        p.awards = []

    # Assign awards (handle ties by awarding all tied)
    for p in participants:
        if p.return_pct == highest_return.return_pct:
            p.awards.append("Highest Return")
        if p.max_drawdown == lowest_dd.max_drawdown:
            p.awards.append("Lowest Drawdown")
        if p.sharpe_ratio == best_sharpe.sharpe_ratio:
            p.awards.append("Best Sharpe")
        if p.win_rate == best_winrate.win_rate:
            p.awards.append("Highest Win Rate")
        if p.composite_score == best_risk_adj.composite_score:
            p.awards.append("Best Risk-Adjusted")

    return participants
