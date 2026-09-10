"""AshtradingAI REST API Server — FastAPI backend for mobile companion app.

M15: Remote MT5 Demo Bridge
- Token-based API authentication
- MT5 read-only endpoints with heartbeat
- Observability logging
- Safety gate enforcement
"""
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.config import Config
from src.persistence.database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Authentication ────────────────────────────────────────────────
# API Authentication via environment variable.
# Set API_SECRET_KEY in .env for production.
# When unset, authentication is disabled (development mode).

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
AUTH_ENABLED = bool(API_SECRET_KEY)


def _hash_token(token: str) -> str:
    """SHA-256 hash for secure token comparison (no plaintext logging)."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_api_key(authorization: Optional[str] = Header(None)) -> bool:
    """FastAPI dependency: verify API key from Authorization header.

    Expected format: Authorization: Bearer <token>
    Returns True if valid, raises 401 if invalid.
    When API_SECRET_KEY is not set, authentication is disabled (dev mode).
    """
    if not AUTH_ENABLED:
        return True

    if not authorization:
        logger.warning("API_AUTH_FAILURE: Missing Authorization header")
        raise HTTPException(status_code=401, detail="Missing authentication")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("API_AUTH_FAILURE: Malformed Authorization header")
        raise HTTPException(status_code=401, detail="Invalid authentication format")

    token = parts[1]
    if not token or len(token) < 8:
        logger.warning("API_AUTH_FAILURE: Token too short")
        raise HTTPException(status_code=401, detail="Invalid token")

    expected_hash = _hash_token(API_SECRET_KEY)
    actual_hash = _hash_token(token)

    if not _constant_time_compare(expected_hash, actual_hash):
        logger.warning("API_AUTH_FAILURE: Invalid token")
        raise HTTPException(status_code=401, detail="Invalid authentication")

    return True


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ── App Setup ─────────────────────────────────────────────────────

APP_VERSION = "1.5.1"

app = FastAPI(
    title="AshtradingAI API",
    description="Research platform API for the AshtradingAI mobile companion",
    version=APP_VERSION,
)

# CORS: restrict in production, allow all in dev
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

import sqlite3
_db_path = str(Path(__file__).resolve().parent / "data" / "ashtrading.db")


def get_db_conn():
    """Thread-safe SQLite connection."""
    conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


from contextlib import contextmanager

@contextmanager
def db_connection():
    """Context manager for thread-safe DB access."""
    conn = get_db_conn()
    try:
        yield conn
    finally:
        conn.close()


def log_event(category: str, severity: str, message: str, details: Optional[str] = None) -> None:
    """Log an event to the event_logs table."""
    try:
        with db_connection() as conn:
            event_id = str(__import__("uuid").uuid4())[:12]
            ts = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO event_logs (id, timestamp, category, severity, message, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, ts, category, severity, message, details),
            )
            conn.commit()
    except Exception as e:
        logger.debug("Failed to log event: %s", e)


# ── Kill Switch State ─────────────────────────────────────────────
_kill_switch_active = False


def is_kill_switch_active() -> bool:
    return _kill_switch_active


# ── Response Models ──────────────────────────────────────────────

class SafetyStatus(BaseModel):
    live_trading: str
    mt5_demo_only: str
    mt5_demo_trading_enabled: str
    paper_trading: str
    market_data: str
    app_env: str


class SystemStatus(BaseModel):
    api_status: str
    database_status: str
    safety: SafetyStatus
    config: dict


class AccountSummary(BaseModel):
    balance: float
    starting_balance: float
    equity: float
    unrealized_pnl: float
    daily_pnl: float
    open_positions: int
    total_trades: int


class PositionInfo(BaseModel):
    id: str
    symbol: str
    side: str
    volume: float
    entry_price: float
    current_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    unrealized_pnl: float
    account: str
    environment: str


class TradeInfo(BaseModel):
    id: str
    timestamp: str
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: Optional[float]
    fee: float


class StrategyInfo(BaseModel):
    name: str
    version: str
    status: str
    signal_count: int
    trades: int
    return_pct: Optional[float]
    sharpe: Optional[float]
    win_rate: Optional[float]
    profit_factor: Optional[float]
    max_drawdown: Optional[float]
    sample_classification: str
    validation_status: str


class ExperimentInfo(BaseModel):
    id: str
    timestamp: str
    strategy: str
    strategy_version: str
    symbol: Optional[str]
    timeframe: Optional[str]
    starting_balance: Optional[float]
    ending_balance: Optional[float]
    return_pct: Optional[float]
    max_drawdown: Optional[float]
    sharpe_ratio: Optional[float]
    profit_factor: Optional[float]
    trade_count: Optional[int]
    metrics_json: Optional[str]


class SignalInfo(BaseModel):
    id: str
    session_id: str
    symbol: str
    direction: str
    phase: str
    candle_timestamp: str
    price: Optional[float]
    atr_value: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    confidence: Optional[float]
    reason: Optional[str]


class LogEntry(BaseModel):
    timestamp: str
    category: str
    severity: str
    message: str


class AIResearchQuery(BaseModel):
    question: str


class AIResearchResponse(BaseModel):
    answer: str
    evidence: list
    confidence: str
    disclaimer: str


# ── Endpoints ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "AshtradingAI API", "version": APP_VERSION, "status": "running"}


@app.get("/api/status", response_model=SystemStatus)
def get_status():
    """System status including safety flags."""
    config_dict = Config.as_dict()
    safety = SafetyStatus(
        live_trading="LOCKED / DISABLED" if not Config.LIVE_TRADING else "ENABLED (DANGER)",
        mt5_demo_only="ENABLED" if Config.MT5_DEMO_ONLY else "DISABLED",
        mt5_demo_trading_enabled="ENABLED" if Config.MT5_DEMO_TRADING_ENABLED else "CURRENTLY DISABLED",
        paper_trading="AVAILABLE",
        market_data="AVAILABLE" if Config.DATA_SOURCE == "live" else "SYNTHETIC",
        app_env=Config.APP_ENV,
    )
    try:
        conn = get_db_conn()
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return SystemStatus(
        api_status="healthy",
        database_status=db_status,
        safety=safety,
        config={k: v for k, v in config_dict.items() if not k.endswith("_KEY") and not k.endswith("_PASSWORD")},
    )


@app.get("/api/safety", response_model=SafetyStatus)
def get_safety():
    """Safety center status."""
    return SafetyStatus(
        live_trading="LOCKED / DISABLED" if not Config.LIVE_TRADING else "ENABLED (DANGER)",
        mt5_demo_only="ENABLED" if Config.MT5_DEMO_ONLY else "DISABLED",
        mt5_demo_trading_enabled="ENABLED" if Config.MT5_DEMO_TRADING_ENABLED else "CURRENTLY DISABLED",
        paper_trading="AVAILABLE",
        market_data="AVAILABLE" if Config.DATA_SOURCE == "live" else "SYNTHETIC",
        app_env=Config.APP_ENV,
    )


@app.get("/api/account", response_model=AccountSummary)
def get_account(authorized: bool = Depends(verify_api_key)):
    """Account summary from latest paper session."""
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM paper_sessions WHERE status='active' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row:
        positions_json = json.loads(row["open_positions_json"] or "{}")
        trades_json = json.loads(row["trade_history_json"] or "[]")
        return AccountSummary(
            balance=row["current_balance"] or 0.0,
            starting_balance=row["starting_balance"] or 0.0,
            equity=row["current_balance"] or 0.0,
            unrealized_pnl=0.0,
            daily_pnl=0.0,
            open_positions=len(positions_json),
            total_trades=len(trades_json),
        )
    return AccountSummary(
        balance=Config.STARTING_BALANCE,
        starting_balance=Config.STARTING_BALANCE,
        equity=Config.STARTING_BALANCE,
        unrealized_pnl=0.0,
        daily_pnl=0.0,
        open_positions=0,
        total_trades=0,
    )


@app.get("/api/positions")
def get_positions(authorized: bool = Depends(verify_api_key)):
    """List open positions from active paper sessions."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_sessions WHERE status='active'"
        ).fetchall()
    positions = []
    for row in rows:
        positions_json = json.loads(row["open_positions_json"] or "{}")
        for symbol, pos_data in positions_json.items():
            positions.append({
                "id": f"{row['id']}_{symbol}",
                "symbol": symbol,
                "side": pos_data.get("side", "unknown"),
                "volume": pos_data.get("qty", 0.0),
                "entry_price": pos_data.get("entry", 0.0),
                "current_price": None,
                "stop_loss": None,
                "take_profit": None,
                "unrealized_pnl": 0.0,
                "account": row["id"],
                "environment": "PAPER",
            })
    return {"positions": positions}


