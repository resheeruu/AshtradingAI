"""TradingAI implementation backed by an OpenAI-compatible API provider."""
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional

from src.ai.base import TradingAI, MarketContext
from src.ai.providers.openai_compatible import OpenAICompatibleProvider, parse_ai_response

logger = logging.getLogger(__name__)


class ProviderTradingAI(TradingAI):
    """TradingAI that delegates decisions to an OpenAI-compatible provider with fallback support."""

    def __init__(
        self,
        ai_id: str,
        provider: OpenAICompatibleProvider,
        fallback_providers: Optional[List[OpenAICompatibleProvider]] = None,
        health_manager: Optional[Any] = None,
        enable_cache: bool = True,
    ):
        super().__init__(ai_id=ai_id, model=provider.model or "unknown")
        self.provider = provider
        self.fallback_providers = fallback_providers or []
        self.health_manager = health_manager
        self.enable_cache = enable_cache

    def _make_cache_key(self, context: MarketContext) -> str:
        prompt = self._build_prompt(context)
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _try_provider(self, provider: OpenAICompatibleProvider, prompt: str) -> Dict[str, Any]:
        return provider.generate(prompt)

    def decide(self, context: MarketContext) -> Dict[str, Any]:
        """Build a prompt from market context and query the provider with fallback."""
        prompt = self._build_prompt(context)

        if self.enable_cache and self.health_manager is not None:
            cache_key = self._make_cache_key(context)
            cached = self.health_manager.check_cache(
                self.provider.provider_id, self.provider.model,
                context.symbol, context.timeframe, context.timestamp, cache_key,
            )
            if cached is not None:
                return cached

        result = self._try_provider(self.provider, prompt)

        providers_to_try = [self.provider] + self.fallback_providers
        for provider in providers_to_try:
            result = self._try_provider(provider, prompt)
            if result.get("success"):
                break

        if not result.get("success"):
            logger.warning("[%s] All providers failed, defaulting to HOLD: %s", self.ai_id, result.get("error"))
            decision = {"decision": "HOLD", "confidence": 0.0, "reason": f"provider_error: {result.get('error')}"}
            if self.enable_cache and self.health_manager is not None:
                cache_key = self._make_cache_key(context)
                self.health_manager.store_cache(
                    provider.provider_id, provider.model,
                    context.symbol, context.timeframe, context.timestamp, cache_key, decision,
                )
            return decision

        raw_text = result.get("response", "")
        parsed = parse_ai_response(raw_text)

        validated = self.validate_decision(parsed)
        decision = {
            "decision": validated.decision,
            "confidence": validated.confidence,
            "reason": validated.reason,
            "suggested_position_size": validated.suggested_position_size,
            "stop_loss": validated.stop_loss,
            "take_profit": validated.take_profit,
        }

        if self.enable_cache and self.health_manager is not None:
            cache_key = self._make_cache_key(context)
            self.health_manager.store_cache(
                provider.provider_id, provider.model,
                context.symbol, context.timeframe, context.timestamp, cache_key, decision,
            )

        return decision

    def _build_prompt(self, context: MarketContext) -> str:
        """Build a structured prompt for the AI provider."""
        recent_candles = context.candles[-20:] if len(context.candles) > 20 else context.candles
        candle_summary = json.dumps(recent_candles, indent=1) if recent_candles else "no candle data"

        indicators_str = json.dumps(context.indicators, indent=1) if context.indicators else "no indicators"

        positions_str = ", ".join(context.open_positions) if context.open_positions else "none"

        return f"""Market Analysis Request:

Symbol: {context.symbol}
Timeframe: {context.timeframe}
Current Price: {context.current_price}
Portfolio Balance: ${context.portfolio_balance:.2f}
Open Positions: {positions_str}
Timestamp: {context.timestamp}

Recent Candles (last {len(recent_candles)}):
{candle_summary}

Technical Indicators:
{indicators_str}

Provide your trading decision as JSON:
{{"decision": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "reason": "...", "suggested_position_size": 0.0-0.25, "stop_loss": price, "take_profit": price}}"""
