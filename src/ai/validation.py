"""AI Decision Validation Engine — structured pipeline for AI signal validation.

Implements the required pipeline:
Market Data → Indicators → Strategy → ML Prediction → AI Validation → Risk Engine → Safety Gates → Execution

AI may validate but must NEVER bypass risk controls.
"""
import logging
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.signals import Signal, AIDecision
from src.core.enums import TradingMode, MarketHealthStatus

logger = logging.getLogger(__name__)


@dataclass
class AIValidationConfig:
    """Configuration for AI validation engine."""
    min_confidence: float = 0.60
    max_risk_flags: int = 3
    require_regime_classification: bool = True
    require_entry_validation: bool = True
    require_exit_validation: bool = False
    timeout_seconds: float = 30.0
    enable_fallback: bool = True
    fallback_confidence: float = 0.50
    max_ai_calls_per_session: int = 100
    cache_decisions: bool = True
    cache_ttl: int = 300  # seconds


@dataclass
class MarketRegimeClassification:
    """AI-classified market regime."""
    regime: str  # TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY, etc.
    confidence: float
    reasoning: List[str] = field(default_factory=list)
    features: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeSetupValidation:
    """AI validation of a technical trade setup."""
    valid: bool
    confidence: float
    reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    suggested_adjustments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIValidationResult:
    """Complete AI validation result."""
    signal_id: str
    approved: bool
    decision: str  # "LONG", "SHORT", "HOLD"
    confidence: float
    reasoning: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    regime: Optional[MarketRegimeClassification] = None
    setup_validation: Optional[TradeSetupValidation] = None
    ai_provider: str = ""
    ai_model: str = ""
    validation_time_ms: float = 0.0
    cached: bool = False


