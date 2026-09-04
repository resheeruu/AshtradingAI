"""AshtradingAI CLI entry point."""
import argparse
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Config
from src.notifications.logger import setup_logging
from src.ai.test_strategy import TestStrategy
from src.ai.manager import AIManager
from src.ai.health import ProviderHealthManager
from src.market.candles import generate_synthetic_candles
from src.market.data import MarketData
from src.persistence.database import Database
from src.paper_live.engine import PaperLiveEngine, SOFTWARE_VERSION
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


def _fetch_live_data_strict(exchange: str, symbols: list, timeframe: str, limit: int) -> dict:
    """Fetch live market data — NO synthetic fallback. Returns empty dict on failure."""
    md = MarketData(exchange_id=exchange)
    data = {}
    for sym in symbols:
        logger.info("Fetching %s candles for %s...", limit, sym)
        candles = md.fetch_candles(sym, timeframe, limit)
        if candles:
            data[sym] = candles
            logger.info("Got %d candles for %s", len(candles), sym)
        else:
            logger.error("NO DATA for %s — refusing synthetic fallback in paper-live", sym)
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

    # MT5 configuration
    if Config.MT5_ENABLED:
        print(f"\n--- MT5 Configuration ---")
        print(f"  MT5 Enabled:          {Config.MT5_ENABLED}")
        print(f"  MT5 Demo Only:        {Config.MT5_DEMO_ONLY}")
        print(f"  MT5 Demo Trading:     {Config.MT5_DEMO_TRADING_ENABLED}")
        print(f"  MT5 Magic Number:     {Config.MT5_MAGIC_NUMBER}")
        if Config.MT5_EXPECTED_SERVER:
            print(f"  Expected Server:      {Config.MT5_EXPECTED_SERVER}")
        if Config.MT5_EXPECTED_LOGIN:
            print(f"  Expected Login:       {Config.MT5_EXPECTED_LOGIN}")
        if Config.MT5_SYMBOL_MAP:
            try:
                sm = json.loads(Config.MT5_SYMBOL_MAP)
                print(f"  Symbol Map:           {sm}")
            except json.JSONDecodeError:
                print(f"  Symbol Map:           (invalid JSON)")

    # M7 configuration
    if Config.M7_ENABLED:
        print(f"\n--- M7 Strategy ---")
        print(f"  M7 Enabled:           {Config.M7_ENABLED}")
        print(f"  ATR Filter:           {'ON' if Config.M7_ATR_FILTER_ENABLED else 'OFF'}")
        print(f"  Angle Filter:         {'ON' if Config.M7_ANGLE_FILTER_ENABLED else 'OFF'}")
        print(f"  Price/EMA:            {'ON' if Config.M7_PRICE_EMA_FILTER_ENABLED else 'OFF'}")
        print(f"  Candle Filter:        {'ON' if Config.M7_CANDLE_FILTER_ENABLED else 'OFF'}")
        print(f"  EMA Order:            {'ON' if Config.M7_EMA_ORDER_FILTER_ENABLED else 'OFF'}")
        print(f"  Session Filter:       {'ON' if Config.M7_SESSION_FILTER_ENABLED else 'OFF'}")
        print(f"  Pullback:             {Config.M7_PULLBACK_CANDLES} candles")
        print(f"  Breakout Window:      {Config.M7_BREAKOUT_WINDOW} candles")
        print(f"  Risk Percent:         {Config.M7_RISK_PERCENT:.1%}")
    
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

    # Show provider health summary
    if health_manager:
        provider_summary = health_manager.get_provider_status_summary()
        if provider_summary:
            print("\n--- Provider Health ---")
            for p in provider_summary:
                print(f"  {p['provider']}/{p['model']}: {p['state']} "
                      f"(F:{p['total_failures']} S:{p['total_successes']})")


