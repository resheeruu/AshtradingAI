"""Provider failover — AI providers must not crash trading.

Implements primary → secondary → fallback → unavailable cascade.
If all providers fail: AI_UNAVAILABLE → NO NEW TRADES.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.enums import AIProviderStatus

logger = logging.getLogger(__name__)


@dataclass
class ProviderEntry:
    name: str
    status: AIProviderStatus = AIProviderStatus.PRIMARY
    provider: Any = None
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    cooldown_until: float = 0.0
    total_failures: int = 0
    total_successes: int = 0


class ProviderFailover:
    """Manages AI provider failover with safety-first defaults."""

    def __init__(self, max_failures: int = 3, cooldown_seconds: float = 60.0):
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self._providers: List[ProviderEntry] = []
        self._all_failed = False

    def register(self, name: str, provider: Any, status: AIProviderStatus = AIProviderStatus.PRIMARY) -> None:
        self._providers.append(ProviderEntry(name=name, provider=provider, status=status))
        logger.info("Provider registered: %s (%s)", name, status.value)

    @property
    def all_failed(self) -> bool:
        return self._all_failed

    def get_active_provider(self) -> Optional[Any]:
        """Get the first available provider. Returns None if all failed."""
        now = time.time()
        for entry in self._providers:
            if entry.status == AIProviderStatus.UNAVAILABLE:
                continue
            if now < entry.cooldown_until:
                continue
            if entry.provider is not None:
                return entry.provider

        self._all_failed = True
        logger.critical("ALL AI PROVIDERS FAILED — NO NEW TRADES")
        return None

    def record_success(self, name: str) -> None:
        for entry in self._providers:
            if entry.name == name:
                entry.consecutive_failures = 0
                entry.total_successes += 1
                if entry.status == AIProviderStatus.UNAVAILABLE:
                    entry.status = AIProviderStatus.PRIMARY
                    logger.info("Provider %s recovered", name)
                break
        self._all_failed = False

    def record_failure(self, name: str, error: str = "") -> None:
        now = time.time()
        for entry in self._providers:
            if entry.name == name:
                entry.consecutive_failures += 1
                entry.total_failures += 1
                entry.last_failure_time = now

                if entry.consecutive_failures >= self.max_failures:
                    entry.status = AIProviderStatus.UNAVAILABLE
                    entry.cooldown_until = now + self.cooldown_seconds
                    logger.warning("Provider %s set to UNAVAILABLE (cooldown %ds): %s",
                                   name, self.cooldown_seconds, error)
                break

        if all(p.status == AIProviderStatus.UNAVAILABLE for p in self._providers):
            self._all_failed = True
            logger.critical("ALL AI PROVIDERS FAILED — BLOCKING NEW TRADES")

    def get_status(self) -> Dict[str, Any]:
        return {
            "all_failed": self._all_failed,
            "providers": [
                {
                    "name": p.name,
                    "status": p.status.value,
                    "consecutive_failures": p.consecutive_failures,
                    "total_failures": p.total_failures,
                    "total_successes": p.total_successes,
                }
                for p in self._providers
            ],
        }
