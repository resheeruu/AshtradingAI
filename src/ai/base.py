"""Base interface for all trading AIs."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MarketContext:
    """Standardised market context passed to every AI."""
    symbol: str
    timeframe: str
    current_price: float
    candles: List[Dict]  # list of candle dicts
    indicators: Dict[str, List] = field(default_factory=dict)
    portfolio_balance: float = 0.0
    open_positions: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class AIDecision:
    """Validated AI decision output."""
    decision: str  # BUY, SELL, HOLD
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    suggested_position_size: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class TradingAI(ABC):
    """Abstract base for trading AI providers."""

    def __init__(self, ai_id: str, model: str = ""):
        self.ai_id = ai_id
        self.model = model

    @abstractmethod
    def decide(self, context: MarketContext) -> Dict[str, Any]:
        """Return a decision dict with keys: decision, confidence, reason, ..."""
        ...

    def validate_decision(self, raw: Dict[str, Any]) -> AIDecision:
        """Validate and normalise a raw AI response."""
        decision = str(raw.get("decision", "HOLD")).upper()
        if decision not in ("BUY", "SELL", "HOLD"):
            decision = "HOLD"
        confidence = float(raw.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        return AIDecision(
            decision=decision,
            confidence=confidence,
            reason=str(raw.get("reason", "")),
            suggested_position_size=raw.get("suggested_position_size"),
            stop_loss=raw.get("stop_loss"),
            take_profit=raw.get("take_profit"),
        )