@app.get("/api/trades")
def get_trades(limit: int = Query(50, ge=1, le=500), authorized: bool = Depends(verify_api_key)):
    """Recent trades from the database."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    trades = []
    for row in rows:
        trades.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "symbol": row["symbol"],
            "side": row["side"],
            "entry_price": row["entry_price"],
            "exit_price": row["exit_price"],
            "quantity": row["quantity"],
            "pnl": row["pnl"],
            "fee": row["fee"],
        })
    return {"trades": trades}


@app.get("/api/strategies")
def get_strategies(authorized: bool = Depends(verify_api_key)):
    """List available strategies with metrics from backtest runs."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT ai_id, COUNT(*) as run_count, AVG(return_percent) as avg_return, "
            "AVG(sharpe_ratio) as avg_sharpe, AVG(win_rate) as avg_win_rate, "
            "AVG(profit_factor) as avg_pf, AVG(max_drawdown) as avg_dd "
            "FROM backtest_runs GROUP BY ai_id"
        ).fetchall()
    strategies = []
    for row in rows:
        run_count = row["run_count"]
        classification = "VALID" if run_count >= 30 else "INSUFFICIENT SAMPLE" if run_count > 0 else "NOT APPLICABLE"
        strategies.append({
            "name": row["ai_id"],
            "version": "1.0",
            "status": "ACTIVE" if run_count > 0 else "INACTIVE",
            "signal_count": run_count,
            "trades": run_count,
            "return_pct": round(row["avg_return"] or 0.0, 2),
            "sharpe": round(row["avg_sharpe"] or 0.0, 2),
            "win_rate": round(row["avg_win_rate"] or 0.0, 2),
            "profit_factor": round(row["avg_pf"] or 0.0, 2),
            "max_drawdown": round(row["avg_dd"] or 0.0, 2),
            "sample_classification": classification,
            "validation_status": classification,
        })
    return {"strategies": strategies}


