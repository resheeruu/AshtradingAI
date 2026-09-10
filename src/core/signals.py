"""Standardized signal types for the strategy-AI-risk pipeline.

Strategies produce Signals. Signals are validated by AI. Risk gates decide.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from src.core.enums import SignalDirection, Timeframe


@dataclass
class Signal:
    """Unified signal produced by strategies and consumed by AI/Risk."""
    symbol: str
    timeframe: str
    timestamp: str
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    confidence: float
    entry: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    strategy_id: str = ""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    features: Dict[str, Any] = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)
    regime: Optional[str] = None
    asset_class: Optional[str] = None

    def __post_init__(self):
        if self.direction not in ("LONG", "SHORT", "NEUTRAL"):
            self.direction = "NEUTRAL"
        if self.confidence < 0:
            self.confidence = 0.0
        if self.confidence > 1.0:
            self.confidence = 1.0
        if self.stop_loss is not None and self.entry > 0 and self.stop_loss > 0:
            sl_dist = abs(self.entry - self.stop_loss)
            if self.take_profit is not None and self.take_profit > 0:
                tp_dist = abs(self.take_profit - self.entry)
                if sl_dist > 0:
                    self.risk_reward = round(tp_dist / sl_dist, 2)

    @property
    def is_actionable(self) -> bool:
        return self.direction in ("LONG", "SHORT") and self.confidence > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "strategy_id": self.strategy_id,
            "features": self.features,
            "reasoning": self.reasoning,
            "regime": self.regime,
            "asset_class": self.asset_class,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Signal":
        return cls(
            symbol=d.get("symbol", ""),
            timeframe=d.get("timeframe", ""),
            timestamp=d.get("timestamp", ""),
            direction=d.get("direction", "NEUTRAL"),
            confidence=d.get("confidence", 0.0),
            entry=d.get("entry", 0.0),
            stop_loss=d.get("stop_loss"),
            take_profit=d.get("take_profit"),
            risk_reward=d.get("risk_reward"),
            strategy_id=d.get("strategy_id", ""),
            signal_id=d.get("signal_id", str(uuid.uuid4())[:12]),
            features=d.get("features", {}),
            reasoning=d.get("reasoning", []),
            regime=d.get("regime"),
            asset_class=d.get("asset_class"),
        )


@dataclass
class AIDecision:
    """Structured AI output validated before entering RiskManager."""
    signal_id: str
    symbol: str
    decision: str  # "LONG", "SHORT", "HOLD"
    confidence: float
    reasoning: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    invalidated: bool = False
    ai_provider: str = ""
    ai_model: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_valid(self) -> bool:
        return (
            not self.invalidated
            and self.decision in ("LONG", "SHORT", "HOLD")
            and 0.0 <= self.confidence <= 1.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "risk_flags": self.risk_flags,
            "invalidated": self.invalidated,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "timestamp": self.timestamp,
        }


@dataclass
class TradeJournalEntry:
    """Complete audit trail for every trade decision."""
    trade_id: str
    signal: Optional[Signal] = None
    ai_decision: Optional[AIDecision] = None
    strategy_id: str = ""
    market_state: Dict[str, Any] = field(default_factory=dict)
    risk_checks: List[Dict[str, Any]] = field(default_factory=list)
    risk_rejection: Optional[str] = None
    approved: bool = False
    execution: Optional[Dict[str, Any]] = None
    fill_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    fees: float = 0.0
    slippage: float = 0.0
    exit_reason: str = ""
    mistake_tags: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "signal": self.signal.to_dict() if self.signal else None,
            "ai_decision": self.ai_decision.to_dict() if self.ai_decision else None,
            "strategy_id": self.strategy_id,
            "market_state": self.market_state,
            "risk_checks": self.risk_checks,
            "risk_rejection": self.risk_rejection,
            "approved": self.approved,
            "execution": self.execution,
            "fill_price": self.fill_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "fees": self.fees,
            "slippage": self.slippage,
            "exit_reason": self.exit_reason,
            "mistake_tags": self.mistake_tags,
            "timestamp": self.timestamp,
        }


@dataclass
class RiskBlock:
    """Record of a rejected trade for audit."""
    trade_id: str
    reason: str
    gate: str
    account_snapshot: Dict[str, Any] = field(default_factory=dict)
    signal_snapshot: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
