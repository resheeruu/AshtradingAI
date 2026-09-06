"""Experiment management — reproducible experiment records.

Every backtest/tournament produces an experiment record containing:
- experiment ID, timestamp, git commit/version
- symbol, timeframe, data source, start/end period
- strategy config, risk config, execution assumptions
- AI participants, regime config, random seed
- metrics, robustness metrics

The experiment must be reproducible from its recorded configuration.
Never stores secrets.
"""
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


def _get_git_commit() -> str:
    """Get current git commit hash. Returns 'unknown' if not in a git repo."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@dataclass
class ExecutionAssumptions:
    """Realistic execution assumptions for an experiment."""
    fee: float = 0.001
    slippage: float = 0.0005
    spread: float = 0.0001
    fill_model: str = "full"  # "full", "partial", "reject"

    def summary(self) -> dict:
        return {
            "fee": self.fee,
            "slippage": self.slippage,
            "spread": self.spread,
            "fill_model": self.fill_model,
        }


@dataclass
class ExperimentConfig:
    """Complete experiment configuration for reproducibility."""
    experiment_id: str = ""
    timestamp: str = ""
    git_commit: str = ""
    symbol: str = ""
    timeframe: str = ""
    data_source: str = ""
    candle_count: int = 0
    start_period: str = ""
    end_period: str = ""
    starting_balance: float = 0.0

    # Strategy config
    strategy_name: str = ""
    strategy_config: Dict[str, Any] = field(default_factory=dict)

    # Risk config
    risk_percent: float = 0.01
    max_position_size: float = 0.10
    max_open_positions: int = 3
    max_daily_loss: float = 0.03
    max_drawdown: float = 0.15
    min_confidence: float = 0.60

    # Execution
    execution: ExecutionAssumptions = field(default_factory=ExecutionAssumptions)

    # AI participants
    ai_participants: List[str] = field(default_factory=list)

    # Regime
    regime_config: Dict[str, Any] = field(default_factory=dict)

    # Random seed
    seed: int = 42

    def __post_init__(self):
        if not self.experiment_id:
            self.experiment_id = str(uuid.uuid4())[:8]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.git_commit:
            self.git_commit = _get_git_commit()

    def to_dict(self) -> dict:
        d = {
            "experiment_id": self.experiment_id,
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "data_source": self.data_source,
            "candle_count": self.candle_count,
            "start_period": self.start_period,
            "end_period": self.end_period,
            "starting_balance": self.starting_balance,
            "strategy_name": self.strategy_name,
            "strategy_config": self.strategy_config,
            "risk_percent": self.risk_percent,
            "max_position_size": self.max_position_size,
            "max_open_positions": self.max_open_positions,
            "max_daily_loss": self.max_daily_loss,
            "max_drawdown": self.max_drawdown,
            "min_confidence": self.min_confidence,
            "execution": self.execution.summary(),
            "ai_participants": self.ai_participants,
            "regime_config": self.regime_config,
            "seed": self.seed,
        }
        return d

    def config_hash(self) -> str:
        """Hash of configuration for deduplication."""
        content = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ExperimentResult:
    """Results from a completed experiment."""
    config: ExperimentConfig = field(default_factory=ExperimentConfig)
    metrics: Dict[str, Any] = field(default_factory=dict)
    robustness: Dict[str, Any] = field(default_factory=dict)
    regime_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "metrics": self.metrics,
            "robustness": self.robustness,
            "regime_history_summary": {
                "total_candles": len(self.regime_history),
                "regime_counts": _count_regimes(self.regime_history),
            },
        }


def _count_regimes(history: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in history:
        r = entry.get("regime", "UNKNOWN")
        counts[r] = counts.get(r, 0) + 1
    return counts


def create_experiment(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    data_source: str = "synthetic",
    candle_count: int = 500,
    starting_balance: float = 1000.0,
    strategy_name: str = "m7",
    seed: int = 42,
    **kwargs,
) -> ExperimentConfig:
    """Factory to create an experiment config with sensible defaults."""
    return ExperimentConfig(
        symbol=symbol,
        timeframe=timeframe,
        data_source=data_source,
        candle_count=candle_count,
        starting_balance=starting_balance,
        strategy_name=strategy_name,
        seed=seed,
        **kwargs,
    )