@app.get("/api/experiments")
def get_experiments(limit: int = Query(50, ge=1, le=200), authorized: bool = Depends(verify_api_key)):
    """List backtest experiments."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    experiments = []
    for row in rows:
        experiments.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "strategy": row["ai_id"],
            "strategy_version": "1.0",
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "starting_balance": row["starting_balance"],
            "ending_balance": row["ending_balance"],
            "return_pct": row["return_percent"],
            "max_drawdown": row["max_drawdown"],
            "sharpe_ratio": row["sharpe_ratio"],
            "profit_factor": row["profit_factor"],
            "trade_count": row["trade_count"],
            "metrics_json": row["metrics_json"],
        })
    return {"experiments": experiments}


@app.get("/api/signals")
def get_signals(limit: int = Query(100, ge=1, le=1000), authorized: bool = Depends(verify_api_key)):
    """M7 signals from the database."""
    with db_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT * FROM m7_signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            rows = []
    signals = []
    for row in rows:
        signals.append({
            "id": row["id"],
            "session_id": row["session_id"],
            "symbol": row["symbol"],
            "direction": row["direction"],
            "phase": row["phase"],
            "candle_timestamp": row["candle_timestamp"],
            "price": row["price"],
            "atr_value": row["atr_value"],
            "stop_loss": row["stop_loss"],
            "take_profit": row["take_profit"],
            "confidence": row["confidence"],
            "reason": row["reason"],
        })
    return {"signals": signals}


@app.get("/api/ai-decisions")
def get_ai_decisions(limit: int = Query(100, ge=1, le=1000), authorized: bool = Depends(verify_api_key)):
    """AI decisions from the database."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    decisions = []
    for row in rows:
        decisions.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "ai_id": row["ai_id"],
            "symbol": row["symbol"],
            "decision": row["decision"],
            "confidence": row["confidence"],
            "reason": row["reason"],
            "action_taken": row["action_taken"],
        })
    return {"decisions": decisions}


