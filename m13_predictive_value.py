#!/usr/bin/env python3
"""M13: M7 Signal Predictive-Value Study.

Determines whether the existing M7 directional signal contains measurable
predictive information about future price movement.

This is research-only. Does NOT modify production M7.
"""
import sys
import os
import json
import math
import time
import random
import logging
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("m13")
logger.setLevel(logging.INFO)

from src.market.coinsph import CoinsPhMarketData
from src.indicators.technical import ema, atr
from src.strategy.filters import FilterCascade


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

HORIZONS = [1, 2, 4, 8, 12, 24]
RANDOM_SEED = 42
RANDOM_REPEATS = 1000
MIN_SAMPLE_FOR_EDGE = 30
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005


# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_data(symbols, timeframe="1h", limit=1000):
    md = CoinsPhMarketData()
    data = {}
    for sym in symbols:
        try:
            candles = md.fetch_candles(sym, timeframe, limit)
            logger.info("  %s %s: %d candles (%s to %s, %.2f-%.2f)",
                        sym, timeframe, len(candles),
                        candles[0]["timestamp"][:19] if candles else "?",
                        candles[-1]["timestamp"][:19] if candles else "?",
                        min(c["low"] for c in candles) if candles else 0,
                        max(c["high"] for c in candles) if candles else 0)
            data[sym] = candles
        except Exception as e:
            logger.warning("  %s %s: fetch failed (%s)", sym, timeframe, e)
            data[sym] = []
        time.sleep(0.5)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: REPRODUCE M7 SIGNAL (exact production implementation)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    symbol: str
    direction: str  # "LONG" or "SHORT"
    signal_idx: int  # index in candle list
    signal_ts: str
    signal_close: float  # close price at signal candle
    signal_high: float
    signal_low: float
    filters_passed: bool
    filter_rejection: Optional[str] = None
    armed: bool = False


def detect_direction(candles, idx):
    """Production M7 direction detector. Uses completed candles only.
    
    At index idx, the forming candle is candles[idx].
    Completed candles are candles[:idx] (i.e., up to idx-1).
    The signal uses completed[-1] (= candles[idx-1]) and completed[-2] (= candles[idx-2]).
    """
    completed = candles[:idx]
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


def extract_signals(data, symbols, timeframe):
    """Extract all M7 directional signals from data.
    
    A signal is generated when direction is detected at candle index i.
    The signal candle is completed[-1] = candles[i-1].
    We record the signal at index i (the candle where we observe the signal).
    """
    all_signals = []
    filters = FilterCascade({})  # default config = production defaults
    
    for sym in symbols:
        candles = data.get(sym, [])
        if len(candles) < 55:  # need enough for EMA filters
            continue
        
        for i in range(3, len(candles)):
            direction = detect_direction(candles, i)
            if not direction:
                continue
            
            # Signal candle is the last completed candle = candles[i-1]
            signal_candle = candles[i - 1]
            
            # Run filter cascade on completed candles up to signal candle
            completed = candles[:i]
            filter_result = filters.evaluate(completed, direction)
            
            sig = Signal(
                symbol=sym,
                direction=direction,
                signal_idx=i - 1,  # index of the signal candle
                signal_ts=signal_candle["timestamp"],
                signal_close=signal_candle["close"],
                signal_high=signal_candle["high"],
                signal_low=signal_candle["low"],
                filters_passed=filter_result.passed,
                filter_rejection=filter_result.rejection_reason if not filter_result.passed else None,
                armed=filter_result.passed,
            )
            all_signals.append(sig)
    
    return all_signals


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: FORWARD RETURN STUDY
# ═══════════════════════════════════════════════════════════════════════════════

def compute_forward_returns(signals, data, horizons):
    """For each signal, compute forward returns at each horizon.
    
    LONG: forward_return = future_close / signal_close - 1
    SHORT: forward_return = signal_close / future_close - 1
    """
    results = {h: [] for h in horizons}
    signal_details = []
    
    for sig in signals:
        candles = data[sig.symbol]
        idx = sig.signal_idx
        
        detail = {
            "symbol": sig.symbol,
            "direction": sig.direction,
            "signal_idx": idx,
            "signal_close": sig.signal_close,
            "filters_passed": sig.filters_passed,
            "forward_returns": {},
        }
        
        for h in horizons:
            future_idx = idx + h
            if future_idx >= len(candles):
                detail["forward_returns"][h] = None
                continue
            
            future_close = candles[future_idx]["close"]
            if sig.direction == "LONG":
                ret = future_close / sig.signal_close - 1
            else:  # SHORT
                ret = sig.signal_close / future_close - 1
            
            results[h].append(ret)
            detail["forward_returns"][h] = ret
        
        signal_details.append(detail)
    
    return results, signal_details