def cmd_paper_live(args):
    """Run paper-live mode: real market data + simulated execution."""
    if Config.LIVE_TRADING:
        logger.critical("LIVE_TRADING is enabled. Paper-live refuses to start.")
        print("ERROR: LIVE_TRADING=true. Paper-live mode requires LIVE_TRADING=false.")
        sys.exit(1)

    session_id = Config.PAPER_SESSION_ID or str(uuid.uuid4())[:12]
    logger.info("Starting paper-live session (session=%s)", session_id)

    ai = TestStrategy(ai_id="paper-live-strategy")

    db = None
    try:
        db = _get_database()
    except Exception as e:
        logger.warning("Database unavailable: %s", e)

    if db and Config.PAPER_AUTO_RESUME:
        existing = db.get_active_paper_session(Config.EXCHANGE)
        if existing:
            session_id = existing["id"]
            logger.info("Resuming existing session %s", session_id)

    if db:
        existing = db.get_paper_session(session_id)
        if not existing:
            db.create_paper_session(
                session_id=session_id,
                exchange=Config.EXCHANGE,
                symbols=",".join(Config.SYMBOLS),
                timeframe=Config.TIMEFRAME,
                data_source="live",
                starting_balance=Config.STARTING_BALANCE,
                config_json=json.dumps(Config.as_dict()),
                software_version=SOFTWARE_VERSION,
            )

    health_manager = None
    try:
        health_manager = _get_health_manager()
    except Exception:
        pass

    engine = PaperLiveEngine(
        session_id=session_id,
        ai=ai,
        database=db,
        health_manager=health_manager,
        exchange=Config.EXCHANGE,
        symbols=Config.SYMBOLS,
        timeframe=Config.TIMEFRAME,
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        max_stale_seconds=Config.MARKET_MAX_STALE_SECONDS,
        retry_seconds=Config.MARKET_RETRY_SECONDS,
        heartbeat_seconds=Config.PAPER_HEARTBEAT_SECONDS,
        candle_limit=Config.CANDLE_LIMIT,
    )

    if Config.PAPER_AUTO_RESUME:
        engine.recover_from_db()

    engine.run()

    if db:
        db.close()


def cmd_paper_live_test(args):
    """Deterministic paper-live test using the real PaperLiveEngine with mocked market data."""
    if Config.LIVE_TRADING:
        logger.critical("LIVE_TRADING is enabled. Paper-live-test refuses to start.")
        sys.exit(1)

    print("=" * 40)
    print("  ASHTRADINGAI PAPER-LIVE-TEST MODE")
    print("=" * 40)
    print("  Testing REAL PaperLiveEngine with synthetic data")
    print("  Phases: market -> scheduler -> AI -> risk -> execution -> SQLite -> restart")
    print("=" * 40)

    session_id = "test-" + str(uuid.uuid4())[:8]
    ai = TestStrategy(ai_id="test-strategy")

    db = None
    try:
        db = _get_database()
    except Exception as e:
        logger.warning("Database unavailable: %s", e)

    if db:
        db.create_paper_session(
            session_id=session_id,
            exchange=Config.EXCHANGE,
            symbols=",".join(Config.SYMBOLS),
            timeframe=Config.TIMEFRAME,
            data_source="synthetic",
            starting_balance=Config.STARTING_BALANCE,
            config_json=json.dumps(Config.as_dict()),
            software_version=SOFTWARE_VERSION,
        )

    # Generate deterministic synthetic candles for all symbols
    print("\n--- Phase 1: Generate synthetic market data ---")
    synthetic_data: Dict[str, List[Dict]] = {}
    for sym in Config.SYMBOLS:
        candles = generate_synthetic_candles(symbol=sym, periods=100)
        synthetic_data[sym] = candles
        print(f"  {sym}: {len(candles)} candles generated")

    # Create a mock MarketData that returns our synthetic data
    from unittest.mock import MagicMock
    mock_market_data = MagicMock()
    mock_market_data.fetch_candles = MagicMock(side_effect=lambda sym, tf, limit=500: synthetic_data.get(sym, []))

    print("\n--- Phase 2: Run PaperLiveEngine with mock market data ---")
    engine = PaperLiveEngine(
        session_id=session_id,
        ai=ai,
        database=db,
        health_manager=None,
        exchange=Config.EXCHANGE,
        symbols=Config.SYMBOLS,
        timeframe=Config.TIMEFRAME,
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        max_stale_seconds=Config.MARKET_MAX_STALE_SECONDS,
        retry_seconds=Config.MARKET_RETRY_SECONDS,
        heartbeat_seconds=Config.PAPER_HEARTBEAT_SECONDS,
        candle_limit=Config.CANDLE_LIMIT,
    )
    # Inject mock market data
    engine.market_data = mock_market_data

    engine.start()
    # Process each symbol once through the real engine
    for sym in Config.SYMBOLS:
        engine._process_symbol(sym)
    trades_before = engine._trades_count
    balance_before = engine.portfolio.balance
    positions_before = dict(engine.portfolio.positions)
    print(f"  Trades executed: {trades_before}")
    print(f"  Balance: ${engine.portfolio.balance:,.2f}")
    print(f"  Open positions: {len(engine.portfolio.positions)}")

    print("\n--- Phase 3: Persist state to SQLite ---")
    engine._save_state()
    if db:
        session = db.get_paper_session(session_id)
        assert session is not None, "Session not found after save"
        print(f"  Session {session_id} saved to SQLite")

    print("\n--- Phase 4: Simulate restart recovery ---")
    # Create a new engine instance (simulates restart)
    recovered_ai = TestStrategy(ai_id="test-strategy")
    recovered_engine = PaperLiveEngine(
        session_id=session_id,
        ai=recovered_ai,
        database=db,
        health_manager=None,
        exchange=Config.EXCHANGE,
        symbols=Config.SYMBOLS,
        timeframe=Config.TIMEFRAME,
        starting_balance=Config.STARTING_BALANCE,
        fee=Config.TRADING_FEE,
        slippage=Config.SLIPPAGE,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        max_stale_seconds=Config.MARKET_MAX_STALE_SECONDS,
        retry_seconds=Config.MARKET_RETRY_SECONDS,
        heartbeat_seconds=Config.PAPER_HEARTBEAT_SECONDS,
        candle_limit=Config.CANDLE_LIMIT,
    )
    recovered_engine.market_data = mock_market_data

    # Recover state from database
    recovered = recovered_engine.recover_from_db()
    assert recovered, "Recovery failed"

    balance_match = abs(recovered_engine.portfolio.balance - balance_before) < 0.01
    positions_match = len(recovered_engine.portfolio.positions) == len(positions_before)
    trades_match = len(recovered_engine.portfolio.trade_history) == len(engine.portfolio.trade_history)

    # Verify per-symbol state recovery
    for sym in Config.SYMBOLS:
        orig_ts = engine.schedulers[sym].last_processed_candle
        rec_ts = recovered_engine.schedulers[sym].last_processed_candle
        if orig_ts and rec_ts:
            assert orig_ts == rec_ts, f"Per-symbol state mismatch for {sym}: {orig_ts} != {rec_ts}"

    print(f"  Balance recovered: ${recovered_engine.portfolio.balance:,.2f} (match: {balance_match})")
    print(f"  Positions recovered: {len(recovered_engine.portfolio.positions)} (match: {positions_match})")
    print(f"  Trades recovered: {len(recovered_engine.portfolio.trade_history)} (match: {trades_match})")

    # Verify no duplicate processing after restart
    recovered_engine._process_symbol(Config.SYMBOLS[0])
    assert recovered_engine._trades_count == 0, "Recovered engine should not reprocess candles"

    print("\n--- Phase 5: Verify safety ---")
    print(f"  LIVE_TRADING: {Config.LIVE_TRADING}")
    print(f"  Real orders: DISABLED")
    print(f"  Synthetic fallback: NOT USED in engine (data was provided by test)")
    safety_ok = not Config.LIVE_TRADING
    print(f"\n  SAFETY CHECK: {'PASS' if safety_ok else 'FAIL'}")

    if balance_match and positions_match and trades_match and safety_ok:
        print("\n  ALL PHASES: PASS")
    else:
        print("\n  SOME PHASES: FAIL")
        sys.exit(1)

    engine.stop()
    if db:
        db.close()

    print("\n" + "=" * 40)
    print("  PAPER-LIVE-TEST: ALL PHASES COMPLETE")
    print("=" * 40)


