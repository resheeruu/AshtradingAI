"""AI manager for running multiple AIs in parallel with isolated portfolios."""
import logging
import math
from typing import Dict, List, Optional

from src.ai.base import TradingAI, MarketContext
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.trading.engine import TradingEngine
from src.backtest.engine import BacktestEngine, BacktestMetrics

logger = logging.getLogger(__name__)


class AICompetitionEntry:
    """Holds data for one AI in a competition."""

    def __init__(self, ai: TradingAI, portfolio: Portfolio, engine: TradingEngine):
        self.ai = ai
        self.portfolio = portfolio
        self.engine = engine
        self.metrics: Optional[BacktestMetrics] = None


class AIManager:
    """Manages multiple AIs with completely isolated portfolios."""

    def __init__(
        self,
        starting_balance: float = 1000.0,
        fee: float = 0.001,
        slippage: float = 0.0005,
        max_position_size: float = 0.10,
        max_open_positions: int = 3,
        max_daily_loss: float = 0.03,
        max_drawdown: float = 0.15,
        min_confidence: float = 0.60,
    ):
        self.starting_balance = starting_balance
        self.fee = fee
        self.slippage = slippage
        self.entries: List[AICompetitionEntry] = []
        self._risk_manager = RiskManager(
            max_position_size=max_position_size,
            max_open_positions=max_open_positions,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            min_confidence=min_confidence,
        )

    def register_ai(self, ai: TradingAI) -> None:
        portfolio = Portfolio(ai_id=ai.ai_id, starting_balance=self.starting_balance)
        broker = PaperBroker(fee=self.fee, slippage=self.slippage)
        engine = TradingEngine(portfolio=portfolio, risk_manager=self._risk_manager, broker=broker)
        self.entries.append(AICompetitionEntry(ai=ai, portfolio=portfolio, engine=engine))
        logger.info("Registered AI: %s (%s)", ai.ai_id, ai.model)

    def run_competition(
        self,
        data: Dict[str, List[dict]],
        timeframe: str = "1h",
    ) -> List[dict]:
        """Backtest all registered AIs and return ranked results."""
        results = []
        for entry in self.entries:
            bt = BacktestEngine(
                starting_balance=self.starting_balance,
                fee=self.fee,
                slippage=self.slippage,
            )
            metrics, portfolio = bt.run(entry.ai, data, timeframe)
            entry.metrics = metrics
            entry.portfolio = portfolio
            results.append({
                "ai_id": entry.ai.ai_id,
                "model": entry.ai.model,
                "metrics": metrics.summary(),
            })

        for r in results:
            r["composite_score"] = self._composite_score(r["metrics"])

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def _composite_score(self, m: dict) -> float:
        return_pct = m.get("return_pct", 0.0)
        max_dd = m.get("max_drawdown", 0.0)
        sharpe = m.get("sharpe_ratio", 0.0)
        sortino = m.get("sortino_ratio", 0.0)
        win_rate = m.get("win_rate", 0.0)
        pf = min(m.get("profit_factor", 0.0), 5.0)
        score = (
            return_pct * 0.25
            + sharpe * 0.20
            + sortino * 0.20
            + win_rate * 0.10
            + (1.0 - max_dd) * 0.15
            + (pf / 5.0) * 0.10
        )
        return round(score, 6)

    def get_leaderboard(self) -> str:
        lines = [
            f"{'AI':<20} {'Balance':>10} {'Return':>10} {'WinRate':>10} {'MaxDD':>10} {'Sharpe':>10} {'Score':>10}",
            "-" * 90,
        ]
        for entry in self.entries:
            if entry.metrics is None:
                continue
            m = entry.metrics.summary()
            score = self._composite_score(m)
            lines.append(
                f"{entry.ai.ai_id:<20} "
                f"${m['ending_balance']:>9,.2f} "
                f"{m['return_pct']:>9.2%} "
                f"{m['win_rate']:>9.2%} "
                f"{m['max_drawdown']:>9.2%} "
                f"{m['sharpe_ratio']:>10.4f} "
                f"{score:>10.6f}"
            )
        return "\n".join(lines)
