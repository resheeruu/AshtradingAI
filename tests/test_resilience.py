"""Comprehensive tests for AI provider resilience system."""
import time
from unittest.mock import MagicMock, patch

import pytest

from src.ai.health import (
    ProviderHealthManager, ProviderState, ErrorKind, ClassifiedError,
    BackoffCalculator, CooldownManager, CooldownInfo, QuotaManager,
    ModelQuota, LRUCache, Governor, GovernorLimits, FailoverChain,
)


# ---------------------------------------------------------------------------
# ClassifiedError tests
# ---------------------------------------------------------------------------

class TestClassifiedError:
    def test_timeout_error(self):
        error = ClassifiedError.classify(timeout=True)
        assert error.kind == ErrorKind.TIMEOUT
        assert error.is_transient is True

    def test_rate_limit_429(self):
        error = ClassifiedError.classify(status_code=429, message="Rate limited")
        assert error.kind == ErrorKind.RATE_LIMIT
        assert error.is_transient is True

    def test_tpm_rate_limit(self):
        error = ClassifiedError.classify(status_code=429, message="token limit exceeded")
        assert error.kind == ErrorKind.TPM_RATE_LIMIT

    def test_daily_quota(self):
        error = ClassifiedError.classify(status_code=429, message="daily quota exceeded")
        assert error.kind == ErrorKind.DAILY_QUOTA

    def test_auth_error(self):
        error = ClassifiedError.classify(status_code=401, message="Unauthorized")
        assert error.kind == ErrorKind.AUTH_ERROR
        assert error.is_transient is False

    def test_forbidden(self):
        error = ClassifiedError.classify(status_code=403, message="Forbidden")
        assert error.kind == ErrorKind.FORBIDDEN
        assert error.is_transient is False

    def test_not_found(self):
        error = ClassifiedError.classify(status_code=404, message="Not found")
        assert error.kind == ErrorKind.NOT_FOUND
        assert error.is_transient is False

    def test_server_error(self):
        error = ClassifiedError.classify(status_code=500, message="Internal error")
        assert error.kind == ErrorKind.SERVER_ERROR
        assert error.is_transient is True

    def test_unknown_error(self):
        error = ClassifiedError.classify(status_code=418, message="I'm a teapot")
        assert error.kind == ErrorKind.UNKNOWN

    def test_retry_after_parsing(self):
        error = ClassifiedError.classify(status_code=429, message="Rate limit, retry after 30 seconds")
        assert error.retry_after == 30.0


# ---------------------------------------------------------------------------
# BackoffCalculator tests
# ---------------------------------------------------------------------------

class TestBackoffCalculator:
    def test_exponential_growth(self):
        calc = BackoffCalculator(base_delay=1.0, max_delay=100.0, multiplier=2.0, jitter=False)
        assert calc.delay(0) == 1.0
        assert calc.delay(1) == 2.0
        assert calc.delay(2) == 4.0
        assert calc.delay(3) == 8.0

    def test_max_delay_cap(self):
        calc = BackoffCalculator(base_delay=1.0, max_delay=10.0, multiplier=2.0, jitter=False)
        assert calc.delay(10) == 10.0

    def test_jitter_adds_variance(self):
        calc = BackoffCalculator(base_delay=1.0, max_delay=100.0, multiplier=2.0, jitter=True)
        delays = [calc.delay(3) for _ in range(10)]
        assert len(set(delays)) > 1  # Should have some variance


# ---------------------------------------------------------------------------
# CooldownManager tests
# ---------------------------------------------------------------------------

class TestCooldownManager:
    def test_initial_state(self):
        mgr = CooldownManager()
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.ONLINE
        assert info.consecutive_failures == 0

    def test_record_success(self):
        mgr = CooldownManager()
        mgr.record_success("openai", "gpt-4")
        info = mgr.get_state("openai", "gpt-4")
        assert info.total_successes == 1
        assert info.consecutive_failures == 0

    def test_record_failure_stays_online_below_threshold(self):
        mgr = CooldownManager(max_failures_before_cooldown=3)
        for _ in range(2):
            mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.ONLINE
        assert info.consecutive_failures == 2

    def test_record_failure_enters_cooldown(self):
        mgr = CooldownManager(max_failures_before_cooldown=3, cooldown_seconds=60.0)
        for _ in range(4):
            mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.COOLDOWN
        assert info.cooldown_until > time.time()

    def test_auth_failure_marks_auth_failed(self):
        mgr = CooldownManager()
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=401))
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.AUTH_FAILED

    def test_not_found_marks_model_unavailable(self):
        mgr = CooldownManager()
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=404))
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.MODEL_UNAVAILABLE

    def test_daily_quota_marks_quota_exhausted(self):
        mgr = CooldownManager()
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=429, message="daily quota"))
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.QUOTA_EXHAUSTED

    def test_is_available_online(self):
        mgr = CooldownManager()
        assert mgr.is_available("openai", "gpt-4") is True

    def test_is_not_available_cooldown(self):
        mgr = CooldownManager(max_failures_before_cooldown=1)
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        assert mgr.is_available("openai", "gpt-4") is False

    def test_cooldown_recovery(self):
        mgr = CooldownManager(max_failures_before_cooldown=1, cooldown_seconds=0.01)
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        time.sleep(0.02)
        assert mgr.is_available("openai", "gpt-4") is True

    def test_force_online(self):
        mgr = CooldownManager()
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=401))
        assert mgr.is_available("openai", "gpt-4") is False
        mgr.force_online("openai", "gpt-4")
        assert mgr.is_available("openai", "gpt-4") is True

    def test_success_resets_cooldown(self):
        mgr = CooldownManager(max_failures_before_cooldown=1)
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        mgr.record_failure("openai", "gpt-4", ClassifiedError.classify(status_code=500))
        mgr.record_success("openai", "gpt-4")
        info = mgr.get_state("openai", "gpt-4")
        assert info.state == ProviderState.ONLINE
        assert info.consecutive_failures == 0


