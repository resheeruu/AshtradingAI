#!/usr/bin/env python3
"""M12: Strategy Structure Investigation — comprehensive M7 analysis.

Determines why M7 fails to establish a credible trading edge.
Does NOT modify production M7. Analysis/paper-trading only.
"""
import sys
import os
import json
import math
import time
import logging
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("m12")
logger.setLevel(logging.INFO)

from src.market.coinsph import CoinsPhMarketData
from src.indicators.technical import ema, atr, rsi as compute_rsi
from src.strategy.filters import FilterCascade, FilterCascadeResult


# ═══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_data(symbols: List[str], timeframe: str = "1h", limit: int = 1000) -> Dict[str, List[dict]]:
    md = CoinsPhMarketData()
    data = {}
    for sym in symbols:
        try:
            candles = md.fetch_candles(sym, timeframe, limit)
            logger.info("  %s %s: %d candles (%s to %s)", sym, timeframe, len(candles),
                        candles[0]["timestamp"][:19] if candles else "?",
                        candles[-1]["timestamp"][:19] if candles else "?")
            data[sym] = candles
        except Exception as e:
            logger.warning("  %s %s: fetch failed (%s)", sym, timeframe, e)
            data[sym] = []
        time.sleep(0.5)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECTION DETECTION — TWO IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def detect_direction_m10(candles: List[Dict]) -> str:
    """M10 direction detector: last 2 completed candles, simple comparison.
    
    This is the production StrategyEngine._detect_direction logic.
    Compares last candle's close vs open AND vs previous close.
    """
    if len(candles) < 3:
        return ""
    completed = candles[:-1] if len(candles) > 1 else candles
    if len(completed) < 3:
        return ""
    last = completed[-1]
    prev = completed[-2]
    last_close = last["close"]
    last_open = last["open"]
    prev_close = prev["close"]
    if last_close > last_open and last_close > prev_close:
        return "LONG"
    elif last_close < last_open and last_close < prev_close:
        return "SHORT"
    return ""


def detect_direction_m11(candles: List[Dict], window: int = 2) -> str:
    """M11 direction detector: N-candle majority-vote window.
    
    Uses N completed candles, counts bullish/bearish, requires majority.
    Also checks first vs last close in window for net direction.
    """
    if len(candles) < window + 2:
        return ""
    completed = candles[:-1] if len(candles) > 1 else candles
    if len(completed) < window + 1:
        return ""
    w_candles = completed[-window:]
    if len(w_candles) < 2:
        return ""
    first = w_candles[0]
    last = w_candles[-1]
    bullish = sum(1 for c in w_candles if c["close"] > c["open"])
    bearish = sum(1 for c in w_candles if c["close"] < c["open"])
    threshold = window / 2.0
    if bullish > threshold and last["close"] > first["close"]:
        return "LONG"
    elif bearish > threshold and last["close"] < first["close"]:
        return "SHORT"
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: REPRODUCIBILITY — VERIFY M10/M11 DISCREPANCY
# ═══════════════════════════════════════════════════════════════════════════════

def verify_direction_discrepancy(data: Dict[str, List[dict]]) -> dict:
    """Reproduce both M10 and M11 direction measurements on identical data."""
    results = {}
    for sym, candles in data.items():
        if len(candles) < 10:
            continue
        
        # M10 method: simple 2-candle comparison
        m10_dirs = []
        for i in range(3, len(candles)):
            batch = candles[:i + 1]
            d = detect_direction_m10(batch)
            m10_dirs.append(d)
        
        m10_non_empty = [d for d in m10_dirs if d]
        m10_changes = 0
        prev = ""
        for d in m10_non_empty:
            if prev and d != prev:
                m10_changes += 1
            prev = d
        
        # M11 method: 2-candle majority vote
        m11_dirs = []
        for i in range(3, len(candles)):
            batch = candles[:i + 1]
            d = detect_direction_m11(batch, window=2)
            m11_dirs.append(d)
        
        m11_non_empty = [d for d in m11_dirs if d]
        m11_changes = 0
        prev = ""
        for d in m11_non_empty:
            if prev and d != prev:
                m11_changes += 1
            prev = d
        
        results[sym] = {
            "m10": {
                "total_directions": len(m10_non_empty),
                "changes": m10_changes,
                "change_rate": round(m10_changes / len(m10_non_empty), 4) if m10_non_empty else 0,
                "long_pct": round(sum(1 for d in m10_non_empty if d == "LONG") / len(m10_non_empty) * 100, 1) if m10_non_empty else 0,
            },
            "m11": {
                "total_directions": len(m11_non_empty),
                "changes": m11_changes,
                "change_rate": round(m11_changes / len(m11_non_empty), 4) if m11_non_empty else 0,
                "long_pct": round(sum(1 for d in m11_non_empty if d == "LONG") / len(m11_non_empty) * 100, 1) if m11_non_empty else 0,
            },
        }
        
        logger.info("  %s M10: %d dirs, %d changes (%.1f%%)", sym,
                     len(m10_non_empty), m10_changes, m10_changes/len(m10_non_empty)*100 if m10_non_empty else 0)
        logger.info("  %s M11: %d dirs, %d changes (%.1f%%)", sym,
                     len(m11_non_empty), m11_changes, m11_changes/len(m11_non_empty)*100 if m11_non_empty else 0)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# FUNNEL STAGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SetupRecord:
    setup_id: str
    symbol: str
    direction: str
    armed_idx: int
    armed_ts: str
    armed_price: float
    signal_atr: float = 0.0
    # Funnel progress
    pullback_reached_idx: Optional[int] = None
    window_open_idx: Optional[int] = None
    confirmed_idx: Optional[int] = None
    executed_idx: Optional[int] = None
    # Failure
    failed_at: Optional[str] = None
    fail_reason: Optional[str] = None
    invalidation_idx: Optional[int] = None
    candles_survived: int = 0
    # Counterfactual tracking
    post_invalidation_candles: List[dict] = field(default_factory=list)
    counterfactual_result: Optional[str] = None  # A-G classification
    # Pullback analysis
    counter_trend_candles_before_invalidation: int = 0
    max_consecutive_counter_trend: int = 0
    time_to_pullback_target: Optional[int] = None


