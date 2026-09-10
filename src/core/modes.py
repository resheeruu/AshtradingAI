"""Centralized trading mode manager.

Single source of truth for execution policy. Modes control what is allowed.
No scattered mode checks throughout the code.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.core.enums import TradingMode

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPolicy:
    """What is allowed in each mode."""
    allows_signal_generation: bool = False
    allows_ai_decisions: bool = False
    allows_paper_execution: bool = False
    allows_mt5_execution: bool = False
    allows_backtesting: bool = False
    uses_live_data: bool = False
    uses_historical_data: bool = False
    records_trades: bool = False
    requires_reconciliation: bool = False


MODE_POLICIES = {
    TradingMode.RESEARCH: ExecutionPolicy(
        allows_signal_generation=True,
        allows_ai_decisions=True,
        allows_paper_execution=False,
        allows_mt5_execution=False,
        allows_backtesting=False,
        uses_live_data=False,
        uses_historical_data=True,
        records_trades=False,
    ),
    TradingMode.BACKTEST: ExecutionPolicy(
        allows_signal_generation=True,
        allows_ai_decisions=True,
        allows_paper_execution=True,
        allows_mt5_execution=False,
        allows_backtesting=True,
        uses_live_data=False,
        uses_historical_data=True,
        records_trades=True,
    ),
    TradingMode.PAPER: ExecutionPolicy(
        allows_signal_generation=True,
        allows_ai_decisions=True,
        allows_paper_execution=True,
        allows_mt5_execution=False,
        allows_backtesting=False,
        uses_live_data=False,
        uses_historical_data=True,
        records_trades=True,
    ),
    TradingMode.PAPER_LIVE: ExecutionPolicy(
        allows_signal_generation=True,
        allows_ai_decisions=True,
        allows_paper_execution=True,
        allows_mt5_execution=False,
        allows_backtesting=False,
        uses_live_data=True,
        uses_historical_data=False,
        records_trades=True,
    ),
    TradingMode.MT5_DEMO: ExecutionPolicy(
        allows_signal_generation=True,
        allows_ai_decisions=True,
        allows_paper_execution=False,
        allows_mt5_execution=True,
        allows_backtesting=False,
        uses_live_data=True,
        uses_historical_data=False,
        records_trades=True,
        requires_reconciliation=True,
    ),
    TradingMode.LIVE_LOCKED: ExecutionPolicy(
        allows_signal_generation=False,
        allows_ai_decisions=False,
        allows_paper_execution=False,
        allows_mt5_execution=False,
        allows_backtesting=False,
        uses_live_data=False,
        uses_historical_data=False,
        records_trades=False,
    ),
}


class ModeManager:
    """Centralized mode gate. Single authority for execution policy."""

    def __init__(self, mode: TradingMode = TradingMode.PAPER):
        self._mode = mode
        self._policy = MODE_POLICIES[mode]
        logger.info("ModeManager initialized: %s", mode.value)

    @property
    def mode(self) -> TradingMode:
        return self._mode

    @property
    def policy(self) -> ExecutionPolicy:
        return self._policy

    def set_mode(self, mode: TradingMode) -> None:
        if mode == TradingMode.LIVE_LOCKED:
            logger.warning("LIVE_LOCKED mode is permanently disabled")
            return
        self._mode = mode
        self._policy = MODE_POLICIES[mode]
        logger.info("Mode changed to: %s", mode.value)

    def check(self, capability: str) -> bool:
        """Check if the current mode allows a specific capability."""
        return getattr(self._policy, capability, False)

    def block_if_unauthorized(self, operation: str) -> Optional[str]:
        """Return error message if operation is not allowed, else None."""
        cap = f"allows_{operation}" if not operation.startswith("uses_") else operation
        if not self.check(cap):
            return f"Mode {self._mode.value} does not allow {operation}"
        return None
