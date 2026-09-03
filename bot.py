"""AshtradingAI CLI entry point."""
import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Config
from src.notifications.logger import setup_logging
from src.ai.test_strategy import TestStrategy
from src.ai.manager import AIManager
from src.ai.health import ProviderHealthManager
from src.market.candles import generate_synthetic_candles
from src.market.data import MarketData
from src.persistence.database import Database
from src.tournament.engine import TournamentEngine, TournamentConfig
from src.tournament.participant import load_participants_from_env, ParticipantConfig
from src.tournament.leaderboard import format_leaderboard
from src.tournament.metrics import TournamentMetrics, compute_tournament_metrics, compute_composite_score, assign_awards

logger = logging.getLogger("ashtradingai")


def _get_database() -> Database:
    """Initialize and return the database connection."""
    db_path = Path(Config.DB_PATH) if Config.DB_PATH else None
    db = Database(db_path=db_path)
    db.connect()
    return db


def _get_health_manager() -> ProviderHealthManager:
    """Initialize and return the health manager from config."""
    config = {
        "cooldown_seconds": Config.AI_COOLDOWN_SECONDS,
        "max_failures_before_cooldown": Config.AI_MAX_FAILURES_BEFORE_COOLDOWN,
        "max_cooldown_seconds": Config.AI_MAX_COOLDOWN_SECONDS,
        "cache_max_size": Config.AI_CACHE_MAX_SIZE,
        "cache_ttl_seconds": Config.AI_CACHE_TTL_SECONDS,
        "failover_enabled": Config.AI_FAILOVER_ENABLED,
        "failover_targets": [],
    }
    if Config.AI_FALLBACK_PROVIDER and Config.AI_FALLBACK_MODEL:
        config["failover_targets"] = [{
            "provider": Config.AI_FALLBACK_PROVIDER,
            "model": Config.AI_FALLBACK_MODEL,
        }]
    return ProviderHealthManager(config)


def _fetch_live_data(exchange: str, symbols: list, timeframe: str, limit: int) -> dict:
    """Fetch live market data for all symbols."""
    md = MarketData(exchange_id=exchange)
    data = {}
    for sym in symbols:
        logger.info("Fetching %s candles for %s...", limit, sym)
        candles = md.fetch_candles(sym, timeframe, limit)
        if candles:
            data[sym] = candles
            logger.info("Got %d candles for %s", len(candles), sym)
        else:
            logger.warning("No data for %s, using synthetic fallback", sym)
            data[sym] = generate_synthetic_candles(symbol=sym, periods=limit)
    return data


def cmd_backtest(args):
    """Run backtest with deterministic test strategy."""
    logger.info("Running backtest mode")

    ai = TestStrategy(ai_id="test-strategy")

    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    from src.backtest.engine import BacktestEngine
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

    # Persist if configured
    experiment_id = Config.EXPERIMENT_ID or str(uuid.uuid4())[:8]
    db = None
    try:
        db = _get_database()
        db.log_backtest_run(
            ai_id="test-strategy",
            symbol=",".join(Config.SYMBOLS),
            timeframe=Config.TIMEFRAME,
            starting_balance=m["starting_balance"],
            ending_balance=m["ending_balance"],
            return_percent=m["return_pct"],
            max_drawdown=m["max_drawdown"],
            win_rate=m["win_rate"],
            profit_factor=m["profit_factor"],
            sharpe_ratio=m["sharpe_ratio"],
            sortino_ratio=m["sortino_ratio"],
            trade_count=m["num_trades"],
            experiment_id=experiment_id,
            metrics_json=str(m),
        )
        for trade in portfolio.trade_history:
            db.log_trade(
                ai_id="test-strategy",
                symbol=trade.symbol,
                side=trade.side,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                quantity=trade.quantity,
                fee=trade.fee,
                slippage=trade.slippage,
                pnl=trade.pnl,
                balance=portfolio.balance,
                experiment_id=experiment_id,
            )
        logger.info("Results saved to database (experiment=%s)", experiment_id)
    except Exception as e:
        logger.warning("Could not persist results: %s", e)
    finally:
        if db:
            db.close()

    print("\n=== BACKTEST RESULTS ===")
    print(json.dumps(m, indent=2))
    print(f"\nTrades: {m['num_trades']} (W:{m['winning_trades']} L:{m['losing_trades']})")
    print(f"Return: {m['return_pct']:.2%}")
    print(f"Max Drawdown: {m['max_drawdown']:.2%}")
    print(f"Sharpe: {m['sharpe_ratio']:.4f}")
    print(f"Sortino: {m['sortino_ratio']:.4f}")
    print(f"Experiment ID: {experiment_id}")


