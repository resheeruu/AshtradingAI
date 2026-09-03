"""Deterministic test strategy for validation (no API key required)."""
from typing import Dict, Any, List

from src.ai.base import TradingAI, MarketContext
from src.indicators.technical import rsi as compute_rsi


class TestStrategy(TradingAI):
    """Simple RSI-based strategy for testing without API credentials."""

    def __init__(self, ai_id: str = "test-strategy"):
        super().__init__(ai_id=ai_id, model="deterministic-rsi")

    def decide(self, context: MarketContext) -> Dict[str, Any]:
        candles = context.candles
        if len(candles) < 15:
            return {"decision": "HOLD", "confidence": 0.0, "reason": "insufficient_data"}

        close = [c["close"] for c in candles]
        rsi_vals = compute_rsi(close, 14)
        current_rsi = 50.0
        for v in reversed(rsi_vals):
            if v is not None:
                current_rsi = v
                break

        has_position = context.symbol in context.open_positions

        if current_rsi < 30 and not has_position:
            size = (context.portfolio_balance * 0.10) / context.current_price if context.current_price > 0 else 0
            return {
                "decision": "BUY",
                "confidence": 0.75,
                "reason": f"RSI oversold ({current_rsi:.1f})",
                "suggested_position_size": size,
                "stop_loss": context.current_price * 0.97,
                "take_profit": context.current_price * 1.05,
            }
        elif current_rsi > 70 and has_position:
            return {
                "decision": "SELL",
                "confidence": 0.70,
                "reason": f"RSI overbought ({current_rsi:.1f})",
            }
        return {"decision": "HOLD", "confidence": 0.5, "reason": f"RSI neutral ({current_rsi:.1f})"}
