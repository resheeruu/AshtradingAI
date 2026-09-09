"""AshtradingAI REST API Server — FastAPI backend for mobile companion app."""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.config import Config
from src.persistence.database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AshtradingAI API",
    description="Research platform API for the AshtradingAI mobile companion",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
    return {"service": "AshtradingAI API", "version": "1.0.0", "status": "running"}


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
def get_account():
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
def get_positions():
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
def get_trades(limit: int = Query(50, ge=1, le=500)):
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
def get_strategies():
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
def get_experiments(limit: int = Query(50, ge=1, le=200)):
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
def get_signals(limit: int = Query(100, ge=1, le=1000)):
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
def get_ai_decisions(limit: int = Query(100, ge=1, le=1000)):
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
def get_mt5_status():
    """MT5 Demo connection and configuration status (read-only)."""
    from src.mt5.readonly_api import get_status
    return get_status()


@app.get("/api/mt5/account")
def get_mt5_account():
    """MT5 Demo account information (read-only). Balance, equity, margin, etc."""
    from src.mt5.readonly_api import get_account
    return get_account()


@app.get("/api/mt5/positions")
def get_mt5_positions(symbol: Optional[str] = None):
    """MT5 Demo open positions (read-only)."""
    from src.mt5.readonly_api import get_positions
    return {"positions": get_positions(symbol=symbol)}


@app.get("/api/mt5/orders")
def get_mt5_orders():
    """MT5 Demo pending orders (read-only)."""
    from src.mt5.readonly_api import get_orders
    return {"orders": get_orders()}


@app.get("/api/mt5/symbols")
def get_mt5_symbols():
    """MT5 Demo available symbols (read-only)."""
    from src.mt5.readonly_api import get_symbols
    return {"symbols": get_symbols()}


@app.get("/api/mt5/quote/{symbol}")
def get_mt5_quote(symbol: str):
    """MT5 Demo current bid/ask quote for a symbol (read-only)."""
    from src.mt5.readonly_api import get_quote
    quote = get_quote(symbol)
    if quote is None:
        return {"symbol": symbol, "bid": 0.0, "ask": 0.0, "error": "Symbol unavailable or MT5 not connected"}
    return quote


@app.get("/api/mt5/heartbeat")
def get_mt5_heartbeat():
    """MT5 Demo connection heartbeat — lightweight health check."""
    from src.mt5.readonly_api import get_heartbeat
    return get_heartbeat()


@app.get("/api/config")
def get_config():
    """Public configuration (no secrets)."""
    config_dict = Config.as_dict()
    safe_config = {k: v for k, v in config_dict.items()
                   if not any(s in k for s in ["KEY", "PASSWORD", "SECRET", "TOKEN"])}
    return {"config": safe_config}


@app.get("/api/market/health")
def get_market_health():
    """Market data health status."""
    return {
        "data_source": Config.DATA_SOURCE,
        "exchange": Config.EXCHANGE,
        "symbols": Config.SYMBOLS,
        "timeframe": Config.TIMEFRAME,
        "status": "ONLINE" if Config.DATA_SOURCE == "live" else "SYNTHETIC",
    }


@app.post("/api/ai/research", response_model=AIResearchResponse)
def ai_research(query: AIResearchQuery):
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
def get_research_reports():
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    logger.info("Starting AshtradingAI API on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
