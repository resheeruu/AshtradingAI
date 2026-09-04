"""M7 Strategy State Machine and Engine.

Four phases: SCANNING → ARMED → WINDOW_OPEN → ENTRY
Operates on completed candles only. No lookahead.
State persists to SQLite for restart survival.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any

from src.ai.base import TradingAI, MarketContext
from src.strategy.filters import FilterCascade, FilterCascadeResult, build_filter_config_from_settings

logger = logging.getLogger(__name__)


class StrategyPhase(str, Enum):
    SCANNING = "SCANNING"
    ARMED = "ARMED"
    WINDOW_OPEN = "WINDOW_OPEN"
    ENTRY = "ENTRY"


@dataclass
class StrategyState:
    """Persistable state for the strategy state machine."""
    phase: StrategyPhase = StrategyPhase.SCANNING
    direction: str = ""  # "LONG" or "SHORT"
    signal_timestamp: str = ""
    signal_price: float = 0.0
    signal_atr: float = 0.0
    pullback_count: int = 0
    pullback_target: int = 2
    breakout_high: float = 0.0
    breakout_low: float = 0.0
    window_start: str = ""
    window_expiry: str = ""
    window_candles_remaining: int = 0
    last_processed_candle: str = ""
    setup_id: str = ""
    symbol: str = ""
    timeframe: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "direction": self.direction,
            "signal_timestamp": self.signal_timestamp,
            "signal_price": self.signal_price,
            "signal_atr": self.signal_atr,
            "pullback_count": self.pullback_count,
            "pullback_target": self.pullback_target,
            "breakout_high": self.breakout_high,
            "breakout_low": self.breakout_low,
            "window_start": self.window_start,
            "window_expiry": self.window_expiry,
            "window_candles_remaining": self.window_candles_remaining,
            "last_processed_candle": self.last_processed_candle,
            "setup_id": self.setup_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategyState":
        phase_str = d.get("phase", "SCANNING")
        try:
            phase = StrategyPhase(phase_str)
        except ValueError:
            phase = StrategyPhase.SCANNING
        return cls(
            phase=phase,
            direction=d.get("direction", ""),
            signal_timestamp=d.get("signal_timestamp", ""),
            signal_price=d.get("signal_price", 0.0),
            signal_atr=d.get("signal_atr", 0.0),
            pullback_count=d.get("pullback_count", 0),
            pullback_target=d.get("pullback_target", 2),
            breakout_high=d.get("breakout_high", 0.0),
            breakout_low=d.get("breakout_low", 0.0),
            window_start=d.get("window_start", ""),
            window_expiry=d.get("window_expiry", ""),
            window_candles_remaining=d.get("window_candles_remaining", 0),
            last_processed_candle=d.get("last_processed_candle", ""),
            setup_id=d.get("setup_id", ""),
            symbol=d.get("symbol", ""),
            timeframe=d.get("timeframe", ""),
        )


@dataclass
class StrategySignal:
    """Output of the state machine: a signal to be evaluated by RiskManager."""
    symbol: str
    direction: str  # "BUY" or "SELL"
    phase: StrategyPhase
    price: float
    atr_value: float
    stop_loss: float
    take_profit: float
    confidence: float
    reason: str
    setup_id: str
    candle_timestamp: str
    filter_results: Optional[FilterCascadeResult] = None


class StrategyEngine:
    """M7 Strategy Engine with state machine, filters, and AI integration.

    Coordinates the full pipeline:
    Completed Candles → Filters → State Machine → AI Decision → Signal

    Does NOT execute orders. Produces signals for RiskManager/broker.
    """

    def __init__(
        self,
        ai: TradingAI,
        symbol: str = "",
        timeframe: str = "",
        filter_config: Optional[Dict] = None,
        pullback_candles: int = 2,
        breakout_window: int = 3,
        sl_atr_multiplier: float = 2.0,
        tp_atr_multiplier: float = 3.0,
        risk_percent: float = 0.01,
    ):
        self.ai = ai
        self.symbol = symbol
        self.timeframe = timeframe
        self.state = StrategyState(symbol=symbol, timeframe=timeframe)
        self.state.pullback_target = pullback_candles
        self.breakout_window = breakout_window
        self.sl_atr_multiplier = sl_atr_multiplier
        self.tp_atr_multiplier = tp_atr_multiplier
        self.risk_percent = risk_percent
        self.filters = FilterCascade(filter_config)
        self._setup_counter = 0

    def _new_setup_id(self) -> str:
        self._setup_counter += 1
        return f"{self.symbol}:{self.timeframe}:{self._setup_counter}"

    def _detect_direction(self, candles: List[Dict]) -> str:
        """Detect potential direction from recent price action.

        Uses completed candles only (excludes forming candle).
        Returns "LONG", "SHORT", or "" for no setup.
        """
        if len(candles) < 3:
            return ""

        # Use completed candles only
        completed = candles[:-1] if len(candles) > 1 else candles
        if len(completed) < 3:
            return ""

        last = completed[-1]
        prev = completed[-2]

        last_close = last["close"]
        last_open = last["open"]
        prev_close = prev["close"]

        # Simple direction detection: bullish/bearish candle with momentum
        if last_close > last_open and last_close > prev_close:
            return "LONG"
        elif last_close < last_open and last_close < prev_close:
            return "SHORT"
        return ""

    def _check_pullback(self, candles: List[Dict], direction: str) -> bool:
        """Check if required pullback candles occurred after signal."""
        if len(candles) < 2:
            return False

        completed = candles[:-1] if len(candles) > 1 else candles
        if len(completed) < 2:
            return False

        # Count counter-trend candles
        count = 0
        for c in completed[-self.state.pullback_target - 1:-1]:
            if c["close"] < c["open"] and direction == "LONG":
                count += 1
            elif c["close"] > c["open"] and direction == "SHORT":
                count += 1

        return count >= self.state.pullback_target

    def _check_breakout(self, candles: List[Dict], direction: str) -> bool:
        """Check if price broke out of the window levels."""
        if len(candles) < 2:
            return False

        completed = candles[:-1] if len(candles) > 1 else candles
        last = completed[-1]
        price = last["close"]

        if direction == "LONG":
            return price > self.state.breakout_high
        else:
            return price < self.state.breakout_low

    def _compute_breakout_levels(self, candles: List[Dict]) -> None:
        """Set breakout levels from the signal candle's high/low."""
        if len(candles) < 2:
            return

        completed = candles[:-1] if len(candles) > 1 else candles
        signal_candle = completed[-1]
        self.state.breakout_high = signal_candle["high"]
        self.state.breakout_low = signal_candle["low"]

    def process_candle(
        self,
        candles: List[Dict],
        indicators: Optional[Dict] = None,
        portfolio_balance: float = 0.0,
        open_positions: Optional[List[str]] = None,
    ) -> Optional[StrategySignal]:
        """Process a new completed candle through the state machine.

        This is the main entry point. Call once per new completed candle.
        Returns a StrategySignal if entry conditions are met, None otherwise.

        CRITICAL: candles[-1] is treated as the forming/current candle
        and is NEVER used for signal generation.
        """
        if not candles or len(candles) < 3:
            return None

        # Ensure we have at least 2 completed candles
        completed = candles[:-1]
        if len(completed) < 2:
            return None

        current_candle = completed[-1]
        candle_ts = current_candle.get("timestamp", "")

        # Skip if we already processed this candle
        if candle_ts == self.state.last_processed_candle:
            return None

        self.state.last_processed_candle = candle_ts

        # Detect direction if in SCANNING
        direction = self._detect_direction(candles)

        if self.state.phase == StrategyPhase.SCANNING:
            return self._process_scanning(candles, direction, portfolio_balance, open_positions)

        elif self.state.phase == StrategyPhase.ARMED:
            return self._process_armed(candles, portfolio_balance, open_positions)

        elif self.state.phase == StrategyPhase.WINDOW_OPEN:
            return self._process_window_open(candles, portfolio_balance, open_positions)

        elif self.state.phase == StrategyPhase.ENTRY:
            # Reset after entry
            signal = self._build_entry_signal(candles, portfolio_balance, open_positions)
            self._reset()
            return signal

        return None

    def _process_scanning(
        self,
        candles: List[Dict],
        direction: str,
        balance: float,
        open_positions: Optional[List[str]],
    ) -> Optional[StrategySignal]:
        """SCANNING: look for directional setup that passes all filters."""
        if not direction:
            return None

        # Run filter cascade
        completed = candles[:-1]
        filter_result = self.filters.evaluate(completed, direction)

        if not filter_result.passed:
            logger.debug(
                "M7 filters rejected %s %s: %s",
                self.symbol, direction, filter_result.rejection_reason,
            )
            return None

        # Setup detected — transition to ARMED
        self._setup_counter += 1
        self.state.phase = StrategyPhase.ARMED
        self.state.direction = direction
        self.state.setup_id = self._new_setup_id()
        self.state.signal_timestamp = completed[-1].get("timestamp", "")
        self.state.signal_price = completed[-1]["close"]

        # Store ATR from filter
        atr_result = filter_result.results.get("ATR")
        self.state.signal_atr = atr_result.value if atr_result and atr_result.value else 0.0

        self.state.pullback_count = 0

        logger.info(
            "M7 %s ARMED %s (setup=%s, ATR=%.4f)",
            self.symbol, direction, self.state.setup_id, self.state.signal_atr,
        )
        return None

    def _process_armed(
        self,
        candles: List[Dict],
        balance: float,
        open_positions: Optional[List[str]],
    ) -> Optional[StrategySignal]:
        """ARMED: wait for pullback confirmation, then open window."""
        completed = candles[:-1]

        # Check for invalidation: opposite signal
        new_direction = self._detect_direction(candles)
        if new_direction and new_direction != self.state.direction:
            logger.info(
                "M7 %s invalidated: opposite signal %s in ARMED state",
                self.symbol, new_direction,
            )
            self._reset()
            return None

        # Check pullback
        if self._check_pullback(candles, self.state.direction):
            # Pullback confirmed — open window
            self.state.phase = StrategyPhase.WINDOW_OPEN
            self._compute_breakout_levels(candles)
            self.state.window_candles_remaining = self.breakout_window

            logger.info(
                "M7 %s WINDOW_OPEN %s (setup=%s, high=%.4f, low=%.4f)",
                self.symbol, self.state.direction, self.state.setup_id,
                self.state.breakout_high, self.state.breakout_low,
            )
            return None

        return None

    def _process_window_open(
        self,
        candles: List[Dict],
        balance: float,
        open_positions: Optional[List[str]],
    ) -> Optional[StrategySignal]:
        """WINDOW_OPEN: check for breakout or expiry."""
        completed = candles[:-1]

        # Check for invalidation
        new_direction = self._detect_direction(candles)
        if new_direction and new_direction != self.state.direction:
            logger.info(
                "M7 %s invalidated: opposite signal %s in WINDOW_OPEN state",
                self.symbol, new_direction,
            )
            self._reset()
            return None

        # Check breakout
        if self._check_breakout(candles, self.state.direction):
            # Breakout confirmed — ENTRY
            self.state.phase = StrategyPhase.ENTRY
            logger.info(
                "M7 %s ENTRY %s (setup=%s)",
                self.symbol, self.state.direction, self.state.setup_id,
            )
            # Build signal immediately
            signal = self._build_entry_signal(candles, balance, open_positions)
            self._reset()
            return signal

        # Check window expiry
        self.state.window_candles_remaining -= 1
        if self.state.window_candles_remaining <= 0:
            logger.info(
                "M7 %s window expired (setup=%s)",
                self.symbol, self.state.setup_id,
            )
            self._reset()
            return None

        return None

    def _build_entry_signal(
        self,
        candles: List[Dict],
        balance: float,
        open_positions: Optional[List[str]],
    ) -> StrategySignal:
        """Build entry signal from current state."""
        completed = candles[:-1]
        price = completed[-1]["close"] if completed else 0.0

        # Compute SL/TP from ATR
        atr_val = self.state.signal_atr if self.state.signal_atr > 0 else price * 0.01
        if self.state.direction == "LONG":
            stop_loss = price - atr_val * self.sl_atr_multiplier
            take_profit = price + atr_val * self.tp_atr_multiplier
        else:
            stop_loss = price + atr_val * self.sl_atr_multiplier
            take_profit = price - atr_val * self.tp_atr_multiplier

        # Get AI context for confidence
        ai_context = MarketContext(
            symbol=self.symbol,
            timeframe=self.timeframe,
            current_price=price,
            candles=candles,
            portfolio_balance=balance,
            open_positions=open_positions or [],
        )

        try:
            ai_decision = self.ai.decide(ai_context)
            confidence = float(ai_decision.get("confidence", 0.6))
            decision = ai_decision.get("decision", "HOLD")
        except Exception as e:
            logger.warning("M7 AI decision failed: %s", e)
            confidence = 0.6
            decision = "HOLD"

        return StrategySignal(
            symbol=self.symbol,
            direction="BUY" if self.state.direction == "LONG" else "SELL",
            phase=StrategyPhase.ENTRY,
            price=price,
            atr_value=atr_val,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            reason=f"M7 {self.state.direction} entry: {self.state.setup_id}",
            setup_id=self.state.setup_id,
            candle_timestamp=self.state.last_processed_candle,
        )

    def _reset(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = StrategyState(
            symbol=self.symbol,
            timeframe=self.timeframe,
            pullback_target=self.state.pullback_target,
        )

    def invalidate(self, reason: str = "") -> None:
        """Force reset the state machine."""
        logger.info("M7 %s invalidated: %s", self.symbol, reason)
        self._reset()

    def is_stale(self, max_age_candles: int = 50) -> bool:
        """Check if the current state is stale (too many candles without progress)."""
        if self.state.phase == StrategyPhase.SCANNING:
            return False
        # Simple staleness: if we have a signal timestamp, check age
        return self.state.window_candles_remaining < -max_age_candles

    def get_state_dict(self) -> Dict[str, Any]:
        """Get serializable state for persistence."""
        return self.state.to_dict()

    def load_state_dict(self, d: Dict[str, Any]) -> None:
        """Load state from persistence."""
        self.state = StrategyState.from_dict(d)

    def get_summary(self) -> Dict[str, Any]:
        """Get human-readable summary for monitoring."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "phase": self.state.phase.value,
            "direction": self.state.direction,
            "signal_price": self.state.signal_price,
            "atr": self.state.signal_atr,
            "pullback_count": self.state.pullback_count,
            "pullback_target": self.state.pullback_target,
            "breakout_high": self.state.breakout_high,
            "breakout_low": self.state.breakout_low,
            "window_remaining": self.state.window_candles_remaining,
            "setup_id": self.state.setup_id,
            "last_candle": self.state.last_processed_candle,
        }
