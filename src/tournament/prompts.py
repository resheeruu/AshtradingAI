"""Standardized AI prompts for fair tournament execution."""
import json
from typing import Dict, List, Optional
from src.ai.base import MarketContext


SYSTEM_PROMPT = """You are a quantitative trading AI participating in a tournament.
You must respond ONLY with a JSON object. No markdown, no explanation outside JSON.

Response format:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation of your reasoning",
  "suggested_position_size": 0.0 to 0.25,
  "stop_loss": price level or null,
  "take_profit": price level or null
}

Rules:
- decision must be exactly BUY, SELL, or HOLD
- confidence must be between 0.0 and 1.0
- suggested_position_size is fraction of portfolio (max 0.25 = 25%)
- stop_loss and take_profit are absolute price levels
- You may only use information provided below. You have NO access to future data.
- Respond with valid JSON only."""


def build_tournament_prompt(context: MarketContext, risk_limits: Optional[Dict] = None) -> str:
    """Build a standardized prompt that gives the AI only information available at candle N.

    This enforces the no-lookahead rule: the AI receives:
    - Current candle OHLCV
    - Historical candles up to and including current
    - Current indicators (computed from historical data only)
    - Portfolio state (balance, positions)
    - Risk limits

    The AI does NOT receive:
    - Future candles
    - Future prices
    - Other AIs' decisions
    - Other AIs' portfolio states
    """
    recent_candles = context.candles[-20:] if len(context.candles) > 20 else context.candles

    # Build candle summary (OHLCV only, no future data)
    candle_data = []
    for c in recent_candles:
        candle_data.append({
            "t": c.get("timestamp", ""),
            "o": c.get("open", 0),
            "h": c.get("high", 0),
            "l": c.get("low", 0),
            "c": c.get("close", 0),
            "v": c.get("volume", 0),
        })

    # Current candle is the last one
    current = candle_data[-1] if candle_data else {}

    # Indicators (already computed from historical data only)
    indicators = context.indicators if context.indicators else {}

    # Portfolio state
    positions_str = ", ".join(context.open_positions) if context.open_positions else "none"

    # Risk limits summary
    risk_str = ""
    if risk_limits:
        risk_str = f"""
Risk Limits:
- Max Position Size: {risk_limits.get('max_position_size', 0.10):.0%} of portfolio
- Max Open Positions: {risk_limits.get('max_open_positions', 3)}
- Max Daily Loss: {risk_limits.get('max_daily_loss', 0.03):.0%}
- Max Drawdown: {risk_limits.get('max_drawdown', 0.15):.0%}
- Min Confidence: {risk_limits.get('min_confidence', 0.60):.0%}"""

    return f"""=== MARKET DATA ===
Symbol: {context.symbol}
Timeframe: {context.timeframe}
Timestamp: {context.timestamp}

=== CURRENT CANDLE (most recent) ===
Open: {current.get('o', 'N/A')}
High: {current.get('h', 'N/A')}
Low: {current.get('l', 'N/A')}
Close: {current.get('c', 'N/A')}
Volume: {current.get('v', 'N/A')}

=== RECENT CANDLES (last {len(candle_data)}) ===
{json.dumps(candle_data[-10:], indent=1)}

=== TECHNICAL INDICATORS (current values) ===
{json.dumps(indicators, indent=1) if indicators else "No indicators available"}

=== PORTFOLIO STATE ===
Balance: ${context.portfolio_balance:.2f}
Open Positions: {positions_str}
Symbol: {context.symbol}
{risk_str}

=== YOUR TASK ===
Based ONLY on the data above, provide your trading decision as JSON.
You have no access to future candles, other AIs' decisions, or any other information."""


def build_risk_limits_dict(
    max_position_size: float = 0.10,
    max_open_positions: int = 3,
    max_daily_loss: float = 0.03,
    max_drawdown: float = 0.15,
    min_confidence: float = 0.60,
) -> Dict:
    """Build risk limits dict for prompt inclusion."""
    return {
        "max_position_size": max_position_size,
        "max_open_positions": max_open_positions,
        "max_daily_loss": max_daily_loss,
        "max_drawdown": max_drawdown,
        "min_confidence": min_confidence,
    }
