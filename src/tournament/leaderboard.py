"""Tournament leaderboard with composite scoring and awards."""
from typing import List, Optional
from src.tournament.metrics import TournamentMetrics


def format_leaderboard(
    participants: List[TournamentMetrics],
    experiment_id: str = "",
    show_awards: bool = True,
) -> str:
    """Format a tournament leaderboard.

    Displays:
    - Rank, AI name, Return%, MaxDD%, Sharpe, Win Rate%, Profit Factor, Composite Score
    - Special awards for top performers
    """
    if not participants:
        return "No participants to display."

    lines = []

    if experiment_id:
        lines.append(f"Experiment: {experiment_id}")
        lines.append("")

    # Main table header
    header = (
        f"{'RANK':<5} {'AI':<22} {'RETURN':>9} {'DRAWDOWN':>10} "
        f"{'SHARPE':>8} {'WIN RATE':>10} {'PF':>7} {'SCORE':>9}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for rank, m in enumerate(participants, 1):
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor < 100 else "inf"
        line = (
            f"{rank:<5} {m.ai_id:<22} "
            f"{m.return_pct:>+8.1%} "
            f"{m.max_drawdown:>9.1%} "
            f"{m.sharpe_ratio:>8.2f} "
            f"{m.win_rate:>9.1%} "
            f"{pf_str:>7} "
            f"{m.composite_score:>9.4f}"
        )
        lines.append(line)

    lines.append("")

    # Awards section
    if show_awards:
        award_names = {
            "Highest Return": "HIGHEST RETURN",
            "Lowest Drawdown": "LOWEST DRAWDOWN",
            "Best Sharpe": "BEST SHARPE",
            "Highest Win Rate": "HIGHEST WIN RATE",
            "Best Risk-Adjusted": "BEST RISK-ADJUSTED",
        }

        lines.append("=== AWARDS ===")
        awarded = False
        for m in participants:
            if m.awards:
                awarded = True
                for award in m.awards:
                    display = award_names.get(award, award.upper())
                    lines.append(f"  {display}: {m.ai_id}")

        if not awarded:
            lines.append("  No awards (all participants identical)")

    # Detailed stats
    lines.append("")
    lines.append("=== DETAILED STATS ===")
    for rank, m in enumerate(participants, 1):
        lines.append(f"\n  #{rank} {m.ai_id}")
        lines.append(f"    Starting Balance: ${m.starting_balance:,.2f}")
        lines.append(f"    Ending Balance:   ${m.ending_balance:,.2f}")
        lines.append(f"    Net Profit:       ${m.net_profit:,.2f}")
        lines.append(f"    Return:           {m.return_pct:+.2%}")
        lines.append(f"    Trades:           {m.num_trades} (W:{m.winning_trades} L:{m.losing_trades})")
        lines.append(f"    Win Rate:         {m.win_rate:.1%}")
        lines.append(f"    Avg Win:          ${m.avg_win:,.2f}")
        lines.append(f"    Avg Loss:         ${m.avg_loss:,.2f}")
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor < 100 else "inf"
        lines.append(f"    Profit Factor:    {pf_str}")
        lines.append(f"    Max Drawdown:     {m.max_drawdown:.2%}")
        lines.append(f"    Sharpe Ratio:     {m.sharpe_ratio:.4f}")
        lines.append(f"    Sortino Ratio:    {m.sortino_ratio:.4f}")
        lines.append(f"    Fees Paid:        ${m.fees_paid:,.2f}")
        lines.append(f"    Total Slippage:   ${m.total_slippage:,.4f}")
        lines.append(f"    Largest Win:      ${m.largest_win:,.2f}")
        lines.append(f"    Largest Loss:     ${m.largest_loss:,.2f}")
        lines.append(f"    Losing Streak:    {m.longest_losing_streak}")
        if m.awards:
            lines.append(f"    Awards:           {', '.join(m.awards)}")

    # Composite score formula documentation
    lines.append("")
    lines.append("=== COMPOSITE SCORE FORMULA ===")
    lines.append("  Score = return_pct * 0.25")
    lines.append("        + sharpe_ratio * 0.20")
    lines.append("        + sortino_ratio * 0.20")
    lines.append("        + win_rate * 0.10")
    lines.append("        + (1 - max_drawdown) * 0.15")
    lines.append("        + min(profit_factor, 5) / 5 * 0.10")
    lines.append("  Higher score = better risk-adjusted performance")
    lines.append("  Drawdown is penalized (lower DD = higher score component)")

    return "\n".join(lines)


def format_leaderboard_compact(
    participants: List[TournamentMetrics],
    experiment_id: str = "",
) -> str:
    """Format a compact leaderboard for quick display."""
    if not participants:
        return "No participants."

    lines = []
    if experiment_id:
        lines.append(f"Experiment: {experiment_id}")

    header = f"{'#':<3} {'AI':<20} {'RETURN':>9} {'DD':>8} {'SHARPE':>8} {'WR':>7} {'SCORE':>9}"
    lines.append(header)
    lines.append("-" * len(header))

    for rank, m in enumerate(participants, 1):
        line = (
            f"{rank:<3} {m.ai_id:<20} "
            f"{m.return_pct:>+8.1%} "
            f"{m.max_drawdown:>7.1%} "
            f"{m.sharpe_ratio:>8.2f} "
            f"{m.win_rate:>6.1%} "
            f"{m.composite_score:>9.4f}"
        )
        lines.append(line)

    # Quick awards
    for m in participants:
        if m.awards:
            award_short = "/".join(a.split()[0] for a in m.awards)
            lines.append(f"  {m.ai_id}: {award_short}")

    return "\n".join(lines)