def cmd_paper(args):
    """Run paper trading demo."""
    logger.info("Running paper trading demo")
    ai = TestStrategy(ai_id="test-strategy")

    db = None
    try:
        db = _get_database()
    except Exception:
        pass

    manager = AIManager(
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        database=db,
    )
    manager.register_ai(ai)

    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    experiment_id = Config.EXPERIMENT_ID or str(uuid.uuid4())[:8]
    results = manager.run_competition(data, Config.TIMEFRAME, experiment_id=experiment_id)

    if db:
        db.close()

    print("\n=== PAPER TRADING RESULTS ===")
    print(json.dumps(results, indent=2))
    print(f"\nExperiment ID: {experiment_id}")


def cmd_status(args):
    """Show current configuration and provider health."""
    print("\n=== ASHTRADINGAI STATUS ===")
    print(f"LIVE_TRADING: {Config.LIVE_TRADING}")
    print(f"Environment:  {Config.APP_ENV}")
    print(f"Exchange:     {Config.EXCHANGE}")
    print(f"Symbols:      {Config.SYMBOLS}")
    print(f"Timeframe:    {Config.TIMEFRAME}")
    print(f"Candle Limit: {Config.CANDLE_LIMIT}")
    print(f"Balance:      ${Config.STARTING_BALANCE:,.2f}")
    print(f"Fee:          {Config.TRADING_FEE:.4f}")
    print(f"Slippage:     {Config.SLIPPAGE:.5f}")
    print(f"Data Source:  {Config.DATA_SOURCE}")
    print(f"AI Provider:  {Config.AI_PROVIDER or '(none - using test strategy)'}")
    if Config.AI_PARTICIPANTS:
        print(f"Participants: {Config.AI_PARTICIPANTS}")
    if Config.AI_BASE_URL:
        print(f"AI Base URL:  {Config.AI_BASE_URL}")
    
    # Resilience configuration
    print(f"\n--- Resilience ---")
    print(f"Failover:     {'enabled' if Config.AI_FAILOVER_ENABLED else 'disabled'}")
    print(f"Cache:        {'enabled' if Config.AI_CACHE_ENABLED else 'disabled'} (max: {Config.AI_CACHE_MAX_SIZE}, ttl: {Config.AI_CACHE_TTL_SECONDS}s)")
    print(f"Cooldown:     {Config.AI_COOLDOWN_SECONDS}s (max: {Config.AI_MAX_COOLDOWN_SECONDS}s, failures: {Config.AI_MAX_FAILURES_BEFORE_COOLDOWN})")
    if Config.AI_DAILY_TOKEN_LIMIT > 0:
        print(f"Daily Tokens: {Config.AI_DAILY_TOKEN_LIMIT:,}")
    if Config.AI_DAILY_REQUEST_LIMIT > 0:
        print(f"Daily Reqs:   {Config.AI_DAILY_REQUEST_LIMIT:,}")
    if Config.AI_FALLBACK_PROVIDER:
        print(f"Fallback:     {Config.AI_FALLBACK_PROVIDER}/{Config.AI_FALLBACK_MODEL}")
    
    # Show provider health from database
    db = None
    try:
        db = _get_database()
        health_summary = db.get_provider_health_summary()
        if health_summary:
            print(f"\n--- Provider Health ---")
            for h in health_summary:
                state = h.get("state", "UNKNOWN")
                provider = h.get("provider", "unknown")
                model = h.get("model", "unknown")
                failures = h.get("failure_count", 0)
                successes = h.get("success_count", 0)
                last_error = h.get("last_error", "")
                print(f"  {provider}/{model}: {state} (F:{failures} S:{successes})")
                if last_error:
                    print(f"    Last error: {last_error[:80]}")
        
        usage_summary = db.get_provider_usage_summary()
        if usage_summary:
            print(f"\n--- Provider Usage ---")
            for u in usage_summary:
                provider = u.get("provider", "unknown")
                model = u.get("model", "unknown")
                total = u.get("total_requests", 0)
                tokens = u.get("total_tokens", 0)
                success = u.get("successful", 0)
                failed = u.get("failed", 0)
                print(f"  {provider}/{model}: {total} reqs, {tokens:,} tokens (OK:{success} FAIL:{failed})")
    except Exception as e:
        logger.debug("Could not load provider health: %s", e)
    finally:
        if db:
            db.close()
    
    errors = Config.validate()
    if errors:
        print("\nCONFIG ERRORS:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\nConfig: OK")


