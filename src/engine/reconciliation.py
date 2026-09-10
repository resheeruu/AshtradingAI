"""Reconciliation engine — compares internal state vs broker state.

Detects discrepancies and creates audit warnings. Never silently overwrites.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationWarning:
    warning_type: str
    symbol: str
    internal_value: Any
    broker_value: Any
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.warning_type,
            "symbol": self.symbol,
            "internal": str(self.internal_value),
            "broker": str(self.broker_value),
            "description": self.description,
            "timestamp": self.timestamp,
        }


class ReconciliationEngine:
    """Compares internal portfolio state with broker-reported state."""

    def __init__(self):
        self._warnings: List[ReconciliationWarning] = []
        self._last_reconciliation: Optional[str] = None
        self._reconciliation_count = 0

    @property
    def last_reconciliation(self) -> Optional[str]:
        return self._last_reconciliation

    @property
    def warning_count(self) -> int:
        return len(self._warnings)

    def reconcile(
        self,
        internal_positions: Dict[str, Dict[str, Any]],
        broker_positions: Dict[str, Dict[str, Any]],
        tolerance: float = 0.001,
    ) -> List[ReconciliationWarning]:
        """Compare internal vs broker positions. Returns warnings for discrepancies."""
        new_warnings = []
        self._last_reconciliation = datetime.now(timezone.utc).isoformat()
        self._reconciliation_count += 1

        all_symbols = set(list(internal_positions.keys()) + list(broker_positions.keys()))

        for symbol in all_symbols:
            internal = internal_positions.get(symbol)
            broker = broker_positions.get(symbol)

            if internal is None and broker is not None:
                w = ReconciliationWarning(
                    warning_type="UNEXPECTED_POSITION",
                    symbol=symbol,
                    internal_value=None,
                    broker_value=broker,
                    description=f"Broker has position in {symbol} not tracked internally",
                )
                new_warnings.append(w)
                logger.warning("RECONCILIATION_WARNING: unexpected position %s", symbol)

            elif internal is not None and broker is None:
                w = ReconciliationWarning(
                    warning_type="MISSING_POSITION",
                    symbol=symbol,
                    internal_value=internal,
                    broker_value=None,
                    description=f"Internal position in {symbol} not found at broker",
                )
                new_warnings.append(w)
                logger.warning("RECONCILIATION_WARNING: missing position %s", symbol)

            elif internal is not None and broker is not None:
                int_qty = internal.get("quantity", 0)
                brk_qty = broker.get("quantity", 0)
                if abs(int_qty - brk_qty) > tolerance:
                    w = ReconciliationWarning(
                        warning_type="QUANTITY_MISMATCH",
                        symbol=symbol,
                        internal_value=int_qty,
                        broker_value=brk_qty,
                        description=f"Quantity mismatch {symbol}: internal={int_qty}, broker={brk_qty}",
                    )
                    new_warnings.append(w)
                    logger.warning("RECONCILIATION_WARNING: qty mismatch %s", symbol)

                int_sl = internal.get("stop_loss")
                brk_sl = broker.get("stop_loss")
                if int_sl is not None and brk_sl is not None:
                    if abs(float(int_sl) - float(brk_sl)) > tolerance * float(int_sl):
                        w = ReconciliationWarning(
                            warning_type="SL_MISMATCH",
                            symbol=symbol,
                            internal_value=int_sl,
                            broker_value=brk_sl,
                            description=f"SL mismatch {symbol}: internal={int_sl}, broker={brk_sl}",
                        )
                        new_warnings.append(w)

                int_tp = internal.get("take_profit")
                brk_tp = broker.get("take_profit")
                if int_tp is not None and brk_tp is not None:
                    if abs(float(int_tp) - float(brk_tp)) > tolerance * float(int_tp):
                        w = ReconciliationWarning(
                            warning_type="TP_MISMATCH",
                            symbol=symbol,
                            internal_value=int_tp,
                            broker_value=brk_tp,
                            description=f"TP mismatch {symbol}: internal={int_tp}, broker={brk_tp}",
                        )
                        new_warnings.append(w)

        self._warnings.extend(new_warnings)
        if new_warnings:
            logger.warning("Reconciliation found %d warnings", len(new_warnings))
        else:
            logger.info("Reconciliation clean — no discrepancies")
        return new_warnings

    def get_warnings(self) -> List[Dict[str, Any]]:
        return [w.to_dict() for w in self._warnings]

    def get_status(self) -> Dict[str, Any]:
        return {
            "last_reconciliation": self._last_reconciliation,
            "total_reconciliations": self._reconciliation_count,
            "total_warnings": len(self._warnings),
            "recent_warnings": [w.to_dict() for w in self._warnings[-10:]],
        }
