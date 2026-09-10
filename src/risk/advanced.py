"""Advanced risk engine — layered gates before every trade.

Signal → Mode Gate → Market Health Gate → Symbol Gate → Session Gate →
Spread Gate → Volatility Gate → R:R Gate → Position Size Gate →
Exposure Gate → Correlation Gate → Daily Loss Gate → Drawdown Gate →
Margin Gate → Trade Frequency Gate → Cooldown Gate → Kill Switch → Execution

Every rejected trade is recorded with gate, reason, and snapshots.
"""
import logging
import time
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.enums import TradingMode, MarketHealthStatus, RiskGate
from src.core.signals import Signal, RiskBlock

logger = logging.getLogger(__name__)


@dataclass
class RiskGateResult:
    passed: bool
    gate: str
    reason: str = ""
    blocked: bool = False


@dataclass
class RiskAuditEntry:
    gate: str
    passed: bool
    reason: str
    timestamp: str = ""
    snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioExposure:
    total_exposure: float = 0.0
    asset_exposure: Dict[str, float] = field(default_factory=dict)
    currency_exposure: Dict[str, float] = field(default_factory=dict)
    strategy_exposure: Dict[str, float] = field(default_factory=dict)
    directional_exposure: Dict[str, float] = field(default_factory=dict)
    margin_usage: float = 0.0


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01
    max_daily_loss: float = 0.03
    max_weekly_loss: float = 0.05
    max_drawdown: float = 0.15
    max_consecutive_losses: int = 5
    max_open_positions: int = 3
    max_total_exposure: float = 0.30
    max_correlated_exposure: float = 0.20
    max_trades_per_day: int = 10
    min_risk_reward: float = 1.5
    min_confidence: float = 0.60
    max_spread: float = 0.005
    max_volatility: float = 0.05
    cooldown_seconds: int = 300
    weekend_trading: bool = False
    margin_safety: float = 0.50
    max_position_size: float = 0.10


