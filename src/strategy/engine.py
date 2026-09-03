"""Strategy engine placeholder — AIs provide their own logic."""
from src.ai.base import TradingAI, MarketContext


class StrategyEngine:
    """Coordinates strategy execution for a single AI."""

    def __init__(self, ai: TradingAI):
        self.ai = ai

    def evaluate(self, context: MarketContext) -> dict:
        """Delegate to the AI's decide method."""
        return self.ai.decide(context)
