"""Robustness lab — research layer around M7BacktestEngine.

Provides:
- Rolling walk-forward validation
- Parameter sensitivity analysis
- Monte Carlo robustness (trade reshuffling)
- Deflated Sharpe / overfitting awareness
- Robustness score

Does NOT modify core trading logic. Analysis only.
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable

from src.backtest.m7_backtest import M7BacktestEngine, M7BacktestMetrics
from src.ai.base import TradingAI
from src.portfolio.portfolio import Portfolio


@dataclass
class WalkForwardWindow:
    """A single walk-forward window result."""
    window_id: int
    in_sample_start: int
    in_sample_end: int
    out_sample_start: int
    out_sample_end: int
    in_sample_return: float
    out_sample_return: float
    in_sample_max_dd: float
    out_sample_max_dd: float
    in_sample_trades: int
    out_sample_trades: int


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward validation result."""
    windows: List[WalkForwardWindow] = field(default_factory=list)
    oos_returns: List[float] = field(default_factory=list)
    is_returns: List[float] = field(default_factory=list)

    @property
    def num_windows(self) -> int:
        return len(self.windows)

    @property
    def mean_oos_return(self) -> float:
        return sum(self.oos_returns) / len(self.oos_returns) if self.oos_returns else 0.0

    @property
    def oos_positive_pct(self) -> float:
        if not self.oos_returns:
            return 0.0
        return sum(1 for r in self.oos_returns if r > 0) / len(self.oos_returns)

    def summary(self) -> dict:
        return {
            "num_windows": self.num_windows,
            "mean_oos_return": round(self.mean_oos_return, 6),
            "oos_positive_pct": round(self.oos_positive_pct, 4),
            "mean_is_return": round(sum(self.is_returns) / len(self.is_returns), 6) if self.is_returns else 0.0,
            "windows": [
                {
                    "id": w.window_id,
                    "is_return": round(w.in_sample_return, 6),
                    "oos_return": round(w.out_sample_return, 6),
                    "is_dd": round(w.in_sample_max_dd, 6),
                    "oos_dd": round(w.out_sample_max_dd, 6),
                }
                for w in self.windows
            ],
        }


@dataclass
class SensitivityResult:
    """Parameter sensitivity analysis result."""
    param_name: str
    base_value: float
    tested_values: List[float] = field(default_factory=list)
    returns: List[float] = field(default_factory=list)
    drawdowns: List[float] = field(default_factory=list)
    trade_counts: List[int] = field(default_factory=list)

    @property
    def return_std(self) -> float:
        if len(self.returns) < 2:
            return 0.0
        mean = sum(self.returns) / len(self.returns)
        return math.sqrt(sum((r - mean) ** 2 for r in self.returns) / (len(self.returns) - 1))

    @property
    def stable(self) -> bool:
        """Returns are stable if std < 50% of mean absolute return."""
        if not self.returns:
            return False
        mean_abs = sum(abs(r) for r in self.returns) / len(self.returns)
        return self.return_std < mean_abs * 0.5 if mean_abs > 0 else True

    def summary(self) -> dict:
        return {
            "param": self.param_name,
            "base_value": self.base_value,
            "tested_values": self.tested_values,
            "returns": [round(r, 6) for r in self.returns],
            "return_std": round(self.return_std, 6),
            "stable": self.stable,
        }


@dataclass
class MonteCarloResult:
    """Monte Carlo robustness analysis result."""
    n_simulations: int = 0
    median_return: float = 0.0
    percentile_5_return: float = 0.0
    percentile_25_return: float = 0.0
    percentile_75_return: float = 0.0
    percentile_95_return: float = 0.0
    probability_of_loss: float = 0.0
    worst_drawdown: float = 0.0
    median_drawdown: float = 0.0
    mean_return: float = 0.0

    def summary(self) -> dict:
        return {
            "n_simulations": self.n_simulations,
            "median_return": round(self.median_return, 6),
            "percentile_5_return": round(self.percentile_5_return, 6),
            "percentile_95_return": round(self.percentile_95_return, 6),
            "probability_of_loss": round(self.probability_of_loss, 4),
            "worst_drawdown": round(self.worst_drawdown, 6),
            "median_drawdown": round(self.median_drawdown, 6),
            "mean_return": round(self.mean_return, 6),
        }