def cmd_mt5_demo(args):
    """Run MT5 demo trading mode: real MT5 terminal + demo account."""
    if Config.LIVE_TRADING:
        logger.critical("LIVE_TRADING is enabled. MT5-demo refuses to start.")
        print("ERROR: LIVE_TRADING=true. MT5-demo mode requires LIVE_TRADING=false.")
        sys.exit(1)

    if not Config.MT5_ENABLED:
        logger.critical("MT5_ENABLED is false. MT5-demo refuses to start.")
        print("ERROR: MT5_ENABLED=false. Set MT5_ENABLED=true to run MT5-demo mode.")
        sys.exit(1)

    if not Config.MT5_DEMO_ONLY:
        logger.critical("MT5_DEMO_ONLY is false. MT5-demo refuses to start.")
        print("ERROR: MT5_DEMO_ONLY=false. Demo mode requires MT5_DEMO_ONLY=true.")
        sys.exit(1)

    session_id = Config.PAPER_SESSION_ID or "mt5-demo-" + str(uuid.uuid4())[:8]
    logger.info("Starting MT5 demo session (session=%s)", session_id)

    print("=" * 50)
    print("  ASHTRADINGAI MT5 DEMO MODE")
    print("=" * 50)
    print("  REAL MT5 terminal + DEMO account ONLY")
    print("  No live trading. No live account bypass.")
    print("  Safety: MT5_DEMO_ONLY=true | LIVE_TRADING=false")
    print("=" * 50)

    # Lazy MT5 import
    try:
        from src.mt5.connection import MT5ConnectionManager
        from src.mt5.market_data import MT5MarketData
        from src.mt5.broker import MT5DemoBroker
        from src.mt5.health import MT5State
    except ImportError as e:
        logger.critical("Failed to import MT5 modules: %s", e)
        print(f"ERROR: MT5 import failed: {e}")
        print("Install MetaTrader5 package: pip install MetaTrader5")
        sys.exit(1)

    # Parse symbol map
    symbol_map = {}
    if Config.MT5_SYMBOL_MAP:
        try:
            symbol_map = json.loads(Config.MT5_SYMBOL_MAP)
            logger.info("Loaded MT5 symbol map: %s", symbol_map)
        except json.JSONDecodeError as e:
            logger.warning("Invalid MT5_SYMBOL_MAP JSON: %s — using defaults", e)

    # Connect to MT5
    print("\n--- Connecting to MT5 terminal ---")
    conn = MT5ConnectionManager(
        enabled=Config.MT5_ENABLED,
        demo_only=Config.MT5_DEMO_ONLY,
        demo_trading_enabled=Config.MT5_DEMO_TRADING_ENABLED,
        path=Config.MT5_PATH,
        login=Config.MT5_LOGIN,
        password=Config.MT5_PASSWORD,
        server=Config.MT5_SERVER,
        timeout=Config.MT5_TIMEOUT,
        expected_server=Config.MT5_EXPECTED_SERVER,
        expected_login=Config.MT5_EXPECTED_LOGIN,
        magic_number=Config.MT5_MAGIC_NUMBER,
    )

    if not conn.connect():
        print(f"ERROR: MT5 connection failed. State: {conn.health.state.value}")
        conn.health.print_summary()
        sys.exit(1)

    print(f"  Connected to MT5 terminal")
    print(f"  Account: {conn.account_info.get('login', '?')}")
    print(f"  Server: {conn.account_info.get('server', '?')}")
    print(f"  Trade mode: {'DEMO' if conn.account_info.get('trade_mode') == 0 else 'NOT DEMO'}")
    print(f"  Balance: {conn.account_info.get('balance', 0):.2f}")

    # Show health
    conn.health.print_summary()

    # Determine mode: read-only or trading-enabled
    trading_mode = Config.MT5_DEMO_TRADING_ENABLED
    if not trading_mode:
        print("\n  MT5_DEMO_TRADING_ENABLED=false — READ-ONLY mode")
        print("  Will NOT place any orders.")
    else:
        if not conn.can_trade():
            print("ERROR: MT5 cannot trade (health gate failed)")
            sys.exit(1)

    # Initialize components
    ai = TestStrategy(ai_id="mt5-demo-strategy")
    db = None
    try:
        db = _get_database()
    except Exception as e:
        logger.warning("Database unavailable: %s", e)

    if db:
        try:
            db.create_paper_session(
                session_id=session_id,
                exchange="mt5",
                symbols=",".join(Config.SYMBOLS),
                timeframe=Config.TIMEFRAME,
                data_source="mt5-demo",
                starting_balance=Config.STARTING_BALANCE,
                config_json=json.dumps(Config.as_dict()),
                software_version="0.6.0",
            )
        except Exception as e:
            logger.warning("Could not create session: %s", e)

    market_data = MT5MarketData(conn)

    from src.risk.manager import RiskManager
    from src.portfolio.portfolio import Portfolio

    portfolio = Portfolio(session_id, Config.STARTING_BALANCE)

    # Only create broker and risk manager when trading is enabled
    broker = None
    risk = None
    if trading_mode:
        broker = MT5DemoBroker(
            conn,
            symbol_map=symbol_map,
            magic_number=Config.MT5_MAGIC_NUMBER,
        )
        risk = RiskManager(
            max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
            max_daily_loss=Config.MAX_DAILY_LOSS,
            min_confidence=Config.MIN_AI_CONFIDENCE,
        )

    print(f"\n--- Fetching candles ---")
    candle_data = {}
    for sym in Config.SYMBOLS:
        mt5_sym = symbol_map.get(sym, sym)
        candles = market_data.fetch_candles(mt5_sym, Config.TIMEFRAME, Config.CANDLE_LIMIT)
        if candles:
            candle_data[sym] = candles
            print(f"  {sym} ({mt5_sym}): {len(candles)} candles")
        else:
            print(f"  {sym} ({mt5_sym}): NO DATA")

    if not candle_data:
        print("\nERROR: No candle data available for any symbol")
        conn.shutdown()
        sys.exit(1)

    # Process each symbol
    print(f"\n--- Processing decisions ---")
    for sym, candles in candle_data.items():
        if len(candles) < 2:
            print(f"  {sym}: insufficient candles, skipping")
            continue

        last_candle = candles[-1]
        indicators = {}
        try:
            from src.indicators.technical import compute_all_indicators
            indicators = compute_all_indicators(candles)
        except Exception as e:
            logger.warning("Indicator computation failed for %s: %s", sym, e)

        decision = ai.decide(
            symbol=sym,
            candles=candles,
            indicators=indicators,
            portfolio=portfolio,
            current_price=last_candle["close"],
        )

        print(f"  {sym}: {decision.action} (conf={decision.confidence:.2f})")

        if not trading_mode:
            # Read-only: log decision, never execute
            print(f"    -> READ-ONLY: no order sent")
            continue

        if decision.action in ("BUY", "SELL"):
            risk_check = risk.evaluate(
                symbol=sym,
                side=decision.action.lower(),
                confidence=decision.confidence,
                position_size=decision.position_size,
                portfolio=portfolio,
            )

            if risk_check.rejected:
                print(f"    -> RISK REJECTED: {risk_check.reason}")
                continue

            order = broker.execute(
                symbol=sym,
                side=decision.action,
                quantity=decision.position_size,
                current_price=last_candle["close"],
                risk_assessment=risk_check,
            )

            if order:
                print(f"    -> ORDER FILLED: {order['id']}")
                if db:
                    try:
                        db.log_trade(
                            ai_id="mt5-demo-strategy",
                            symbol=sym,
                            side=order["side"],
                            entry_price=order.get("price", last_candle["close"]),
                            exit_price=0,
                            quantity=order.get("quantity", 0),
                            fee=0,
                            slippage=0,
                            pnl=0,
                            balance=portfolio.balance,
                            experiment_id=session_id,
                        )
                    except Exception as e:
                        logger.warning("Could not log trade: %s", e)
            else:
                print(f"    -> ORDER FAILED")

    # Summary
    print(f"\n--- Session Summary ---")
    print(f"  Session: {session_id}")
    print(f"  Trading mode: {'ENABLED' if trading_mode else 'READ-ONLY'}")
    print(f"  Portfolio Balance: ${portfolio.balance:,.2f}")
    print(f"  Open Positions: {len(portfolio.positions)}")
    print(f"  Total Trades: {len(portfolio.trade_history)}")

    if db:
        try:
            db.update_paper_session(
                session_id=session_id,
                current_balance=portfolio.balance,
                trades_count=len(portfolio.trade_history),
                status="completed",
            )
        except Exception as e:
            logger.warning("Could not update session: %s", e)

    # Shutdown
    print(f"\n--- Shutting down MT5 ---")
    conn.shutdown()
    if db:
        db.close()

    print(f"\nMT5 demo session complete: {session_id}")


