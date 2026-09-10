"""News/event safety layer — optional, pluggable.

Blocks or reduces risk around high-impact events.
If no provider exists, reports NEWS DATA UNAVAILABLE.
Never fabricates news data.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timezone

from src.core.enums import RiskGate

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    event_type: str  # HIGH_IMPACT_EVENT, MEDIUM_IMPACT_EVENT, LOW_IMPACT_EVENT, UNKNOWN
    title: str
    currency: str = ""
    timestamp: str = ""
    impact_level: int = 0  # 0=none, 1=low, 2=medium, 3=high
    description: str = ""


class NewsSafetyLayer:
    """Optional news event filtering. Pluggable provider interface."""

    def __init__(self):
        self._provider = None
        self._enabled = False
        self._last_events: List[NewsEvent] = []

    def set_provider(self, provider) -> None:
        self._provider = provider
        self._enabled = True
        logger.info("News provider enabled: %s", type(provider).__name__)

    @property
    def available(self) -> bool:
        return self._enabled and self._provider is not None

    def get_status(self) -> Dict[str, str]:
        if not self.available:
            return {"status": "NEWS_DATA_UNAVAILABLE", "provider": "none"}
        return {"status": "AVAILABLE", "provider": type(self._provider).__name__}

    def check_symbol_safe(self, symbol: str) -> tuple:
        """Check if it's safe to trade a symbol. Returns (safe: bool, reason: str)."""
        if not self.available:
            return True, "no_news_filtering"

        if self._provider is None:
            return True, "no_provider"

        try:
            events = self._provider.get_upcoming_events(symbol=symbol, hours_ahead=4)
            self._last_events = events
            high_impact = [e for e in events if e.impact_level >= 3]
            medium_impact = [e for e in events if e.impact_level == 2]

            if high_impact:
                return False, f"high_impact_event_within_4h:{high_impact[0].title}"
            if medium_impact:
                return True, f"medium_impact_event:{medium_impact[0].title}"

            return True, "no_nearby_events"
        except Exception as e:
            logger.warning("News check failed: %s", e)
            return True, "news_check_failed"

    def get_recommendation(self, symbol: str) -> Dict:
        safe, reason = self.check_symbol_safe(symbol)
        return {
            "symbol": symbol,
            "safe_to_trade": safe,
            "reason": reason,
            "upcoming_events": [
                {"type": e.event_type, "title": e.title, "impact": e.impact_level}
                for e in self._last_events[:5]
            ],
            "available": self.available,
        }
