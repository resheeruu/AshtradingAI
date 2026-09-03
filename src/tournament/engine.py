"""Tournament engine — candle-by-candle execution with strict no-lookahead."""
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.ai.base import TradingAI, MarketContext
from src.ai.providers.openai_compatible import parse_ai_response
from src.ai.health import ProviderHealthManager
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.indicators.technical import compute_all_indicators
from src.tournament.participant import ParticipantConfig
from src.tournament.prompts import build_tournament_prompt, build_risk_limits_dict
from src.tournament.metrics import (
    TournamentMetrics, compute_tournament_metrics, compute_composite_score, assign_awards,
)

logger = logging.getLogger(__name__)


@dataclass
class TournamentConfig:
    """Configuration for a tournament experiment."""
    experiment_id: str = ""
    exchange: str = "binance"
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    timeframe: str = "1h"
    candle_limit: int = 500
    starting_balance: float = 1000.0
    fee: float = 0.001
    slippage: float = 0.0005
    max_position_size: float = 0.10
    max_open_positions: int = 3
    max_daily_loss: float = 0.03
    max_drawdown: float = 0.15
    min_confidence: float = 0.60
    software_version: str = "0.1.0"

    def __post_init__(self):
        if not self.experiment_id:
            self.experiment_id = str(uuid.uuid4())[:8]


@dataclass
class AIDecisionLog:
    """Audit trail entry for a single AI decision."""
    experiment_id: str
    timestamp: str
    candle_index: int
    ai_id: str
    symbol: str
    price: float
    decision: str
    confidence: float
    reason: str
    suggested_position_size: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    action_taken: str  # EXECUTED, REJECTED_BY_RISK, HOLD, AI_ERROR
    balance_before: float
    balance_after: float


