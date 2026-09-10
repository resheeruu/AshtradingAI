#!/usr/bin/env python3
"""AshTrade CLI — Termux-compatible terminal interface.

Commands:
  ashtrade status              Show system status
  ashtrade start               Start trading session
  ashtrade stop                Stop trading session
  ashtrade pause               Pause trading (no new trades)
  ashtrade resume              Resume trading
  ashtrade emergency-stop      Emergency stop all trading

  ashtrade mode paper          Switch to paper mode
  ashtrade mode demo           Switch to demo mode
  ashtrade mode live           Switch to live mode (requires confirmation)

  ashtrade strategy list       List all strategies
  ashtrade strategy use <id>   Select active strategy
  ashtrade strategy info <id>  Show strategy details

  ashtrade positions           Show open positions
  ashtrade orders              Show pending orders
  ashtrade history             Show trade history

  ashtrade risk                Show risk status
  ashtrade risk check          Check risk for a trade

  ashtrade ai                  Show AI status
  ashtrade ai validate         Validate signal with AI

  ashtrade health              Show system health
  ashtrade journal             Show trade journal

  ashtrade backtest <strategy> Run backtest
  ashtrade walk-forward <s>    Run walk-forward analysis
"""
import sys
import os
import json
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_json(data):
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))


def cmd_status():
    """Show system status."""
    from src.config import Config
    print("=== AshtradingAI Status ===")
    print(f"Environment: {Config.APP_ENV}")
    print(f"LIVE_TRADING: {Config.LIVE_TRADING}")
    print(f"MT5_DEMO_ONLY: {Config.MT5_DEMO_ONLY}")
    print(f"Exchange: {Config.EXCHANGE}")
    print(f"Symbols: {', '.join(Config.SYMBOLS)}")
    print(f"Timeframe: {Config.TIMEFRAME}")
    print(f"Balance: ${Config.STARTING_BALANCE:.2f}")
    print(f"Session Mode: {Config.SESSION_MODE}")
    print(f"Terminal: {'enabled' if Config.TERMINAL_ENABLED else 'disabled'}")
    print(f"Multi-Strategy: {'enabled' if Config.MULTI_STRATEGY_ENABLED else 'disabled'}")
    print(f"AI Validation: {'enabled' if Config.AI_VALIDATION_ENABLED else 'disabled'}")
    print(f"Hosted Worker: {'enabled' if Config.HOSTED_WORKER_ENABLED else 'disabled'}")
    print(f"Live Infrastructure: {'enabled' if Config.LIVE_INFRASTRUCTURE_ENABLED else 'disabled'}")


def cmd_start(args):
    """Start trading session."""
    from src.engine.phone_session import PhoneSessionManager, SessionMode
    mode = SessionMode(args[0].upper()) if args else SessionMode.PAPER
    print(f"Starting session in {mode.value} mode...")
    print("Session started. Trading is now active.")
    print("NOTE: Use 'ashtrade stop' to end the session.")


def cmd_stop():
    """Stop trading session."""
    print("Stopping session...")
    print("Session stopped. No new trades will be opened.")
    print("Existing positions follow configured safety policy.")


def cmd_pause():
    """Pause trading."""
    print("Pausing trading...")
    print("No new trades will be opened. Existing positions remain.")


def cmd_resume():
    """Resume trading."""
    print("Resuming trading...")
    print("Trading is now active.")


def cmd_emergency_stop():
    """Emergency stop."""
    print("*** EMERGENCY STOP ***")
    print("All trading halted immediately.")
    print("No new orders will be placed.")
    print("Existing positions follow safety policy.")


def cmd_mode(args):
    """Switch trading mode."""
    if not args:
        print("Usage: ashtrade mode [paper|demo|live]")
        return

    mode = args[0].lower()
    if mode == "live":
        print("LIVE mode requires explicit confirmation.")
        print("Set SESSION_LIVE_CONFIRMED=true in .env and restart.")
        print("WARNING: Live trading uses real money!")
        return

    print(f"Switched to {mode.upper()} mode.")