# ---------------------------------------------------------------------------
# QuotaManager tests
# ---------------------------------------------------------------------------

class TestQuotaManager:
    def test_unlimited_by_default(self):
        mgr = QuotaManager()
        assert mgr.can_use("openai", "gpt-4") is True

    def test_token_limit(self):
        mgr = QuotaManager()
        mgr.set_limits("openai", "gpt-4", daily_token_limit=1000)
        assert mgr.can_use("openai", "gpt-4", estimated_tokens=500) is True
        mgr.record_usage("openai", "gpt-4", 800)
        assert mgr.can_use("openai", "gpt-4", estimated_tokens=500) is False

    def test_request_limit(self):
        mgr = QuotaManager()
        mgr.set_limits("openai", "gpt-4", daily_request_limit=2)
        mgr.record_usage("openai", "gpt-4", 100)
        mgr.record_usage("openai", "gpt-4", 100)
        assert mgr.can_use("openai", "gpt-4") is False

    def test_daily_reset(self):
        mgr = QuotaManager()
        mgr.set_limits("openai", "gpt-4", daily_token_limit=100)
        mgr.record_usage("openai", "gpt-4", 100)
        assert mgr.can_use("openai", "gpt-4", estimated_tokens=1) is False
        q = mgr.get_quota("openai", "gpt-4")
        q.last_reset_date = "2000-01-01"  # Force reset
        assert mgr.can_use("openai", "gpt-4", estimated_tokens=1) is True


# ---------------------------------------------------------------------------
# LRUCache tests
# ---------------------------------------------------------------------------

class TestLRUCache:
    def test_set_get(self):
        cache = LRUCache(max_size=10, ttl_seconds=3600)
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1", "value1")
        result = cache.get("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1")
        assert result == "value1"

    def test_cache_miss(self):
        cache = LRUCache(max_size=10, ttl_seconds=3600)
        result = cache.get("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1")
        assert result is None

    def test_cache_expiry(self):
        cache = LRUCache(max_size=10, ttl_seconds=0.01)
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1", "value1")
        time.sleep(0.02)
        result = cache.get("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1")
        assert result is None

    def test_lru_eviction(self):
        cache = LRUCache(max_size=2, ttl_seconds=3600)
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 1.0, "h1", "v1")
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 2.0, "h2", "v2")
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 3.0, "h3", "v3")
        assert cache.get("openai", "gpt-4", "BTC/USDT", "1h", 1.0, "h1") is None
        assert cache.get("openai", "gpt-4", "BTC/USDT", "1h", 2.0, "h2") == "v2"

    def test_clear(self):
        cache = LRUCache(max_size=10, ttl_seconds=3600)
        cache.set("openai", "gpt-4", "BTC/USDT", "1h", 1.0, "h1", "v1")
        cache.clear()
        assert len(cache) == 0


# ---------------------------------------------------------------------------
# Governor tests
# ---------------------------------------------------------------------------

class TestGovernor:
    def test_unlimited(self):
        gov = Governor()
        ok, reason = gov.can_request("openai", "gpt-4")
        assert ok is True

    def test_rpm_limit(self):
        gov = Governor(GovernorLimits(global_max_rpm=2))
        gov.record_request("openai", "gpt-4", 100)
        gov.record_request("openai", "gpt-4", 100)
        ok, reason = gov.can_request("openai", "gpt-4")
        assert ok is False
        assert "RPM" in reason

    def test_tpm_limit(self):
        gov = Governor(GovernorLimits(global_max_tpm=100))
        gov.record_request("openai", "gpt-4", 100)
        ok, reason = gov.can_tokens("openai", "gpt-4", 50)
        assert ok is False
        assert "TPM" in reason

    def test_per_provider_limit(self):
        gov = Governor(GovernorLimits(per_provider_max_rpm=1))
        gov.record_request("openai", "gpt-4", 100)
        ok, reason = gov.can_request("openai", "gpt-4")
        assert ok is False

    def test_usage_tracking(self):
        gov = Governor()
        gov.record_request("openai", "gpt-4", 100)
        gov.record_request("openai", "gpt-4", 200)
        usage = gov.get_usage()
        assert usage["global_rpm"] == 2
        assert usage["global_tpm"] == 300


# ---------------------------------------------------------------------------
# FailoverChain tests
# ---------------------------------------------------------------------------