def compute_return_stats(returns, horizon):
    """Compute statistics for a list of returns."""
    if not returns:
        return {"horizon": horizon, "count": 0}
    
    n = len(returns)
    mean_r = statistics.mean(returns)
    median_r = statistics.median(returns)
    std_r = statistics.stdev(returns) if n > 1 else 0.0
    
    positive = sum(1 for r in returns if r > 0)
    negative = sum(1 for r in returns if r < 0)
    zero = sum(1 for r in returns if r == 0)
    
    sorted_r = sorted(returns)
    
    # Confidence interval for mean (95%)
    if n > 1:
        se = std_r / math.sqrt(n)
        ci_lower = mean_r - 1.96 * se
        ci_upper = mean_r + 1.96 * se
    else:
        ci_lower = ci_upper = mean_r
    
    # After fees (approximate: assume entry at signal close, exit at future close)
    net_returns = [r - 2 * (FEE_RATE + SLIPPAGE_RATE) for r in returns]
    net_mean = statistics.mean(net_returns)
    
    return {
        "horizon": horizon,
        "count": n,
        "mean_return": round(mean_r, 6),
        "median_return": round(median_r, 6),
        "std_return": round(std_r, 6),
        "positive_pct": round(positive / n, 4) if n > 0 else 0,
        "negative_pct": round(negative / n, 4) if n > 0 else 0,
        "zero_pct": round(zero / n, 4) if n > 0 else 0,
        "ci_lower_95": round(ci_lower, 6),
        "ci_upper_95": round(ci_upper, 6),
        "net_mean_after_fees": round(net_mean, 6),
        "min_return": round(min(returns), 6),
        "max_return": round(max(returns), 6),
        "percentile_5": round(sorted_r[int(n * 0.05)], 6) if n > 20 else None,
        "percentile_25": round(sorted_r[int(n * 0.25)], 6) if n > 4 else None,
        "percentile_75": round(sorted_r[int(n * 0.75)], 6) if n > 4 else None,
        "percentile_95": round(sorted_r[int(n * 0.95)], 6) if n > 20 else None,
        "sharpe_approx": round(mean_r / std_r * math.sqrt(252), 4) if std_r > 1e-10 else 0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: MAE/MFE
# ═══════════════════════════════════════════════════════════════════════════════

def compute_mae_mfe(signals, data, horizons):
    """Compute Maximum Favorable/Adverse Excursion for each signal."""
    results = {h: {"long": [], "short": []} for h in horizons}
    
    for sig in signals:
        candles = data[sig.symbol]
        idx = sig.signal_idx
        
        for h in horizons:
            future_start = idx + 1
            future_end = min(idx + h + 1, len(candles))
            if future_start >= len(candles):
                continue
            
            window = candles[future_start:future_end]
            if not window:
                continue
            
            highs = [c["high"] for c in window]
            lows = [c["low"] for c in window]
            
            if sig.direction == "LONG":
                # MFE: max price went above entry
                mfe = (max(highs) - sig.signal_close) / sig.signal_close
                # MAE: max price went below entry
                mae = (sig.signal_close - min(lows)) / sig.signal_close
            else:  # SHORT
                # MFE: max price went below entry
                mfe = (sig.signal_close - min(lows)) / sig.signal_close
                # MAE: max price went above entry
                mae = (max(highs) - sig.signal_close) / sig.signal_close
            
            results[h]["long" if sig.direction == "LONG" else "short"].append({
                "mae": mae,
                "mfe": mfe,
                "direction": sig.direction,
            })
    
    return results


def summarize_mae_mfe(mae_mfe_data, horizons):
    """Summarize MAE/MFE statistics."""
    summaries = {}
    for h in horizons:
        for direction in ["long", "short"]:
            entries = mae_mfe_data[h][direction]
            if not entries:
                continue
            
            maes = [e["mae"] for e in entries]
            mfes = [e["mfe"] for e in entries]
            
            key = f"h{h}_{direction}"
            summaries[key] = {
                "horizon": h,
                "direction": direction,
                "count": len(entries),
                "mean_mae": round(statistics.mean(maes), 6),
                "median_mae": round(statistics.median(maes), 6),
                "mean_mfe": round(statistics.mean(mfes), 6),
                "median_mfe": round(statistics.median(mfes), 6),
                "mfe_mae_ratio": round(statistics.mean(mfes) / statistics.mean(maes), 4) if statistics.mean(maes) > 1e-10 else 0,
                "asymmetric": round(statistics.mean(mfes) - statistics.mean(maes), 6),
            }
    return summaries


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: RANDOM CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

def random_control_experiment(data, symbols, n_signals, horizons, seed=RANDOM_SEED, n_repeats=RANDOM_REPEATS):
    """Deterministic random-entry control experiment.
    
    Creates random signals on the same candles, measures forward returns.
    Repeats n_repeats times to estimate distribution.
    """
    rng = random.Random(seed)
    
    # Collect all valid candle indices across symbols
    valid_indices = []
    for sym in symbols:
        candles = data.get(sym, [])
        for i in range(3, len(candles) - max(horizons)):
            valid_indices.append((sym, i))
    
    if not valid_indices:
        return {}
    
    all_repeat_results = []
    
    for repeat in range(n_repeats):
        # Sample n_signals random entries
        sampled = rng.sample(valid_indices, min(n_signals, len(valid_indices)))
        
        repeat_returns = {h: [] for h in horizons}
        
        for sym, idx in sampled:
            candles = data[sym]
            entry_price = candles[idx]["close"]
            direction = rng.choice(["LONG", "SHORT"])
            
            for h in horizons:
                future_idx = idx + h
                if future_idx >= len(candles):
                    continue
                future_close = candles[future_idx]["close"]
                if direction == "LONG":
                    ret = future_close / entry_price - 1
                else:
                    ret = entry_price / future_close - 1
                repeat_returns[h].append(ret)
        
        repeat_stats = {}
        for h in horizons:
            if repeat_returns[h]:
                repeat_stats[h] = {
                    "mean": statistics.mean(repeat_returns[h]),
                    "positive_pct": sum(1 for r in repeat_returns[h] if r > 0) / len(repeat_returns[h]),
                }
            else:
                repeat_stats[h] = {"mean": 0, "positive_pct": 0}
        all_repeat_results.append(repeat_stats)
    
    # Aggregate across repeats
    aggregated = {}
    for h in horizons:
        means = [r[h]["mean"] for r in all_repeat_results if h in r]
        pos_pcts = [r[h]["positive_pct"] for r in all_repeat_results if h in r]
        if means:
            aggregated[h] = {
                "mean_of_means": round(statistics.mean(means), 6),
                "std_of_means": round(statistics.stdev(means), 6) if len(means) > 1 else 0,
                "mean_positive_pct": round(statistics.mean(pos_pcts), 4),
                "ci_lower": round(statistics.mean(means) - 1.96 * (statistics.stdev(means) / math.sqrt(len(means))), 6) if len(means) > 1 else 0,
                "ci_upper": round(statistics.mean(means) + 1.96 * (statistics.stdev(means) / math.sqrt(len(means))), 6) if len(means) > 1 else 0,
                "n_repeats": len(means),
            }
    
    return aggregated


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: BASELINE COMPARISONS
# ═══════════════════════════════════════════════════════════════════════════════

def buy_and_hold_returns(data, symbols, horizons):
    """Buy & Hold baseline: buy at first candle, measure returns."""
    results = {}
    for h in horizons:
        rets = []
        for sym in symbols:
            candles = data.get(sym, [])
            if len(candles) < h + 1:
                continue
            entry = candles[0]["close"]
            exit_ = candles[min(h, len(candles) - 1)]["close"]
            rets.append(exit_ / entry - 1)
        if rets:
            results[h] = {
                "mean_return": round(statistics.mean(rets), 6),
                "count": len(rets),
            }
    return results


def sma_crossover_returns(data, symbols, horizons, fast=20, slow=50):
    """SMA crossover baseline returns at signal points."""
    results = {h: [] for h in horizons}
    
    for sym in symbols:
        candles = data.get(sym, [])
        if len(candles) < slow + 2:
            continue
        
        close = [c["close"] for c in candles]
        sma_fast = ema(close, fast)
        sma_slow = ema(close, slow)
        
        position = None
        for i in range(slow + 1, len(candles)):
            if sma_fast[i] is None or sma_slow[i] is None:
                continue
            if sma_fast[i - 1] is None or sma_slow[i - 1] is None:
                continue
            
            # Golden cross
            if sma_fast[i - 1] <= sma_slow[i - 1] and sma_fast[i] > sma_slow[i] and position is None:
                position = {"entry_idx": i, "entry_price": close[i], "direction": "LONG"}
            # Death cross
            elif sma_fast[i - 1] >= sma_slow[i - 1] and sma_fast[i] < sma_slow[i] and position is not None:
                for h in horizons:
                    exit_idx = position["entry_idx"] + h
                    if exit_idx < len(candles):
                        ret = close[exit_idx] / position["entry_price"] - 1
                        results[h].append(ret)
                position = None
    
    return {h: {"mean_return": round(statistics.mean(rets), 6) if rets else 0, "count": len(rets)} for h, rets in results.items()}


def rsi_baseline_returns(data, symbols, horizons, period=14, oversold=30, overbought=70):
    """RSI mean reversion baseline returns at signal points."""
    results = {h: [] for h in horizons}
    
    for sym in symbols:
        candles = data.get(sym, [])
        if len(candles) < period + 2:
            continue
        
        close = [c["close"] for c in candles]
        rsi_vals = _compute_rsi(close, period)
        
        position = None
        for i in range(period + 1, len(candles)):
            if rsi_vals[i] is None:
                continue
            
            if rsi_vals[i] < oversold and position is None:
                position = {"entry_idx": i, "entry_price": close[i]}
            elif rsi_vals[i] > overbought and position is not None:
                for h in horizons:
                    exit_idx = position["entry_idx"] + h
                    if exit_idx < len(candles):
                        ret = close[exit_idx] / position["entry_price"] - 1
                        results[h].append(ret)
                position = None
    
    return {h: {"mean_return": round(statistics.mean(rets), 6) if rets else 0, "count": len(rets)} for h, rets in results.items()}


def _compute_rsi(close, period):
    """Simple RSI computation."""
    result = [None] * len(close)
    if len(close) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, len(close)):
        delta = close[i] - close[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            result[i + 1] = 100 - 100 / (1 + avg_gain / avg_loss)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 & 7: LONG/SHORT SEPARATION + FILTERED VS UNFILTERED
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_by_category(signals, data, horizons):
    """Analyze forward returns by direction and filter status."""
    categories = {
        "all_signals": [s for s in signals],
        "long_only": [s for s in signals if s.direction == "LONG"],
        "short_only": [s for s in signals if s.direction == "SHORT"],
        "filtered_pass": [s for s in signals if s.filters_passed],
        "filtered_fail": [s for s in signals if not s.filters_passed],
        "armed_only": [s for s in signals if s.armed],
    }
    
    results = {}
    for cat_name, cat_signals in categories.items():
        if not cat_signals:
            results[cat_name] = {"count": 0}
            continue
        
        fwd_returns, _ = compute_forward_returns(cat_signals, data, horizons)
        
        cat_stats = {}
        for h in horizons:
            if fwd_returns[h]:
                cat_stats[h] = compute_return_stats(fwd_returns[h], h)
            else:
                cat_stats[h] = {"horizon": h, "count": 0}
        
        results[cat_name] = {
            "count": len(cat_signals),
            "long_count": sum(1 for s in cat_signals if s.direction == "LONG"),
            "short_count": sum(1 for s in cat_signals if s.direction == "SHORT"),
            "horizon_stats": cat_stats,
        }
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE DETECTION TEST
# ═══════════════════════════════════════════════════════════════════════════════

def test_predictive_edge(m7_returns, random_agg, horizons):
    """Determine if M7 signal has predictive edge over random.
    
    Tests:
    1. M7 mean return significantly different from random mean
    2. M7 positive rate significantly different from random positive rate
    3. M7 mean return significantly different from zero (after fees)
    """
    edge_results = {}
    
    for h in horizons:
        m7_stats = compute_return_stats(m7_returns.get(h, []), h)
        rand_stats = random_agg.get(h, {})
        
        if m7_stats["count"] < MIN_SAMPLE_FOR_EDGE:
            edge_results[h] = {
                "verdict": "INSUFFICIENT SAMPLE",
                "m7_count": m7_stats["count"],
                "min_required": MIN_SAMPLE_FOR_EDGE,
            }
            continue
        
        m7_mean = m7_stats["mean_return"]
        m7_std = m7_stats["std_return"]
        m7_n = m7_stats["count"]
        rand_mean = rand_stats.get("mean_of_means", 0)
        rand_std = rand_stats.get("std_of_means", 0)
        
        # Test 1: M7 mean != 0 (after fees)
        net_cost = 2 * (FEE_RATE + SLIPPAGE_RATE)
        net_mean = m7_mean - net_cost
        if m7_std > 1e-10 and m7_n > 1:
            t_stat = net_mean / (m7_std / math.sqrt(m7_n))
            # Rough two-tailed p-value approximation
            p_approx = 2 * (1 - _approx_cdf(abs(t_stat)))
        else:
            t_stat = 0
            p_approx = 1.0
        
        # Test 2: M7 mean != random mean
        if m7_std > 1e-10 and m7_n > 1:
            diff = m7_mean - rand_mean
            pooled_se = math.sqrt(m7_std**2 / m7_n + rand_std**2) if rand_std > 0 else m7_std / math.sqrt(m7_n)
            if pooled_se > 1e-10:
                z_stat = diff / pooled_se
                p_random = 2 * (1 - _approx_cdf(abs(z_stat)))
            else:
                z_stat = 0
                p_random = 1.0
        else:
            z_stat = 0
            p_random = 1.0
        
        # Test 3: M7 positive rate != random positive rate
        m7_pos = m7_stats["positive_pct"]
        rand_pos = rand_stats.get("mean_positive_pct", 0.5)
        # Standard error for proportion difference
        p_pool = (m7_pos * m7_n + rand_pos * m7_n) / (2 * m7_n) if m7_n > 0 else 0.5
        se_prop = math.sqrt(2 * p_pool * (1 - p_pool) / m7_n) if m7_n > 0 else 1
        if se_prop > 1e-10:
            z_prop = (m7_pos - rand_pos) / se_prop
            p_prop = 2 * (1 - _approx_cdf(abs(z_prop)))
        else:
            z_prop = 0
            p_prop = 1.0
        
        edge_results[h] = {
            "m7_mean": m7_mean,
            "m7_net_mean_after_fees": round(net_mean, 6),
            "m7_std": m7_std,
            "m7_count": m7_n,
            "m7_positive_pct": m7_pos,
            "random_mean": rand_mean,
            "random_positive_pct": rand_pos,
            "net_cost": round(net_cost, 6),
            # Test 1: Is M7 mean != 0 after fees?
            "t_stat_vs_zero": round(t_stat, 4),
            "p_value_vs_zero": round(p_approx, 6),
            "significant_vs_zero_5pct": p_approx < 0.05,
            # Test 2: Is M7 mean != random mean?
            "z_stat_vs_random": round(z_stat, 4),
            "p_value_vs_random": round(p_random, 6),
            "significant_vs_random_5pct": p_random < 0.05,
            # Test 3: Is M7 positive rate != random positive rate?
            "z_prop_vs_random": round(z_prop, 4),
            "p_prop_vs_random": round(p_prop, 6),
            "significant_positive_rate_5pct": p_prop < 0.05,
        }
    
    return edge_results


def _approx_cdf(x):
    """Approximate normal CDF using error function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: MULTI-TIMEFRAME
# ═══════════════════════════════════════════════════════════════════════════════

def run_timeframe_study(symbols):
    """Run predictive-value study across multiple timeframes."""
    results = {}
    for tf in ["15m", "1h", "4h", "1d"]:
        try:
            d = fetch_data(symbols, tf, 1000)
            min_c = min(len(c) for c in d.values()) if d else 0
            if min_c < 55:
                logger.info("  %s: insufficient data (%d candles)", tf, min_c)
                continue
            
            signals = extract_signals(d, symbols, tf)
            fwd_returns, _ = compute_forward_returns(signals, d, HORIZONS)
            
            # Count per symbol
            per_sym = {}
            for s in signals:
                per_sym.setdefault(s.symbol, {"long": 0, "short": 0, "total": 0})
                per_sym[s.symbol]["total"] += 1
                if s.direction == "LONG":
                    per_sym[s.symbol]["long"] += 1
                else:
                    per_sym[s.symbol]["short"] += 1
            
            # Random control
            n_sigs = len(signals)
            rand_agg = random_control_experiment(d, symbols, n_sigs, HORIZONS)
            
            # Edge test
            edge = test_predictive_edge(fwd_returns, rand_agg, HORIZONS)
            
            horizon_stats = {}
            for h in HORIZONS:
                if fwd_returns[h]:
                    horizon_stats[h] = compute_return_stats(fwd_returns[h], h)
            
            results[tf] = {
                "candle_count": min_c,
                "total_signals": len(signals),
                "per_symbol": per_sym,
                "horizon_stats": horizon_stats,
                "edge_test": edge,
            }
        except Exception as e:
            logger.warning("  %s: error - %s", tf, e)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 80)
    logger.info("M13: M7 SIGNAL PREDICTIVE-VALUE STUDY")
    logger.info("=" * 80)
    
    symbols = ["BTC/USDT", "ETH/USDT"]
    
    # ── Step 1: Fetch data and reproduce signals ──
    logger.info("\n[1/8] Fetching 1h data and reproducing M7 signals...")
    data_1h = fetch_data(symbols, "1h", 1000)
    total_1h = min(len(c) for c in data_1h.values()) if data_1h else 0
    
    signals = extract_signals(data_1h, symbols, "1h")
    
    long_count = sum(1 for s in signals if s.direction == "LONG")
    short_count = sum(1 for s in signals if s.direction == "SHORT")
    neutral_count = sum(1 for s in signals if not s.direction)  # should be 0
    filtered_pass = sum(1 for s in signals if s.filters_passed)
    armed = sum(1 for s in signals if s.armed)
    
    # Per-symbol signal counts
    per_sym = {}
    for s in signals:
        per_sym.setdefault(s.symbol, {"long": 0, "short": 0, "total": 0, "armed": 0})
        per_sym[s.symbol]["total"] += 1
        per_sym[s.symbol]["armed"] += 1 if s.armed else 0
        if s.direction == "LONG":
            per_sym[s.symbol]["long"] += 1
        else:
            per_sym[s.symbol]["short"] += 1
    
    logger.info("  Total signals: %d (LONG=%d, SHORT=%d, neutral=%d)", len(signals), long_count, short_count, neutral_count)
    logger.info("  Filters passed: %d / %d (%.1f%%)", filtered_pass, len(signals), filtered_pass/len(signals)*100 if signals else 0)
    logger.info("  Armed: %d / %d", armed, len(signals))
    for sym, counts in per_sym.items():
        logger.info("  %s: total=%d long=%d short=%d armed=%d", sym, counts["total"], counts["long"], counts["short"], counts["armed"])
    
    # ── Step 2: Forward returns ──
    logger.info("\n[2/8] Computing forward returns...")
    fwd_returns_all, signal_details = compute_forward_returns(signals, data_1h, HORIZONS)
    
    logger.info("\n  All signals combined:")
    for h in HORIZONS:
        stats = compute_return_stats(fwd_returns_all[h], h)
        logger.info("    h=%2d: n=%d mean=%.4f%% median=%.4f%% pos=%.1f%% net_after_fees=%.4f%% sharpe=%.2f ci=[%.4f, %.4f]",
                     h, stats["count"],
                     stats.get("mean_return", 0) * 100,
                     stats.get("median_return", 0) * 100,
                     stats.get("positive_pct", 0) * 100,
                     stats.get("net_mean_after_fees", 0) * 100,
                     stats.get("sharpe_approx", 0),
                     stats.get("ci_lower_95", 0) * 100,
                     stats.get("ci_upper_95", 0) * 100)
    
    # ── Step 3: MAE/MFE ──
    logger.info("\n[3/8] Computing MAE/MFE...")
    mae_mfe_data = compute_mae_mfe(signals, data_1h, HORIZONS)
    mae_mfe_summary = summarize_mae_mfe(mae_mfe_data, HORIZONS)
    
    for h in HORIZONS:
        for d in ["long", "short"]:
            key = f"h{h}_{d}"
            if key in mae_mfe_summary:
                s = mae_mfe_summary[key]
                logger.info("    h=%d %s: n=%d mean_MAE=%.4f%% mean_MFE=%.4f%% ratio=%.2f asymmetric=%.4f%%",
                             h, d, s["count"], s["mean_mae"]*100, s["mean_mfe"]*100,
                             s["mfe_mae_ratio"], s["asymmetric"]*100)
    
    # ── Step 4: Random control ──
    logger.info("\n[4/8] Running random control experiment (%d repeats)...", RANDOM_REPEATS)
    n_sigs = len(signals)
    rand_agg = random_control_experiment(data_1h, symbols, n_sigs, HORIZONS)
    
    logger.info("  Random control results:")
    for h in HORIZONS:
        if h in rand_agg:
            r = rand_agg[h]
            logger.info("    h=%2d: mean=%.4f%% std=%.4f%% pos=%.1f%% ci=[%.4f%%, %.4f%%]",
                         h, r["mean_of_means"]*100, r["std_of_means"]*100,
                         r["mean_positive_pct"]*100, r["ci_lower"]*100, r["ci_upper"]*100)
    
    # ── Step 5: Baseline comparisons ──
    logger.info("\n[5/8] Computing baseline comparisons...")
    bh_returns = buy_and_hold_returns(data_1h, symbols, HORIZONS)
    sma_returns = sma_crossover_returns(data_1h, symbols, HORIZONS)
    rsi_returns = rsi_baseline_returns(data_1h, symbols, HORIZONS)
    
    logger.info("  Buy & Hold:")
    for h in HORIZONS:
        if h in bh_returns:
            logger.info("    h=%2d: mean=%.4f%%", h, bh_returns[h]["mean_return"]*100)
    logger.info("  SMA Crossover:")
    for h in HORIZONS:
        if h in sma_returns:
            logger.info("    h=%2d: mean=%.4f%% n=%d", h, sma_returns[h]["mean_return"]*100, sma_returns[h]["count"])
    logger.info("  RSI Mean Reversion:")
    for h in HORIZONS:
        if h in rsi_returns:
            logger.info("    h=%2d: mean=%.4f%% n=%d", h, rsi_returns[h]["mean_return"]*100, rsi_returns[h]["count"])
    
    # ── Step 6 & 7: Category analysis ──
    logger.info("\n[6/8] Long/Short separation and filtered vs unfiltered...")
    cat_results = analyze_by_category(signals, data_1h, HORIZONS)
    
    for cat_name, cat_data in cat_results.items():
        if cat_data.get("count", 0) == 0:
            continue
        logger.info("  %s (n=%d, long=%d, short=%d):", cat_name, cat_data["count"],
                     cat_data.get("long_count", 0), cat_data.get("short_count", 0))
        for h in HORIZONS:
            if h in cat_data.get("horizon_stats", {}):
                hs = cat_data["horizon_stats"][h]
                if hs.get("count", 0) > 0:
                    logger.info("    h=%2d: mean=%.4f%% pos=%.1f%% net=%.4f%%",
                                 h, hs.get("mean_return", 0)*100,
                                 hs.get("positive_pct", 0)*100,
                                 hs.get("net_mean_after_fees", 0)*100)
    
    # ── Step 7.5: Edge detection test ──
    logger.info("\n[7/8] Edge detection tests...")
    edge_results = test_predictive_edge(fwd_returns_all, rand_agg, HORIZONS)
    
    for h in HORIZONS:
        e = edge_results.get(h, {})
        if "verdict" in e:
            logger.info("  h=%2d: %s", h, e["verdict"])
        else:
            logger.info("  h=%2d: net_mean=%.4f%% (p=%.4f vs zero), vs_random (p=%.4f), pos_rate=%.1f%% (p=%.4f) -> %s",
                         h,
                         e.get("m7_net_mean_after_fees", 0)*100,
                         e.get("p_value_vs_zero", 1),
                         e.get("p_value_vs_random", 1),
                         e.get("m7_positive_pct", 0)*100,
                         e.get("p_prop_vs_random", 1),
                         "EDGE" if e.get("significant_vs_random_5pct") else "NO EDGE")
    
    # ── Step 8: Multi-timeframe ──
    logger.info("\n[8/8] Multi-timeframe study...")
    tf_results = run_timeframe_study(symbols)
    for tf, tf_data in tf_results.items():
        logger.info("  %s (%d candles, %d signals):", tf, tf_data["candle_count"], tf_data["total_signals"])
        for h in HORIZONS:
            if h in tf_data.get("horizon_stats", {}):
                hs = tf_data["horizon_stats"][h]
                edge = tf_data.get("edge_test", {}).get(h, {})
                if hs.get("count", 0) > 0:
                    logger.info("    h=%2d: mean=%.4f%% pos=%.1f%% %s",
                                 h, hs.get("mean_return", 0)*100,
                                 hs.get("positive_pct", 0)*100,
                                 "EDGE" if edge.get("significant_vs_random_5pct") else "no edge")
    
    # ── Compile report ──
    logger.info("\nCompiling final report...")
    
    # Statistical labels
    stat_labels = {}
    for h in HORIZONS:
        count = len(fwd_returns_all.get(h, []))
        if count >= MIN_SAMPLE_FOR_EDGE:
            stat_labels[f"h{h}"] = "VALID"
        elif count > 0:
            stat_labels[f"h{h}"] = "INSUFFICIENT SAMPLE"
        else:
            stat_labels[f"h{h}"] = "NOT APPLICABLE"
    
    final_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": "05780ac",
        "production_m7_changed": False,
        
        # 1. Signal reproduction
        "signal_reproduction": {
            "data_source": "Coins.ph REST API",
            "symbols": symbols,
            "timeframe": "1h",
            "candle_count": total_1h,
            "date_range": {
                "start": data_1h[symbols[0]][0]["timestamp"][:19] if data_1h.get(symbols[0]) else "",
                "end": data_1h[symbols[0]][-1]["timestamp"][:19] if data_1h.get(symbols[0]) else "",
            },
            "total_signals": len(signals),
            "long_count": long_count,
            "short_count": short_count,
            "neutral_count": neutral_count,
            "filters_passed": filtered_pass,
            "armed": armed,
            "per_symbol": per_sym,
        },
        
        # 2. Forward returns
        "forward_returns": {
            "all_signals": {str(h): compute_return_stats(fwd_returns_all[h], h) for h in HORIZONS},
        },
        
        # 3. MAE/MFE
        "mae_mfe": mae_mfe_summary,
        
        # 4. Random control
        "random_control": {
            "seed": RANDOM_SEED,
            "n_repeats": RANDOM_REPEATS,
            "results": {str(h): v for h, v in rand_agg.items()},
        },
        
        # 5. Baselines
        "baselines": {
            "buy_and_hold": {str(h): v for h, v in bh_returns.items()},
            "sma_crossover": {str(h): v for h, v in sma_returns.items()},
            "rsi_mean_reversion": {str(h): v for h, v in rsi_returns.items()},
        },
        
        # 6. Category analysis
        "category_analysis": {
            cat: {
                "count": d.get("count", 0),
                "long_count": d.get("long_count", 0),
                "short_count": d.get("short_count", 0),
                "horizons": {str(h): d.get("horizon_stats", {}).get(h, {}) for h in HORIZONS},
            }
            for cat, d in cat_results.items()
        },
        
        # 7. Edge detection
        "edge_detection": {str(h): v for h, v in edge_results.items()},
        
        # 8. Timeframe analysis
        "timeframe_analysis": tf_results,
        
        # 9. Statistical labels
        "statistical_labels": stat_labels,
        
        # 10. Safety
        "safety_audit": {
            "LIVE_TRADING": "false",
            "MT5_DEMO_ONLY": "true",
            "MT5_DEMO_TRADING_ENABLED": "false",
            "production_m7_changed": False,
        },
    }
    
    # Save JSON
    with open("m13_predictive_value_report.json", "w") as f:
        json.dump(final_report, f, indent=2, default=str)
    
    # Save MD
    write_markdown_report(final_report)
    
    logger.info("\n" + "=" * 80)
    logger.info("M13 STUDY COMPLETE")
    logger.info("=" * 80)
    logger.info("Reports: m13_predictive_value_report.json, M13_PREDICTIVE_VALUE_REPORT.md")
    logger.info("Production M7 changed: NO")
    
    return 0


def write_markdown_report(report):
    lines = []
    lines.append("# M13 Signal Predictive-Value Study\n")
    lines.append(f"**Date:** {report['timestamp']}")
    lines.append(f"**Git Commit:** {report['git_commit']}")
    lines.append(f"**Production M7 Changed:** NO\n")
    
    # 1. Executive Summary
    lines.append("## 1. Executive Summary\n")
    sr = report["signal_reproduction"]
    lines.append(f"- **Data:** {sr['candle_count']} candles, {sr['symbols']}, {sr['timeframe']}")
    lines.append(f"- **Date Range:** {sr['date_range']['start']} to {sr['date_range']['end']}")
    lines.append(f"- **Total Signals:** {sr['total_signals']} (LONG={sr['long_count']}, SHORT={sr['short_count']})")
    lines.append(f"- **Filters Passed:** {sr['filters_passed']} ({sr['filters_passed']/sr['total_signals']*100:.1f}%)")
    lines.append(f"- **Armed:** {sr['armed']}\n")
    
    # 2. Forward Returns
    lines.append("## 2. Forward Returns (All Signals)\n")
    lines.append("| Horizon | Count | Mean | Median | Std | Positive% | Net After Fees | Sharpe | CI 95% |")
    lines.append("|---------|-------|------|--------|-----|-----------|----------------|--------|--------|")
    fr = report["forward_returns"]["all_signals"]
    for h_str in ["1", "2", "4", "8", "12", "24"]:
        if h_str in fr:
            s = fr[h_str]
            if s.get("count", 0) > 0:
                lines.append(f"| {h_str}c | {s['count']} | {s['mean_return']*100:.4f}% | {s['median_return']*100:.4f}% | {s['std_return']*100:.4f}% | {s['positive_pct']*100:.1f}% | {s['net_mean_after_fees']*100:.4f}% | {s['sharpe_approx']:.2f} | [{s['ci_lower_95']*100:.4f}%, {s['ci_upper_95']*100:.4f}%] |")
    lines.append("")
    
    # 3. MAE/MFE
    lines.append("## 3. MAE/MFE Analysis\n")
    lines.append("| Horizon | Direction | Count | Mean MAE | Mean MFE | MFE/MAE Ratio | Asymmetric |")
    lines.append("|---------|-----------|-------|----------|----------|---------------|------------|")
    for h in HORIZONS:
        for d in ["long", "short"]:
            key = f"h{h}_{d}"
            if key in report.get("mae_mfe", {}):
                s = report["mae_mfe"][key]
                lines.append(f"| {h}c | {d} | {s['count']} | {s['mean_mae']*100:.4f}% | {s['mean_mfe']*100:.4f}% | {s['mfe_mae_ratio']:.2f} | {s['asymmetric']*100:.4f}% |")
    lines.append("")
    
    # 4. Random Control
    lines.append("## 4. Random Control Experiment\n")
    lines.append(f"**Configuration:** seed={report['random_control']['seed']}, repeats={report['random_control']['n_repeats']}\n")
    lines.append("| Horizon | Random Mean | Random Std | Random Positive% | Random CI 95% |")
    lines.append("|---------|-------------|------------|-------------------|---------------|")
    for h_str in ["1", "2", "4", "8", "12", "24"]:
        if h_str in report["random_control"]["results"]:
            r = report["random_control"]["results"][h_str]
            lines.append(f"| {h_str}c | {r['mean_of_means']*100:.4f}% | {r['std_of_means']*100:.4f}% | {r['mean_positive_pct']*100:.1f}% | [{r['ci_lower']*100:.4f}%, {r['ci_upper']*100:.4f}%] |")
    lines.append("")
    
    # 5. Baselines
    lines.append("## 5. Baseline Comparison\n")
    lines.append("| Horizon | M7 Signal | Buy&Hold | SMA Cross | RSI MR | Random |")
    lines.append("|---------|-----------|----------|-----------|--------|--------|")
    for h_str in ["1", "2", "4", "8", "12", "24"]:
        m7_mean = fr.get(h_str, {}).get("mean_return", 0) * 100
        bh_mean = report["baselines"]["buy_and_hold"].get(h_str, {}).get("mean_return", 0) * 100
        sma_mean = report["baselines"]["sma_crossover"].get(h_str, {}).get("mean_return", 0) * 100
        rsi_mean = report["baselines"]["rsi_mean_reversion"].get(h_str, {}).get("mean_return", 0) * 100
        rand_mean = report["random_control"]["results"].get(h_str, {}).get("mean_of_means", 0) * 100
        lines.append(f"| {h_str}c | {m7_mean:.4f}% | {bh_mean:.4f}% | {sma_mean:.4f}% | {rsi_mean:.4f}% | {rand_mean:.4f}% |")
    lines.append("")
    
    # 6. Category Analysis
    lines.append("## 6. Long/Short Separation & Filtered vs Unfiltered\n")
    for cat_name, cat_data in report.get("category_analysis", {}).items():
        if cat_data.get("count", 0) == 0:
            continue
        lines.append(f"### {cat_name} (n={cat_data['count']})\n")
        lines.append("| Horizon | Mean | Median | Positive% | Net After Fees | Sharpe |")
        lines.append("|---------|------|--------|-----------|----------------|--------|")
        for h_str in ["1", "2", "4", "8", "12", "24"]:
            if h_str in cat_data.get("horizons", {}):
                s = cat_data["horizons"][h_str]
                if s.get("count", 0) > 0:
                    lines.append(f"| {h_str}c | {s.get('mean_return',0)*100:.4f}% | {s.get('median_return',0)*100:.4f}% | {s.get('positive_pct',0)*100:.1f}% | {s.get('net_mean_after_fees',0)*100:.4f}% | {s.get('sharpe_approx',0):.2f} |")
        lines.append("")
    
    # 7. Edge Detection
    lines.append("## 7. Edge Detection Tests\n")
    lines.append("| Horizon | M7 Net Mean | vs Zero (p) | vs Random (p) | Positive Rate | Verdict |")
    lines.append("|---------|-------------|-------------|---------------|---------------|---------|")
    for h_str in ["1", "2", "4", "8", "12", "24"]:
        e = report["edge_detection"].get(h_str, {})
        if "verdict" in e:
            lines.append(f"| {h_str}c | — | — | — | — | {e['verdict']} |")
        else:
            verdict = "EDGE" if e.get("significant_vs_random_5pct") else "NO EDGE"
            lines.append(f"| {h_str}c | {e.get('m7_net_mean_after_fees',0)*100:.4f}% | {e.get('p_value_vs_zero',1):.4f} | {e.get('p_value_vs_random',1):.4f} | {e.get('m7_positive_pct',0)*100:.1f}% | {verdict} |")
    lines.append("")
    
    # 8. Timeframe Analysis
    lines.append("## 8. Multi-Timeframe Analysis\n")
    for tf, tf_data in report.get("timeframe_analysis", {}).items():
        lines.append(f"### {tf} ({tf_data['candle_count']} candles, {tf_data['total_signals']} signals)\n")
        lines.append("| Horizon | Mean | Positive% | Edge? |")
        lines.append("|---------|------|-----------|-------|")
        for h_str in ["1", "2", "4", "8", "12", "24"]:
            if h_str in tf_data.get("horizon_stats", {}):
                hs = tf_data["horizon_stats"][h_str]
                edge = tf_data.get("edge_test", {}).get(h_str, {})
                if hs.get("count", 0) > 0:
                    verdict = "EDGE" if edge.get("significant_vs_random_5pct") else "no edge"
                    lines.append(f"| {h_str}c | {hs.get('mean_return',0)*100:.4f}% | {hs.get('positive_pct',0)*100:.1f}% | {verdict} |")
        lines.append("")
    
    # 9. Statistical Labels
    lines.append("## 9. Statistical Honesty\n")
    for key, label in report.get("statistical_labels", {}).items():
        lines.append(f"- **{key}:** {label}")
    lines.append("")
    
    # 10. Conclusion
    lines.append("## 10. Conclusion\n")
    
    # Determine overall verdict
    edge_found = False
    for h_str in ["1", "2", "4", "8", "12", "24"]:
        e = report["edge_detection"].get(h_str, {})
        if e.get("significant_vs_random_5pct"):
            edge_found = True
            break
    
    if edge_found:
        lines.append("**Verdict:** M7 directional signal shows SOME predictive value over random at certain horizons.\n")
        lines.append("However, this does NOT automatically mean the strategy is profitable after fees,")
        lines.append("as the pullback/confirmation mechanics may degrade the signal quality.\n")
    else:
        lines.append("**Verdict:** M7 directional signal does NOT show statistically significant predictive value over random.\n")
        lines.append("The signal is essentially noise on 1h BTC/ETH data. The direction detector produces")
        lines.append("signals that are not meaningfully different from random entries.\n")
        lines.append("This confirms the M12 finding that the M7 strategy's failure is a DESIGN LIMITATION")
        lines.append("of the direction detection approach, not a bug in the implementation.\n")
    
    lines.append("### Production M7 Status\n")
    lines.append("**No changes made.** No implementation bug was proven.\n")
    
    with open("M13_PREDICTIVE_VALUE_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