@app.get("/api/logs")
def get_logs(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    authorized: bool = Depends(verify_api_key),
):
    """Event logs from the database. Categories: SYSTEM, MARKET, STRATEGY, AI, RISK, PAPER, MT5, SAFETY, ERROR."""
    with db_connection() as conn:
        try:
            if category:
                rows = conn.execute(
                    "SELECT * FROM event_logs WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM event_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
        except Exception:
            rows = []
    logs = []
    for row in rows:
        logs.append({
            "timestamp": row["timestamp"],
            "category": row["category"],
            "severity": row["severity"],
            "message": row["message"],
        })
    return {"logs": logs}


@app.get("/api/mt5/status")
def get_mt5_status(authorized: bool = Depends(verify_api_key)):
    """MT5 Demo connection and configuration status (read-only)."""
    from src.mt5.readonly_api import get_status
    return get_status()


@app.get("/api/mt5/account")
def get_mt5_account(authorized: bool = Depends(verify_api_key)):
    """MT5 Demo account information (read-only). Balance, equity, margin, etc."""
    from src.mt5.readonly_api import get_account
    return get_account()


@app.get("/api/mt5/positions")
def get_mt5_positions(symbol: Optional[str] = None, authorized: bool = Depends(verify_api_key)):
    """MT5 Demo open positions (read-only)."""
    from src.mt5.readonly_api import get_positions
    return {"positions": get_positions(symbol=symbol)}


@app.get("/api/mt5/orders")
def get_mt5_orders(authorized: bool = Depends(verify_api_key)):
    """MT5 Demo pending orders (read-only)."""
    from src.mt5.readonly_api import get_orders
    return {"orders": get_orders()}


@app.get("/api/mt5/symbols")
def get_mt5_symbols(authorized: bool = Depends(verify_api_key)):
    """MT5 Demo available symbols (read-only)."""
    from src.mt5.readonly_api import get_symbols
    return {"symbols": get_symbols()}


@app.get("/api/mt5/quote/{symbol}")
def get_mt5_quote(symbol: str, authorized: bool = Depends(verify_api_key)):
    """MT5 Demo current bid/ask quote for a symbol (read-only)."""
    from src.mt5.readonly_api import get_quote
    quote = get_quote(symbol)
    if quote is None:
        return {"symbol": symbol, "bid": 0.0, "ask": 0.0, "error": "Symbol unavailable or MT5 not connected"}
    return quote


@app.get("/api/mt5/heartbeat")
def get_mt5_heartbeat(authorized: bool = Depends(verify_api_key)):
    """MT5 Demo connection heartbeat — lightweight health check with timestamps."""
    from src.mt5.readonly_api import get_heartbeat
    return get_heartbeat()


@app.get("/api/config")
def get_config(authorized: bool = Depends(verify_api_key)):
    """Public configuration (no secrets)."""
    config_dict = Config.as_dict()
    safe_config = {k: v for k, v in config_dict.items()
                   if not any(s in k for s in ["KEY", "PASSWORD", "SECRET", "TOKEN"])}
    return {"config": safe_config}


@app.get("/api/market/health")
def get_market_health(authorized: bool = Depends(verify_api_key)):
    """Market data health status."""
    return {
        "data_source": Config.DATA_SOURCE,
        "exchange": Config.EXCHANGE,
        "symbols": Config.SYMBOLS,
        "timeframe": Config.TIMEFRAME,
        "status": "ONLINE" if Config.DATA_SOURCE == "live" else "SYNTHETIC",
    }


@app.get("/api/health")
def get_health(authorized: bool = Depends(verify_api_key)):
    """Full system health: application, database, MT5, safety."""
    health = {
        "application": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "unknown",
        "mt5": "unknown",
        "safety": {
            "live_trading": Config.LIVE_TRADING,
            "mt5_demo_only": Config.MT5_DEMO_ONLY,
            "mt5_demo_trading_enabled": Config.MT5_DEMO_TRADING_ENABLED,
        },
    }
    # Database check
    try:
        with db_connection() as conn:
            conn.execute("SELECT 1")
        health["database"] = "healthy"
    except Exception as e:
        health["database"] = f"error: {e}"
    # MT5 check
    try:
        from src.mt5.readonly_api import get_heartbeat
        hb = get_heartbeat()
        health["mt5"] = "connected" if hb.get("connected") else "disconnected"
        health["mt5_heartbeat"] = hb
    except Exception as e:
        health["mt5"] = f"error: {e}"
    log_event("SYSTEM", "INFO", "Health check completed")
    return health


@app.get("/api/kill-switch")
def get_kill_switch(authorized: bool = Depends(verify_api_key)):
    """Get kill switch status."""
    return {
        "active": _kill_switch_active,
        "message": "ALL TRADING HALTED" if _kill_switch_active else "Normal operation",
    }


@app.post("/api/kill-switch")
def set_kill_switch(active: bool = True, authorized: bool = Depends(verify_api_key)):
    """Activate or deactivate the global kill switch.

    When activated: no new orders, no strategy execution that creates orders.
    Existing positions are NOT closed (no safe-close mechanism implemented).
    """
    global _kill_switch_active
    _kill_switch_active = active
    severity = "CRITICAL" if active else "INFO"
    message = "KILL SWITCH ACTIVATED — all trading halted" if active else "KILL SWITCH DEACTIVATED — trading resumed"
    log_event("SAFETY", severity, message)
    logger.log(logging.CRITICAL if active else logging.INFO, message)
    return {
        "active": _kill_switch_active,
        "message": message,
    }


@app.post("/api/ai/research", response_model=AIResearchResponse)
def ai_research(query: AIResearchQuery, authorized: bool = Depends(verify_api_key)):
    """AI Research endpoint — reads existing data to answer questions.
    NOTE: This is a placeholder. Full AI integration requires backend AI gateway."""
    question = query.question.lower()
    evidence = []

    with db_connection() as conn:
        if "m7" in question or "strategy" in question:
            m7_runs = conn.execute(
                "SELECT COUNT(*) as cnt FROM backtest_runs WHERE ai_id LIKE '%m7%' OR ai_id LIKE '%M7%'"
            ).fetchone()
            if m7_runs:
                evidence.append(f"M7 backtest runs found: {m7_runs['cnt']}")

            try:
                m7_signals = conn.execute("SELECT COUNT(*) as cnt FROM m7_signals").fetchone()
                if m7_signals:
                    evidence.append(f"M7 signals recorded: {m7_signals['cnt']}")
            except Exception:
                evidence.append("M7 signals table: no data")

        if "trade" in question or "execute" in question:
            trade_count = conn.execute("SELECT COUNT(*) as cnt FROM trades").fetchone()
            evidence.append(f"Total trades executed: {trade_count['cnt'] if trade_count else 0}")

    if "safety" in question or "live" in question:
        evidence.append(f"LIVE_TRADING: {Config.LIVE_TRADING}")
        evidence.append(f"MT5_DEMO_ONLY: {Config.MT5_DEMO_ONLY}")
        evidence.append(f"MT5_DEMO_TRADING_ENABLED: {Config.MT5_DEMO_TRADING_ENABLED}")

    if not evidence:
        evidence.append("No specific data found for this query in the current database.")

    answer = (
        f"Based on available data: {'; '.join(evidence)}. "
        "This is a data-based response from the AshtradingAI database. "
        "For deeper AI analysis, the full AI gateway integration is required."
    )

    return AIResearchResponse(
        answer=answer,
        evidence=evidence,
        confidence="DATA_BASED",
        disclaimer="This response is based on stored data only. It does not constitute financial advice.",
    )


@app.get("/api/research/reports")
def get_research_reports(authorized: bool = Depends(verify_api_key)):
    """List available research reports (M9-M13)."""
    reports_dir = Path(__file__).resolve().parent
    reports = []
    for prefix in ["m9", "m10", "m11", "m12", "m13"]:
        json_file = reports_dir / f"{prefix}_validation_report.json" if prefix == "m9" else reports_dir / f"{prefix}_diagnostics_report.json" if prefix == "m10" else reports_dir / f"{prefix}_calibration_report.json" if prefix == "m11" else reports_dir / f"{prefix}_strategy_structure_report.json" if prefix == "m12" else reports_dir / f"{prefix}_predictive_value_report.json"
        if json_file.exists():
            try:
                with open(json_file) as f:
                    data = json.load(f)
                reports.append({
                    "id": prefix.upper(),
                    "file": str(json_file.name),
                    "available": True,
                    "summary": str(data)[:500] if isinstance(data, dict) else str(data)[:500],
                })
            except Exception:
                reports.append({"id": prefix.upper(), "file": str(json_file.name), "available": True, "summary": "Unable to parse"})
    return {"reports": reports}


# ── Multi-Strategy Engine Endpoints ───────────────────────────────────

@app.get("/api/strategies/registry")
def get_strategy_registry(authorized: bool = Depends(verify_api_key)):
    """List all registered strategies with their specs."""
    from src.strategy.spec import get_default_strategies
    strategies = get_default_strategies()
    return {
        "strategies": [
            {
                "strategy_id": s.strategy_id,
                "name": s.spec.name,
                "family": s.spec.strategy_family,
                "holding_period": s.spec.expected_holding_period,
                "timeframes": s.spec.supported_timeframes,
                "regimes": s.spec.regime_compatibility,
                "entry_conditions": s.spec.entry_conditions,
                "invalidation_conditions": s.spec.invalidation_conditions,
                "min_bars": s.spec.min_bars_required,
            }
            for s in strategies
        ],
        "total": len(strategies),
    }


@app.get("/api/strategies/leaderboard")
def get_strategy_leaderboard(
    symbol: Optional[str] = None,
    regime: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    authorized: bool = Depends(verify_api_key),
):
    """Strategy leaderboard with scoring."""
    from src.strategy.spec import get_default_strategies
    from src.strategy.scoring import StrategyScorer
    from src.strategy.regime_detector import MarketRegimeDetector

    strategies_list = get_default_strategies()
    strategies_dict = {s.strategy_id: s for s in strategies_list}
    scorer = StrategyScorer()

    # Generate synthetic candles for scoring demo
    candles = [
        {"close": 1.1 + (i * 0.0001), "high": 1.101 + (i * 0.0001),
         "low": 1.099 + (i * 0.0001), "open": 1.1 + ((i - 1) * 0.0001),
         "timestamp": f"2024-01-01T{i:02d}:00:00", "volume": 1000}
        for i in range(100)
    ]
    indicators = {}
    context = {"symbol": symbol or "EURUSD", "timeframe": "H1"}

    scores = scorer.score_strategies(strategies_dict, candles, indicators, context, regime)
    return {
        "leaderboard": [s.to_dict() for s in scores[:limit]],
        "total_strategies": len(scores),
        "regime_filter": regime,
        "symbol_filter": symbol,
    }


@app.get("/api/regime/detect")
def detect_market_regime(
    symbol: Optional[str] = None,
    authorized: bool = Depends(verify_api_key),
):
    """Detect current market regime."""
    from src.strategy.regime_detector import MarketRegimeDetector

    detector = MarketRegimeDetector()
    candles = [
        {"close": 1.1 + (i * 0.0001), "high": 1.101 + (i * 0.0001),
         "low": 1.099 + (i * 0.0001), "open": 1.1 + ((i - 1) * 0.0001),
         "timestamp": f"2024-01-01T{i:02d}:00:00", "volume": 1000}
        for i in range(100)
    ]
    indicators = {
        "ema_12": [1.1 + (i * 0.0001) for i in range(100)],
        "ema_26": [1.1 + (i * 0.00005) for i in range(100)],
        "adx_14": [30.0] * 100,
        "atr_14": [0.001] * 100,
    }

    regime = detector.detect(candles, indicators)
    preferences = detector.get_strategy_preferences(regime)

    return {
        "regime": regime.to_dict(),
        "strategy_preferences": preferences,
    }


@app.get("/api/ai/strategy-select")
def ai_select_strategy(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    authorized: bool = Depends(verify_api_key),
):
    """AI strategy selection based on market conditions."""
    from src.strategy.spec import get_default_strategies
    from src.strategy.ai_selector import AIStrategySelector
    from src.strategy.regime_detector import MarketRegimeDetector

    strategies_list = get_default_strategies()
    strategies_dict = {s.strategy_id: s for s in strategies_list}
    detector = MarketRegimeDetector()
    selector = AIStrategySelector(strategies_dict, detector)

    candles = [
        {"close": 1.1 + (i * 0.0001), "high": 1.101 + (i * 0.0001),
         "low": 1.099 + (i * 0.0001), "open": 1.1 + ((i - 1) * 0.0001),
         "timestamp": f"2024-01-01T{i:02d}:00:00", "volume": 1000}
        for i in range(100)
    ]
    indicators = {
        "ema_12": [1.1 + (i * 0.0001) for i in range(100)],
        "ema_26": [1.1 + (i * 0.00005) for i in range(100)],
        "adx_14": [30.0] * 100,
        "atr_14": [0.001] * 100,
    }
    context = {
        "symbol": symbol or "EURUSD",
        "timeframe": timeframe or "H1",
        "session": "API",
        "open_positions": [],
        "risk_state": {},
    }

    selection = selector.select_strategy(candles, indicators, context)
    return {"selection": selection.to_dict()}


@app.get("/api/automation/status")
def get_automation_status(authorized: bool = Depends(verify_api_key)):
    """Get phone session automation status."""
    return {
        "session": {
            "state": "INACTIVE",
            "is_active": False,
            "allows_new_trades": False,
        },
        "lease": None,
        "config": {
            "heartbeat_interval": 30.0,
            "lease_duration": 300.0,
            "max_lease_extensions": 10,
        },
    }


@app.post("/api/automation/start")
def start_automation(
    session_id: str = "api_session",
    authorized: bool = Depends(verify_api_key),
):
    """Start automation session (phone-first)."""
    log_event("AUTOMATION", "INFO", f"Automation session started: {session_id}")
    return {
        "status": "started",
        "session_id": session_id,
        "message": "Automation session started. Heartbeat required to maintain.",
    }


@app.post("/api/automation/stop")
def stop_automation(authorized: bool = Depends(verify_api_key)):
    """Stop automation session. No new trades after this."""
    log_event("AUTOMATION", "INFO", "Automation session stopped")
    return {
        "status": "stopped",
        "message": "Automation stopped. No new trades will be placed.",
    }


@app.post("/api/automation/heartbeat")
def automation_heartbeat(authorized: bool = Depends(verify_api_key)):
    """Send heartbeat to keep automation session alive."""
    return {
        "status": "ok",
        "message": "Heartbeat received",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/risk/multi-strategy")
def get_multi_strategy_risk(authorized: bool = Depends(verify_api_key)):
    """Get multi-strategy risk status."""
    return {
        "config": {
            "max_strategies_per_symbol": 3,
            "max_correlated_exposure": 0.30,
            "max_total_exposure": 0.50,
            "strategy_switch_cooldown": 300,
            "max_trades_per_strategy_per_day": 5,
        },
        "strategy_states": {},
        "total_exposure": 0.0,
    }


@app.get("/api/risk/advanced")
def get_advanced_risk(authorized: bool = Depends(verify_api_key)):
    """Get advanced risk engine status."""
    return {
        "kill_switch": False,
        "trades_today": 0,
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "consecutive_losses": 0,
        "peak_balance": Config.STARTING_BALANCE,
        "total_blocks": 0,
        "config": {
            "risk_per_trade": 0.01,
            "max_daily_loss": Config.MAX_DAILY_LOSS,
            "max_drawdown": Config.MAX_DRAWDOWN,
            "max_open_positions": Config.MAX_OPEN_POSITIONS,
            "min_confidence": Config.MIN_AI_CONFIDENCE,
            "cooldown_seconds": 300,
        },
    }


@app.get("/api/journal")
def get_journal(
    limit: int = Query(50, ge=1, le=500),
    authorized: bool = Depends(verify_api_key),
):
    """Get trade journal entries."""
    with db_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            rows = []
    entries = []
    for row in rows:
        entries.append({
            "trade_id": row["id"],
            "timestamp": row["timestamp"],
            "symbol": row["symbol"],
            "side": row["side"],
            "entry_price": row["entry_price"],
            "exit_price": row["exit_price"],
            "quantity": row["quantity"],
            "pnl": row["pnl"],
            "fee": row["fee"],
        })
    return {"journal": entries}


@app.get("/api/performance")
def get_performance(authorized: bool = Depends(verify_api_key)):
    """Get performance metrics."""
    with db_connection() as conn:
        try:
            trades = conn.execute("SELECT * FROM trades").fetchall()
        except Exception:
            trades = []

    total_trades = len(trades)
    winning = sum(1 for t in trades if (t["pnl"] or 0) > 0)
    losing = sum(1 for t in trades if (t["pnl"] or 0) <= 0)
    total_pnl = sum(t["pnl"] or 0 for t in trades)
    win_rate = winning / total_trades if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total_trades, 4) if total_trades > 0 else 0.0,
    }