def cmd_leaderboard(args):
    """Run competition and show leaderboard from SQLite or live run."""
    experiment_id = Config.EXPERIMENT_ID or str(uuid.uuid4())[:8]
    logger.info("Running AI competition (experiment=%s)", experiment_id)

    db = None
    try:
        db = _get_database()
    except Exception:
        pass

    manager = AIManager(
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        database=db,
    )
    manager.register_ai(TestStrategy(ai_id="RSI-Conservative"))
    manager.register_ai(TestStrategy(ai_id="RSI-Aggressive"))
    manager.register_ai(TestStrategy(ai_id="RSI-Balanced"))

    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    manager.run_competition(data, Config.TIMEFRAME, experiment_id=experiment_id)

    print("\n=== AI COMPETITION LEADERBOARD ===")
    print(f"Experiment: {experiment_id}")
    print(manager.get_leaderboard())

    # Show additional rankings from database
    if db:
        lb_data = db.get_leaderboard_data(experiment_id)
        if lb_data:
            print("\n=== DATABASE LEADERBOARD ===")
            print(f"{'AI':<20} {'Start':>10} {'End':>10} {'Return':>10} {'WinRate':>10} {'MaxDD':>10} {'Sharpe':>10} {'Sortino':>10}")
            print("-" * 100)
            for r in sorted(lb_data, key=lambda x: x.get("sharpe_ratio", 0), reverse=True):
                print(
                    f"{r['ai_id']:<20} "
                    f"${r['starting_balance']:>9,.2f} "
                    f"${r['ending_balance']:>9,.2f} "
                    f"{r['return_percent']:>9.2%} "
                    f"{r['win_rate']:>9.2%} "
                    f"{r['max_drawdown']:>9.2%} "
                    f"{r['sharpe_ratio']:>10.4f} "
                    f"{r['sortino_ratio']:>10.4f}"
                )
        db.close()


