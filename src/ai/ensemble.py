"""AI Ensemble — multiple AI opinions with safety boundaries.

AI NEVER bypasses RiskManager. Ensemble may calculate agreement/conflict scores
but final authority remains with the risk engine.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.signals import AIDecision

logger = logging.getLogger(__name__)


@dataclass
class EnsembleOpinion:
    provider: str
    decision: AIDecision
    weight: float = 1.0


@dataclass
class EnsembleResult:
    decision: str  # "LONG", "SHORT", "HOLD"
    confidence: float
    agreement_score: float
    conflict_score: float
    opinions: List[Dict[str, Any]] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    invalidated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "agreement_score": self.agreement_score,
            "conflict_score": self.conflict_score,
            "opinions": self.opinions,
            "reasoning": self.reasoning,
            "risk_flags": self.risk_flags,
            "invalidated": self.invalidated,
        }


class AIEnsemble:
    """Combines multiple AI opinions into a consensus decision.

    Safety rules:
    - AI NEVER bypasses RiskManager
    - AI NEVER changes safety flags
    - AI NEVER disables kill switch
    - AI NEVER modifies broker credentials
    """

    def __init__(self, min_agreement: float = 0.6, min_confidence: float = 0.5):
        self.min_agreement = min_agreement
        self.min_confidence = min_confidence
        self._opinions: List[EnsembleOpinion] = []

    def add_opinion(self, provider: str, decision: AIDecision, weight: float = 1.0) -> None:
        self._opinions.append(EnsembleOpinion(provider=provider, decision=decision, weight=weight))

    def clear(self) -> None:
        self._opinions.clear()

    def compute_consensus(self) -> EnsembleResult:
        if not self._opinions:
            return EnsembleResult(
                decision="HOLD", confidence=0.0,
                agreement_score=0.0, conflict_score=0.0,
                reasoning=["no_ai_opinions"],
            )

        valid = [o for o in self._opinions if o.decision.is_valid]
        if not valid:
            return EnsembleResult(
                decision="HOLD", confidence=0.0,
                agreement_score=0.0, conflict_score=1.0,
                reasoning=["all_ai_opinions_invalid"],
                invalidated=True,
            )

        votes = {"LONG": 0.0, "SHORT": 0.0, "HOLD": 0.0}
        total_weight = 0.0
        for o in valid:
            votes[o.decision.decision] = votes.get(o.decision.decision, 0) + o.weight
            total_weight += o.weight

        if total_weight <= 0:
            return EnsembleResult(
                decision="HOLD", confidence=0.0,
                agreement_score=0.0, conflict_score=1.0,
                reasoning=["zero_total_weight"],
            )

        for k in votes:
            votes[k] /= total_weight

        majority = max(votes, key=votes.get)
        agreement = votes[majority]
        others = [v for k, v in votes.items() if k != majority]
        conflict = max(others) if others else 0.0

        confidences = [o.decision.confidence * o.weight for o in valid]
        avg_confidence = sum(confidences) / total_weight if total_weight > 0 else 0.0

        all_reasoning = []
        all_risk_flags = []
        for o in valid:
            all_reasoning.extend(o.decision.reasoning)
            all_risk_flags.extend(o.decision.risk_flags)

        invalidated = agreement < self.min_agreement or avg_confidence < self.min_confidence

        return EnsembleResult(
            decision=majority if not invalidated else "HOLD",
            confidence=avg_confidence,
            agreement_score=agreement,
            conflict_score=conflict,
            opinions=[{"provider": o.provider, "decision": o.decision.decision,
                       "confidence": o.decision.confidence} for o in valid],
            reasoning=all_reasoning[:10],
            risk_flags=all_risk_flags[:10],
            invalidated=invalidated,
        )
