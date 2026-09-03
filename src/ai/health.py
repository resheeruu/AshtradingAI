"""Provider Health Manager - tracks provider state, handles errors, backoff, cooldowns, quotas, and failover.

State Machine:
    ONLINE ──> COOLDOWN ──> ONLINE (after cooldown, transient errors)
    ONLINE ──> QUOTA_EXHAUSTED ──> ONLINE (after daily reset or manual override)
    ONLINE ──> AUTH_FAILED (requires config change, no auto-recovery)
    ONLINE ──> MODEL_UNAVAILABLE (requires config change, no auto-recovery)
    ONLINE ──> DISABLED (admin override)

Backoff: Exponential with jitter for transient errors (429, 5xx, timeout).
Cooldown: Configurable per-provider cooldown period after consecutive failures.
Quota: Track daily token usage per provider/model, enforce global and per-provider limits.
Cache: LRU in-memory cache for AI responses to avoid redundant API calls.

Failover: Configurable fallback chain; disabled by default in tournament mode for fairness.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider States
# ---------------------------------------------------------------------------

class ProviderState(str, Enum):
    ONLINE = "ONLINE"
    COOLDOWN = "COOLDOWN"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------

class ErrorKind(str, Enum):
    RATE_LIMIT = "RATE_LIMIT"           # 429
    TPM_RATE_LIMIT = "TPM_RATE_LIMIT"   # 429 with token limit
    DAILY_QUOTA = "DAILY_QUOTA"         # 429 daily limit
    AUTH_ERROR = "AUTH_ERROR"           # 401
    FORBIDDEN = "FORBIDDEN"             # 403
    NOT_FOUND = "NOT_FOUND"            # 404
    SERVER_ERROR = "SERVER_ERROR"       # 5xx
    TIMEOUT = "TIMEOUT"                 # request timeout
    MALFORMED = "MALFORMED"            # unparseable response
    UNKNOWN = "UNKNOWN"


@dataclass
class ClassifiedError:
    kind: ErrorKind
    status_code: Optional[int] = None
    is_transient: bool = False
    message: str = ""
    retry_after: Optional[float] = None  # seconds, from Retry-After header

    @staticmethod
    def classify(status_code: Optional[int] = None, message: str = "", timeout: bool = False) -> "ClassifiedError":
        if timeout:
            return ClassifiedError(kind=ErrorKind.TIMEOUT, is_transient=True, message="Request timed out")
        if status_code == 429:
            kind = ErrorKind.RATE_LIMIT
            lower_msg = message.lower()
            if "token" in lower_msg or "tpm" in lower_msg:
                kind = ErrorKind.TPM_RATE_LIMIT
            elif "daily" in lower_msg:
                kind = ErrorKind.DAILY_QUOTA
            retry_after = _parse_retry_after(message)
            return ClassifiedError(kind=kind, status_code=429, is_transient=True, message=message, retry_after=retry_after)
        if status_code == 401:
            return ClassifiedError(kind=ErrorKind.AUTH_ERROR, status_code=401, is_transient=False, message=message)
        if status_code == 403:
            return ClassifiedError(kind=ErrorKind.FORBIDDEN, status_code=403, is_transient=False, message=message)
        if status_code == 404:
            return ClassifiedError(kind=ErrorKind.NOT_FOUND, status_code=404, is_transient=False, message=message)
        if status_code is not None and status_code >= 500:
            return ClassifiedError(kind=ErrorKind.SERVER_ERROR, status_code=status_code, is_transient=True, message=message)
        return ClassifiedError(kind=ErrorKind.UNKNOWN, status_code=status_code, is_transient=True, message=message)


def _parse_retry_after(message: str) -> Optional[float]:
    try:
        lower = message.lower()
        for token in lower.split():
            if token.isdigit():
                return float(token)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Backoff Calculator
# ---------------------------------------------------------------------------

class BackoffCalculator:
    """Exponential backoff with jitter."""

    def __init__(self, base_delay: float = 1.0, max_delay: float = 300.0, multiplier: float = 2.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def delay(self, attempt: int) -> float:
        import random
        delay = min(self.base_delay * (self.multiplier ** attempt), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay


# ---------------------------------------------------------------------------
# Cooldown Manager
# ---------------------------------------------------------------------------

@dataclass
class CooldownInfo:
    provider: str
    model: str
    state: ProviderState = ProviderState.ONLINE
    failure_count: int = 0
    last_failure_time: float = 0.0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_error_kind: Optional[ErrorKind] = None
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_success_time: float = 0.0


class CooldownManager:
    """Manages per-provider-model cooldown state."""

    def __init__(self, cooldown_seconds: float = 60.0, max_failures_before_cooldown: int = 3, max_cooldown_seconds: float = 3600.0):
        self.cooldown_seconds = cooldown_seconds
        self.max_failures_before_cooldown = max_failures_before_cooldown
        self.max_cooldown_seconds = max_cooldown_seconds
        self._states: dict[str, CooldownInfo] = {}

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}|{model}"

    def get_state(self, provider: str, model: str) -> CooldownInfo:
        key = self._key(provider, model)
        if key not in self._states:
            self._states[key] = CooldownInfo(provider=provider, model=model)
        return self._states[key]

    def record_success(self, provider: str, model: str) -> CooldownInfo:
        info = self.get_state(provider, model)
        info.total_successes += 1
        info.last_success_time = time.time()
        if info.state == ProviderState.COOLDOWN:
            info.state = ProviderState.ONLINE
            info.consecutive_failures = 0
            info.cooldown_until = 0.0
            logger.info("Provider %s/%s recovered from COOLDOWN", provider, model)
        elif info.state == ProviderState.ONLINE:
            info.consecutive_failures = 0
        return info

    def record_failure(self, provider: str, model: str, error: ClassifiedError) -> CooldownInfo:
        info = self.get_state(provider, model)
        info.total_failures += 1
        info.consecutive_failures += 1
        info.last_failure_time = time.time()
        info.last_error = error.message
        info.last_error_kind = error.kind

        if error.kind == ErrorKind.AUTH_ERROR:
            info.state = ProviderState.AUTH_FAILED
            logger.warning("Provider %s/%s marked AUTH_FAILED (no auto-recovery)", provider, model)
        elif error.kind == ErrorKind.NOT_FOUND:
            info.state = ProviderState.MODEL_UNAVAILABLE
            logger.warning("Provider %s/%s marked MODEL_UNAVAILABLE (no auto-recovery)", provider, model)
        elif error.kind == ErrorKind.DAILY_QUOTA:
            info.state = ProviderState.QUOTA_EXHAUSTED
            logger.warning("Provider %s/%s marked QUOTA_EXHAUSTED", provider, model)
        elif error.is_transient and info.consecutive_failures >= self.max_failures_before_cooldown:
            backoff = BackoffCalculator(
                base_delay=self.cooldown_seconds,
                max_delay=self.max_cooldown_seconds,
            )
            delay = backoff.delay(min(info.consecutive_failures - self.max_failures_before_cooldown, 10))
            info.state = ProviderState.COOLDOWN
            info.cooldown_until = time.time() + delay
            logger.warning("Provider %s/%s entering COOLDOWN for %.1fs (consecutive failures: %d)",
                           provider, model, delay, info.consecutive_failures)

        return info

    def is_available(self, provider: str, model: str) -> bool:
        info = self.get_state(provider, model)
        if info.state == ProviderState.ONLINE:
            return True
        if info.state == ProviderState.COOLDOWN and time.time() >= info.cooldown_until:
            info.state = ProviderState.ONLINE
            info.consecutive_failures = 0
            info.cooldown_until = 0.0
            logger.info("Provider %s/%s cooldown expired, transitioning to ONLINE", provider, model)
            return True
        return False

    def get_all_states(self) -> dict[str, CooldownInfo]:
        return dict(self._states)

    def set_state(self, provider: str, model: str, state: ProviderState) -> CooldownInfo:
        info = self.get_state(provider, model)
        old_state = info.state
        info.state = state
        if state == ProviderState.ONLINE:
            info.consecutive_failures = 0
            info.cooldown_until = 0.0
        logger.info("Provider %s/%s state manually changed: %s -> %s", provider, model, old_state, state)
        return info

    def force_online(self, provider: str, model: str) -> CooldownInfo:
        return self.set_state(provider, model, ProviderState.ONLINE)


# ---------------------------------------------------------------------------
# Quota Manager
# ---------------------------------------------------------------------------

@dataclass
class ModelQuota:
    daily_token_limit: int = 0  # 0 = unlimited
    tokens_used_today: int = 0
    last_reset_date: str = ""  # YYYY-MM-DD
    requests_today: int = 0
    daily_request_limit: int = 0  # 0 = unlimited


class QuotaManager:
    """Tracks daily token usage per provider/model with auto-reset at midnight UTC."""

    def __init__(self):
        self._quotas: dict[str, ModelQuota] = {}

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}|{model}"

    def _today(self) -> str:
        import datetime
        return datetime.datetime.utcnow().strftime("%Y-%m-%d")

    def get_quota(self, provider: str, model: str) -> ModelQuota:
        key = self._key(provider, model)
        today = self._today()
        if key not in self._quotas:
            self._quotas[key] = ModelQuota()
        q = self._quotas[key]
        if q.last_reset_date != today:
            q.tokens_used_today = 0
            q.requests_today = 0
            q.last_reset_date = today
        return q

    def can_use(self, provider: str, model: str, estimated_tokens: int = 0) -> bool:
        q = self.get_quota(provider, model)
        if q.daily_token_limit > 0 and q.tokens_used_today + estimated_tokens > q.daily_token_limit:
            return False
        if q.daily_request_limit > 0 and q.requests_today >= q.daily_request_limit:
            return False
        return True

    def can_use_tokens(self, provider: str, model: str, tokens: int) -> bool:
        q = self.get_quota(provider, model)
        if q.daily_token_limit > 0 and q.tokens_used_today + tokens > q.daily_token_limit:
            return False
        return True

    def record_usage(self, provider: str, model: str, tokens_used: int) -> ModelQuota:
        q = self.get_quota(provider, model)
        q.tokens_used_today += tokens_used
        q.requests_today += 1
        return q

    def set_limits(self, provider: str, model: str, daily_token_limit: int = 0, daily_request_limit: int = 0) -> ModelQuota:
        q = self.get_quota(provider, model)
        q.daily_token_limit = daily_token_limit
        q.daily_request_limit = daily_request_limit
        return q

    def get_all_quotas(self) -> dict[str, ModelQuota]:
        return dict(self._quotas)


# ---------------------------------------------------------------------------
# AI Response Cache
# ---------------------------------------------------------------------------

class LRUCache:
    """Simple in-memory LRU cache for AI responses."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _make_key(self, provider: str, model: str, symbol: str, timeframe: str, candle_ts: float, prompt_hash: str) -> str:
        return f"{provider}|{model}|{symbol}|{timeframe}|{candle_ts:.0f}|{prompt_hash}"

    def get(self, provider: str, model: str, symbol: str, timeframe: str, candle_ts: float, prompt_hash: str) -> Optional[Any]:
        key = self._make_key(provider, model, symbol, timeframe, candle_ts, prompt_hash)
        if key in self._cache:
            ts, value = self._cache[key]
            if time.time() - ts < self.ttl_seconds:
                self._cache.move_to_end(key)
                return value
            del self._cache[key]
        return None

    def set(self, provider: str, model: str, symbol: str, timeframe: str, candle_ts: float, prompt_hash: str, value: Any) -> None:
        key = self._make_key(provider, model, symbol, timeframe, candle_ts, prompt_hash)
        self._cache[key] = (time.time(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Global Governor (API Usage Safety Limits)
# ---------------------------------------------------------------------------

@dataclass
class GovernorLimits:
    global_max_rpm: int = 0       # requests per minute, 0 = unlimited
    global_max_tpm: int = 0       # tokens per minute, 0 = unlimited
    per_provider_max_rpm: int = 0
    per_provider_max_tpm: int = 0
    per_model_max_rpm: int = 0
    per_model_max_tpm: int = 0


class Governor:
    """Local safety governor for API usage — tracks request rate and token throughput."""

    def __init__(self, limits: Optional[GovernorLimits] = None):
        self.limits = limits or GovernorLimits()
        self._global_rpm: list[float] = []
        self._global_tpm: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._provider_rpm: dict[str, list[float]] = {}
        self._provider_tpm: dict[str, list[tuple[float, int]]] = {}
        self._model_rpm: dict[str, list[float]] = {}
        self._model_tpm: dict[str, list[tuple[float, int]]] = {}

    def _prune(self, timestamps: list[float], window: float = 60.0) -> list[float]:
        now = time.time()
        return [t for t in timestamps if now - t < window]

    def _prune_token_window(self, entries: list[tuple[float, int]], window: float = 60.0) -> list[tuple[float, int]]:
        now = time.time()
        return [(t, tok) for t, tok in entries if now - t < window]

    def can_request(self, provider: str, model: str) -> tuple[bool, str]:
        now = time.time()
        if self.limits.global_max_rpm > 0:
            self._global_rpm = self._prune(self._global_rpm)
            if len(self._global_rpm) >= self.limits.global_max_rpm:
                return False, f"Global RPM limit reached ({self.limits.global_max_rpm})"
        if self.limits.per_provider_max_rpm > 0:
            entries = self._provider_rpm.get(provider, [])
            entries = self._prune(entries)
            self._provider_rpm[provider] = entries
            if len(entries) >= self.limits.per_provider_max_rpm:
                return False, f"Provider {provider} RPM limit reached ({self.limits.per_provider_max_rpm})"
        if self.limits.per_model_max_rpm > 0:
            key = f"{provider}|{model}"
            entries = self._model_rpm.get(key, [])
            entries = self._prune(entries)
            self._model_rpm[key] = entries
            if len(entries) >= self.limits.per_model_max_rpm:
                return False, f"Model {model} RPM limit reached ({self.limits.per_model_max_rpm})"
        return True, ""

    def can_tokens(self, provider: str, model: str, estimated_tokens: int) -> tuple[bool, str]:
        now = time.time()
        if self.limits.global_max_tpm > 0:
            self._global_tpm = self._prune_token_window(self._global_tpm)
            used = sum(tok for _, tok in self._global_tpm)
            if used + estimated_tokens > self.limits.global_max_tpm:
                return False, f"Global TPM limit reached ({self.limits.global_max_tpm})"
        if self.limits.per_provider_max_tpm > 0:
            entries = self._provider_tpm.get(provider, [])
            entries = self._prune_token_window(entries)
            self._provider_tpm[provider] = entries
            used = sum(tok for _, tok in entries)
            if used + estimated_tokens > self.limits.per_provider_max_tpm:
                return False, f"Provider {provider} TPM limit reached ({self.limits.per_provider_max_tpm})"
        if self.limits.per_model_max_tpm > 0:
            key = f"{provider}|{model}"
            entries = self._model_tpm.get(key, [])
            entries = self._prune_token_window(entries)
            self._model_tpm[key] = entries
            used = sum(tok for _, tok in entries)
            if used + estimated_tokens > self.limits.per_model_max_tpm:
                return False, f"Model {model} TPM limit reached ({self.limits.per_model_max_tpm})"
        return True, ""

    def record_request(self, provider: str, model: str, tokens_used: int) -> None:
        now = time.time()
        self._global_rpm.append(now)
        self._global_tpm.append((now, tokens_used))
        self._provider_rpm.setdefault(provider, []).append(now)
        self._provider_tpm.setdefault(provider, []).append((now, tokens_used))
        key = f"{provider}|{model}"
        self._model_rpm.setdefault(key, []).append(now)
        self._model_tpm.setdefault(key, []).append((now, tokens_used))

    def get_usage(self) -> dict:
        now = time.time()
        return {
            "global_rpm": len(self._prune(self._global_rpm)),
            "global_tpm": sum(tok for _, tok in self._prune_token_window(self._global_tpm)),
            "providers": {
                p: {
                    "rpm": len(self._prune(entries)),
                    "tpm": sum(tok for _, tok in self._prune_token_window(self._provider_tpm.get(p, []))),
                }
                for p, entries in self._provider_rpm.items()
            },
            "models": {
                m: {
                    "rpm": len(self._prune(entries)),
                    "tpm": sum(tok for _, tok in self._prune_token_window(self._model_tpm.get(m, []))),
                }
                for m, entries in self._model_rpm.items()
            },
        }


# ---------------------------------------------------------------------------
# Failover Chain
# ---------------------------------------------------------------------------

@dataclass
class FailoverChain:
    """Ordered list of provider/model fallback targets."""
    targets: list[tuple[str, str]] = field(default_factory=list)  # [(provider, model), ...]
    enabled: bool = False  # disabled by default in tournament mode for fairness

    def __iter__(self):
        return iter(self.targets)

    def __len__(self):
        return len(self.targets)

    def __bool__(self):
        return self.enabled and len(self.targets) > 0


# ---------------------------------------------------------------------------
# Provider Health Manager (Main Facade)
# ---------------------------------------------------------------------------

class ProviderHealthManager:
    """Central facade for all provider resilience operations.

    Coordinates cooldown, quota, governor, cache, and failover.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        cooldown_seconds = config.get("cooldown_seconds", 60.0)
        max_failures = config.get("max_failures_before_cooldown", 3)
        max_cooldown = config.get("max_cooldown_seconds", 3600.0)
        cache_size = config.get("cache_max_size", 1000)
        cache_ttl = config.get("cache_ttl_seconds", 3600)
        failover_enabled = config.get("failover_enabled", False)
        failover_targets = config.get("failover_targets", [])

        self.cooldown = CooldownManager(
            cooldown_seconds=cooldown_seconds,
            max_failures_before_cooldown=max_failures,
            max_cooldown_seconds=max_cooldown,
        )
        self.quota = QuotaManager()
        self.cache = LRUCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self.governor = Governor()
        self.failover = FailoverChain(
            targets=[(t["provider"], t["model"]) for t in failover_targets],
            enabled=failover_enabled,
        )
        self._api_metrics: dict[str, dict] = {}  # per-participant API tracking for tournament

    def record_success(self, provider: str, model: str, tokens_used: int = 0) -> None:
        self.cooldown.record_success(provider, model)
        if tokens_used > 0:
            self.quota.record_usage(provider, model, tokens_used)
            self.governor.record_request(provider, model, tokens_used)

    def record_failure(self, provider: str, model: str, error: ClassifiedError) -> None:
        self.cooldown.record_failure(provider, model, error)

    def is_provider_available(self, provider: str, model: str) -> bool:
        if not self.cooldown.is_available(provider, model):
            return False
        if not self.quota.can_use(provider, model):
            return False
        return True

    def get_provider_state(self, provider: str, model: str) -> ProviderState:
        return self.cooldown.get_state(provider, model).state

    def get_all_provider_states(self) -> dict[str, CooldownInfo]:
        return self.cooldown.get_all_states()

    def get_provider_status_summary(self) -> list[dict]:
        states = self.cooldown.get_all_states()
        result = []
        for key, info in sorted(states.items()):
            q = self.quota.get_quota(info.provider, info.model)
            result.append({
                "provider": info.provider,
                "model": info.model,
                "state": info.state.value,
                "consecutive_failures": info.consecutive_failures,
                "total_failures": info.total_failures,
                "total_successes": info.total_successes,
                "last_error": info.last_error[:100] if info.last_error else "",
                "last_error_kind": info.last_error_kind.value if info.last_error_kind else None,
                "cooldown_until": info.cooldown_until if info.state == ProviderState.COOLDOWN else None,
                "tokens_used_today": q.tokens_used_today,
                "daily_token_limit": q.daily_token_limit,
                "requests_today": q.requests_today,
                "daily_request_limit": q.daily_request_limit,
            })
        return result

    def check_cache(self, provider: str, model: str, symbol: str, timeframe: str, candle_ts: float, prompt_hash: str) -> Optional[Any]:
        return self.cache.get(provider, model, symbol, timeframe, candle_ts, prompt_hash)

    def store_cache(self, provider: str, model: str, symbol: str, timeframe: str, candle_ts: float, prompt_hash: str, value: Any) -> None:
        self.cache.set(provider, model, symbol, timeframe, candle_ts, prompt_hash, value)

    def can_make_request(self, provider: str, model: str, estimated_tokens: int = 0) -> tuple[bool, str]:
        if not self.is_provider_available(provider, model):
            state = self.get_provider_state(provider, model)
            return False, f"Provider {provider}/{model} is {state.value}"
        ok, reason = self.governor.can_request(provider, model)
        if not ok:
            return False, reason
        ok, reason = self.governor.can_tokens(provider, model, estimated_tokens)
        if not ok:
            return False, reason
        return True, ""

    def get_next_failover_target(self, failed_provider: str, failed_model: str) -> Optional[tuple[str, str]]:
        if not self.failover:
            return None
        for provider, model in self.failover:
            if provider == failed_provider and model == failed_model:
                continue
            if self.is_provider_available(provider, model):
                return (provider, model)
        return None

    def record_tournament_api_usage(self, participant_id: str, provider: str, model: str, tokens_used: int, success: bool) -> None:
        if participant_id not in self._api_metrics:
            self._api_metrics[participant_id] = {
                "provider": provider,
                "model": model,
                "total_tokens": 0,
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "first_request_time": None,
                "last_request_time": None,
            }
        m = self._api_metrics[participant_id]
        m["total_tokens"] += tokens_used
        m["total_requests"] += 1
        if success:
            m["successful_requests"] += 1
        else:
            m["failed_requests"] += 1
        now = time.time()
        if m["first_request_time"] is None:
            m["first_request_time"] = now
        m["last_request_time"] = now

    def get_tournament_api_usage(self, participant_id: Optional[str] = None) -> dict:
        if participant_id:
            return {participant_id: self._api_metrics.get(participant_id, {})}
        return dict(self._api_metrics)

    def set_quota_limits(self, provider: str, model: str, daily_token_limit: int = 0, daily_request_limit: int = 0) -> None:
        self.quota.set_limits(provider, model, daily_token_limit=daily_token_limit, daily_request_limit=daily_request_limit)

    def force_provider_online(self, provider: str, model: str) -> None:
        self.cooldown.force_online(provider, model)

    def force_provider_disabled(self, provider: str, model: str) -> None:
        self.cooldown.set_state(provider, model, ProviderState.DISABLED)

    def get_governor_usage(self) -> dict:
        return self.governor.get_usage()
