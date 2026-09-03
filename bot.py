"""AshtradingAI CLI entry point."""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Config
from src.notifications.logger import setup_logging
from src.ai.test_strategy import TestStrategy
from src.ai.manager import AIManager
from src.market.candles import generate_synthetic_candles
from src.backtest.engine import BacktestEngine

logger = logging.getLogger("ashtradingai")


def cmd_backtest(args):
    """Run backtest with deterministic test strategy."""
    logger.info("Running backtest mode")
    ai = TestStrategy(ai_id="test-strategy")
    data = {sym: generate_synthetic_candles(symbol=sym, periods=500) for sym in Config.SYMBOLS}

    bt = BacktestEngine(
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
    )
    metrics, portfolio = bt.run(ai, data, Config.TIMEFRAME)
    m = metrics.summary()

    print("\n=== BACKTEST RESULTS ===")
    print(json.dumps(m, indent=2))
    print(f"\nTrades: {m['num_trades']} (W:{m['winning_trades']} L:{m['losing_trades']})")
    print(f"Return: {m['return_pct']:.2%}")
    print(f"Max Drawdown: {m['max_drawdown']:.2%}")
    print(f"Sharpe: {m['sharpe_ratio']:.4f}")
    print(f"Sortino: {m['sortino_ratio']:.4f}")


def cmd_paper(args):
    """Run paper trading demo."""
    logger.info("Running paper trading demo")
    ai = TestStrategy(ai_id="test-strategy")
    manager = AIManager(
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
    )
    manager.register_ai(ai)
    data = {sym: generate_synthetic_candles(symbol=sym, periods=500) for sym in Config.SYMBOLS}
    results = manager.run_competition(data, Config.TIMEFRAME)
    print("\n=== PAPER TRADING RESULTS ===")
    print(json.dumps(results, indent=2))


def cmd_status(args):
    """Show current configuration."""
    print("\n=== ASHTRADINGAI STATUS ===")
    print(f"LIVE_TRADING: {Config.LIVE_TRADING}")
    print(f"Environment:  {Config.APP_ENV}")
    print(f"Exchange:     {Config.EXCHANGE}")
    print(f"Symbols:      {Config.SYMBOLS}")
    print(f"Timeframe:    {Config.TIMEFRAME}")
    print(f"Balance:      ${Config.STARTING_BALANCE:,.2f}")
    print(f"Fee:          {Config.TRADING_FEE:.4f}")
    print(f"Slippage:     {Config.SLIPPAGE:.5f}")
    print(f"AI Provider:  {Config.AI_PROVIDER or '(none - using test strategy)'}")
    errors = Config.validate()
    if errors:
        print("\nCONFIG ERRORS:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\nConfig: OK")


def cmd_leaderboard(args):
    """Run competition and show leaderboard."""
    logger.info("Running AI competition")
    manager = AIManager(
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
    )
    manager.register_ai(TestStrategy(ai_id="RSI-Conservative"))
    manager.register_ai(TestStrategy(ai_id="RSI-Aggressive"))
    manager.register_ai(TestStrategy(ai_id="RSI-Balanced"))
    data = {sym: generate_synthetic_candles(symbol=sym, periods=500) for sym in Config.SYMBOLS}
    manager.run_competition(data, Config.TIMEFRAME)
    print("\n=== AI COMPETITION LEADERBOARD ===")
    print(manager.get_leaderboard())


def main():
    parser = argparse.ArgumentParser(description="AshtradingAI - AI Multi-Trader System")
    parser.add_argument("--mode", choices=["backtest", "paper", "status", "leaderboard"], default="status")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    setup_logging(level=args.log_level)

    errors = Config.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        if Config.LIVE_TRADING:
            logger.critical("LIVE_TRADING is enabled. Refusing to start.")
            sys.exit(1)

    cmd_map = {
        "backtest": cmd_backtest,
        "paper": cmd_paper,
        "status": cmd_status,
        "leaderboard": cmd_leaderboard,
    }
    cmd_map[args.mode](args)


if __name__ == "__main__":
    main()