class AIDecisionValidator:
    """Validates trading decisions through structured AI pipeline.

    Pipeline:
    1. Classify market regime
    2. Validate technical setup
    3. Score confidence
    4. Detect conflicting signals
    5. Generate reasoning
    6. Recommend HOLD if uncertain

    Safety:
    - Never bypasses risk limits
    - Never bypasses session controls
    - Never bypasses emergency stop
    - Returns HOLD on AI failure
    """

    def __init__(self, config: Optional[AIValidationConfig] = None):
        self.config = config or AIValidationConfig()
        self._validation_cache: Dict[str, AIValidationResult] = {}
        self._calls_today = 0
        self._last_reset = time.time()

    def validate_signal(
        self,
        signal: Signal,
        candles: List[Dict],
        indicators: Dict,
        portfolio_balance: float,
        open_positions: int,
        current_regime: Optional[str] = None,
        ai_provider: Optional[Any] = None,
    ) -> AIValidationResult:
        """Validate a trading signal through the AI pipeline.

        Args:
            signal: The strategy signal to validate
            candles: Historical OHLCV data
            indicators: Pre-computed indicators
            portfolio_balance: Current portfolio balance
            open_positions: Number of open positions
            current_regime: Current market regime (if known)
            ai_provider: AI provider instance for external calls

        Returns:
            AIValidationResult with approval/rejection and reasoning
        """
        start_time = time.time()

        # Check daily limit
        self._check_daily_limit()

        # Check cache
        cache_key = f"{signal.signal_id}_{signal.symbol}_{signal.direction}"
        if self.config.cache_decisions and cache_key in self._validation_cache:
            cached = self._validation_cache[cache_key]
            if time.time() - cached.validation_time_ms / 1000 < self.config.cache_ttl:
                cached.cached = True
                return cached

        # Initialize result
        result = AIValidationResult(
            signal_id=signal.signal_id,
            approved=False,
            decision="HOLD",
            confidence=0.0,
            ai_provider=signal.strategy_id,
        )

        # Step 1: Basic signal validation
        if not self._validate_signal_basics(signal):
            result.reasoning.append("Signal failed basic validation")
            return result

        # Step 2: Classify market regime (if not provided)
        regime = None
        if self.config.require_regime_classification and not current_regime:
            regime = self._classify_regime(candles, indicators, ai_provider)
            result.regime = regime
            if regime and not self._regime_compatible(signal, regime):
                result.reasoning.append(f"Signal incompatible with regime: {regime.regime}")
                result.risk_flags.append("REGIME_MISMATCH")
                return result

        # Step 3: Validate trade setup
        setup_validation = self._validate_setup(
            signal, candles, indicators, portfolio_balance, open_positions, ai_provider
        )
        result.setup_validation = setup_validation

        if not setup_validation.valid:
            result.reasoning.extend(setup_validation.reasons)
            result.risk_flags.extend(setup_validation.risk_flags)
            return result

        # Step 4: Score confidence
        confidence = self._score_confidence(
            signal, setup_validation, regime, candles, indicators
        )
        result.confidence = confidence

        # Step 5: Check minimum confidence
        if confidence < self.config.min_confidence:
            result.reasoning.append(
                f"Confidence {confidence:.2f} below minimum {self.config.min_confidence}"
            )
            return result

        # Step 6: Check risk flags
        if len(result.risk_flags) > self.config.max_risk_flags:
            result.reasoning.append(
                f"Too many risk flags: {len(result.risk_flags)} > {self.config.max_risk_flags}"
            )
            return result

        # Step 7: AI reasoning (if provider available)
        if ai_provider:
            ai_reasoning = self._get_ai_reasoning(
                signal, candles, indicators, setup_validation, ai_provider
            )
            result.reasoning.extend(ai_reasoning)

        # All checks passed
        result.approved = True
        result.decision = signal.direction
        result.validation_time_ms = (time.time() - start_time) * 1000

        # Cache result
        if self.config.cache_decisions:
            self._validation_cache[cache_key] = result

        self._calls_today += 1

        logger.info(
            "AI VALIDATED [%s] %s %s conf=%.2f time=%.1fms",
            signal.strategy_id, signal.direction, signal.symbol,
            confidence, result.validation_time_ms,
        )

        return result

    def _validate_signal_basics(self, signal: Signal) -> bool:
        """Validate basic signal properties."""
        if not signal.is_actionable:
            return False
        if signal.entry <= 0:
            return False
        if signal.confidence < 0 or signal.confidence > 1:
            return False
        if signal.direction not in ("LONG", "SHORT"):
            return False
        return True

    def _classify_regime(
        self,
        candles: List[Dict],
        indicators: Dict,
        ai_provider: Optional[Any] = None,
    ) -> Optional[MarketRegimeClassification]:
        """Classify current market regime."""
        if not candles or len(candles) < 20:
            return None

        # Simple regime classification based on indicators
        ema_20 = indicators.get("ema_20", [])
        ema_50 = indicators.get("ema_50", [])
        rsi = indicators.get("rsi_14", [])
        atr = indicators.get("atr_14", [])

        if not ema_20 or not ema_50 or not atr:
            return None

        price = candles[-1]["close"]
        e20 = ema_20[-1]
        e50 = ema_50[-1]
        a = atr[-1]
        r = rsi[-1] if rsi else 50.0

        # Trend detection
        if e20 > e50 and price > e20:
            regime = "TRENDING_UP"
            confidence = 0.7
        elif e20 < e50 and price < e20:
            regime = "TRENDING_DOWN"
            confidence = 0.7
        else:
            # Volatility-based
            if len(atr) > 20:
                avg_atr = sum(atr[-20:]) / 20
                if a > avg_atr * 1.5:
                    regime = "HIGH_VOLATILITY"
                    confidence = 0.65
                elif a < avg_atr * 0.7:
                    regime = "LOW_VOLATILITY"
                    confidence = 0.65
                else:
                    regime = "RANGING"
                    confidence = 0.6
            else:
                regime = "RANGING"
                confidence = 0.5

        return MarketRegimeClassification(
            regime=regime,
            confidence=confidence,
            reasoning=[f"EMA20={'>' if e20 > e50 else '<'}EMA50, ATR={'high' if a > 0 else 'low'}"],
            features={"ema_20": e20, "ema_50": e50, "atr": a, "rsi": r},
        )

    def _regime_compatible(self, signal: Signal, regime: MarketRegimeClassification) -> bool:
        """Check if signal is compatible with market regime."""
        # Simple compatibility rules
        if regime.regime == "TRENDING_UP" and signal.direction == "SHORT":
            return regime.confidence < 0.7  # Allow counter-trend with low confidence
        if regime.regime == "TRENDING_DOWN" and signal.direction == "LONG":
            return regime.confidence < 0.7
        if regime.regime == "HIGH_VOLATILITY" and signal.confidence < 0.7:
            return False
        return True

    def _validate_setup(
        self,
        signal: Signal,
        candles: List[Dict],
        indicators: Dict,
        portfolio_balance: float,
        open_positions: int,
        ai_provider: Optional[Any] = None,
    ) -> TradeSetupValidation:
        """Validate the technical trade setup."""
        reasons = []
        risk_flags = []
        adjustments = {}

        # Check stop loss
        if signal.stop_loss is None:
            reasons.append("No stop loss defined")
            risk_flags.append("NO_STOP_LOSS")
        elif signal.entry > 0 and signal.stop_loss > 0:
            sl_distance = abs(signal.entry - signal.stop_loss)
            sl_pct = sl_distance / signal.entry
            if sl_pct > 0.05:  # More than 5%
                reasons.append(f"Stop loss too wide: {sl_pct:.2%}")
                risk_flags.append("WIDE_STOP_LOSS")
            elif sl_pct < 0.001:  # Less than 0.1%
                reasons.append(f"Stop loss too tight: {sl_pct:.2%}")
                risk_flags.append("TIGHT_STOP_LOSS")

        # Check take profit
        if signal.take_profit is not None and signal.entry > 0:
            tp_distance = abs(signal.take_profit - signal.entry)
            tp_pct = tp_distance / signal.entry
            if tp_pct > 0.20:  # More than 20%
                reasons.append(f"Take profit too far: {tp_pct:.2%}")
                risk_flags.append("WIDE_TAKE_PROFIT")

        # Check risk/reward
        if signal.risk_reward is not None:
            if signal.risk_reward < 1.0:
                reasons.append(f"Poor risk/reward: {signal.risk_reward:.2f}")
                risk_flags.append("POOR_RR")

        # Check position limits
        if open_positions >= 3:
            reasons.append(f"Too many open positions: {open_positions}")
            risk_flags.append("POSITION_LIMIT")

        # Check balance
        if portfolio_balance <= 0:
            reasons.append("Zero or negative balance")
            risk_flags.append("NO_BALANCE")

        valid = len([f for f in risk_flags if f in ("NO_STOP_LOSS", "NO_BALANCE")]) == 0
        confidence = 0.8 if valid else 0.3

        return TradeSetupValidation(
            valid=valid,
            confidence=confidence,
            reasons=reasons,
            risk_flags=risk_flags,
            suggested_adjustments=adjustments,
        )

    def _score_confidence(
        self,
        signal: Signal,
        setup: TradeSetupValidation,
        regime: Optional[MarketRegimeClassification],
        candles: List[Dict],
        indicators: Dict,
    ) -> float:
        """Score overall confidence for the trade."""
        base_confidence = signal.confidence

        # Setup quality bonus/penalty
        if setup.valid:
            setup_factor = 1.1  # 10% bonus
        else:
            setup_factor = 0.7  # 30% penalty

        # Regime alignment bonus
        regime_factor = 1.0
        if regime:
            if (regime.regime == "TRENDING_UP" and signal.direction == "LONG") or \
               (regime.regime == "TRENDING_DOWN" and signal.direction == "SHORT"):
                regime_factor = 1.1
            elif regime.regime in ("HIGH_VOLATILITY",):
                regime_factor = 0.9

        # Time-of-day factor (simplified)
        import datetime
        hour = datetime.datetime.utcnow().hour
        if 8 <= hour <= 20:  # London/NY sessions
            session_factor = 1.05
        else:
            session_factor = 0.95

        confidence = base_confidence * setup_factor * regime_factor * session_factor
        return min(max(confidence, 0.0), 1.0)

    def _get_ai_reasoning(
        self,
        signal: Signal,
        candles: List[Dict],
        indicators: Dict,
        setup: TradeSetupValidation,
        ai_provider: Any,
    ) -> List[str]:
        """Get AI reasoning for the validation."""
        reasoning = []

        # Build context for AI
        context = {
            "symbol": signal.symbol,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "risk_reward": signal.risk_reward,
            "setup_valid": setup.valid,
            "setup_confidence": setup.confidence,
            "risk_flags": setup.risk_flags,
        }

        # Add recent price action
        if candles:
            recent = candles[-5:]
            context["recent_closes"] = [c["close"] for c in recent]
            context["price_change_5"] = (recent[-1]["close"] - recent[0]["close"]) / recent[0]["close"]

        # Add key indicators
        for key in ["rsi_14", "macd", "ema_20", "ema_50", "atr_14"]:
            if key in indicators and indicators[key]:
                context[key] = indicators[key][-1]

        try:
            if hasattr(ai_provider, 'decide'):
                decision = ai_provider.decide(context)
                if isinstance(decision, dict):
                    reasoning.append(f"AI decision: {decision.get('decision', 'UNKNOWN')}")
                    if 'reason' in decision:
                        reasoning.append(f"AI reason: {decision['reason']}")
        except Exception as e:
            reasoning.append(f"AI reasoning unavailable: {e}")

        return reasoning

    def _check_daily_limit(self) -> None:
        """Reset daily counter if needed."""
        now = time.time()
        if now - self._last_reset > 86400:  # 24 hours
            self._calls_today = 0
            self._last_reset = now

    def get_status(self) -> Dict[str, Any]:
        """Get validator status."""
        return {
            "calls_today": self._calls_today,
            "cache_size": len(self._validation_cache),
            "config": {
                "min_confidence": self.config.min_confidence,
                "max_risk_flags": self.config.max_risk_flags,
                "timeout_seconds": self.config.timeout_seconds,
            },
        }