class TournamentEngine:
    """Candle-by-candle tournament engine with strict no-lookahead enforcement.

    Fair execution:
    1. Load shared read-only market data
    2. For each candle timestamp:
       a. Compute indicators from historical data only
       b. Build identical market context for each AI
       c. Collect all AI decisions (order-independent)
       d. Apply identical risk rules
       e. Execute paper orders independently
       f. Record all decisions and trades
    """

    def __init__(self, config: TournamentConfig, database=None, health_manager: Optional[ProviderHealthManager] = None):
        self.config = config
        self._database = database
        self._health_manager = health_manager
        self._risk_manager = RiskManager(
            max_position_size=config.max_position_size,
            max_open_positions=config.max_open_positions,
            max_daily_loss=config.max_daily_loss,
            max_drawdown=config.max_drawdown,
            min_confidence=config.min_confidence,
        )

    def run(
        self,
        participants: List[ParticipantConfig],
        data: Dict[str, List[dict]],
    ) -> Dict[str, Any]:
        """Run a tournament with multiple participants on shared data.

        Returns dict with experiment_id, participants results, and decision logs.
        """
        # Create isolated components per participant
        entries = []
        for p_cfg in participants:
            if not p_cfg.is_available:
                logger.warning("Skipping unavailable participant: %s (%s)", p_cfg.id, p_cfg.provider)
                continue

            ai = p_cfg.create_ai()
            if ai is None:
                logger.warning("Failed to create AI for participant: %s", p_cfg.id)
                continue

            portfolio = Portfolio(ai_id=p_cfg.id, starting_balance=self.config.starting_balance)
            broker = PaperBroker(fee=self.config.fee, slippage=self.config.slippage)

            entries.append({
                "config": p_cfg,
                "ai": ai,
                "portfolio": portfolio,
                "broker": broker,
                "trading_returns": [],
                "prev_balance": self.config.starting_balance,
            })

        if not entries:
            return {"error": "no_available_participants", "experiment_id": self.config.experiment_id}

        # Pre-compute indicators per symbol (read-only, shared)
        indicator_data: Dict[str, dict] = {}
        for sym, candles in data.items():
            if len(candles) >= 50:
                indicator_data[sym] = compute_all_indicators(candles)

        # Build unified timestamp index
        all_timestamps = set()
        for candles in data.values():
            for c in candles:
                all_timestamps.add(c["timestamp"])
        timestamps = sorted(all_timestamps)

        # Index candles by timestamp per symbol
        candle_index: Dict[str, Dict[str, dict]] = {}
        for sym, candles in data.items():
            candle_index[sym] = {c["timestamp"]: c for c in candles}

        # Track all decisions for audit trail
        all_decision_logs: List[AIDecisionLog] = []

        # Risk limits for prompt
        risk_limits = build_risk_limits_dict(
            max_position_size=self.config.max_position_size,
            max_open_positions=self.config.max_open_positions,
            max_daily_loss=self.config.max_daily_loss,
            max_drawdown=self.config.max_drawdown,
            min_confidence=self.config.min_confidence,
        )

        # Process each candle
        for candle_idx, ts in enumerate(timestamps):
            for symbol in data:
                if symbol not in candle_index or ts not in candle_index[symbol]:
                    continue

                row = candle_index[symbol][ts]
                candles_list = data[symbol]

                # Build context from historical data ONLY (no lookahead)
                ctx_candles = [c for c in candles_list if c["timestamp"] <= ts]
                if len(ctx_candles) < 20:
                    continue

                # Build indicators for current position only
                ctx_indicators = {}
                if symbol in indicator_data:
                    ind = indicator_data[symbol]
                    idx = None
                    for i, c in enumerate(candles_list):
                        if c["timestamp"] == ts:
                            idx = i
                            break
                    if idx is not None:
                        for key, vals in ind.items():
                            if idx < len(vals) and vals[idx] is not None:
                                ctx_indicators[key] = vals[idx]

                # --- Phase 1: Collect all AI decisions for this candle ---
                decisions = []
                for entry in entries:
                    portfolio = entry["portfolio"]
                    ai = entry["ai"]

                    ctx = MarketContext(
                        symbol=symbol,
                        timeframe=self.config.timeframe,
                        current_price=row["close"],
                        candles=ctx_candles,
                        indicators=ctx_indicators,
                        portfolio_balance=portfolio.balance,
                        open_positions=list(portfolio.positions.keys()),
                        timestamp=ts,
                    )

                    try:
                        raw_decision = ai.decide(ctx)
                    except Exception as e:
                        logger.error("[%s] AI error at candle %d: %s", ai.ai_id, candle_idx, e)
                        raw_decision = {"decision": "HOLD", "confidence": 0.0, "reason": f"ai_error: {e}"}

                    # Normalize decision
                    decision_str = str(raw_decision.get("decision", "HOLD")).upper()
                    if decision_str not in ("BUY", "SELL", "HOLD"):
                        decision_str = "HOLD"

                    # Validate: no position logic conflicts
                    pos = portfolio.get_position(symbol)
                    if decision_str == "SELL" and pos is None:
                        decision_str = "HOLD"
                    if decision_str == "BUY" and pos is not None:
                        decision_str = "HOLD"

                    qty = raw_decision.get("suggested_position_size")
                    if qty is not None and qty <= 0:
                        qty = None

                    decisions.append({
                        "entry": entry,
                        "decision": decision_str,
                        "confidence": raw_decision.get("confidence", 0.0),
                        "reason": raw_decision.get("reason", ""),
                        "position_size": qty,
                        "stop_loss": raw_decision.get("stop_loss"),
                        "take_profit": raw_decision.get("take_profit"),
                    })

                # --- Phase 2: Apply risk rules and execute independently ---
                for dec in decisions:
                    entry = dec["entry"]
                    portfolio = entry["portfolio"]
                    broker = entry["broker"]
                    ai = entry["ai"]
                    balance_before = portfolio.balance

                    if dec["decision"] == "HOLD":
                        action = "HOLD"
                    else:
                        risk = self._risk_manager.evaluate(
                            portfolio=portfolio,
                            decision=dec["decision"],
                            symbol=symbol,
                            price=row["close"],
                            confidence=dec["confidence"],
                            requested_size=dec["position_size"],
                        )
                        if not risk.allowed:
                            action = "REJECTED_BY_RISK"
                        else:
                            qty = risk.adjusted_size if risk.adjusted_size is not None else dec["position_size"]
                            if qty is None or qty <= 0:
                                action = "REJECTED_BY_RISK"
                            elif dec["decision"] == "BUY":
                                result = broker.execute_buy(
                                    portfolio, symbol, row["close"], qty,
                                    stop_loss=dec["stop_loss"],
                                    take_profit=dec["take_profit"],
                                    timestamp=ts,
                                )
                                action = "EXECUTED" if result else "REJECTED_BY_RISK"
                            elif dec["decision"] == "SELL":
                                result = broker.execute_sell(
                                    portfolio, symbol, row["close"], timestamp=ts,
                                )
                                action = "EXECUTED" if result else "REJECTED_BY_RISK"
                            else:
                                action = "HOLD"

                    # Track returns
                    if portfolio.balance != entry["prev_balance"]:
                        ret = (portfolio.balance - entry["prev_balance"]) / entry["prev_balance"] if entry["prev_balance"] > 0 else 0.0
                        entry["trading_returns"].append(ret)
                        entry["prev_balance"] = portfolio.balance

                    # Log decision
                    log_entry = AIDecisionLog(
                        experiment_id=self.config.experiment_id,
                        timestamp=ts,
                        candle_index=candle_idx,
                        ai_id=ai.ai_id,
                        symbol=symbol,
                        price=row["close"],
                        decision=dec["decision"],
                        confidence=dec["confidence"],
                        reason=dec["reason"],
                        suggested_position_size=dec["position_size"],
                        stop_loss=dec["stop_loss"],
                        take_profit=dec["take_profit"],
                        action_taken=action,
                        balance_before=balance_before,
                        balance_after=portfolio.balance,
                    )
                    all_decision_logs.append(log_entry)

        # --- Phase 3: Close remaining positions ---
        for entry in entries:
            portfolio = entry["portfolio"]
            broker = entry["broker"]
            for symbol in list(portfolio.positions.keys()):
                if symbol in candle_index:
                    for ts in reversed(timestamps):
                        if ts in candle_index[symbol]:
                            last_price = candle_index[symbol][ts]["close"]
                            broker.execute_sell(portfolio, symbol, last_price, timestamp=ts)
                            break

        # --- Phase 4: Compute metrics ---
        participants_metrics = []
        for entry in entries:
            metrics = compute_tournament_metrics(
                ai_id=entry["ai"].ai_id,
                starting_balance=self.config.starting_balance,
                ending_balance=entry["portfolio"].balance,
                trades=entry["portfolio"].trade_history,
                trading_returns=entry["trading_returns"],
            )
            metrics.composite_score = compute_composite_score(metrics)
            participants_metrics.append(metrics)

        # Assign awards
        participants_metrics = assign_awards(participants_metrics)

        # Sort by composite score
        participants_metrics.sort(key=lambda p: p.composite_score, reverse=True)

        # --- Phase 5: Persist to database ---
        if self._database:
            self._persist_results(entries, participants_metrics, all_decision_logs)

        # Log provider health and usage if health manager is available
        if self._database and self._health_manager:
            self._log_provider_state()

        return {
            "experiment_id": self.config.experiment_id,
            "config": {
                "exchange": self.config.exchange,
                "symbols": self.config.symbols,
                "timeframe": self.config.timeframe,
                "candle_limit": self.config.candle_limit,
                "starting_balance": self.config.starting_balance,
                "fee": self.config.fee,
                "slippage": self.config.slippage,
                "software_version": self.config.software_version,
            },
            "participants": [m.summary() for m in participants_metrics],
            "decision_logs_count": len(all_decision_logs),
        }

    def _persist_results(
        self,
        entries: List[dict],
        metrics_list: List[TournamentMetrics],
        decision_logs: List[AIDecisionLog],
    ) -> None:
        """Persist tournament results to database."""
        try:
            # Log backtest runs
            for metrics in metrics_list:
                self._database.log_backtest_run(
                    ai_id=metrics.ai_id,
                    symbol=",".join(self.config.symbols),
                    timeframe=self.config.timeframe,
                    starting_balance=metrics.starting_balance,
                    ending_balance=metrics.ending_balance,
                    return_percent=metrics.return_pct,
                    max_drawdown=metrics.max_drawdown,
                    win_rate=metrics.win_rate,
                    profit_factor=metrics.profit_factor,
                    sharpe_ratio=metrics.sharpe_ratio,
                    sortino_ratio=metrics.sortino_ratio,
                    trade_count=metrics.num_trades,
                    experiment_id=self.config.experiment_id,
                    metrics_json=str(metrics.summary()),
                )

            # Log individual trades
            for entry in entries:
                for trade in entry["portfolio"].trade_history:
                    self._database.log_trade(
                        ai_id=entry["ai"].ai_id,
                        symbol=trade.symbol,
                        side=trade.side,
                        entry_price=trade.entry_price,
                        exit_price=trade.exit_price,
                        quantity=trade.quantity,
                        fee=trade.fee,
                        slippage=trade.slippage,
                        pnl=trade.pnl,
                        balance=entry["portfolio"].balance,
                        experiment_id=self.config.experiment_id,
                    )

            # Log AI decisions (batch commit for performance)
            for log in decision_logs:
                self._database.log_decision(
                    ai_id=log.ai_id,
                    symbol=log.symbol,
                    decision=log.decision,
                    confidence=log.confidence,
                    reason=log.reason,
                    suggested_position_size=log.suggested_position_size,
                    stop_loss=log.stop_loss,
                    take_profit=log.take_profit,
                    market_price=log.price,
                    experiment_id=self.config.experiment_id,
                )

            logger.info("Persisted tournament results: %d participants, %d decisions",
                       len(metrics_list), len(decision_logs))
        except Exception as e:
            logger.error("Failed to persist tournament results: %s", e)

    def _log_provider_state(self) -> None:
        """Log provider health and usage to database."""
        try:
            states = self._health_manager.get_all_provider_states()
            for key, info in states.items():
                self._database.log_provider_health(
                    provider=info.provider,
                    model=info.model,
                    state=info.state.value,
                    failure_count=info.total_failures,
                    success_count=info.total_successes,
                    last_error=info.last_error[:500] if info.last_error else None,
                    last_error_kind=info.last_error_kind.value if info.last_error_kind else None,
                    last_failure_time=info.last_failure_time if info.last_failure_time else None,
                    last_success_time=info.last_success_time if info.last_success_time else None,
                    cooldown_until=info.cooldown_until if info.cooldown_until else None,
                )

            api_usage = self._health_manager.get_tournament_api_usage()
            for participant_id, usage in api_usage.items():
                if usage.get("total_requests", 0) > 0:
                    self._database.log_provider_usage(
                        provider=usage.get("provider", ""),
                        model=usage.get("model", ""),
                        tokens_used=usage.get("total_tokens", 0),
                        request_success=usage.get("failed_requests", 0) == 0,
                        experiment_id=self.config.experiment_id,
                        participant_id=participant_id,
                    )
            logger.debug("Logged provider health and usage to database")
        except Exception as e:
            logger.error("Failed to log provider state: %s", e)


def validate_no_lookahead(
    data: Dict[str, List[dict]],
    context_candles: List[dict],
    current_timestamp: str,
    symbol: str,
) -> bool:
    """Validate that context candles contain no future data.

    Returns True if no lookahead detected.
    """
    for c in context_candles:
        if c.get("timestamp", "") > current_timestamp:
            logger.error(
                "LOOKAHEAD DETECTED: candle timestamp %s > current %s in symbol %s",
                c.get("timestamp"), current_timestamp, symbol,
            )
            return False
    return True