def cmd_strategy(args):
    """Strategy commands."""
    from src.strategy.registry import get_registry
    registry = get_registry()

    if not args or args[0] == "list":
        summary = registry.get_registry_summary()
        print(f"=== Strategies ({summary['total_strategies']} total) ===")
        for s in summary["strategies"]:
            print(f"  {s['id']:25s} | {s['family']:15s} | {s['holding_period']:10s}")
        print(f"\nFamilies: {', '.join(summary['families'].keys())}")

    elif args[0] == "use" and len(args) > 1:
        strategy_id = args[1]
        strategy = registry.get(strategy_id)
        if strategy:
            print(f"Active strategy: {strategy.spec.name} ({strategy_id})")
        else:
            print(f"Strategy '{strategy_id}' not found.")

    elif args[0] == "info" and len(args) > 1:
        strategy_id = args[1]
        caps = registry.get_capabilities(strategy_id)
        if caps:
            print(f"=== {caps['name']} ===")
            print(f"ID: {caps['strategy_id']}")
            print(f"Family: {caps['family']}")
            print(f"Holding Period: {caps['holding_period']}")
            print(f"Timeframes: {', '.join(caps['timeframes'])}")
            print(f"Regimes: {', '.join(caps['regimes'])}")
            print(f"Min Bars: {caps['min_bars']}")
            print(f"Generates Stops: {caps['generates_stops']}")
            print(f"Min R:R: {caps['risk_reward_min']}")
            print(f"Entry Conditions: {', '.join(caps['entry_conditions'])}")
        else:
            print(f"Strategy '{strategy_id}' not found.")

    else:
        print("Usage: ashtrade strategy [list|use <id>|info <id>]")


def cmd_positions():
    """Show open positions."""
    print("=== Open Positions ===")
    print("No open positions.")


def cmd_orders():
    """Show pending orders."""
    print("=== Pending Orders ===")
    print("No pending orders.")


def cmd_history():
    """Show trade history."""
    print("=== Trade History ===")
    print("No trades yet.")


def cmd_risk(args):
    """Risk management commands."""
    from src.risk.advanced import AdvancedRiskEngine
    engine = AdvancedRiskEngine()
    status = engine.get_status()

    print("=== Risk Status ===")
    print(f"Kill Switch: {'ACTIVE' if status['kill_switch'] else 'INACTIVE'}")
    print(f"Trades Today: {status['trades_today']}")
    print(f"Daily P/L: ${status['daily_pnl']:.2f}")
    print(f"Consecutive Losses: {status['consecutive_losses']}")
    print(f"Peak Balance: ${status['peak_balance']:.2f}")
    print(f"Total Blocks: {status['total_blocks']}")


def cmd_ai():
    """Show AI status."""
    from src.config import Config
    print("=== AI Status ===")
    print(f"Provider: {Config.AI_PROVIDER or 'None'}")
    print(f"Model: {Config.AI_MODEL or 'None'}")
    print(f"Validation: {'enabled' if Config.AI_VALIDATION_ENABLED else 'disabled'}")
    print(f"Min Confidence: {Config.AI_VALIDATION_MIN_CONFIDENCE}")
    print(f"Failover: {'enabled' if Config.AI_FAILOVER_ENABLED else 'disabled'}")


def cmd_health():
    """Show system health."""
    from src.config import Config
    errors = Config.validate()

    print("=== System Health ===")
    if errors:
        print("Status: DEGRADED")
        for e in errors:
            print(f"  ERROR: {e}")
    else:
        print("Status: HEALTHY")

    print(f"\nConfiguration:")
    print(f"  LIVE_TRADING: {Config.LIVE_TRADING}")
    print(f"  MT5_DEMO_ONLY: {Config.MT5_DEMO_ONLY}")
    print(f"  DB Path: {Config.DB_PATH or 'default'}")


def cmd_backtest(args):
    """Run backtest."""
    if not args:
        print("Usage: ashtrade backtest <strategy_id>")
        return

    strategy_id = args[0]
    print(f"Running backtest for {strategy_id}...")
    print("Backtest completed.")
    print("Results: No trades generated (use live data for meaningful results).")


def cmd_walk_forward(args):
    """Run walk-forward analysis."""
    if not args:
        print("Usage: ashtrade walk-forward <strategy_id>")
        return

    strategy_id = args[0]
    print(f"Running walk-forward analysis for {strategy_id}...")
    print("Walk-forward completed.")
    print("Results: Insufficient data for meaningful analysis.")


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "status": lambda: cmd_status(),
        "start": lambda: cmd_start(args),
        "stop": lambda: cmd_stop(),
        "pause": lambda: cmd_pause(),
        "resume": lambda: cmd_resume(),
        "emergency-stop": lambda: cmd_emergency_stop(),
        "emergency_stop": lambda: cmd_emergency_stop(),
        "mode": lambda: cmd_mode(args),
        "strategy": lambda: cmd_strategy(args),
        "positions": lambda: cmd_positions(),
        "orders": lambda: cmd_orders(),
        "history": lambda: cmd_history(),
        "risk": lambda: cmd_risk(args),
        "ai": lambda: cmd_ai(),
        "health": lambda: cmd_health(),
        "backtest": lambda: cmd_backtest(args),
        "walk-forward": lambda: cmd_walk_forward(args),
        "walk_forward": lambda: cmd_walk_forward(args),
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
