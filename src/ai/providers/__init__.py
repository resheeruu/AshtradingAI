"""AI provider registry — register and discover providers."""
from src.ai.providers.base import AIProvider
from src.ai.providers.openai_compatible import OpenAICompatibleProvider

__all__ = ["AIProvider", "OpenAICompatibleProvider"]