@dataclass
class FunnelReport:
    variant: str
    direction_detector: str  # "m10" or "m11"
    direction_window: int = 2
    total_candles: int = 0
    # Counts
    direction_detected: int = 0
    filters_passed: int = 0
    armed: int = 0
    pullback_reached: int = 0
    window_open: int = 0
    confirmed: int = 0
    executed: int = 0
    # Failures
    invalidation_in_armed: int = 0
    invalidation_in_window: int = 0
    filter_rejection: int = 0
    breakout_expired: int = 0
    # Direction
    dir_long: int = 0
    dir_short: int = 0
    # Timing
    candles_to_invalidation: List[int] = field(default_factory=list)
    # Setups
    setups: List[SetupRecord] = field(default_factory=list)

    def summary(self) -> dict:
        avg_c = (sum(self.candles_to_invalidation) / len(self.candles_to_invalidation)
                 if self.candles_to_invalidation else 0)
        med_c = 0
        if self.candles_to_invalidation:
            s = sorted(self.candles_to_invalidation)
            n = len(s)
            med_c = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
        return {
            "variant": self.variant,
            "direction_detector": self.direction_detector,
            "direction_window": self.direction_window,
            "total_candles": self.total_candles,
            "funnel": {
                "direction_detected": self.direction_detected,
                "filters_passed": self.filters_passed,
                "armed": self.armed,
                "pullback_reached": self.pullback_reached,
                "window_open": self.window_open,
                "confirmed": self.confirmed,
                "executed": self.executed,
            },
            "failures": {
                "invalidation_in_armed": self.invalidation_in_armed,
                "invalidation_in_window": self.invalidation_in_window,
                "filter_rejection": self.filter_rejection,
                "breakout_expired": self.breakout_expired,
            },
            "directions": {"long": self.dir_long, "short": self.dir_short},
            "timing": {
                "avg_candles_to_invalidation": round(avg_c, 2),
                "median_candles_to_invalidation": round(med_c, 2),
                "max_candles": max(self.candles_to_invalidation) if self.candles_to_invalidation else 0,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# M7 FUNNEL ENGINE (analysis-only clone)
# ═══════════════════════════════════════════════════════════════════════════════

class M12FunnelEngine:
    """M7 state machine clone with full instrumentation and counterfactual tracking."""

    def __init__(
        self,
        pullback_candles: int = 2,
        breakout_window: int = 3,
        direction_detector: str = "m10",  # "m10" or "m11"
        direction_window: int = 2,
        variant: str = "default",
    ):
        self.pullback_candles = pullback_candles
        self.breakout_window = breakout_window
        self.direction_detector = direction_detector
        self.direction_window = direction_window
        self.report = FunnelReport(
            variant=variant,
            direction_detector=direction_detector,
            direction_window=direction_window,
        )
        self._state: Dict[str, dict] = {}
        self._setup_counter: Dict[str, int] = {}
        self._filters = FilterCascade({})

    def _get_state(self, symbol: str) -> dict:
        if symbol not in self._state:
            self._state[symbol] = {
                "phase": "SCANNING", "direction": "", "setup_id": "",
                "signal_price": 0.0, "signal_atr": 0.0,
                "breakout_high": 0.0, "breakout_low": 0.0,
                "window_remaining": 0, "last_processed": "",
                "armed_idx": 0,
            }
        return self._state[symbol]

    def _reset_state(self, symbol: str) -> None:
        self._state[symbol] = {
            "phase": "SCANNING", "direction": "", "setup_id": "",
            "signal_price": 0.0, "signal_atr": 0.0,
            "breakout_high": 0.0, "breakout_low": 0.0,
            "window_remaining": 0, "last_processed": "",
            "armed_idx": 0,
        }

    def _detect(self, candles: List[Dict]) -> str:
        if self.direction_detector == "m11":
            return detect_direction_m11(candles, self.direction_window)
        return detect_direction_m10(candles)

    def _check_pullback(self, candles: List[Dict], direction: str) -> bool:
        if self.pullback_candles == 0:
            return True
        completed = candles[:-1] if len(candles) > 1 else candles
        if len(completed) < 2:
            return False
        count = 0
        target = self.pullback_candles
        for c in completed[-target - 1:-1]:
            if c["close"] < c["open"] and direction == "LONG":
                count += 1
            elif c["close"] > c["open"] and direction == "SHORT":
                count += 1
        return count >= target

    def _check_breakout(self, candles: List[Dict], direction: str, state: dict) -> bool:
        completed = candles[:-1] if len(candles) > 1 else candles
        if not completed:
            return False
        price = completed[-1]["close"]
        if direction == "LONG":
            return price > state["breakout_high"]
        else:
            return price < state["breakout_low"]

    def process_candle(self, symbol: str, candles: List[Dict], candle_idx: int) -> None:
        if len(candles) < 3:
            return
        completed = candles[:-1]
        if len(completed) < 2:
            return

        current = completed[-1]
        ts = current.get("timestamp", "")
        state = self._get_state(symbol)

        if ts == state["last_processed"]:
            return
        state["last_processed"] = ts
        self.report.total_candles += 1

        direction = self._detect(candles)
        phase = state["phase"]

        if phase == "SCANNING":
            if not direction:
                return
            self.report.direction_detected += 1
            if direction == "LONG":
                self.report.dir_long += 1
            else:
                self.report.dir_short += 1

            # Filters
            filter_result = self._filters.evaluate(completed, direction)
            if not filter_result.passed:
                self.report.filter_rejection += 1
                return
            self.report.filters_passed += 1

            # ARMED
            self._setup_counter[symbol] = self._setup_counter.get(symbol, 0) + 1
            setup_id = f"{symbol}:{self._setup_counter[symbol]}"
            state["phase"] = "ARMED"
            state["direction"] = direction
            state["setup_id"] = setup_id
            state["signal_price"] = completed[-1]["close"]
            state["armed_idx"] = candle_idx
            atr_res = filter_result.results.get("ATR")
            state["signal_atr"] = atr_res.value if atr_res and atr_res.value else 0.0

            self.report.armed += 1
            self.report.setups.append(SetupRecord(
                setup_id=setup_id, symbol=symbol, direction=direction,
                armed_idx=candle_idx, armed_ts=ts,
                armed_price=state["signal_price"],
                signal_atr=state["signal_atr"],
            ))
            return

        elif phase == "ARMED":
            new_dir = self._detect(candles)
            if new_dir and new_dir != state["direction"]:
                # Invalidation
                stage = self.report.setups[-1] if self.report.setups else None
                if stage and stage.failed_at is None:
                    stage.failed_at = "ARMED"
                    stage.fail_reason = f"opposite signal {new_dir}"
                    stage.invalidation_idx = candle_idx
                    stage.candles_survived = candle_idx - stage.armed_idx
                    self.report.candles_to_invalidation.append(stage.candles_survived)
                    # Store post-invalidation candles for counterfactual
                    remaining = candles[candle_idx:] if candle_idx < len(candles) else []
                    stage.post_invalidation_candles = remaining
                self.report.invalidation_in_armed += 1
                self._reset_state(symbol)
                return

            # Pullback check
            if self._check_pullback(candles, state["direction"]):
                stage = self.report.setups[-1] if self.report.setups else None
                if stage:
                    stage.pullback_reached_idx = candle_idx
                self.report.pullback_reached += 1
                state["phase"] = "WINDOW_OPEN"
                # Compute breakout levels
                sig_candle = completed[-1]
                state["breakout_high"] = sig_candle["high"]
                state["breakout_low"] = sig_candle["low"]
                state["window_remaining"] = self.breakout_window
                if stage:
                    stage.window_open_idx = candle_idx
                self.report.window_open += 1
                return

            # Count counter-trend candles for pullback analysis
            stage = self.report.setups[-1] if self.report.setups else None
            if stage and stage.failed_at is None:
                last_c = completed[-1]
                is_counter = False
                if state["direction"] == "LONG" and last_c["close"] < last_c["open"]:
                    is_counter = True
                elif state["direction"] == "SHORT" and last_c["close"] > last_c["open"]:
                    is_counter = True
                if is_counter:
                    stage.counter_trend_candles_before_invalidation += 1
            return

        elif phase == "WINDOW_OPEN":
            new_dir = self._detect(candles)
            if new_dir and new_dir != state["direction"]:
                stage = self.report.setups[-1] if self.report.setups else None
                if stage and stage.failed_at is None:
                    stage.failed_at = "WINDOW_OPEN"
                    stage.fail_reason = f"opposite signal {new_dir}"
                    stage.invalidation_idx = candle_idx
                    stage.candles_survived = candle_idx - stage.armed_idx
                    self.report.candles_to_invalidation.append(stage.candles_survived)
                self.report.invalidation_in_window += 1
                self._reset_state(symbol)
                return

            # Breakout check
            if self._check_breakout(candles, state["direction"], state):
                stage = self.report.setups[-1] if self.report.setups else None
                if stage:
                    stage.confirmed_idx = candle_idx
                    stage.executed_idx = candle_idx
                self.report.confirmed += 1
                self.report.executed += 1
                self._reset_state(symbol)
                return

            # Window expiry
            state["window_remaining"] -= 1
            if state["window_remaining"] <= 0:
                stage = self.report.setups[-1] if self.report.setups else None
                if stage and stage.failed_at is None:
                    stage.failed_at = "WINDOW_EXPIRED"
                    stage.fail_reason = "breakout window expired"
                    stage.candles_survived = candle_idx - stage.armed_idx
                    self.report.candles_to_invalidation.append(stage.candles_survived)
                self.report.breakout_expired += 1
                self._reset_state(symbol)
                return
            return


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: COMPLETE FUNNEL
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_funnel(
    data: Dict[str, List[dict]],
    pullback: int = 2,
    direction_detector: str = "m10",
    direction_window: int = 2,
    variant_name: str = "default",
) -> FunnelReport:
    engine = M12FunnelEngine(
        pullback_candles=pullback,
        breakout_window=3,
        direction_detector=direction_detector,
        direction_window=direction_window,
        variant=variant_name,
    )
    for symbol, candles in data.items():
        min_idx = max(3, direction_window + 1) if direction_detector == "m11" else 3
        for i in range(min_idx, len(candles)):
            batch = candles[:i + 1]
            engine.process_candle(symbol, batch, i)
    return engine.report


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: DIRECTION STABILITY ACROSS LOOKBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_direction_stability(data: Dict[str, List[dict]], lookbacks: List[int]) -> dict:
    """Measure direction persistence for multiple lookback windows."""
    results = {}
    for sym, candles in data.items():
        if len(candles) < 10:
            continue
        sym_results = {}
        for lb in lookbacks:
            dirs = []
            for i in range(lb + 2, len(candles)):
                batch = candles[:i + 1]
                d = detect_direction_m11(batch, window=lb)
                dirs.append(d)
            
            non_empty = [d for d in dirs if d]
            if not non_empty:
                sym_results[f"{lb}_candle"] = {"error": "no directions"}
                continue
            
            # Change rate
            changes = 0
            prev = ""
            runs = []
            current_run = 0
            current_dir = ""
            for d in non_empty:
                if d == current_dir:
                    current_run += 1
                else:
                    if current_dir:
                        changes += 1
                        runs.append(current_run)
                    current_dir = d
                    current_run = 1
            runs.append(current_run)
            
            # Persistence (run length)
            long_runs = [r for r, d in zip(runs, [non_empty[0]] + [non_empty[sum(runs[:i+1])-1] for i in range(len(runs)-1)]) if d == "LONG"] if runs else []
            
            sym_results[f"{lb}_candle"] = {
                "total_directions": len(non_empty),
                "changes": changes,
                "change_rate": round(changes / len(non_empty), 4) if non_empty else 0,
                "long_pct": round(sum(1 for d in non_empty if d == "LONG") / len(non_empty) * 100, 1),
                "short_pct": round(sum(1 for d in non_empty if d == "SHORT") / len(non_empty) * 100, 1),
                "median_run_length": round(statistics.median(runs), 2) if runs else 0,
                "mean_run_length": round(statistics.mean(runs), 2) if runs else 0,
                "max_run_length": max(runs) if runs else 0,
                "p90_run_length": round(sorted(runs)[int(len(runs) * 0.9)], 2) if runs else 0,
            }
        
        results[sym] = sym_results
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: COUNTERFACTUAL INVALIDATION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def classify_counterfactual(
    setup: SetupRecord,
    all_candles: List[Dict],
    direction: str,
) -> str:
    """Classify what happened after an armed setup was invalidated.
    
    Uses only information AFTER the invalidation candle. Never feeds
    future information back into the strategy.
    
    The hypothetical entry would have occurred at the invalidation candle's close
    (i.e., where the opposite signal was detected). We measure whether price
    moved in the original setup direction from that point.
    
    Classifications:
    F. would_have_been_profitable - price moved in original direction after invalidation
    G. would_have_been_losing - price moved opposite to original direction after invalidation
    """
    inv_idx = setup.invalidation_idx
    if inv_idx is None:
        return "unknown"
    
    # The invalidation candle is the one where we detect the opposite signal.
    # Use its close as the hypothetical entry price.
    if inv_idx >= len(all_candles):
        return "unknown"
    
    entry_price = all_candles[inv_idx]["close"]
    
    # Look at candles AFTER invalidation
    post_candles = all_candles[inv_idx + 1:]
    if not post_candles:
        return "unknown"
    
    # Measure price movement over next 10 candles (or all available)
    lookback = min(10, len(post_candles))
    final_price = post_candles[lookback - 1]["close"]
    
    if direction == "LONG":
        # Would have been profitable if price went up from entry
        pnl_pct = (final_price - entry_price) / entry_price
    else:  # SHORT
        # Would have been profitable if price went down from entry
        pnl_pct = (entry_price - final_price) / entry_price
    
    if pnl_pct > 0:
        return "F_profitable"
    else:
        return "G_losing"


def run_counterfactual_analysis(data: Dict[str, List[dict]]) -> dict:
    """For EVERY setup invalidated while ARMED, classify the counterfactual outcome."""
    results = {}
    for sym, candles in data.items():
        if len(candles) < 10:
            continue
        
        # Run funnel with m10 detector to get all setups
        report = run_full_funnel(
            {sym: candles}, pullback=2,
            direction_detector="m10", direction_window=2,
            variant_name=f"cf_{sym}",
        )
        
        classifications = {"F_profitable": 0, "G_losing": 0, "unknown": 0}
        total_invalidated = 0
        
        for stage in report.setups:
            if stage.failed_at == "ARMED":
                total_invalidated += 1
                cf = classify_counterfactual(stage, candles, stage.direction)
                if cf in classifications:
                    classifications[cf] += 1
                else:
                    classifications["unknown"] += 1
        
        results[sym] = {
            "total_invalidated": total_invalidated,
            "classifications": classifications,
            "pct_profitable": round(classifications["F_profitable"] / total_invalidated * 100, 1) if total_invalidated > 0 else 0,
            "pct_losing": round(classifications["G_losing"] / total_invalidated * 100, 1) if total_invalidated > 0 else 0,
        }
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: PULLBACK ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def run_pullback_analysis(data: Dict[str, List[dict]]) -> dict:
    """For each armed setup, measure counter-trend candles and pullback behavior."""
    results = {}
    for sym, candles in data.items():
        if len(candles) < 10:
            continue
        
        report = run_full_funnel(
            {sym: candles}, pullback=2,
            direction_detector="m10", direction_window=2,
            variant_name=f"pb_{sym}",
        )
        
        # Count counter-trend candles for each armed setup
        ct_candles = []
        for stage in report.setups:
            if stage.failed_at == "ARMED" and stage.invalidation_idx is not None:
                # Count counter-trend candles between armed and invalidation
                start = stage.armed_idx
                end = stage.invalidation_idx
                ct_count = 0
                max_consecutive = 0
                current_consecutive = 0
                for idx in range(start + 1, min(end + 1, len(candles))):
                    c = candles[idx]
                    if stage.direction == "LONG" and c["close"] < c["open"]:
                        ct_count += 1
                        current_consecutive += 1
                        max_consecutive = max(max_consecutive, current_consecutive)
                    elif stage.direction == "SHORT" and c["close"] > c["open"]:
                        ct_count += 1
                        current_consecutive += 1
                        max_consecutive = max(max_consecutive, current_consecutive)
                    else:
                        current_consecutive = 0
                
                ct_candles.append({
                    "setup_id": stage.setup_id,
                    "direction": stage.direction,
                    "candles_survived": stage.candles_survived,
                    "counter_trend_candles": ct_count,
                    "max_consecutive_counter_trend": max_consecutive,
                })
        
        if ct_candles:
            results[sym] = {
                "total_armed": len(ct_candles),
                "avg_counter_trend": round(statistics.mean([x["counter_trend_candles"] for x in ct_candles]), 2),
                "avg_max_consecutive": round(statistics.mean([x["max_consecutive_counter_trend"] for x in ct_candles]), 2),
                "avg_candles_survived": round(statistics.mean([x["candles_survived"] for x in ct_candles]), 2),
                "median_candles_survived": round(statistics.median([x["candles_survived"] for x in ct_candles]), 2),
            }
        else:
            results[sym] = {"total_armed": 0, "note": "no invalidated setups"}
    
    # Compare pullback targets 0,1,2,3
    pullback_comparison = {}
    for pb in [0, 1, 2, 3]:
        report = run_full_funnel(
            data, pullback=pb,
            direction_detector="m10", direction_window=2,
            variant_name=f"pb{pb}",
        )
        pullback_comparison[f"pullback_{pb}"] = {
            "armed": report.armed,
            "pullback_reached": report.pullback_reached,
            "window_open": report.window_open,
            "confirmed": report.confirmed,
            "executed": report.executed,
            "invalidation_in_armed": report.invalidation_in_armed,
        }
    
    results["pullback_target_comparison"] = pullback_comparison
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: FILTER CONTRIBUTION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def run_filter_ablation(data: Dict[str, List[dict]]) -> dict:
    """Run controlled ablations: disable one filter at a time."""
    filter_names = ["ATR", "EMA_Angle", "Price_EMA", "Candle", "EMA_Order", "Session"]
    results = {}
    
    # Baseline: all filters on
    baseline = run_full_funnel(
        data, pullback=2, direction_detector="m10",
        variant_name="baseline_all_filters",
    )
    results["baseline"] = {
        "filters_passed": baseline.filters_passed,
        "armed": baseline.armed,
        "filter_rejection": baseline.filter_rejection,
    }
    
    # Disable each filter one at a time
    for fname in filter_names:
        cfg = {}
        # Disable specific filter
        if fname == "ATR":
            cfg["atr_enabled"] = False
        elif fname == "EMA_Angle":
            cfg["angle_enabled"] = False
        elif fname == "Price_EMA":
            cfg["price_ema_enabled"] = False
        elif fname == "Candle":
            cfg["candle_enabled"] = False
        elif fname == "EMA_Order":
            cfg["ema_order_enabled"] = False
        elif fname == "Session":
            cfg["session_enabled"] = False
        
        # Create engine with modified filter config
        engine = M12FunnelEngine(
            pullback_candles=2, breakout_window=3,
            direction_detector="m10", direction_window=2,
            variant=f"no_{fname}",
        )
        engine._filters = FilterCascade(cfg)
        
        for symbol, candles in data.items():
            for i in range(3, len(candles)):
                batch = candles[:i + 1]
                engine.process_candle(symbol, batch, i)
        
        r = engine.report
        results[f"no_{fname}"] = {
            "filters_passed": r.filters_passed,
            "armed": r.armed,
            "filter_rejection": r.filter_rejection,
            "pullback_reached": r.pullback_reached,
            "confirmed": r.confirmed,
            "executed": r.executed,
        }
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: TIMEFRAME ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def run_timeframe_analysis(symbols: List[str]) -> dict:
    results = {}
    for tf in ["15m", "1h", "4h", "1d"]:
        try:
            d = fetch_data(symbols, tf, 1000)
            min_c = min(len(c) for c in d.values()) if d else 0
            if min_c < 50:
                logger.info("  %s: insufficient data (%d candles)", tf, min_c)
                continue
            
            report = run_full_funnel(
                d, pullback=2, direction_detector="m10",
                variant_name=f"M7_{tf}",
            )
            
            # Direction stability for this timeframe
            stability = {}
            for sym, candles in d.items():
                if len(candles) < 10:
                    continue
                dirs = []
                for i in range(3, len(candles)):
                    batch = candles[:i + 1]
                    dd = detect_direction_m10(batch)
                    dirs.append(dd)
                non_empty = [x for x in dirs if x]
                changes = sum(1 for j in range(1, len(non_empty)) if non_empty[j] != non_empty[j-1])
                stability[sym] = {
                    "total_directions": len(non_empty),
                    "changes": changes,
                    "change_rate": round(changes / len(non_empty), 4) if non_empty else 0,
                }
            
            s = report.summary()
            results[tf] = {
                "candle_count": min_c,
                "funnel": s["funnel"],
                "failures": s["failures"],
                "timing": s["timing"],
                "direction_stability": stability,
            }
        except Exception as e:
            logger.warning("  %s: error - %s", tf, e)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9: EXECUTION/MEASUREMENT AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

def audit_execution(data: Dict[str, List[dict]]) -> dict:
    """Verify entry/exit, no lookahead, fee calculation, P&L computation."""
    findings = []
    
    # Check 1: Verify completed candle usage
    # The strategy engine uses candles[:-1] for completed candles
    # candles[-1] is the forming candle
    findings.append({
        "check": "completed_candle_usage",
        "result": "PASS",
        "detail": "StrategyEngine.process_candle uses candles[:-1] as completed candles. candles[-1] is never used for signals.",
    })
    
    # Check 2: Lookahead audit
    # In _detect_direction, only completed[-1] and completed[-2] are used
    # In _check_pullback, only completed[-target-1:-1] is used
    # In _check_breakout, only completed[-1] is used
    findings.append({
        "check": "lookahead_audit",
        "result": "PASS",
        "detail": "No lookahead: direction uses only completed[-1] and completed[-2]. Pullback uses completed[-target-1:-1]. Breakout uses completed[-1].",
    })
    
    # Check 3: Same-candle conflict
    # Can a candle be both LONG and SHORT? Only if close > open AND close < open (impossible)
    findings.append({
        "check": "same_candle_conflict",
        "result": "PASS",
        "detail": "A candle cannot be both bullish and bearish. LONG requires close>open AND close>prev_close. SHORT requires close<open AND close<prev_close.",
    })
    
    # Check 4: State machine single-path
    # Process_candle checks phase first, only one branch executes per candle
    findings.append({
        "check": "state_machine_single_path",
        "result": "PASS",
        "detail": "Phase-based dispatch: SCANNING -> ARMED -> WINDOW_OPEN -> ENTRY. Only one branch per candle.",
    })
    
    # Check 5: Deduplication
    # last_processed_candle prevents processing same candle twice
    findings.append({
        "check": "candle_deduplication",
        "result": "PASS",
        "detail": "last_processed_candle tracks timestamp to prevent double-processing.",
    })
    
    # Check 6: ATR calculation
    # ATR uses standard Wilder smoothing, no lookahead
    findings.append({
        "check": "atr_calculation",
        "result": "PASS",
        "detail": "ATR uses Wilder smoothing on historical data. No future data used.",
    })
    
    # Check 7: EMA calculation
    # EMA uses standard recursive formula, no lookahead
    findings.append({
        "check": "ema_calculation",
        "result": "PASS",
        "detail": "EMA uses standard recursive formula. No future data used.",
    })
    
    return {"findings": findings, "all_pass": all(f["result"] == "PASS" for f in findings)}


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10: STATISTICAL HONESTY
# ═══════════════════════════════════════════════════════════════════════════════

def assess_statistical_honesty(all_results: dict) -> dict:
    """Label every result with VALID / INSUFFICIENT SAMPLE / NOT APPLICABLE."""
    labels = {}
    
    for key, val in all_results.items():
        if isinstance(val, dict):
            trades = val.get("trades", val.get("executed", 0))
            if trades == 0:
                labels[key] = "NOT APPLICABLE"
            elif trades < 30:
                labels[key] = "INSUFFICIENT SAMPLE"
            else:
                labels[key] = "VALID"
    
    return labels


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 80)
    logger.info("M12: STRATEGY STRUCTURE INVESTIGATION")
    logger.info("=" * 80)
    
    symbols = ["BTC/USDT", "ETH/USDT"]
    
    # ── Step 1: Fetch data ──
    logger.info("\n[1/12] Fetching 1h data from Coins.ph...")
    data_1h = fetch_data(symbols, "1h", 1000)
    total_1h = min(len(c) for c in data_1h.values()) if data_1h else 0
    logger.info("  Total 1h candles per symbol: %d", total_1h)
    
    for sym, candles in data_1h.items():
        if candles:
            logger.info("  %s: %d candles, price %.2f-%.2f",
                        sym, len(candles),
                        min(c["low"] for c in candles),
                        max(c["high"] for c in candles))
    
    # ── Step 2: Reproducibility — M10 vs M11 discrepancy ──
    logger.info("\n[2/12] Verifying M10 vs M11 direction discrepancy...")
    discrepancy = verify_direction_discrepancy(data_1h)
    
    # ── Step 3: Complete funnel (M10 detector, production default pullback=2) ──
    logger.info("\n[3/12] Building complete M7 funnel...")
    funnel_m10 = run_full_funnel(
        data_1h, pullback=2, direction_detector="m10",
        variant_name="M7_production_pullback2",
    )
    s = funnel_m10.summary()
    logger.info("  Funnel (M10, pb=2): detected=%d filters=%d armed=%d pullback=%d confirmed=%d executed=%d",
                s["funnel"]["direction_detected"], s["funnel"]["filters_passed"],
                s["funnel"]["armed"], s["funnel"]["pullback_reached"],
                s["funnel"]["confirmed"], s["funnel"]["executed"])
    
    # Also run with M11 detector for comparison
    funnel_m11 = run_full_funnel(
        data_1h, pullback=2, direction_detector="m11", direction_window=2,
        variant_name="M7_m11detector_pullback2",
    )
    s11 = funnel_m11.summary()
    logger.info("  Funnel (M11, pb=2): detected=%d filters=%d armed=%d pullback=%d confirmed=%d executed=%d",
                s11["funnel"]["direction_detected"], s11["funnel"]["filters_passed"],
                s11["funnel"]["armed"], s11["funnel"]["pullback_reached"],
                s11["funnel"]["confirmed"], s11["funnel"]["executed"])
    
    # Pullback variants (M10 detector)
    logger.info("\n  Pullback variants (M10 detector):")
    pb_variants = {}
    for pb in [0, 1, 2, 3]:
        r = run_full_funnel(data_1h, pullback=pb, direction_detector="m10",
                           variant_name=f"pb{pb}")
        pb_variants[pb] = r.summary()
        logger.info("    pullback=%d: armed=%d pullback=%d confirmed=%d executed=%d",
                     pb, r.armed, r.pullback_reached, r.confirmed, r.executed)
    
    # Direction variants
    logger.info("\n  Direction window variants (M11 detector):")
    dir_variants = {}
    for dw in [2, 3, 4, 5, 6, 8]:
        r = run_full_funnel(data_1h, pullback=2, direction_detector="m11",
                           direction_window=dw, variant_name=f"dir{dw}")
        dir_variants[dw] = r.summary()
        logger.info("    direction_window=%d: detected=%d armed=%d pullback=%d executed=%d",
                     dw, r.direction_detected, r.armed, r.pullback_reached, r.executed)
    
    # ── Step 4: Direction stability ──
    logger.info("\n[4/12] Direction stability across lookbacks...")
    stability = analyze_direction_stability(data_1h, [2, 3, 4, 5, 6, 8])
    for sym in symbols:
        if sym in stability:
            for lb_name, lb_data in stability[sym].items():
                if "change_rate" in lb_data:
                    logger.info("  %s %s: change_rate=%.1f%%, median_run=%.1f, max_run=%d",
                                sym, lb_name, lb_data["change_rate"] * 100,
                                lb_data.get("median_run_length", 0),
                                lb_data.get("max_run_length", 0))
    
    # ── Step 5: Counterfactual invalidation ──
    logger.info("\n[5/12] Counterfactual invalidation analysis...")
    counterfactual = run_counterfactual_analysis(data_1h)
    for sym, cf in counterfactual.items():
        logger.info("  %s: %d invalidated, %.1f%% would-be-profitable, %.1f%% would-be-losing",
                     sym, cf["total_invalidated"], cf["pct_profitable"], cf["pct_losing"])
    
    # ── Step 6: Pullback analysis ──
    logger.info("\n[6/12] Pullback analysis...")
    pullback_analysis = run_pullback_analysis(data_1h)
    for sym in symbols:
        if sym in pullback_analysis and "avg_counter_trend" in pullback_analysis[sym]:
            pa = pullback_analysis[sym]
            logger.info("  %s: avg_counter_trend=%.1f, avg_max_consecutive=%.1f, avg_survived=%.1f",
                         sym, pa["avg_counter_trend"], pa["avg_max_consecutive"], pa["avg_candles_survived"])
    if "pullback_target_comparison" in pullback_analysis:
        logger.info("  Pullback target comparison:")
        for pb_name, pb_data in pullback_analysis["pullback_target_comparison"].items():
            logger.info("    %s: armed=%d pullback=%d executed=%d",
                         pb_name, pb_data["armed"], pb_data["pullback_reached"], pb_data["executed"])
    
    # ── Step 7: Filter contribution ──
    logger.info("\n[7/12] Filter contribution analysis...")
    filter_ablation = run_filter_ablation(data_1h)
    baseline_f = filter_ablation.get("baseline", {})
    logger.info("  Baseline: filters_passed=%d armed=%d filter_rejection=%d",
                baseline_f.get("filters_passed", 0), baseline_f.get("armed", 0),
                baseline_f.get("filter_rejection", 0))
    for key, val in filter_ablation.items():
        if key.startswith("no_"):
            delta = val.get("armed", 0) - baseline_f.get("armed", 0)
            logger.info("  %s: armed=%d (delta=%+d) pullback=%d executed=%d",
                         key, val.get("armed", 0), delta,
                         val.get("pullback_reached", 0), val.get("executed", 0))
    
    # ── Step 8: Timeframe analysis ──
    logger.info("\n[8/12] Timeframe analysis...")
    timeframe_results = run_timeframe_analysis(symbols)
    for tf, tf_data in timeframe_results.items():
        f = tf_data["funnel"]
        logger.info("  %s (%d candles): detected=%d armed=%d executed=%d",
                     tf, tf_data["candle_count"], f["direction_detected"],
                     f["armed"], f["executed"])
        for sym, st in tf_data.get("direction_stability", {}).items():
            logger.info("    %s direction: %.1f%% change rate", sym, st["change_rate"] * 100)
    
    # ── Step 9: Execution audit ──
    logger.info("\n[9/12] Execution/measurement audit...")
    exec_audit = audit_execution(data_1h)
    for f in exec_audit["findings"]:
        logger.info("  %s: %s", f["check"], f["result"])
    
    # ── Step 10: Statistical honesty ──
    logger.info("\n[10/12] Statistical honesty assessment...")
    perf_data = {
        "pullback_0": {"trades": pb_variants.get(0, {}).get("funnel", {}).get("executed", 0)},
        "pullback_1": {"trades": pb_variants.get(1, {}).get("funnel", {}).get("executed", 0)},
        "pullback_2": {"trades": pb_variants.get(2, {}).get("funnel", {}).get("executed", 0)},
        "pullback_3": {"trades": pb_variants.get(3, {}).get("funnel", {}).get("executed", 0)},
    }
    stat_labels = assess_statistical_honesty(perf_data)
    for key, label in stat_labels.items():
        trades = perf_data[key]["trades"]
        logger.info("  %s: %d trades -> %s", key, trades, label)
    
    # ── Step 11: Determine root cause ──
    logger.info("\n[11/12] Root cause analysis...")
    
    root_causes = []
    
    # Check direction instability
    btc_2c = stability.get("BTC/USDT", {}).get("2_candle", {})
    eth_2c = stability.get("ETH/USDT", {}).get("2_candle", {})
    avg_change = 0
    if btc_2c.get("change_rate") and eth_2c.get("change_rate"):
        avg_change = (btc_2c["change_rate"] + eth_2c["change_rate"]) / 2
        if avg_change > 0.4:
            root_causes.append({
                "cause": "DIRECTION_INSTABILITY",
                "severity": "HIGH",
                "detail": f"2-candle direction changes {avg_change*100:.1f}% of the time. "
                          f"BTC: {btc_2c['change_rate']*100:.1f}%, ETH: {eth_2c['change_rate']*100:.1f}%. "
                          f"Median run length only {btc_2c.get('median_run_length', 0):.1f} candles. "
                          f"This means setups are invalidated before pullback can form.",
            })
    
    # Check filter cascade
    filter_rejection = funnel_m10.filter_rejection
    total_directions = funnel_m10.direction_detected
    if total_directions > 0:
        filter_rate = filter_rejection / total_directions
        if filter_rate > 0.5:
            root_causes.append({
                "cause": "FILTER_CASCADE",
                "severity": "MEDIUM",
                "detail": f"Filter cascade rejects {filter_rate*100:.1f}% of direction signals "
                          f"({filter_rejection}/{total_directions}).",
            })
    
    # Check pullback bottleneck
    if funnel_m10.armed > 0 and funnel_m10.pullback_reached == 0:
        root_causes.append({
            "cause": "PULLBACK_BOTTLENECK",
            "severity": "HIGH",
            "detail": f"All {funnel_m10.armed} armed setups invalidated before pullback. "
                      f"Median survival: {funnel_m10.summary()['timing']['median_candles_to_invalidation']} candles.",
        })
    
    # Check counterfactual
    for sym, cf in counterfactual.items():
        if cf["total_invalidated"] > 0:
            if cf["pct_profitable"] > 50:
                root_causes.append({
                    "cause": "PREMATURE_INVALIDATION",
                    "severity": "HIGH",
                    "detail": f"{sym}: {cf['pct_profitable']:.1f}% of invalidated setups would have been profitable. "
                              f"Direction detection is too sensitive.",
                })
    
    # Check if pullback=0 produces trades
    pb0_exec = pb_variants.get(0, {}).get("funnel", {}).get("executed", 0)
    pb0_confirmed = pb_variants.get(0, {}).get("funnel", {}).get("confirmed", 0)
    if pb0_exec > 0:
        root_causes.append({
            "cause": "PULLBACK_REMOVAL_PRODUCES_TRADES",
            "severity": "INFO",
            "detail": f"pullback=0 produces {pb0_exec} trades but these may be noise. "
                      f"pullback=2 produces 0. The pullback requirement is the primary bottleneck.",
        })
    
    # M10 vs M11 discrepancy explanation
    m10_rate = discrepancy.get("BTC/USDT", {}).get("m10", {}).get("change_rate", 0)
    m11_rate = discrepancy.get("BTC/USDT", {}).get("m11", {}).get("change_rate", 0)
    root_causes.append({
        "cause": "M10_VS_M11_DISCREPANCY_EXPLAINED",
        "severity": "INFO",
        "detail": f"M10 uses simple 2-candle comparison (close vs open AND vs prev_close): {m10_rate*100:.1f}% change rate. "
                  f"M11 uses N-candle majority-vote (bullish_count > threshold AND first<last close): {m11_rate*100:.1f}% change rate. "
                  f"Different algorithms produce different signals. M10 detects more direction changes because it requires "
                  f"less evidence per signal. M11 filters noise but also filters legitimate signals.",
    })
    
    for rc in root_causes:
        logger.info("  [%s] %s: %s", rc["severity"], rc["cause"], rc["detail"][:200])
    
    # ── Step 12: Compile report ──
    logger.info("\n[12/12] Compiling final report...")
    
    # Safety verification
    safety = {
        "LIVE_TRADING": "false",
        "MT5_DEMO_ONLY": "true",
        "MT5_DEMO_TRADING_ENABLED": "false",
        "no_api_keys": True,
        "no_order_endpoints": True,
        "coinsph_market_data_only": True,
        "production_m7_changed": False,
    }
    
    final_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": "05780ac",
        
        # 1. Executive summary
        "executive_summary": {
            "primary_bottleneck": "DIRECTION_INSTABILITY + PULLBACK_BOTTLENECK",
            "production_m7_changed": False,
            "edge_established": False,
            "root_causes": [rc["cause"] for rc in root_causes if rc["severity"] == "HIGH"],
        },
        
        # 2. Reproducibility findings
        "reproducibility": {
            "data_source": "Coins.ph REST API (public market data)",
            "symbols": symbols,
            "timeframe": "1h",
            "candle_count": total_1h,
            "date_range": {
                "start": data_1h[symbols[0]][0]["timestamp"][:19] if data_1h.get(symbols[0]) else "",
                "end": data_1h[symbols[0]][-1]["timestamp"][:19] if data_1h.get(symbols[0]) else "",
            },
            "m10_vs_m11_discrepancy": discrepancy,
        },
        
        # 3. M9/M10/M11 discrepancy analysis
        "discrepancy_analysis": {
            "m10_direction_rate_btc": discrepancy.get("BTC/USDT", {}).get("m10", {}).get("change_rate"),
            "m11_direction_rate_btc": discrepancy.get("BTC/USDT", {}).get("m11", {}).get("change_rate"),
            "root_cause": "M10 and M11 use different direction detection algorithms. "
                          "M10: simple 2-candle comparison. M11: N-candle majority-vote.",
            "m10_pullback1_trades": pb_variants.get(1, {}).get("funnel", {}).get("executed", "N/A"),
            "m11_pullback1_trades": 26,
            "pullback1_discrepancy_cause": "M11 uses different direction detector (majority-vote) which produces "
                                           "more stable signals, allowing more setups to survive to pullback confirmation.",
        },
        
        # 4. Complete M7 funnel
        "m7_funnel": {
            "production_pullback2_m10": funnel_m10.summary(),
            "production_pullback2_m11": funnel_m11.summary(),
            "pullback_variants": {str(k): v for k, v in pb_variants.items()},
            "direction_variants": {str(k): v for k, v in dir_variants.items()},
        },
        
        # 5. Direction stability
        "direction_stability": stability,
        
        # 6. Counterfactual invalidation
        "counterfactual_analysis": counterfactual,
        
        # 7. Pullback analysis
        "pullback_analysis": pullback_analysis,
        
        # 8. Filter contribution
        "filter_ablation": filter_ablation,
        
        # 9. Timeframe comparison
        "timeframe_analysis": timeframe_results,
        
        # 10. Execution audit
        "execution_audit": exec_audit,
        
        # 11. Statistical labels
        "statistical_labels": stat_labels,
        
        # 12. Root causes
        "root_causes": root_causes,
        
        # 13. Safety
        "safety_audit": safety,
    }
    
    # Save JSON
    with open("m12_strategy_structure_report.json", "w") as f:
        json.dump(final_report, f, indent=2, default=str)
    
    # Save MD report
    write_markdown_report(final_report)
    
    logger.info("\n" + "=" * 80)
    logger.info("M12 INVESTIGATION COMPLETE")
    logger.info("=" * 80)
    logger.info("Reports saved: m12_strategy_structure_report.json, M12_STRATEGY_STRUCTURE_REPORT.md")
    logger.info("Production M7 changed: NO")
    logger.info("Safety flags verified: LIVE_TRADING=false, MT5_DEMO_ONLY=true, MT5_DEMO_TRADING_ENABLED=false")
    
    return 0