@dataclass
class RobustnessReport:
    """Complete robustness analysis report."""
    walk_forward: WalkForwardResult = field(default_factory=WalkForwardResult)
    sensitivity: List[SensitivityResult] = field(default_factory=list)
    monte_carlo: MonteCarloResult = field(default_factory=MonteCarloResult)
    deflated_sharpe: Optional[float] = None
    deflated_sharpe_note: str = ""
    robustness_score: float = 0.0

    def summary(self) -> dict:
        return {
            "walk_forward": self.walk_forward.summary(),
            "sensitivity": [s.summary() for s in self.sensitivity],
            "monte_carlo": self.monte_carlo.summary(),
            "deflated_sharpe": self.deflated_sharpe,
            "deflated_sharpe_note": self.deflated_sharpe_note,
            "robustness_score": round(self.robustness_score, 4),
        }


class RobustnessLab:
    """Research layer for robustness analysis.

    Wraps M7BacktestEngine without modifying it.
    All analysis is deterministic when given the same seed.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def rolling_walk_forward(
        self,
        ai: TradingAI,
        data: Dict[str, List[dict]],
        timeframe: str = "1h",
        train_pct: float = 0.6,
        test_pct: float = 0.2,
        step_pct: float = 0.1,
        **engine_kwargs,
    ) -> WalkForwardResult:
        """Rolling walk-forward with configurable train/test/step sizes.

        Creates overlapping windows. Each window trains on train_pct,
        validates on test_pct, stepping forward by step_pct.
        No state leaks between windows (fresh engine each time).
        """
        result = WalkForwardResult()

        # Determine total candles per symbol
        total = min(len(candles) for candles in data.values()) if data else 0
        if total < 20:
            return result

        train_size = int(total * train_pct)
        test_size = int(total * test_pct)
        step_size = max(1, int(total * step_pct))

        if train_size + test_size > total:
            return result

        window_id = 0
        start = 0
        while start + train_size + test_size <= total:
            train_end = start + train_size
            test_end = train_end + test_size

            is_data = {sym: candles[start:train_end] for sym, candles in data.items()}
            oos_data = {sym: candles[train_end:test_end] for sym, candles in data.items()}

            # Fresh engine per window — no state leak
            is_engine = M7BacktestEngine(**engine_kwargs)
            oos_engine = M7BacktestEngine(**engine_kwargs)

            is_metrics, _ = is_engine.run(ai, is_data, timeframe)
            oos_metrics, _ = oos_engine.run(ai, oos_data, timeframe)

            window = WalkForwardWindow(
                window_id=window_id,
                in_sample_start=start,
                in_sample_end=train_end,
                out_sample_start=train_end,
                out_sample_end=test_end,
                in_sample_return=is_metrics.standard.return_pct,
                out_sample_return=oos_metrics.standard.return_pct,
                in_sample_max_dd=is_metrics.standard.max_drawdown,
                out_sample_max_dd=oos_metrics.standard.max_drawdown,
                in_sample_trades=is_metrics.standard.num_trades,
                out_sample_trades=oos_metrics.standard.num_trades,
            )
            result.windows.append(window)
            result.is_returns.append(window.in_sample_return)
            result.oos_returns.append(window.out_sample_return)

            start += step_size
            window_id += 1

        return result

    def parameter_sensitivity(
        self,
        ai: TradingAI,
        data: Dict[str, List[dict]],
        timeframe: str = "1h",
        param_name: str = "risk_percent",
        base_value: float = 0.01,
        test_values: Optional[List[float]] = None,
        **engine_kwargs,
    ) -> SensitivityResult:
        """Test sensitivity to a single parameter variation.

        Runs backtest for each test value, reports return stability.
        Does NOT optimize — just measures sensitivity.
        """
        if test_values is None:
            # Default: vary ±50% around base
            test_values = [base_value * m for m in [0.5, 0.75, 1.0, 1.25, 1.5]]

        result = SensitivityResult(param_name=param_name, base_value=base_value)

        for val in test_values:
            kwargs = dict(engine_kwargs)
            kwargs[param_name] = val
            engine = M7BacktestEngine(**kwargs)
            metrics, _ = engine.run(ai, data, timeframe)

            result.tested_values.append(val)
            result.returns.append(metrics.standard.return_pct)
            result.drawdowns.append(metrics.standard.max_drawdown)
            result.trade_counts.append(metrics.standard.num_trades)

        return result

    def monte_carlo(
        self,
        trades: List,
        starting_balance: float = 1000.0,
        n_simulations: int = 1000,
        seed: Optional[int] = None,
    ) -> MonteCarloResult:
        """Monte Carlo analysis by reshuffling trade results.

        Reshuffles trade P&L sequences to estimate outcome distribution.
        Reports percentiles, loss probability, and drawdown distribution.

        WARNING: This is NOT a prediction. It measures robustness of
        the existing trade distribution.
        """
        if not trades or len(trades) < 5:
            return MonteCarloResult(n_simulations=0)

        rng = random.Random(seed if seed is not None else self.seed)
        pnls = [t.pnl for t in trades]

        simulated_returns = []
        simulated_drawdowns = []

        for _ in range(n_simulations):
            shuffled = list(pnls)
            rng.shuffle(shuffled)

            balance = starting_balance
            peak = starting_balance
            max_dd = 0.0
            for pnl in shuffled:
                balance += pnl
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

            ret = (balance - starting_balance) / starting_balance if starting_balance > 0 else 0
            simulated_returns.append(ret)
            simulated_drawdowns.append(max_dd)

        sorted_returns = sorted(simulated_returns)
        sorted_drawdowns = sorted(simulated_drawdowns)
        n = len(sorted_returns)

        result = MonteCarloResult(
            n_simulations=n_simulations,
            median_return=sorted_returns[n // 2],
            percentile_5_return=sorted_returns[int(n * 0.05)],
            percentile_25_return=sorted_returns[int(n * 0.25)],
            percentile_75_return=sorted_returns[int(n * 0.75)],
            percentile_95_return=sorted_returns[int(n * 0.95)],
            probability_of_loss=sum(1 for r in sorted_returns if r < 0) / n,
            worst_drawdown=max(simulated_drawdowns),
            median_drawdown=sorted_drawdowns[n // 2],
            mean_return=sum(simulated_returns) / n,
        )
        return result

    def compute_deflated_sharpe(
        self,
        sharpe_ratio: float,
        n_trials: int,
        n_observations: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
    ) -> Tuple[Optional[float], str]:
        """Compute deflated Sharpe ratio.

        Adjusts for multiple testing. Returns (deflated_sharpe, note).
        If sample is insufficient, returns (None, "INSUFFICIENT_SAMPLE").
        """
        if n_observations < 30:
            return None, "INSUFFICIENT_SAMPLE: need >= 30 observations"
        if n_trials < 1:
            return None, "INSUFFICIENT_SAMPLE: need >= 1 trial"

        # Bailey & Lopez de Prado (2014) deflated Sharpe
        # E[max(SR)] under null hypothesis
        euler_mascheroni = 0.5772156649
        e_max_sr = (1 - euler_mascheroni) * math.log(n_trials) + euler_mascheroni

        # Standard error of Sharpe
        sr_std = math.sqrt((1 + 0.5 * sharpe_ratio**2 - skewness * sharpe_ratio +
                           (kurtosis - 3) / 4 * sharpe_ratio**2) / (n_observations - 1))

        if sr_std <= 0:
            return sharpe_ratio, "computational_limit"

        # Deflated Sharpe = probability that true Sharpe > 0
        z = (sharpe_ratio - e_max_sr) / sr_std
        # Approximate normal CDF
        deflated = _normal_cdf(z)

        return deflated, f"deflated_sharpe_probability (n_trials={n_trials}, n_obs={n_observations})"

    def compute_robustness_score(
        self,
        walk_forward: WalkForwardResult,
        monte_carlo: MonteCarloResult,
        standard_metrics=None,
        n_trials: int = 1,
    ) -> float:
        """Compute transparent robustness score (0.0 - 1.0).

        Based on measurable factors:
        - Out-of-sample performance consistency
        - Drawdown severity
        - Trade count adequacy
        - Monte Carlo survival
        - Parameter stability

        Does NOT imply profitability certainty.
        """
        score = 0.0
        components = 0

        # 1. Walk-forward OOS consistency (0-25 points)
        if walk_forward.num_windows > 0:
            wf_score = walk_forward.oos_positive_pct * 0.25
            score += wf_score
            components += 1

        # 2. Drawdown severity (0-25 points)
        if standard_metrics and standard_metrics.max_drawdown > 0:
            dd_score = max(0, 0.25 * (1.0 - standard_metrics.max_drawdown))
            score += dd_score
            components += 1

        # 3. Trade count (0-20 points)
        if standard_metrics and standard_metrics.num_trades >= 10:
            trade_score = min(0.20, standard_metrics.num_trades / 100 * 0.20)
            score += trade_score
            components += 1

        # 4. Monte Carlo survival (0-20 points)
        if monte_carlo.n_simulations > 0:
            mc_score = 0.20 * (1.0 - monte_carlo.probability_of_loss)
            score += mc_score
            components += 1

        # 5. Deflated Sharpe awareness (0-10 points)
        if n_trials <= 1:
            score += 0.10  # No multiple testing penalty
            components += 1

        return score if components > 0 else 0.0


def _normal_cdf(x: float) -> float:
    """Approximate normal CDF using error function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
