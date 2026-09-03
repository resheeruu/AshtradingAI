"""Tests for AI provider response parsing and isolation."""
import pytest
from src.ai.providers.openai_compatible import parse_ai_response, OpenAICompatibleProvider
from src.ai.base import TradingAI, MarketContext, AIDecision
from src.ai.test_strategy import TestStrategy
from src.ai.provider_strategy import ProviderTradingAI


class TestParseAIResponse:
    def test_normal_json(self):
        resp = '{"decision": "BUY", "confidence": 0.82, "reason": "test", "suggested_position_size": 0.05}'
        parsed = parse_ai_response(resp)
        assert parsed["decision"] == "BUY"
        assert parsed["confidence"] == 0.82
        assert parsed["reason"] == "test"

    def test_json_in_code_block(self):
        resp = '```json\n{"decision": "SELL", "confidence": 0.9}\n```'
        parsed = parse_ai_response(resp)
        assert parsed["decision"] == "SELL"
        assert parsed["confidence"] == 0.9

    def test_json_with_surrounding_text(self):
        resp = 'Here is my analysis:\n{"decision": "HOLD", "confidence": 0.5}\nDone.'
        parsed = parse_ai_response(resp)
        assert parsed["decision"] == "HOLD"

    def test_invalid_json_fallback(self):
        parsed = parse_ai_response("this is not json at all")
        assert parsed["decision"] == "HOLD"
        assert parsed["confidence"] == 0.0

    def test_invalid_decision_normalized(self):
        resp = '{"decision": "MOON", "confidence": 0.5}'
        parsed = parse_ai_response(resp)
        assert parsed["decision"] == "HOLD"

    def test_confidence_clamped_high(self):
        resp = '{"decision": "BUY", "confidence": 5.0}'
        parsed = parse_ai_response(resp)
        assert parsed["confidence"] == 1.0

    def test_confidence_clamped_low(self):
        resp = '{"decision": "BUY", "confidence": -1.0}'
        parsed = parse_ai_response(resp)
        assert parsed["confidence"] == 0.0

    def test_position_size_clamped(self):
        resp = '{"decision": "BUY", "confidence": 0.8, "suggested_position_size": 0.5}'
        parsed = parse_ai_response(resp)
        assert parsed["suggested_position_size"] == 0.25

    def test_null_optional_fields(self):
        resp = '{"decision": "HOLD", "confidence": 0.5}'
        parsed = parse_ai_response(resp)
        assert parsed["stop_loss"] is None
        assert parsed["take_profit"] is None
        assert parsed["suggested_position_size"] is None

    def test_non_dict_json(self):
        parsed = parse_ai_response('[1, 2, 3]')
        assert parsed["decision"] == "HOLD"


class TestOpenAICompatibleProvider:
    def test_not_configured(self):
        p = OpenAICompatibleProvider(api_key="", base_url="")
        assert not p.is_configured()

    def test_configured(self):
        p = OpenAICompatibleProvider(api_key="test-key", base_url="https://api.example.com/v1")
        assert p.is_configured()

    def test_generate_not_configured(self):
        p = OpenAICompatibleProvider(api_key="", base_url="")
        result = p.generate("test prompt")
        assert not result["success"]
        assert "not_configured" in result["error"]


class TestAIIsolation:
    def test_independent_portfolios(self):
        from src.ai.manager import AIManager
        from src.market.candles import generate_synthetic_candles

        manager = AIManager(starting_balance=1000.0)
        manager.register_ai(TestStrategy(ai_id="AI-One"))
        manager.register_ai(TestStrategy(ai_id="AI-Two"))
        data = {"BTC/USDT": generate_synthetic_candles(periods=200)}
        results = manager.run_competition(data)

        assert len(results) == 2
        ids = {r["ai_id"] for r in results}
        assert "AI-One" in ids
        assert "AI-Two" in ids

        # Each AI's portfolio is independent
        for entry in manager.entries:
            assert entry.portfolio.ai_id in ("AI-One", "AI-Two")
            # Starting balance should be the same
            assert entry.portfolio.starting_balance == 1000.0


class TestFairExperiment:
    def test_same_parameters(self):
        from src.ai.manager import AIManager
        from src.market.candles import generate_synthetic_candles

        manager = AIManager(starting_balance=1000.0, fee=0.001, slippage=0.0005)
        manager.register_ai(TestStrategy(ai_id="Fair-A"))
        manager.register_ai(TestStrategy(ai_id="Fair-B"))
        data = {"BTC/USDT": generate_synthetic_candles(periods=300, seed=99)}
        results = manager.run_competition(data, experiment_id="fair-test")

        for r in results:
            assert r["metrics"]["starting_balance"] == 1000.0

        # Verify both used same data
        assert len(data["BTC/USDT"]) == 300