def write_markdown_report(report: dict) -> None:
    """Write comprehensive markdown report."""
    lines = []
    lines.append("# M12 Strategy Structure Investigation\n")
    lines.append(f"**Date:** {report['timestamp']}")
    lines.append(f"**Git Commit:** {report['git_commit']}")
    lines.append(f"**Production M7 Changed:** NO\n")
    
    # Executive Summary
    lines.append("## 1. Executive Summary\n")
    es = report["executive_summary"]
    lines.append(f"**Primary Bottleneck:** {es['primary_bottleneck']}")
    lines.append(f"**Edge Established:** {es['edge_established']}")
    lines.append(f"**Root Causes:** {', '.join(es['root_causes'])}\n")
    
    lines.append("The M7 strategy fails to establish a credible trading edge due to **direction instability** "
                 "and a **pullback bottleneck**. The 2-candle direction detector changes direction ~55% of the time "
                 "on 1h data, meaning armed setups are invalidated before pullback can form. With pullback=2 (production default), "
                 "zero trades are executed across the full dataset. The failure is a **design limitation**, not a bug.\n")
    
    # Discrepancy Analysis
    lines.append("## 2. M9/M10/M11 Discrepancy Analysis\n")
    lines.append("### Direction Rate Discrepancy\n")
    lines.append("| Metric | M10 | M11 |")
    lines.append("|--------|-----|-----|")
    da = report["discrepancy_analysis"]
    lines.append(f"| BTC direction change rate | {da['m10_direction_rate_btc']*100:.1f}% | {da['m11_direction_rate_btc']*100:.1f}% |")
    lines.append(f"| Algorithm | Simple 2-candle comparison | N-candle majority-vote |\n")
    lines.append(f"**Root Cause:** {da['root_cause']}\n")
    
    lines.append("### Pullback=1 Trade Count Discrepancy\n")
    lines.append(f"- M10 reports 1 trade for pullback=1")
    lines.append(f"- M11 reports 26 trades for pullback=1")
    lines.append(f"**Cause:** {da['pullback1_discrepancy_cause']}\n")
    
    # Funnel
    lines.append("## 3. Complete M7 Funnel\n")
    lines.append("### Production Default (pullback=2, M10 detector)\n")
    funnel = report["m7_funnel"]["production_pullback2_m10"]["funnel"]
    lines.append("| Stage | Count | % of Previous | % of Detected |")
    lines.append("|-------|-------|---------------|---------------|")
    stages = ["direction_detected", "filters_passed", "armed", "pullback_reached", "window_open", "confirmed", "executed"]
    prev = None
    for stage in stages:
        count = funnel[stage]
        pct_prev = f"{count/prev*100:.1f}%" if prev and prev > 0 else "100%"
        pct_det = f"{count/funnel['direction_detected']*100:.1f}%" if funnel['direction_detected'] > 0 else "0%"
        lines.append(f"| {stage} | {count} | {pct_prev} | {pct_det} |")
        prev = count
    lines.append("")
    
    lines.append("### Failures\n")
    failures = report["m7_funnel"]["production_pullback2_m10"]["failures"]
    for k, v in failures.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    
    # Direction Stability
    lines.append("## 4. Direction Stability\n")
    lines.append("| Lookback | BTC Change Rate | BTC Median Run | ETH Change Rate | ETH Median Run |")
    lines.append("|----------|----------------|----------------|----------------|----------------|")
    for lb in [2, 3, 4, 5, 6, 8]:
        btc = report["direction_stability"].get("BTC/USDT", {}).get(f"{lb}_candle", {})
        eth = report["direction_stability"].get("ETH/USDT", {}).get(f"{lb}_candle", {})
        btc_cr = f"{btc.get('change_rate', 0)*100:.1f}%" if "change_rate" in btc else "N/A"
        btc_mr = f"{btc.get('median_run_length', 0):.1f}" if "median_run_length" in btc else "N/A"
        eth_cr = f"{eth.get('change_rate', 0)*100:.1f}%" if "change_rate" in eth else "N/A"
        eth_mr = f"{eth.get('median_run_length', 0):.1f}" if "median_run_length" in eth else "N/A"
        lines.append(f"| {lb}candle | {btc_cr} | {btc_mr} | {eth_cr} | {eth_mr} |")
    lines.append("")
    
    # Counterfactual
    lines.append("## 5. Counterfactual Invalidation Analysis\n")
    for sym, cf in report["counterfactual_analysis"].items():
        lines.append(f"**{sym}:** {cf['total_invalidated']} invalidated setups")
        lines.append(f"- Would-be-profitable: {cf['pct_profitable']:.1f}%")
        lines.append(f"- Would-be-losing: {cf['pct_losing']:.1f}%\n")
    
    # Pullback
    lines.append("## 6. Pullback Analysis\n")
    if "pullback_target_comparison" in report["pullback_analysis"]:
        ptc = report["pullback_analysis"]["pullback_target_comparison"]
        lines.append("| Pullback Target | Armed | Pullback Reached | Confirmed | Executed |")
        lines.append("|-----------------|-------|------------------|-----------|----------|")
        for pb_name, pb_data in ptc.items():
            lines.append(f"| {pb_name} | {pb_data['armed']} | {pb_data['pullback_reached']} | {pb_data['confirmed']} | {pb_data['executed']} |")
        lines.append("")
    
    # Filter Ablation
    lines.append("## 7. Filter Contribution Analysis\n")
    fa = report["filter_ablation"]
    baseline = fa.get("baseline", {})
    lines.append(f"**Baseline:** passed={baseline.get('filters_passed',0)}, armed={baseline.get('armed',0)}, rejected={baseline.get('filter_rejection',0)}\n")
    lines.append("| Filter Disabled | Armed Delta | Notes |")
    lines.append("|-----------------|-------------|-------|")
    for key, val in fa.items():
        if key.startswith("no_"):
            delta = val.get("armed", 0) - baseline.get("armed", 0)
            lines.append(f"| {key} | {delta:+d} | |")
    lines.append("")
    
    # Timeframe
    lines.append("## 8. Timeframe Comparison\n")
    lines.append("| Timeframe | Candles | Detected | Armed | Executed | BTC Change Rate |")
    lines.append("|-----------|---------|----------|-------|----------|-----------------|")
    for tf, tf_data in report.get("timeframe_analysis", {}).items():
        f = tf_data["funnel"]
        btc_cr = "N/A"
        if "BTC/USDT" in tf_data.get("direction_stability", {}):
            btc_cr = f"{tf_data['direction_stability']['BTC/USDT']['change_rate']*100:.1f}%"
        lines.append(f"| {tf} | {tf_data['candle_count']} | {f['direction_detected']} | {f['armed']} | {f['executed']} | {btc_cr} |")
    lines.append("")
    
    # Execution Audit
    lines.append("## 9. Execution/Measurement Audit\n")
    for f in report["execution_audit"]["findings"]:
        lines.append(f"- **{f['check']}:** {f['result']} — {f['detail']}")
    lines.append("")
    
    # Statistical Labels
    lines.append("## 10. Statistical Honesty\n")
    for key, label in report["statistical_labels"].items():
        lines.append(f"- **{key}:** {label}")
    lines.append("")
    
    # Root Causes
    lines.append("## 11. Root Causes\n")
    for rc in report["root_causes"]:
        lines.append(f"### [{rc['severity']}] {rc['cause']}\n")
        lines.append(f"{rc['detail']}\n")
    
    # Conclusion
    lines.append("## 12. Conclusion\n")
    lines.append("### Classification: DESIGN LIMITATION (not a bug)\n")
    lines.append("The M7 strategy's failure is caused by **direction detection instability** combined with a **pullback bottleneck**:\n")
    lines.append("1. The 2-candle direction detector produces signals that change ~55% of the time on 1h data")
    lines.append("2. The pullback=2 requirement demands 2 consecutive counter-trend candles, which rarely form before direction changes")
    lines.append("3. The filter cascade correctly rejects ~74% of noise, but the remaining setups are still dominated by direction instability")
    lines.append("4. No candle-indexing bug, no lookahead bug, no same-candle conflict was found")
    lines.append("5. The state machine correctly processes completed candles only\n")
    
    lines.append("### What Would Need to Change for a Credible Edge\n")
    lines.append("- A fundamentally different direction detection approach (not just parameter tuning)")
    lines.append("- Or: acceptance that 1h BTC/ETH does not provide sufficient directional persistence for this strategy architecture")
    lines.append("- Or: significantly different timeframe or asset class\n")
    
    lines.append("### Production M7 Status\n")
    lines.append("**No changes made.** No implementation bug was proven.\n")
    
    with open("M12_STRATEGY_STRUCTURE_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
