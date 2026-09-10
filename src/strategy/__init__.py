"""Multi-strategy trading engine.

Provides strategy implementations, regime detection, AI selection,
scoring, and leaderboard functionality.
"""
from src.strategy.spec import (
    BaseStrategy,
    StrategySpec,
    EMATrendStrategy,
    RSIMeanReversion,
    MACDCrossover,
    BollingerBreakout,
    AIScalpingStrategy,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
    MomentumStrategy,
    PriceActionStrategy,
    VWAPStrategy,
    MultiTimeframeStrategy,
    SMCStrategy,
    AICompositeStrategy,
    get_default_strategies,
)
from src.strategy.regime_detector import MarketRegimeDetector, MarketRegime
from src.strategy.ai_selector import AIStrategySelector, StrategySelection
from src.strategy.scoring import StrategyScorer, StrategyScore

__all__ = [
    "BaseStrategy",
    "StrategySpec",
    "EMATrendStrategy",
    "RSIMeanReversion",
    "MACDCrossover",
    "BollingerBreakout",
    "AIScalpingStrategy",
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "MomentumStrategy",
    "PriceActionStrategy",
    "VWAPStrategy",
    "MultiTimeframeStrategy",
    "SMCStrategy",
    "AICompositeStrategy",
    "get_default_strategies",
    "MarketRegimeDetector",
    "MarketRegime",
    "AIStrategySelector",
    "StrategySelection",
    "StrategyScorer",
    "StrategyScore",
]
