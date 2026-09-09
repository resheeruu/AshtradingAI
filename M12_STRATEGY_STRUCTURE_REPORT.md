# M12 Strategy Structure Investigation

**Date:** 2026-09-08T17:59:26.725445+00:00
**Git Commit:** 05780ac
**Production M7 Changed:** NO

## 1. Executive Summary

**Primary Bottleneck:** DIRECTION_INSTABILITY + PULLBACK_BOTTLENECK
**Edge Established:** False
**Root Causes:** PULLBACK_BOTTLENECK

The M7 strategy fails to establish a credible trading edge due to **direction instability** and a **pullback bottleneck**. The 2-candle direction detector changes direction ~55% of the time on 1h data, meaning armed setups are invalidated before pullback can form. With pullback=2 (production default), zero trades are executed across the full dataset. The failure is a **design limitation**, not a bug.

## 2. M9/M10/M11 Discrepancy Analysis

### Direction Rate Discrepancy

| Metric | M10 | M11 |
|--------|-----|-----|
| BTC direction change rate | 53.4% | 38.4% |
| Algorithm | Simple 2-candle comparison | N-candle majority-vote |

**Root Cause:** M10 and M11 use different direction detection algorithms. M10: simple 2-candle comparison. M11: N-candle majority-vote.

### Pullback=1 Trade Count Discrepancy

- M10 reports 1 trade for pullback=1
- M11 reports 26 trades for pullback=1
**Cause:** M11 uses different direction detector (majority-vote) which produces more stable signals, allowing more setups to survive to pullback confirmation.

## 3. Complete M7 Funnel

### Production Default (pullback=2, M10 detector)

| Stage | Count | % of Previous | % of Detected |
|-------|-------|---------------|---------------|
| direction_detected | 1286 | 100% | 100.0% |
| filters_passed | 367 | 28.5% | 28.5% |
| armed | 367 | 100.0% | 28.5% |
| pullback_reached | 0 | 0.0% | 0.0% |
| window_open | 0 | 100% | 0.0% |
| confirmed | 0 | 100% | 0.0% |
| executed | 0 | 100% | 0.0% |

### Failures

- **invalidation_in_armed:** 366
- **invalidation_in_window:** 0
- **filter_rejection:** 919
- **breakout_expired:** 0

## 4. Direction Stability

| Lookback | BTC Change Rate | BTC Median Run | ETH Change Rate | ETH Median Run |
|----------|----------------|----------------|----------------|----------------|
| 2candle | 38.4% | 2.0 | 38.2% | 2.0 |
| 3candle | 28.0% | 3.0 | 31.0% | 3.0 |
| 4candle | 23.1% | 4.0 | 22.2% | 4.0 |
| 5candle | 19.5% | 5.0 | 19.7% | 4.0 |
| 6candle | 16.7% | 5.0 | 16.3% | 5.0 |
| 8candle | 13.1% | 6.0 | 12.9% | 7.0 |

## 5. Counterfactual Invalidation Analysis

**BTC/USDT:** 183 invalidated setups
- Would-be-profitable: 47.5%
- Would-be-losing: 52.5%

**ETH/USDT:** 183 invalidated setups
- Would-be-profitable: 48.6%
- Would-be-losing: 51.4%

## 6. Pullback Analysis

| Pullback Target | Armed | Pullback Reached | Confirmed | Executed |
|-----------------|-------|------------------|-----------|----------|
| pullback_0 | 386 | 162 | 56 | 56 |
| pullback_1 | 367 | 4 | 1 | 1 |
| pullback_2 | 367 | 0 | 0 | 0 |
| pullback_3 | 367 | 0 | 0 | 0 |

## 7. Filter Contribution Analysis

**Baseline:** passed=367, armed=367, rejected=919

| Filter Disabled | Armed Delta | Notes |
|-----------------|-------------|-------|
| no_ATR | +0 | |
| no_EMA_Angle | +31 | |
| no_Price_EMA | +0 | |
| no_Candle | +0 | |
| no_EMA_Order | +139 | |
| no_Session | +0 | |

## 8. Timeframe Comparison

| Timeframe | Candles | Detected | Armed | Executed | BTC Change Rate |
|-----------|---------|----------|-------|----------|-----------------|
| 15m | 1000 | 1207 | 347 | 0 | 53.1% |
| 1h | 1000 | 1286 | 367 | 0 | 53.4% |
| 4h | 1000 | 1266 | 384 | 0 | 56.7% |
| 1d | 1000 | 1228 | 358 | 0 | 51.4% |

## 9. Execution/Measurement Audit

- **completed_candle_usage:** PASS — StrategyEngine.process_candle uses candles[:-1] as completed candles. candles[-1] is never used for signals.
- **lookahead_audit:** PASS — No lookahead: direction uses only completed[-1] and completed[-2]. Pullback uses completed[-target-1:-1]. Breakout uses completed[-1].
- **same_candle_conflict:** PASS — A candle cannot be both bullish and bearish. LONG requires close>open AND close>prev_close. SHORT requires close<open AND close<prev_close.
- **state_machine_single_path:** PASS — Phase-based dispatch: SCANNING -> ARMED -> WINDOW_OPEN -> ENTRY. Only one branch per candle.
- **candle_deduplication:** PASS — last_processed_candle tracks timestamp to prevent double-processing.
- **atr_calculation:** PASS — ATR uses Wilder smoothing on historical data. No future data used.
- **ema_calculation:** PASS — EMA uses standard recursive formula. No future data used.

## 10. Statistical Honesty

- **pullback_0:** VALID
- **pullback_1:** INSUFFICIENT SAMPLE
- **pullback_2:** NOT APPLICABLE
- **pullback_3:** NOT APPLICABLE

## 11. Root Causes

### [MEDIUM] FILTER_CASCADE

Filter cascade rejects 71.5% of direction signals (919/1286).

### [HIGH] PULLBACK_BOTTLENECK

All 367 armed setups invalidated before pullback. Median survival: 1.0 candles.

### [INFO] PULLBACK_REMOVAL_PRODUCES_TRADES

pullback=0 produces 56 trades but these may be noise. pullback=2 produces 0. The pullback requirement is the primary bottleneck.

### [INFO] M10_VS_M11_DISCREPANCY_EXPLAINED

M10 uses simple 2-candle comparison (close vs open AND vs prev_close): 53.4% change rate. M11 uses N-candle majority-vote (bullish_count > threshold AND first<last close): 38.4% change rate. Different algorithms produce different signals. M10 detects more direction changes because it requires less evidence per signal. M11 filters noise but also filters legitimate signals.

## 12. Conclusion

### Classification: DESIGN LIMITATION (not a bug)

The M7 strategy's failure is caused by **direction detection instability** combined with a **pullback bottleneck**:

1. The 2-candle direction detector produces signals that change ~55% of the time on 1h data
2. The pullback=2 requirement demands 2 consecutive counter-trend candles, which rarely form before direction changes
3. The filter cascade correctly rejects ~74% of noise, but the remaining setups are still dominated by direction instability
4. No candle-indexing bug, no lookahead bug, no same-candle conflict was found
5. The state machine correctly processes completed candles only

### What Would Need to Change for a Credible Edge

- A fundamentally different direction detection approach (not just parameter tuning)
- Or: acceptance that 1h BTC/ETH does not provide sufficient directional persistence for this strategy architecture
- Or: significantly different timeframe or asset class

### Production M7 Status

**No changes made.** No implementation bug was proven.