def cmd_m7(args):
    """Run M7 Advanced Strategy & Risk Monitor (read-only mode).

    Demonstrates the full M7 pipeline:
    Market Data → Filters → State Machine → AI Decision → Risk Check → Monitoring

    In read-only mode: no orders are placed.
    """
    from src.strategy.engine import StrategyEngine, StrategyPhase
    from src.strategy.filters import build_filter_config_from_settings
    from src.risk.manager import RiskManager, BrokerMetadata
    from src.portfolio.portfolio import Portfolio

    print("=" * 50)
    print("  ASHTRADINGAI M7 ADVANCED STRATEGY MONITOR")
    print("=" * 50)

    if not Config.M7_ENABLED:
        print("\n  M7_ENABLED=false — M7 is disabled.")
        print("  Set M7_ENABLED=true to activate advanced strategy monitoring.")
        print("\n  Showing M7 configuration only:\n")

    # Build filter config from settings
    filter_cfg = build_filter_config_from_settings(Config.as_dict())

    portfolio = Portfolio("m7-monitor", Config.STARTING_BALANCE)
    risk = RiskManager(
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        risk_percent=Config.M7_RISK_PERCENT,
    )

    # Show M7 configuration
    print("  --- M7 Configuration ---")
    print(f"  Enabled:         {Config.M7_ENABLED}")
    print(f"  ATR Filter:      {'ON' if Config.M7_ATR_FILTER_ENABLED else 'OFF'} (min={Config.M7_ATR_MIN}, max={Config.M7_ATR_MAX})")
    print(f"  Angle Filter:    {'ON' if Config.M7_ANGLE_FILTER_ENABLED else 'OFF'} (period={Config.M7_ANGLE_EMA_PERIOD}, min={Config.M7_MIN_ANGLE})")
    print(f"  Price/EMA:       {'ON' if Config.M7_PRICE_EMA_FILTER_ENABLED else 'OFF'} (period={Config.M7_PRICE_EMA_PERIOD})")
    print(f"  Candle Filter:   {'ON' if Config.M7_CANDLE_FILTER_ENABLED else 'OFF'}")
    print(f"  EMA Order:       {'ON' if Config.M7_EMA_ORDER_FILTER_ENABLED else 'OFF'} ({Config.M7_EMA_FAST_PERIOD}/{Config.M7_EMA_MEDIUM_PERIOD}/{Config.M7_EMA_SLOW_PERIOD})")
    print(f"  Session Filter:  {'ON' if Config.M7_SESSION_FILTER_ENABLED else 'OFF'} ({Config.M7_SESSION_START_HOUR:02d}:{Config.M7_SESSION_START_MINUTE:02d}-{Config.M7_SESSION_END_HOUR:02d}:{Config.M7_SESSION_END_MINUTE:02d} {Config.M7_SESSION_TIMEZONE})")
    print(f"  Pullback:        {Config.M7_PULLBACK_CANDLES} candles")
    print(f"  Breakout Window: {Config.M7_BREAKOUT_WINDOW} candles")
    print(f"  Risk Percent:    {Config.M7_RISK_PERCENT:.1%}")
    print(f"  SL Multiplier:   {Config.M7_SL_ATR_MULTIPLIER}x ATR")
    print(f"  TP Multiplier:   {Config.M7_TP_ATR_MULTIPLIER}x ATR")

    if not Config.M7_ENABLED:
        errors = Config.validate()
        if errors:
            print("\n  CONFIG ERRORS:")
            for e in errors:
                print(f"    - {e}")
        else:
            print("\n  Config: OK")
        return

    # Fetch data
    print("\n--- Fetching market data ---")
    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    # Create strategy engines for each symbol
    engines = {}
    for sym in Config.SYMBOLS:
        ai = TestStrategy(ai_id=f"m7-{sym}")
        engine = StrategyEngine(
            ai=ai,
            symbol=sym,
            timeframe=Config.TIMEFRAME,
            filter_config=filter_cfg,
            pullback_candles=Config.M7_PULLBACK_CANDLES,
            breakout_window=Config.M7_BREAKOUT_WINDOW,
            sl_atr_multiplier=Config.M7_SL_ATR_MULTIPLIER,
            tp_atr_multiplier=Config.M7_TP_ATR_MULTIPLIER,
            risk_percent=Config.M7_RISK_PERCENT,
        )
        engines[sym] = engine

    # Process last few candles through the pipeline
    print("\n--- Running M7 Pipeline ---")
    for sym, candles in data.items():
        if sym not in engines:
            continue
        engine = engines[sym]

        if len(candles) < 5:
            print(f"\n  {sym}: insufficient data ({len(candles)} candles)")
            continue

        # Process last 3 completed candles
        for i in range(max(0, len(candles) - 3), len(candles) - 1):
            subset = candles[:i + 2]  # +1 for forming candle
            signal = engine.process_candle(
                subset,
                portfolio_balance=portfolio.balance,
                open_positions=list(portfolio.positions.keys()),
            )

        # Show current state
        summary = engine.get_summary()
        print(f"\n  {sym}")
        print(f"  {'─' * 36}")
        print(f"  Phase:       {summary['phase']}")
        print(f"  Direction:   {summary['direction'] or '—'}")
        print(f"  ATR:         {summary['atr']:.4f}")
        print(f"  Pullback:    {summary['pullback_count']}/{summary['pullback_target']}")
        print(f"  Window:      {summary['window_remaining']} candles")
        print(f"  Setup:       {summary['setup_id'] or '—'}")
        print(f"  Last Candle: {summary['last_candle'][:19] if summary['last_candle'] else '—'}")

        # Run filters for display
        if len(candles) > 2:
            from src.strategy.filters import FilterCascade
            cascade = FilterCascade(filter_cfg)
            direction = engine._detect_direction(candles)
            if direction:
                completed = candles[:-1]
                filter_result = cascade.evaluate(completed, direction)
                for name, fr in filter_result.results.items():
                    status = "PASS" if fr.passed else "BLOCK"
                    print(f"  {name:12s} {status}" + (f" ({fr.reason})" if fr.reason and not fr.passed else ""))
            else:
                print(f"  Filters:     no directional setup detected")

        # Show AI decision
        from src.ai.base import MarketContext
        ai = TestStrategy(ai_id=f"m7-{sym}")
        ctx = MarketContext(
            symbol=sym,
            timeframe=Config.TIMEFRAME,
            current_price=candles[-2]["close"] if len(candles) > 1 else 0,
            candles=candles,
            portfolio_balance=portfolio.balance,
            open_positions=list(portfolio.positions.keys()),
        )
        try:
            ai_decision = ai.decide(ctx)
            print(f"  AI:          {ai_decision.get('decision', 'HOLD')} (conf={ai_decision.get('confidence', 0):.2f})")
        except Exception:
            print(f"  AI:          HOLD (error)")

        # Risk status
        print(f"  Risk:        {'ALLOWED' if not risk._kill_switch else 'BLOCKED (kill switch)'}")
        print(f"  Position:    {portfolio.balance:,.2f}")

    print(f"\n--- Session Summary ---")
    print(f"  Balance:     ${portfolio.balance:,.2f}")
    print(f"  Positions:   {len(portfolio.positions)}")
    print(f"  Trades:      {len(portfolio.trade_history)}")
    print(f"\n  NOTE: M7 monitor is READ-ONLY. No orders were placed.")

    errors = Config.validate()
    if errors:
        print("\n  CONFIG ERRORS:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("\n  Config: OK")


def cmd_m7_backtest(args):
    """Run M7 strategy backtest with full pipeline validation.

    Tests M7 filters + state machine on historical data.
    Reports: standard metrics, filter stats, state transitions, AI confirmation rates.
    """
    from src.backtest.m7_backtest import M7BacktestEngine, run_walk_forward
    from src.strategy.filters import build_filter_config_from_settings
    from src.risk.manager import BrokerMetadata
    from src.market.candles import generate_synthetic_candles

    print("=" * 50)
    print("  ASHTRADINGAI M7 STRATEGY BACKTEST")
    print("=" * 50)

    if not Config.M7_ENABLED:
        print("\n  WARNING: M7_ENABLED=false. Running backtest with M7 settings anyway.")

    # Build filter config
    filter_cfg = build_filter_config_from_settings(Config.as_dict())

    # Generate or load data
    print("\n--- Preparing data ---")
    if Config.DATA_SOURCE == "live":
        data = _fetch_live_data(Config.EXCHANGE, Config.SYMBOLS, Config.TIMEFRAME, Config.CANDLE_LIMIT)
    else:
        data = {sym: generate_synthetic_candles(symbol=sym, periods=Config.CANDLE_LIMIT) for sym in Config.SYMBOLS}

    for sym, candles in data.items():
        print(f"  {sym}: {len(candles)} candles")

    # Default broker metadata (generic crypto)
    broker_meta = BrokerMetadata(
        tick_value=1.0, tick_size=0.01, point=0.01,
        contract_size=1, volume_min=0.001, volume_max=10.0,
        volume_step=0.001,
    )

    # Create AI
    from src.ai.test_strategy import TestStrategy
    ai = TestStrategy(ai_id="m7-backtest")

    # Run backtest
    print("\n--- Running M7 backtest ---")
    engine = M7BacktestEngine(
        starting_balance=Config.STARTING_BALANCE,
        fee=0.001,
        slippage=0.0005,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        risk_percent=Config.M7_RISK_PERCENT,
        filter_config=filter_cfg,
        pullback_candles=Config.M7_PULLBACK_CANDLES,
        breakout_window=Config.M7_BREAKOUT_WINDOW,
        sl_atr_multiplier=Config.M7_SL_ATR_MULTIPLIER,
        tp_atr_multiplier=Config.M7_TP_ATR_MULTIPLIER,
        broker_meta=broker_meta,
    )

    metrics, portfolio = engine.run(ai, data, Config.TIMEFRAME)
    m = metrics.standard

    # Display results
    print(f"\n{'='*50}")
    print(f"  M7 BACKTEST RESULTS")
    print(f"{'='*50}")

    print(f"\n  --- Standard Metrics ---")
    print(f"  Starting Balance:  ${m.starting_balance:,.2f}")
    print(f"  Ending Balance:    ${m.ending_balance:,.2f}")
    print(f"  Net Profit:        ${m.net_profit:,.2f}")
    print(f"  Return:            {m.return_pct:.2%}")
    print(f"  Max Drawdown:      {m.max_drawdown:.2%}")
    print(f"  Sharpe Ratio:      {m.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio:     {m.sortino_ratio:.2f}")

    print(f"\n  --- Trade Summary ---")
    print(f"  Total Trades:      {m.num_trades}")
    print(f"  Winning:           {m.winning_trades}")
    print(f"  Losing:            {m.losing_trades}")
    print(f"  Win Rate:          {m.win_rate:.2%}")
    print(f"  Profit Factor:     {m.profit_factor:.2f}")
    print(f"  Avg Win:           ${m.avg_win:,.2f}")
    print(f"  Avg Loss:          ${m.avg_loss:,.2f}")
    print(f"  Fees Paid:         ${m.fees_paid:,.2f}")

    print(f"\n  --- M7 Filter Stats ---")
    fs = metrics.filter_stats.summary()
    print(f"  Total Evaluations: {fs['total_evaluations']}")
    for name, count in fs.get("pass_counts", {}).items():
        fail = fs.get("fail_counts", {}).get(name, 0)
        total = count + fail
        rate = count / total if total > 0 else 0
        print(f"  {name:12s}: {count:4d} pass / {fail:4d} fail ({rate:.0%})")

    print(f"\n  --- State Transitions ---")
    ss = metrics.state_stats.summary()
    print(f"  Candles Processed: {ss['total_candles']}")
    print(f"  Setups Detected:   {ss['setups_detected']}")
    print(f"  Entries Triggered: {ss['entries_triggered']}")
    for trans, count in ss.get("transitions", {}).items():
        print(f"    {trans}: {count}")

    print(f"\n  --- AI Confirmation ---")
    ai_s = metrics.ai_stats.summary()
    print(f"  Total Signals:     {ai_s['total_signals']}")
    print(f"  AI Approved:       {ai_s['ai_approved']}")
    print(f"  AI Rejected:       {ai_s['ai_rejected']}")
    print(f"  Approval Rate:     {ai_s['approval_rate']:.2%}")
    print(f"  Avg Confidence:    {ai_s['avg_confidence']:.2f}")

    if metrics.per_symbol:
        print(f"\n  --- Per Symbol ---")
        for sym, ps in metrics.per_symbol.items():
            print(f"  {sym}: {ps['trades']} trades, PnL=${ps['net_pnl']:,.2f}")

    # Walk-forward validation
    print(f"\n--- Walk-Forward Validation (70/30 split) ---")
    is_m, oos_m, _, _ = run_walk_forward(
        ai, data, Config.TIMEFRAME,
        in_sample_pct=0.7,
        starting_balance=Config.STARTING_BALANCE,
        fee=0.001, slippage=0.0005,
        max_position_size=Config.MAX_POSITION_SIZE,
        max_open_positions=Config.MAX_OPEN_POSITIONS,
        max_daily_loss=Config.MAX_DAILY_LOSS,
        max_drawdown=Config.MAX_DRAWDOWN,
        min_confidence=Config.MIN_AI_CONFIDENCE,
        risk_percent=Config.M7_RISK_PERCENT,
        filter_config=filter_cfg,
        pullback_candles=Config.M7_PULLBACK_CANDLES,
        breakout_window=Config.M7_BREAKOUT_WINDOW,
        sl_atr_multiplier=Config.M7_SL_ATR_MULTIPLIER,
        tp_atr_multiplier=Config.M7_TP_ATR_MULTIPLIER,
        broker_meta=broker_meta,
    )

    print(f"  In-Sample:  {is_m.standard.num_trades} trades, "
          f"return={is_m.standard.return_pct:.2%}, "
          f"max_dd={is_m.standard.max_drawdown:.2%}")
    print(f"  Out-Sample: {oos_m.standard.num_trades} trades, "
          f"return={oos_m.standard.return_pct:.2%}, "
          f"max_dd={oos_m.standard.max_drawdown:.2%}")

    # Overfit warning
    if is_m.standard.return_pct > 0 and oos_m.standard.return_pct < 0:
        print(f"\n  WARNING: Strategy shows positive in-sample but negative out-of-sample.")
        print(f"           Possible overfitting. Do NOT claim profitability.")
    elif is_m.standard.return_pct > 0 and oos_m.standard.return_pct > 0:
        print(f"\n  NOTE: Both in-sample and out-of-sample are positive.")
        print(f"        This is NOT a guarantee of future performance.")

    print(f"\n  NOTE: M7 backtest uses PaperBroker only. No real orders placed.")
    print(f"        Results are NOT financial advice.")


def main():
    parser = argparse.ArgumentParser(description="AshtradingAI Trading Bot")
    parser.add_argument("--mode", required=True,
                        choices=["backtest", "paper", "status", "leaderboard",
                                 "tournament", "tournament-backtest",
                                 "paper-live", "paper-live-test", "mt5-demo",
                                 "m7", "m7-backtest"],
                        help="Operating mode")
    args = parser.parse_args()

    setup_logging()
    logger.info("Starting AshtradingAI in %s mode", args.mode)

    if args.mode == "backtest":
        cmd_backtest(args)
    elif args.mode == "paper":
        cmd_paper(args)
    elif args.mode == "status":
        cmd_status(args)
    elif args.mode == "leaderboard":
        cmd_leaderboard(args)
    elif args.mode == "tournament":
        cmd_tournament(args)
    elif args.mode == "tournament-backtest":
        cmd_tournament_backtest(args)
    elif args.mode == "paper-live":
        cmd_paper_live(args)
    elif args.mode == "paper-live-test":
        cmd_paper_live_test(args)
    elif args.mode == "mt5-demo":
        cmd_mt5_demo(args)
    elif args.mode == "m7":
        cmd_m7(args)
    elif args.mode == "m7-backtest":
        cmd_m7_backtest(args)


if __name__ == "__main__":
    main()