def cmd_tournament(args):
    """Run multi-AI tournament with candle-by-candle execution."""
    if Config.LIVE_TRADING:
        logger.critical("LIVE_TRADING is enabled. Tournament refuses to start.")
        sys.exit(1)

    experiment_id = Config.EXPERIMENT_ID or str(uuid.uuid4())[:8]
    logger.info("Starting tournament (experiment=%s)", experiment_id)

    # Load participants from env or defaults
    participants = load_participants_from_env()
    available = [p for p in participants if p.is_available]
    if not available:
        logger.error("No available participants. Check AI_PARTICIPANTS and API keys.")
        print("ERROR: No available AI participants. Configure AI_PARTICIPANTS and API keys.")
        sys.exit(1)

    print(f"\n=== AI TRADING TOURNAMENT ===")
    print(f"Experiment: {experiment_id}")
    print(f"Participants: {', '.join(p.id for p in available)}")
    print(f"Exchange: {Config.EXCHANGE}")
    print(f"Symbols: {Config.SYMBOLS}")
    print(f"Timeframe: {Config.TIMEFRAME}")
    print(f"Candles: {Config.CANDLE_LIMIT}")
    print(f"Starting Balance: ${Config.STARTING_BALANCE:,.2f}")
    print(f"Fee: {Config.TRADING_FEE:.4f}")
    print(f"Slippage: {Config.SLIPPAGE:.5f}")
    print()

    # Load market data
    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    # Create tournament config
    t_config = TournamentConfig(
        experiment_id=experiment_id,
        exchange=Config.EXCHANGE,
        symbols=Config.SYMBOLS,
        timeframe=Config.TIMEFRAME,
        candle_limit=Config.CANDLE_LIMIT,
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
    )

    # Run tournament
    db = None
    health_manager = None
    try:
        db = _get_database()
    except Exception:
        pass

    try:
        health_manager = _get_health_manager()
    except Exception:
        pass

    engine = TournamentEngine(config=t_config, database=db, health_manager=health_manager)
    result = engine.run(participants=available, data=data)

    # Log tournament metadata
    if db:
        try:
            db.log_tournament(
                experiment_id=experiment_id,
                exchange=Config.EXCHANGE,
                symbols=",".join(Config.SYMBOLS),
                timeframe=Config.TIMEFRAME,
                candle_limit=Config.CANDLE_LIMIT,
                starting_balance=Config.STARTING_BALANCE,
                fee=Config.TRADING_FEE,
                slippage=Config.SLIPPAGE,
                software_version=t_config.software_version,
                participant_count=len(available),
                config_json=json.dumps(t_config.__dict__),
            )
        except Exception as e:
            logger.warning("Could not log tournament metadata: %s", e)

    if db:
        db.close()

    # Display results
    if "error" in result:
        print(f"\nTOURNAMENT ERROR: {result['error']}")
        sys.exit(1)

    # Build metrics objects for leaderboard
    metrics_list = []
    for p_data in result["participants"]:
        m = TournamentMetrics()
        for k, v in p_data.items():
            if hasattr(m, k):
                setattr(m, k, v)
        m = compute_composite_score.__wrapped__(m) if hasattr(compute_composite_score, '__wrapped__') else m
        # Recompute composite score properly
        m.composite_score = p_data.get("composite_score", 0.0)
        m.awards = p_data.get("awards", [])
        metrics_list.append(m)

    print(format_leaderboard(metrics_list, experiment_id=experiment_id))
    print(f"\nDecision logs recorded: {result.get('decision_logs_count', 0)}")

    # Show provider health summary
    if health_manager:
        provider_summary = health_manager.get_provider_status_summary()
        if provider_summary:
            print("\n--- Provider Health ---")
            for p in provider_summary:
                print(f"  {p['provider']}/{p['model']}: {p['state']} "
                      f"(F:{p['total_failures']} S:{p['total_successes']})")


