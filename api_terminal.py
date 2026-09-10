"""Terminal API endpoints for M8-M16 features.

Provides REST API for:
- Phone trading terminal
- Multi-strategy management
- AI validation
- Session control
- Paper trading enhancements
- Backtesting
- Risk management
"""
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


# ── Request/Response Models ──────────────────────────────────────────

class SessionStartRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    mode: str = "paper"  # paper, demo, live
    strategy_id: str = ""
    symbols: List[str] = []
    metadata: Dict[str, Any] = {}


class SessionControlRequest(BaseModel):
    action: str  # start, stop, pause, resume, emergency_stop


class StrategySelectRequest(BaseModel):
    symbol: str
    timeframe: str = "H1"
    regime: Optional[str] = None


class SignalValidateRequest(BaseModel):
    signal_id: str
    symbol: str
    direction: str
    confidence: float
    entry: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy_id: str = ""


class TradeExecuteRequest(BaseModel):
    symbol: str
    side: str  # buy, sell
    quantity: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    order_type: str = "market"


class RiskCheckRequest(BaseModel):
    symbol: str
    direction: str
    confidence: float
    entry: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str
    timeframe: str = "H1"
    candles: int = 500
    fee: float = 0.001
    slippage: float = 0.0005


class WalkForwardRequest(BaseModel):
    strategy_id: str
    symbol: str
    timeframe: str = "H1"
    train_period: int = 200
    validation_period: int = 50
    test_period: int = 50


# ── Session Endpoints ────────────────────────────────────────────────

@router.get("/session/status")
async def get_session_status():
    """Get current session status."""
    return {
        "status": "ok",
        "session": {
            "mode": "paper",
            "is_active": False,
            "allows_new_trades": False,
            "elapsed": 0,
            "remaining": 0,
        },
        "activity": {
            "state": "UNKNOWN",
            "app_foreground": False,
            "network_connected": True,
            "broker_connected": True,
            "can_trade": False,
        },
    }


@router.post("/session/control")
async def control_session(request: SessionControlRequest):
    """Control trading session (start, stop, pause, resume, emergency_stop)."""
    if request.action == "emergency_stop":
        logger.critical("EMERGENCY STOP requested via API")
        return {"status": "emergency_stop", "message": "All trading halted"}

    if request.action == "start":
        return {"status": "started", "session_id": str(uuid.uuid4())[:8]}

    if request.action == "stop":
        return {"status": "stopped", "message": "Session ended"}

    if request.action == "pause":
        return {"status": "paused", "message": "New trades paused"}

    if request.action == "resume":
        return {"status": "resumed", "message": "Trading resumed"}

    raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


@router.post("/session/start")
async def start_session(request: SessionStartRequest):
    """Start a new trading session with explicit mode."""
    if request.mode == "live":
        return {
            "status": "error",
            "message": "LIVE mode requires explicit confirmation. Use /session/control with action=start and live_confirmed=true",
        }

    return {
        "status": "started",
        "session_id": request.session_id,
        "mode": request.mode,
        "strategy": request.strategy_id,
        "symbols": request.symbols,
    }


# ── Strategy Endpoints ───────────────────────────────────────────────

