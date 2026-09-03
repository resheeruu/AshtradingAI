"""Abstract base for AI providers — independent of specific API implementations."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class AIProvider(ABC):
    """Base class for all AI providers."""

    def __init__(self, provider_id: str, api_key: str = "", model: str = ""):
        self.provider_id = provider_id
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """Send prompt to the AI and return the raw response.

        Returns dict with at minimum:
          - "response": str (the raw text response)
          - "success": bool
          - "error": str (empty on success)
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this provider has valid credentials configured."""
        ...

    def close(self) -> None:
        """Clean up resources. Override if needed."""
        pass