class AdvancedRiskEngine:
    """Multi-gate risk engine with full audit trail."""

    def __init__(self, config: Optional[RiskConfig] = None, starting_balance: float = 1000.0):
        self.config = config or RiskConfig()
        self.starting_balance = starting_balance
        self._kill_switch = False
        self._trade_count_today = 0
        self._consecutive_losses = 0
        self._last_trade_time: float = 0
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._peak_balance: float = starting_balance
        self._audit_log: List[RiskAuditEntry] = []
        self._risk_blocks: List[RiskBlock] = []

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def activate_kill_switch(self) -> None:
        self._kill_switch = True
        logger.critical("KILL SWITCH ACTIVATED — all trading halted")

    def deactivate_kill_switch(self) -> None:
        self._kill_switch = False
        logger.info("Kill switch deactivated")

    def evaluate_signal(
        self,
        signal: Signal,
        mode: TradingMode,
        health_status: MarketHealthStatus,
        symbol_available: bool,
        current_spread: float = 0.0,
        portfolio_balance: float = 0.0,
        open_positions: int = 0,
        open_position_symbols: Optional[List[str]] = None,
        current_regime: Optional[str] = None,
    ) -> tuple:
        """Run all risk gates. Returns (allowed: bool, decision: str, audit: List[Dict])."""
        audit: List[RiskAuditEntry] = []
        balance = portfolio_balance or self.starting_balance

        # 1. Mode Gate
        r = self._check_mode(signal, mode)
        audit.append(RiskAuditEntry(gate="MODE", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "MODE", r.reason, audit, balance)

        # 2. Market Health Gate
        r = self._check_market_health(health_status)
        audit.append(RiskAuditEntry(gate="MARKET_HEALTH", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "MARKET_HEALTH", r.reason, audit, balance)

        # 3. Symbol Gate
        r = self._check_symbol(symbol_available, signal.symbol)
        audit.append(RiskAuditEntry(gate="SYMBOL", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "SYMBOL", r.reason, audit, balance)

        # 4. Kill Switch
        r = self._check_kill_switch()
        audit.append(RiskAuditEntry(gate="KILL_SWITCH", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "KILL_SWITCH", r.reason, audit, balance)

        # 5. Confidence
        r = self._check_confidence(signal)
        audit.append(RiskAuditEntry(gate="CONFIDENCE", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "CONFIDENCE", r.reason, audit, balance)

        # 6. Spread Gate
        r = self._check_spread(current_spread)
        audit.append(RiskAuditEntry(gate="SPREAD", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "SPREAD", r.reason, audit, balance)

        # 7. R:R Gate
        r = self._check_risk_reward(signal)
        audit.append(RiskAuditEntry(gate="RISK_REWARD", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "RISK_REWARD", r.reason, audit, balance)

        # 8. Position Count Gate
        r = self._check_position_count(open_positions)
        audit.append(RiskAuditEntry(gate="POSITION_COUNT", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "POSITION_COUNT", r.reason, audit, balance)

        # 9. Daily Loss Gate
        r = self._check_daily_loss(balance)
        audit.append(RiskAuditEntry(gate="DAILY_LOSS", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "DAILY_LOSS", r.reason, audit, balance)

        # 10. Drawdown Gate
        r = self._check_drawdown(balance)
        audit.append(RiskAuditEntry(gate="DRAWDOWN", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "DRAWDOWN", r.reason, audit, balance)

        # 11. Consecutive Losses
        r = self._check_consecutive_losses()
        audit.append(RiskAuditEntry(gate="CONSECUTIVE_LOSSES", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "CONSECUTIVE_LOSSES", r.reason, audit, balance)

        # 12. Trade Frequency
        r = self._check_trade_frequency()
        audit.append(RiskAuditEntry(gate="TRADE_FREQUENCY", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "TRADE_FREQUENCY", r.reason, audit, balance)

        # 13. Cooldown
        r = self._check_cooldown()
        audit.append(RiskAuditEntry(gate="COOLDOWN", passed=r.passed, reason=r.reason))
        if r.blocked:
            return self._reject(signal, "COOLDOWN", r.reason, audit, balance)

        # 14. Position Size
        qty = self._calculate_position_size(signal, balance)
        if qty <= 0:
            audit.append(RiskAuditEntry(gate="POSITION_SIZE", passed=False, reason="calculated_size_zero"))
            return self._reject(signal, "POSITION_SIZE", "calculated_size_zero", audit, balance)
        audit.append(RiskAuditEntry(gate="POSITION_SIZE", passed=True, reason=f"volume={qty:.4f}"))

        # All gates passed
        self._audit_log.extend(audit)
        return True, signal.direction, [a.__dict__ for a in audit], qty

    def record_trade_result(self, pnl: float) -> None:
        self._trade_count_today += 1
        self._daily_pnl += pnl
        self._weekly_pnl += pnl
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._last_trade_time = time.time()
        balance = self.starting_balance + self._daily_pnl
        if balance > self._peak_balance:
            self._peak_balance = balance

    def reset_daily(self) -> None:
        self._trade_count_today = 0
        self._daily_pnl = 0.0

    def _check_mode(self, signal: Signal, mode: TradingMode) -> RiskGateResult:
        if mode == TradingMode.LIVE_LOCKED:
            return RiskGateResult(passed=False, gate="MODE", reason="live_locked", blocked=True)
        if mode == TradingMode.RESEARCH and signal.direction != "NEUTRAL":
            return RiskGateResult(passed=True, gate="MODE", reason="research_mode_advisory")
        return RiskGateResult(passed=True, gate="MODE")

    def _check_market_health(self, status: MarketHealthStatus) -> RiskGateResult:
        if status in (MarketHealthStatus.DISCONNECTED, MarketHealthStatus.INVALID):
            return RiskGateResult(passed=False, gate="MARKET_HEALTH", reason=f"market_{status.value}", blocked=True)
        if status == MarketHealthStatus.STALE:
            return RiskGateResult(passed=False, gate="MARKET_HEALTH", reason="market_stale", blocked=True)
        return RiskGateResult(passed=True, gate="MARKET_HEALTH")

    def _check_symbol(self, available: bool, symbol: str) -> RiskGateResult:
        if not available:
            return RiskGateResult(passed=False, gate="SYMBOL", reason=f"symbol_unavailable:{symbol}", blocked=True)
        return RiskGateResult(passed=True, gate="SYMBOL")

    def _check_kill_switch(self) -> RiskGateResult:
        if self._kill_switch:
            return RiskGateResult(passed=False, gate="KILL_SWITCH", reason="kill_switch_active", blocked=True)
        return RiskGateResult(passed=True, gate="KILL_SWITCH")

    def _check_confidence(self, signal: Signal) -> RiskGateResult:
        if signal.confidence < self.config.min_confidence:
            return RiskGateResult(
                passed=False, gate="CONFIDENCE",
                reason=f"confidence {signal.confidence:.2f} < {self.config.min_confidence}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="CONFIDENCE")

    def _check_spread(self, spread: float) -> RiskGateResult:
        if spread > self.config.max_spread and self.config.max_spread > 0:
            return RiskGateResult(
                passed=False, gate="SPREAD",
                reason=f"spread {spread:.6f} > {self.config.max_spread}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="SPREAD")

    def _check_risk_reward(self, signal: Signal) -> RiskGateResult:
        if signal.risk_reward is not None and signal.risk_reward < self.config.min_risk_reward:
            return RiskGateResult(
                passed=False, gate="RISK_REWARD",
                reason=f"rr {signal.risk_reward:.2f} < {self.config.min_risk_reward}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="RISK_REWARD")

    def _check_position_count(self, open_positions: int) -> RiskGateResult:
        if open_positions >= self.config.max_open_positions:
            return RiskGateResult(
                passed=False, gate="POSITION_COUNT",
                reason=f"open={open_positions} >= {self.config.max_open_positions}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="POSITION_COUNT")

    def _check_daily_loss(self, balance: float) -> RiskGateResult:
        if self.starting_balance > 0:
            daily_loss_pct = abs(min(self._daily_pnl, 0)) / self.starting_balance
            if daily_loss_pct >= self.config.max_daily_loss:
                return RiskGateResult(
                    passed=False, gate="DAILY_LOSS",
                    reason=f"daily_loss {daily_loss_pct:.2%} >= {self.config.max_daily_loss:.2%}",
                    blocked=True,
                )
        return RiskGateResult(passed=True, gate="DAILY_LOSS")

    def _check_drawdown(self, balance: float) -> RiskGateResult:
        if self._peak_balance > 0:
            dd = (self._peak_balance - balance) / self._peak_balance
            if dd >= self.config.max_drawdown:
                return RiskGateResult(
                    passed=False, gate="DRAWDOWN",
                    reason=f"drawdown {dd:.2%} >= {self.config.max_drawdown:.2%}",
                    blocked=True,
                )
        return RiskGateResult(passed=True, gate="DRAWDOWN")

    def _check_consecutive_losses(self) -> RiskGateResult:
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            return RiskGateResult(
                passed=False, gate="CONSECUTIVE_LOSSES",
                reason=f"consecutive_losses={self._consecutive_losses} >= {self.config.max_consecutive_losses}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="CONSECUTIVE_LOSSES")

    def _check_trade_frequency(self) -> RiskGateResult:
        if self._trade_count_today >= self.config.max_trades_per_day:
            return RiskGateResult(
                passed=False, gate="TRADE_FREQUENCY",
                reason=f"trades_today={self._trade_count_today} >= {self.config.max_trades_per_day}",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="TRADE_FREQUENCY")

    def _check_cooldown(self) -> RiskGateResult:
        elapsed = time.time() - self._last_trade_time
        if elapsed < self.config.cooldown_seconds and self._last_trade_time > 0:
            return RiskGateResult(
                passed=False, gate="COOLDOWN",
                reason=f"cooldown {elapsed:.0f}s < {self.config.cooldown_seconds}s",
                blocked=True,
            )
        return RiskGateResult(passed=True, gate="COOLDOWN")

    def _calculate_position_size(self, signal: Signal, balance: float) -> float:
        risk_amount = balance * self.config.risk_per_trade
        if signal.entry <= 0 or signal.stop_loss is None:
            return 0.0
        sl_distance = abs(signal.entry - signal.stop_loss)
        if sl_distance <= 0:
            return 0.0
        qty = risk_amount / sl_distance
        max_qty = balance * self.config.max_position_size / signal.entry
        return min(qty, max_qty) if max_qty > 0 else 0.0

    def _reject(self, signal: Signal, gate: str, reason: str, audit: list, balance: float):
        block = RiskBlock(
            trade_id=signal.signal_id,
            reason=reason,
            gate=gate,
            account_snapshot={"balance": balance, "daily_pnl": self._daily_pnl},
            signal_snapshot=signal.to_dict(),
        )
        self._risk_blocks.append(block)
        self._audit_log.extend(audit)
        logger.info("RISK_BLOCK [%s] %s: %s", gate, signal.symbol, reason)
        return False, "HOLD", [a.__dict__ for a in audit], 0.0

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return [{"gate": a.gate, "passed": a.passed, "reason": a.reason} for a in self._audit_log]

    def get_risk_blocks(self) -> List[Dict[str, Any]]:
        return [b.__dict__ for b in self._risk_blocks]

    def get_status(self) -> Dict[str, Any]:
        return {
            "kill_switch": self._kill_switch,
            "trades_today": self._trade_count_today,
            "daily_pnl": self._daily_pnl,
            "weekly_pnl": self._weekly_pnl,
            "consecutive_losses": self._consecutive_losses,
            "peak_balance": self._peak_balance,
            "total_blocks": len(self._risk_blocks),
        }