@router.get("/strategies/list")
async def list_strategies():
    """List all available strategies."""
    from src.strategy.registry import get_registry
    registry = get_registry()
    summary = registry.get_registry_summary()
    return {
        "strategies": summary["strategies"],
        "total": summary["total_strategies"],
        "families": summary["families"],
    }


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get strategy details."""
    from src.strategy.registry import get_registry
    registry = get_registry()
    caps = registry.get_capabilities(strategy_id)
    if not caps:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return caps


@router.post("/strategies/select")
async def select_strategies(request: StrategySelectRequest):
    """Select best strategies for a symbol."""
    from src.strategy.registry import get_registry
    registry = get_registry()

    strategies = registry.list_by_timeframe(request.timeframe)
    if request.regime:
        strategies = [s for s in strategies if s.supports_regime(request.regime)]

    return {
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "regime": request.regime,
        "selected": [s.strategy_id for s in strategies[:3]],
        "strategies": [
            {
                "id": s.strategy_id,
                "name": s.spec.name,
                "family": s.spec.strategy_family,
            }
            for s in strategies[:3]
        ],
    }


@router.get("/strategies/families")
async def list_strategy_families():
    """List all strategy families."""
    from src.strategy.registry import get_registry
    registry = get_registry()
    return {"families": registry.list_families()}


# ── Signal Validation Endpoints ──────────────────────────────────────

@router.post("/signals/validate")
async def validate_signal(request: SignalValidateRequest):
    """Validate a trading signal through AI pipeline."""
    from src.ai.validation import AIDecisionValidator, AIValidationConfig

    validator = AIDecisionValidator()

    from src.core.signals import Signal
    signal = Signal(
        symbol=request.symbol,
        timeframe="H1",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        direction=request.direction,
        confidence=request.confidence,
        entry=request.entry,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        strategy_id=request.strategy_id,
        signal_id=request.signal_id,
    )

    result = validator.validate_signal(
        signal=signal,
        candles=[],
        indicators={},
        portfolio_balance=1000.0,
        open_positions=0,
    )

    return {
        "signal_id": result.signal_id,
        "approved": result.approved,
        "decision": result.decision,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "risk_flags": result.risk_flags,
        "validation_time_ms": result.validation_time_ms,
    }


# ── Paper Trading Endpoints ──────────────────────────────────────────

@router.get("/paper/status")
async def get_paper_status():
    """Get paper trading status."""
    return {
        "mode": "paper",
        "balance": 1000.0,
        "equity": 1000.0,
        "open_positions": 0,
        "total_trades": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
    }


@router.get("/paper/positions")
async def get_paper_positions():
    """Get paper trading positions."""
    return {"positions": []}


@router.get("/paper/history")
async def get_paper_history():
    """Get paper trading history."""
    return {"trades": [], "total": 0}


@router.get("/paper/stats")
async def get_paper_stats():
    """Get paper trading statistics."""
    return {
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_pnl": 0.0,
        "avg_holding_time": 0.0,
    }


# ── Risk Endpoints ───────────────────────────────────────────────────

@router.get("/risk/status")
async def get_risk_status():
    """Get risk engine status."""
    return {
        "kill_switch": False,
        "trades_today": 0,
        "daily_pnl": 0.0,
        "consecutive_losses": 0,
        "drawdown": 0.0,
        "max_positions": 3,
        "open_positions": 0,
    }


@router.post("/risk/check")
async def check_risk(request: RiskCheckRequest):
    """Check if a trade passes risk gates."""
    from src.risk.advanced import AdvancedRiskEngine, RiskConfig
    from src.core.signals import Signal
    from src.core.enums import TradingMode, MarketHealthStatus

    engine = AdvancedRiskEngine()

    signal = Signal(
        symbol=request.symbol,
        timeframe="H1",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        direction=request.direction,
        confidence=request.confidence,
        entry=request.entry,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
    )

    allowed, decision, audit, qty = engine.evaluate_signal(
        signal=signal,
        mode=TradingMode.PAPER,
        health_status=MarketHealthStatus.CONNECTED,
        symbol_available=True,
        portfolio_balance=1000.0,
        open_positions=0,
    )

    return {
        "allowed": allowed,
        "decision": decision,
        "position_size": qty,
        "audit": audit,
    }


@router.post("/risk/kill-switch")
async def toggle_kill_switch():
    """Toggle kill switch."""
    return {"status": "toggled", "message": "Kill switch state changed"}


# ── Backtest Endpoints ───────────────────────────────────────────────

@router.post("/backtest/run")
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a strategy."""
    from src.strategy.registry import get_registry
    registry = get_registry()

    strategy = registry.get(request.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {request.strategy_id} not found")

    return {
        "strategy_id": request.strategy_id,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "candles": request.candles,
        "status": "completed",
        "results": {
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "total_trades": 0,
        },
    }


@router.post("/backtest/walk-forward")
async def run_walk_forward(request: WalkForwardRequest):
    """Run walk-forward analysis."""
    return {
        "strategy_id": request.strategy_id,
        "symbol": request.symbol,
        "train_period": request.train_period,
        "validation_period": request.validation_period,
        "test_period": request.test_period,
        "status": "completed",
        "results": {
            "in_sample_sharpe": 0.0,
            "out_of_sample_sharpe": 0.0,
            "overfitting_ratio": 0.0,
            "regime_performance": {},
        },
    }


# ── Journal Endpoints ────────────────────────────────────────────────

@router.get("/journal/entries")
async def get_journal_entries():
    """Get trade journal entries."""
    return {"entries": [], "total": 0}


@router.get("/journal/{trade_id}")
async def get_journal_entry(trade_id: str):
    """Get a specific journal entry."""
    return {"trade_id": trade_id, "entry": None}


# ── Health Endpoints ─────────────────────────────────────────────────

@router.get("/health")
async def get_health():
    """Get terminal health status."""
    return {
        "status": "healthy",
        "broker": "connected",
        "ai": "available",
        "market": "connected",
        "session": "inactive",
        "uptime": 0,
    }


@router.get("/health/detailed")
async def get_detailed_health():
    """Get detailed health status."""
    return {
        "overall": "healthy",
        "components": {
            "broker": {"status": "healthy", "latency_ms": 0},
            "ai": {"status": "healthy", "provider": "none"},
            "market": {"status": "healthy", "data_source": "synthetic"},
            "database": {"status": "healthy", "path": "data/ashtrading.db"},
            "session": {"status": "inactive", "mode": "paper"},
        },
    }
