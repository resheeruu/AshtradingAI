"""AI Participant configuration and management for tournaments."""
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.ai.base import TradingAI
from src.ai.test_strategy import TestStrategy
from src.ai.providers.base import AIProvider
from src.ai.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

# Provider-specific environment variable mappings
PROVIDER_CONFIGS = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
    },
    "openrouter": {
        "api_key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3-haiku",
    },
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-haiku-20240307",
    },
    "test": {
        "api_key_env": "",
        "model_env": "",
        "base_url": "",
        "default_model": "deterministic-rsi",
    },
}


@dataclass
class ParticipantConfig:
    """Configuration for a single tournament participant."""
    id: str
    provider: str  # e.g. "openai", "deepseek", "gemini", "test"
    model: str = ""
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    timeout: int = 30
    max_retries: int = 2

    def __post_init__(self):
        """Resolve provider-specific defaults from environment."""
        if self.provider in PROVIDER_CONFIGS:
            cfg = PROVIDER_CONFIGS[self.provider]
            if not self.api_key and cfg["api_key_env"]:
                self.api_key = os.getenv(cfg["api_key_env"], "")
            if not self.base_url:
                self.base_url = cfg["base_url"]
            if not self.model:
                self.model = cfg["default_model"]
        # Mark unavailable if provider needs key but has none
        if self.provider != "test" and not self.api_key:
            self.enabled = False
            logger.warning("Participant %s (%s) disabled: no API key configured", self.id, self.provider)

    @property
    def is_available(self) -> bool:
        return self.enabled and (self.provider == "test" or bool(self.api_key))

    def create_ai(self) -> Optional[TradingAI]:
        """Create a TradingAI instance for this participant."""
        if not self.is_available:
            return None

        if self.provider == "test":
            return TestStrategy(ai_id=self.id)

        provider = OpenAICompatibleProvider(
            provider_id=self.provider,
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

        try:
            from src.ai.provider_strategy import ProviderTradingAI
            return ProviderTradingAI(ai_id=self.id, provider=provider)
        except Exception as e:
            logger.error("Failed to create AI for participant %s: %s", self.id, e)
            return None


def load_participants_from_env() -> List[ParticipantConfig]:
    """Load participant list from AI_PARTICIPANTS env var.

    Format: AI_PARTICIPANTS=deepseek,gemini,openai,test
    Each entry maps to PROVIDER_CONFIGS for default settings.
    """
    raw = os.getenv("AI_PARTICIPANTS", "")
    if not raw.strip():
        # Fall back to single AI_PROVIDER config
        provider = os.getenv("AI_PROVIDER", "")
        if provider:
            return [ParticipantConfig(
                id=f"ai-{provider}",
                provider=provider,
                model=os.getenv("AI_MODEL", ""),
                api_key=os.getenv("AI_API_KEY", ""),
                base_url=os.getenv("AI_BASE_URL", ""),
            )]
        # Default: test strategy
        return [ParticipantConfig(id="test-strategy", provider="test")]

    participants = []
    for name in raw.split(","):
        name = name.strip()
        if not name:
            continue
        participants.append(ParticipantConfig(id=f"ai-{name}", provider=name))

    return participants


def load_participants_from_list(configs: List[Dict[str, Any]]) -> List[ParticipantConfig]:
    """Create participants from a list of config dicts.

    Each dict should have at minimum: {"id": "...", "provider": "..."}
    Optional: model, enabled, api_key, base_url, timeout, max_retries
    """
    participants = []
    for cfg in configs:
        participants.append(ParticipantConfig(**cfg))
    return participants
