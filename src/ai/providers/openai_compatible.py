"""OpenAI-compatible AI provider — works with OpenAI, DeepSeek, Groq, OpenRouter, etc."""
import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional
import requests

from src.ai.providers.base import AIProvider

logger = logging.getLogger(__name__)

# Default OpenAI base URL
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Trading-specific system prompt
DEFAULT_SYSTEM_PROMPT = """You are a trading AI. Respond ONLY with a JSON object containing:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation",
  "suggested_position_size": 0.0 to 1.0 (fraction of portfolio),
  "stop_loss": price level as float (or null),
  "take_profit": price level as float (or null)
}

Rules:
- decision must be exactly BUY, SELL, or HOLD
- confidence must be between 0.0 and 1.0
- suggested_position_size must be between 0.0 and 0.25
- Always respond with valid JSON only, no markdown"""


class OpenAICompatibleProvider(AIProvider):
    """Generic OpenAI-compatible provider for chat completions with resilience support."""

    def __init__(
        self,
        provider_id: str = "openai-compatible",
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        timeout: int = 30,
        max_retries: int = 2,
        health_manager: Optional[Any] = None,
    ):
        super().__init__(provider_id=provider_id, api_key=api_key, model=model)
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.health_manager = health_manager
        self._session = requests.Session()
        if self.api_key:
            self._session.headers["Authorization"] = f"Bearer {self.api_key}"
        self._session.headers["Content-Type"] = "application/json"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _estimate_tokens(self, prompt: str, system_prompt: str = "") -> int:
        text = prompt + (system_prompt or DEFAULT_SYSTEM_PROMPT)
        return max(1, len(text) // 4)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        """Send a chat completion request to the OpenAI-compatible API with resilience."""
        if not self.is_configured():
            return {"response": "", "success": False, "error": "provider_not_configured"}

        if self.health_manager is not None:
            estimated_tokens = self._estimate_tokens(prompt, system_prompt)
            ok, reason = self.health_manager.can_make_request(self.provider_id, self.model, estimated_tokens)
            if not ok:
                return {"response": "", "success": False, "error": f"unavailable: {reason}"}

        messages = []
        sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 500,
        }

        url = f"{self.base_url}/chat/completions"
        last_err = ""

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 * (attempt + 1)))
                    logger.warning("Rate limited on %s, waiting %ds", self.provider_id, retry_after)
                    if self.health_manager is not None:
                        from src.ai.health import ClassifiedError
                        error = ClassifiedError.classify(
                            status_code=429,
                            message=f"Rate limited. Retry-After: {retry_after}",
                        )
                        self.health_manager.record_failure(self.provider_id, self.model, error)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()

                choices = data.get("choices", [])
                if not choices:
                    if self.health_manager is not None:
                        self.health_manager.record_success(self.provider_id, self.model, 0)
                    return {"response": "", "success": False, "error": "no_choices_in_response"}

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    if self.health_manager is not None:
                        self.health_manager.record_success(self.provider_id, self.model, 0)
                    return {"response": "", "success": False, "error": "empty_response"}

                tokens_used = data.get("usage", {}).get("total_tokens", 0)
                if self.health_manager is not None:
                    self.health_manager.record_success(self.provider_id, self.model, tokens_used)

                return {"response": content, "success": True, "error": ""}

            except requests.exceptions.Timeout:
                last_err = "timeout"
                logger.warning("Timeout on %s (attempt %d)", self.provider_id, attempt + 1)
                if self.health_manager is not None:
                    from src.ai.health import ClassifiedError
                    error = ClassifiedError.classify(timeout=True)
                    self.health_manager.record_failure(self.provider_id, self.model, error)
            except requests.exceptions.ConnectionError as e:
                last_err = f"connection_error"
                logger.warning("Connection error on %s: %s", self.provider_id, e)
                if self.health_manager is not None:
                    from src.ai.health import ClassifiedError
                    error = ClassifiedError.classify(message=str(e))
                    self.health_manager.record_failure(self.provider_id, self.model, error)
            except requests.exceptions.HTTPError as e:
                status = getattr(e.response, "status_code", 0) if e.response is not None else 0
                last_err = f"http_{status}"
                if self.health_manager is not None:
                    from src.ai.health import ClassifiedError
                    error = ClassifiedError.classify(status_code=status, message=str(e))
                    self.health_manager.record_failure(self.provider_id, self.model, error)
                if status >= 500:
                    logger.warning("Server error %d on %s", status, self.provider_id)
                else:
                    return {"response": "", "success": False, "error": f"http_{status}"}
            except Exception as e:
                last_err = str(e)
                logger.error("Unexpected error on %s: %s", self.provider_id, e)
                return {"response": "", "success": False, "error": last_err}

            if attempt < self.max_retries:
                time.sleep(1.0 * (2 ** attempt))

        return {"response": "", "success": False, "error": f"retries_exhausted: {last_err}"}

    def close(self) -> None:
        self._session.close()


def parse_ai_response(raw_text: str) -> Dict[str, Any]:
    """Parse a raw AI text response into a structured trading decision dict.

    Handles markdown code blocks, extra text around JSON, etc.
    Returns normalized dict with standard keys.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try to find JSON in the text
    # Look for first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return _fallback_decision(raw_text)

    json_str = text[start:end + 1]
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return _fallback_decision(raw_text)

    if not isinstance(parsed, dict):
        return _fallback_decision(raw_text)

    return _normalize_decision(parsed)


def _normalize_decision(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a parsed JSON decision into standard format."""
    decision = str(raw.get("decision", "HOLD")).upper()
    if decision not in ("BUY", "SELL", "HOLD"):
        decision = "HOLD"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    position_size = raw.get("suggested_position_size")
    if position_size is not None:
        try:
            position_size = float(position_size)
            position_size = max(0.0, min(0.25, position_size))
        except (TypeError, ValueError):
            position_size = None

    stop_loss = raw.get("stop_loss")
    if stop_loss is not None:
        try:
            stop_loss = float(stop_loss)
        except (TypeError, ValueError):
            stop_loss = None

    take_profit = raw.get("take_profit")
    if take_profit is not None:
        try:
            take_profit = float(take_profit)
        except (TypeError, ValueError):
            take_profit = None

    return {
        "decision": decision,
        "confidence": confidence,
        "reason": str(raw.get("reason", "")),
        "suggested_position_size": position_size,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }


def _fallback_decision(raw_text: str) -> Dict[str, Any]:
    """Produce a safe HOLD decision when parsing fails completely."""
    logger.warning("Failed to parse AI response, defaulting to HOLD")
    return {
        "decision": "HOLD",
        "confidence": 0.0,
        "reason": f"parse_error: could not extract JSON from response",
        "suggested_position_size": None,
        "stop_loss": None,
        "take_profit": None,
    }