class TestFailoverChain:
    def test_disabled_by_default(self):
        chain = FailoverChain()
        assert bool(chain) is False

    def test_enabled_with_targets(self):
        chain = FailoverChain(
            targets=[("deepseek", "deepseek-chat")],
            enabled=True,
        )
        assert bool(chain) is True
        assert len(chain) == 1

    def test_iteration(self):
        chain = FailoverChain(
            targets=[("deepseek", "deepseek-chat"), ("groq", "llama-3.3-70b")],
            enabled=True,
        )
        targets = list(chain)
        assert len(targets) == 2
        assert targets[0] == ("deepseek", "deepseek-chat")


# ---------------------------------------------------------------------------
# ProviderHealthManager integration tests
# ---------------------------------------------------------------------------

class TestProviderHealthManager:
    def test_init_defaults(self):
        mgr = ProviderHealthManager()
        assert mgr.failover.enabled is False
        assert len(mgr.failover) == 0

    def test_record_success(self):
        mgr = ProviderHealthManager()
        mgr.record_success("openai", "gpt-4", tokens_used=100)
        state = mgr.get_provider_state("openai", "gpt-4")
        assert state == ProviderState.ONLINE

    def test_record_failure(self):
        mgr = ProviderHealthManager()
        error = ClassifiedError.classify(status_code=500)
        mgr.record_failure("openai", "gpt-4", error)
        info = mgr.get_all_provider_states()["openai|gpt-4"]
        assert info.total_failures == 1

    def test_is_provider_available(self):
        mgr = ProviderHealthManager()
        assert mgr.is_provider_available("openai", "gpt-4") is True

    def test_can_make_request(self):
        mgr = ProviderHealthManager()
        ok, reason = mgr.can_make_request("openai", "gpt-4", 1000)
        assert ok is True

    def test_quota_tracking(self):
        mgr = ProviderHealthManager()
        mgr.set_quota_limits("openai", "gpt-4", daily_token_limit=500)
        assert mgr.can_make_request("openai", "gpt-4", 300)[0] is True
        mgr.record_success("openai", "gpt-4", 400)
        # Check quota manager directly
        q = mgr.quota.get_quota("openai", "gpt-4")
        assert q.tokens_used_today == 400
        assert q.daily_token_limit == 500
        assert mgr.quota.can_use_tokens("openai", "gpt-4", 200) is False
        assert mgr.quota.can_use_tokens("openai", "gpt-4", 100) is True

    def test_cache_operations(self):
        mgr = ProviderHealthManager()
        mgr.store_cache("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1", {"decision": "BUY"})
        cached = mgr.check_cache("openai", "gpt-4", "BTC/USDT", "1h", 1234567890.0, "hash1")
        assert cached == {"decision": "BUY"}

    def test_failover_disabled(self):
        mgr = ProviderHealthManager()
        target = mgr.get_next_failover_target("openai", "gpt-4")
        assert target is None

    def test_failover_enabled(self):
        mgr = ProviderHealthManager(config={
            "failover_enabled": True,
            "failover_targets": [{"provider": "deepseek", "model": "deepseek-chat"}],
        })
        target = mgr.get_next_failover_target("openai", "gpt-4")
        assert target == ("deepseek", "deepseek-chat")

    def test_failover_skips_unavailable(self):
        mgr = ProviderHealthManager(config={
            "failover_enabled": True,
            "failover_targets": [{"provider": "deepseek", "model": "deepseek-chat"}],
        })
        mgr.force_provider_disabled("deepseek", "deepseek-chat")
        target = mgr.get_next_failover_target("openai", "gpt-4")
        assert target is None

    def test_tournament_api_usage(self):
        mgr = ProviderHealthManager()
        mgr.record_tournament_api_usage("p1", "openai", "gpt-4", 100, True)
        mgr.record_tournament_api_usage("p1", "openai", "gpt-4", 200, False)
        usage = mgr.get_tournament_api_usage("p1")
        assert usage["p1"]["total_tokens"] == 300
        assert usage["p1"]["successful_requests"] == 1
        assert usage["p1"]["failed_requests"] == 1

    def test_provider_status_summary(self):
        mgr = ProviderHealthManager()
        mgr.record_success("openai", "gpt-4", 100)
        summary = mgr.get_provider_status_summary()
        assert len(summary) == 1
        assert summary[0]["provider"] == "openai"
        assert summary[0]["model"] == "gpt-4"
        assert summary[0]["state"] == "ONLINE"
        assert summary[0]["total_successes"] == 1

    def test_force_provider_online(self):
        mgr = ProviderHealthManager()
        mgr.force_provider_disabled("openai", "gpt-4")
        assert mgr.is_provider_available("openai", "gpt-4") is False
        mgr.force_provider_online("openai", "gpt-4")
        assert mgr.is_provider_available("openai", "gpt-4") is True

    def test_governor_usage(self):
        mgr = ProviderHealthManager()
        mgr.record_success("openai", "gpt-4", 100)
        usage = mgr.get_governor_usage()
        assert usage["global_rpm"] == 1
        assert usage["global_tpm"] == 100
