#!/usr/bin/env python3
"""M9: Real Historical Data Validation for M7 Strategy.

Fetches real BTC/USDT and ETH/USDT 1h candles from Coins.ph API,
runs M7 strategy and baselines, calculates metrics.
"""
import sys
import os
import json
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("m9_validation")

from src.market.coinsph import CoinsPhMarketData
from src.backtest.m7_backtest import M7BacktestEngine, run_walk_forward
from src.backtest.engine import BacktestEngine, BacktestMetrics, compute_metrics
from src.backtest.baselines import BuyAndHold, SMACrossover, RSIMeanReversion
from src.backtest.robustness import RobustnessLab
from src.ai.test_strategy import TestStrategy
from src.portfolio.portfolio import Portfolio


def fetch_real_data(symbols, timeframe="1h", limit=2000):
    """Fetch real historical data from Coins.ph API."""
    md = CoinsPhMarketData()
    data = {}
    for sym in symbols:
        logger.info("Fetching %s %s candles (limit=%d)...", sym, timeframe, limit)
        candles = md.fetch_candles(sym, timeframe, limit)
        logger.info("  Got %d candles for %s", len(candles), sym)
        if candles:
            first_ts = candles[0]["timestamp"]
            last_ts = candles[-1]["timestamp"]
            logger.info("  Range: %s to %s", first_ts[:19], last_ts[:19])
            logger.info("  Price range: %.2f - %.2f", 
                        min(c["low"] for c in candles), 
                        max(c["high"] for c in candles))
        data[sym] = candles
    return data


def run_m7_detailed(data, timeframe="1h"):
    """Run M7 backtest with detailed instrumentation."""
    ai = TestStrategy(ai_id="m9-test")
    engine = M7BacktestEngine(
        starting_balance=10000.0,
        fee=0.001,
        slippage=0.0005,
        max_position_size=0.10,
        max_open_positions=3,
        max_daily_loss=0.03,
        max_drawdown=0.15,
        min_confidence=0.60,
        risk_percent=0.01,
    )
    
    logger.info("Running M7 backtest...")
    metrics, portfolio = engine.run(ai, data, timeframe)
    
    # Detailed summary
    summary = metrics.summary()
    logger.info("=== M7 Backtest Results ===")
    logger.info("Standard metrics: %s", json.dumps(summary["standard"], indent=2))
    logger.info("State stats: %s", json.dumps(summary["state_stats"], indent=2))
    logger.info("AI stats: %s", json.dumps(summary["ai_stats"], indent=2))
    logger.info("Per-symbol: %s", json.dumps(summary["per_symbol"], indent=2))
    
    return metrics, portfolio


def run_baselines(data, timeframe="1h"):
    """Run all baseline strategies on identical data."""
    results = {}
    
    for name, StrategyClass in [
        ("BuyAndHold", BuyAndHold),
        ("SMACrossover", SMACrossover),
        ("RSIMeanReversion", RSIMeanReversion),
    ]:
        logger.info("Running %s...", name)
        ai = StrategyClass()
        
        # Use BacktestEngine (not M7) for baselines
        engine = BacktestEngine(
            starting_balance=10000.0,
            fee=0.001,
            slippage=0.0005,
        )
        
        metrics, portfolio = engine.run(ai, data, timeframe)
        summary = metrics.summary()
        logger.info("  %s: trades=%d, return=%.4f, sharpe=%.4f", 
                    name, summary["num_trades"], summary["return_pct"], summary["sharpe_ratio"])
        results[name] = {"metrics": metrics, "portfolio": portfolio}
    
    return results


def run_robustness(data, timeframe="1h"):
    """Run robustness lab on real historical data."""
    logger.info("Running RobustnessLab...")
    ai = TestStrategy(ai_id="m9-robustness")
    lab = RobustnessLab(seed=42)
    
    # Walk-forward validation
    logger.info("Running walk-forward validation...")
    wf_result = lab.rolling_walk_forward(
        ai, data, timeframe,
        train_pct=0.6, test_pct=0.2, step_pct=0.1,
        starting_balance=10000.0, fee=0.001, slippage=0.0005,
    )
    
    # Sensitivity analysis
    logger.info("Running sensitivity analysis...")
    sensitivity = lab.parameter_sensitivity(
        ai, data, timeframe,
        param_name="risk_percent", base_value=0.01,
        starting_balance=10000.0, fee=0.001, slippage=0.0005,
    )
    
    # Monte Carlo simulation (needs trades from M7 run)
    logger.info("Running Monte Carlo simulation...")
    m7_engine = M7BacktestEngine(
        starting_balance=10000.0, fee=0.001, slippage=0.0005,
    )
    m7_metrics, portfolio = m7_engine.run(ai, data, timeframe)
    mc_results = lab.monte_carlo(portfolio.trade_history, n_simulations=1000)
    
    # Compute robustness score
    robustness_score = lab.compute_robustness_score(wf_result, mc_results, m7_metrics.standard)
    
    return {
        "walk_forward": wf_result.summary(),
        "sensitivity": sensitivity.summary(),
        "monte_carlo": mc_results.summary(),
        "robustness_score": robustness_score,
    }