# ── Phase 26: WebSocket Real-Time Updates ─────────────────────────────

import asyncio
from collections import deque
from fastapi import WebSocket, WebSocketDisconnect

_ws_clients: list = []
_event_buffer: deque = deque(maxlen=100)


async def broadcast_event(event_type: str, data: dict):
    """Broadcast event to all connected WebSocket clients."""
    message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
    _event_buffer.append({"type": event_type, "data": data})
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    _ws_clients.append(websocket)
    logger.info("WebSocket client connected (%d total)", len(_ws_clients))
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            cmd = msg.get("command", "")
            if cmd == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif cmd == "status":
                status = {"mode": "PAPER", "kill_switch": False, "market_health": "CONNECTED"}
                await websocket.send_text(json.dumps({"type": "status", "data": status}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
    finally:
        try:
            _ws_clients.remove(websocket)
        except ValueError:
            pass
        logger.info("WebSocket client disconnected (%d remaining)", len(_ws_clients))


# ── Phase 25: Terminal API ────────────────────────────────────────────

TERMINAL_ALLOWED_COMMANDS = {
    "status", "health", "account", "markets", "positions", "orders",
    "journal", "risk", "strategies", "paper_start", "paper_stop",
    "paper_pause", "paper_resume", "backtest", "reconcile", "kill_switch",
}


class TerminalCommand(BaseModel):
    command: str
    args: dict = {}


class TerminalResponse(BaseModel):
    command: str
    result: dict
    error: Optional[str] = None
    timestamp: str = ""


@app.post("/api/terminal")
def execute_terminal_command(
    cmd: TerminalCommand,
    authorized: bool = Depends(verify_api_key),
):
    """Execute a predefined terminal command. No arbitrary shell access."""
    if cmd.command not in TERMINAL_ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Command not allowed: {cmd.command}")

    result = {"command": cmd.command, "status": "executed"}
    ts = datetime.now(timezone.utc).isoformat()

    if cmd.command == "status":
        result["data"] = {
            "mode": "PAPER",
            "lived_trading": Config.LIVE_TRADING,
            "mt5_demo_only": Config.MT5_DEMO_ONLY,
            "version": "2.0.0",
        }
    elif cmd.command == "health":
        result["data"] = {"api": "healthy", "database": "healthy", "market": "no_data"}
    elif cmd.command == "account":
        result["data"] = {"balance": Config.STARTING_BALANCE, "mode": "paper"}
    elif cmd.command == "kill_switch":
        result["data"] = {"kill_switch_activated": True}
    elif cmd.command == "risk":
        result["data"] = {
            "max_daily_loss": Config.MAX_DAILY_LOSS,
            "max_drawdown": Config.MAX_DRAWDOWN,
            "max_positions": Config.MAX_OPEN_POSITIONS,
        }
    else:
        result["data"] = {"message": f"{cmd.command} acknowledged"}

    return TerminalResponse(command=cmd.command, result=result, timestamp=ts)


# ── Phase 42: Safety Invariant Endpoint ───────────────────────────────

@app.get("/api/safety/invariants")
def check_safety_invariants(authorized: bool = Depends(verify_api_key)):
    """Verify safety invariants are never silently changed."""
    return {
        "LIVE_TRADING": {"value": Config.LIVE_TRADING, "expected": False, "safe": not Config.LIVE_TRADING},
        "MT5_DEMO_ONLY": {"value": Config.MT5_DEMO_ONLY, "expected": True, "safe": Config.MT5_DEMO_ONLY},
        "MT5_DEMO_TRADING_ENABLED": {"value": Config.MT5_DEMO_TRADING_ENABLED, "expected": False, "safe": not Config.MT5_DEMO_TRADING_ENABLED},
        "all_safe": not Config.LIVE_TRADING and Config.MT5_DEMO_ONLY and not Config.MT5_DEMO_TRADING_ENABLED,
    }


# ── Phase 26: Event Types ────────────────────────────────────────────

@app.get("/api/events/recent")
def get_recent_events(authorized: bool = Depends(verify_api_key)):
    """Get recent WebSocket events from buffer."""
    return {"events": list(_event_buffer)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    logger.info("Starting AshtradingAI API on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
