"""Centralized engine watchdog — monitors health of all subsystems."""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.core.enums import WatchdogStatus

logger = logging.getLogger(__name__)


@dataclass
class SubsystemHealth:
    name: str
    status: WatchdogStatus = WatchdogStatus.HEALTHY
    last_heartbeat: float = 0.0
    error_message: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


class EngineWatchdog:
    """Monitors all subsystems and triggers protective actions on failure."""

    def __init__(self, heartbeat_timeout: int = 300):
        self.heartbeat_timeout = heartbeat_timeout
        self._subsystems: Dict[str, SubsystemHealth] = {}
        self._overall = WatchdogStatus.HEALTHY
        self._trade_blocked = False

    def register(self, name: str) -> None:
        self._subsystems[name] = SubsystemHealth(name=name, last_heartbeat=time.time())

    def heartbeat(self, name: str, metadata: Optional[Dict[str, str]] = None) -> None:
        sub = self._subsystems.get(name)
        if sub:
            sub.last_heartbeat = time.time()
            sub.status = WatchdogStatus.HEALTHY
            sub.error_message = ""
            if metadata:
                sub.metadata = metadata
        self._recalculate()

    def record_error(self, name: str, error: str) -> None:
        sub = self._subsystems.get(name)
        if sub:
            sub.status = WatchdogStatus.FAILED
            sub.error_message = error
        self._recalculate()

    def record_degraded(self, name: str, reason: str) -> None:
        sub = self._subsystems.get(name)
        if sub:
            sub.status = WatchdogStatus.DEGRADED
            sub.error_message = reason
        self._recalculate()

    def check_timeouts(self) -> None:
        now = time.time()
        for sub in self._subsystems.values():
            if sub.status == WatchdogStatus.HEALTHY:
                elapsed = now - sub.last_heartbeat
                if elapsed > self.heartbeat_timeout:
                    sub.status = WatchdogStatus.FAILED
                    sub.error_message = f"heartbeat timeout ({elapsed:.0f}s)"
                    logger.warning("WATCHDOG: %s heartbeat timeout", sub.name)
        self._recalculate()

    def _recalculate(self) -> None:
        statuses = [s.status for s in self._subsystems.values()]
        if any(s == WatchdogStatus.FAILED for s in statuses):
            self._overall = WatchdogStatus.FAILED
            self._trade_blocked = True
        elif any(s == WatchdogStatus.BLOCKED for s in statuses):
            self._overall = WatchdogStatus.BLOCKED
            self._trade_blocked = True
        elif any(s == WatchdogStatus.DEGRADED for s in statuses):
            self._overall = WatchdogStatus.DEGRADED
        else:
            self._overall = WatchdogStatus.HEALTHY
            self._trade_blocked = False

    @property
    def overall(self) -> WatchdogStatus:
        return self._overall

    @property
    def trades_blocked(self) -> bool:
        return self._trade_blocked

    def get_status(self) -> Dict[str, any]:
        return {
            "overall": self._overall.value,
            "trades_blocked": self._trade_blocked,
            "subsystems": {
                name: {"status": sub.status.value, "error": sub.error_message}
                for name, sub in self._subsystems.items()
            },
        }