def cmd_tournament_backtest(args):
    """Run tournament backtest with test strategies on historical data."""
    if Config.LIVE_TRADING:
        logger.critical("LIVE_TRADING is enabled. Tournament refuses to start.")
        sys.exit(1)

    experiment_id = Config.EXPERIMENT_ID or str(uuid.uuid4())[:8]
    logger.info("Starting tournament backtest (experiment=%s)", experiment_id)

    # Use test strategies with different configurations
    test_participants = [
        ParticipantConfig(id="RSI-Conservative", provider="test"),
        ParticipantConfig(id="RSI-Aggressive", provider="test"),
        ParticipantConfig(id="RSI-Balanced", provider="test"),
    ]

    available = [p for p in test_participants if p.is_available]

    print(f"\n=== TOURNAMENT BACKTEST ===")
    print(f"Experiment: {experiment_id}")
    print(f"Participants: {', '.join(p.id for p in available)}")
    print(f"Exchange: {Config.EXCHANGE}")
    print(f"Symbols: {Config.SYMBOLS}")
    print(f"Timeframe: {Config.TIMEFRAME}")
    print(f"Candles: {Config.CANDLE_LIMIT}")
    print(f"Starting Balance: ${Config.STARTING_BALANCE:,.2f}")
    print()

    # Load market data (shared read-only)
    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    # Create tournament config
    t_config = TournamentConfig(
        experiment_id=experiment_id,
        exchange=Config.EXCHANGE,
        symbols=Config.SYMBOLS,
        timeframe=Config.TIMEFRAME,
        candle_limit=Config.CANDLE_LIMIT,
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
    )

    # Run tournament
    db = None
    health_manager = None
    try:
        db = _get_database()
    except Exception:
        pass

    try:
        health_manager = _get_health_manager()
    except Exception:
        pass

    engine = TournamentEngine(config=t_config, database=db, health_manager=health_manager)
    result = engine.run(participants=available, data=data)

    # Log tournament metadata
    if db:
        try:
            db.log_tournament(
                experiment_id=experiment_id,
                exchange=Config.EXCHANGE,
                symbols=",".join(Config.SYMBOLS),
                timeframe=Config.TIMEFRAME,
                candle_limit=Config.CANDLE_LIMIT,
                starting_balance=Config.STARTING_BALANCE,
                fee=Config.TRADING_FEE,
                slippage=Config.SLIPPAGE,
                software_version=t_config.software_version,
                participant_count=len(available),
                config_json=json.dumps(t_config.__dict__),
            )
        except Exception as e:
            logger.warning("Could not log tournament metadata: %s", e)

    if db:
        db.close()

    # Display results
    if "error" in result:
        print(f"\nTOURNAMENT ERROR: {result['error']}")
        sys.exit(1)

    # Build metrics objects for leaderboard
    metrics_list = []
    for p_data in result["participants"]:
        m = TournamentMetrics()
        for k, v in p_data.items():
            if hasattr(m, k):
                setattr(m, k, v)
        m.composite_score = p_data.get("composite_score", 0.0)
        m.awards = p_data.get("awards", [])
        metrics_list.append(m)

    print(format_leaderboard(metrics_list, experiment_id=experiment_id))
    print(f"\nDecision logs recorded: {result.get('decision_logs_count', 0)}")

    # Also show in-memory leaderboard
    print("\n=== BACKTEST SUMMARY ===")
    for p in metrics_list:
        print(f"  {p.ai_id}: Return={p.return_pct:+.2%}, DD={p.max_drawdown:.2%}, "
              f"Sharpe={p.sharpe_ratio:.4f}, Score={p.composite_score:.4f}")

    # Show provider health summary
    if health_manager:
        provider_summary = health_manager.get_provider_status_summary()
        if provider_summary:
            print("\n--- Provider Health ---")
            for p in provider_summary:
                print(f"  {p['provider']}/{p['model']}: {p['state']} "
                      f"(F:{p['total_failures']} S:{p['total_successes']})")


def main():
    parser = argparse.ArgumentParser(description="AshtradingAI - AI Multi-Trader Tournament System")
    parser.add_argument("--mode", choices=[
        "backtest", "paper", "status", "leaderboard",
        "tournament", "tournament-backtest",
    ], default="status")
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
        "tournament": cmd_tournament,
        "tournament-backtest": cmd_tournament_backtest,
    }
    cmd_map[args.mode](args)


if __name__ == "__main__":
    main()