def generate_report(m7_metrics, baseline_results, robustness_results, data):
    """Generate comprehensive validation report."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_quality": {},
        "m7_results": {},
        "baseline_results": {},
        "robustness": {},
        "verdict": "UNKNOWN",
    }
    
    # Data quality
    for sym, candles in data.items():
        report["data_quality"][sym] = {
            "candle_count": len(candles),
            "first_candle": candles[0]["timestamp"] if candles else None,
            "last_candle": candles[-1]["timestamp"] if candles else None,
            "price_range": {
                "low": min(c["low"] for c in candles) if candles else 0,
                "high": max(c["high"] for c in candles) if candles else 0,
            },
        }
    
    # M7 results
    m7_summary = m7_metrics.summary()
    report["m7_results"] = m7_summary
    
    # Baseline results
    for name, result in baseline_results.items():
        report["baseline_results"][name] = result["metrics"].summary()
    
    # Robustness
    report["robustness"] = robustness_results
    
    # Determine verdict
    m7_trades = m7_summary["standard"]["num_trades"]
    m7_return = m7_summary["standard"]["return_pct"]
    
    if m7_trades < 10:
        report["verdict"] = "INSUFFICIENT DATA - fewer than 10 trades"
    elif m7_return <= 0:
        report["verdict"] = "STRATEGY NOT PROFITABLE - negative return"
    else:
        # Check if M7 beats buy-and-hold
        bh_return = report["baseline_results"].get("BuyAndHold", {}).get("return_pct", 0)
        if m7_return > bh_return:
            report["verdict"] = "STRATEGY VALIDATED - outperforms buy-and-hold"
        else:
            report["verdict"] = "STRATEGY UNDERPERFORMS - buy-and-hold is better"
    
    return report


def main():
    """Main validation entry point."""
    logger.info("=" * 80)
    logger.info("M9: Real Historical Data Validation for M7 Strategy")
    logger.info("=" * 80)
    
    # Step 1: Fetch real historical data
    symbols = ["BTC/USDT", "ETH/USDT"]
    timeframe = "1h"
    limit = 2000  # Max available from Coins.ph
    
    data = fetch_real_data(symbols, timeframe, limit)
    
    # Check if we got enough data
    for sym, candles in data.items():
        if len(candles) < 100:
            logger.warning("Insufficient data for %s: %d candles (need ≥100)", sym, len(candles))
    
    # Step 2: Run M7 with detailed instrumentation
    m7_metrics, m7_portfolio = run_m7_detailed(data, timeframe)
    
    # Step 3: Run baselines
    baseline_results = run_baselines(data, timeframe)
    
    # Step 4: Run robustness analysis
    robustness_results = run_robustness(data, timeframe)
    
    # Step 5: Generate report
    report = generate_report(m7_metrics, baseline_results, robustness_results, data)
    
    # Save report
    report_path = "m9_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Report saved to %s", report_path)
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)
    logger.info("Data quality:")
    for sym, stats in report["data_quality"].items():
        logger.info("  %s: %d candles", sym, stats["candle_count"])
    
    m7_summary = report["m7_results"]["standard"]
    logger.info("\nM7 performance:")
    logger.info("  Trades: %d", m7_summary["num_trades"])
    logger.info("  Return: %.2f%%", m7_summary["return_pct"] * 100)
    logger.info("  Sharpe: %.4f", m7_summary["sharpe_ratio"])
    logger.info("  Max Drawdown: %.2f%%", m7_summary["max_drawdown"] * 100)
    
    logger.info("\nBaseline comparisons:")
    for name, metrics in report["baseline_results"].items():
        logger.info("  %s: trades=%d, return=%.2f%%, sharpe=%.4f", 
                    name, metrics["num_trades"], metrics["return_pct"] * 100, metrics["sharpe_ratio"])
    
    logger.info("\nVerdict: %s", report["verdict"])
    
    return 0 if "VALIDATED" in report["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
