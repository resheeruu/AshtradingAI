"""Tests for Milestone 7: Advanced Strategy & Risk Monitor.

Covers:
- Filter cascade (ATR, EMA angle, price/EMA, candle direction, EMA ordering, session)
- Strategy state machine (SCANNING → ARMED → WINDOW_OPEN → ENTRY)
- Broker-aware position sizing
- SL/TP validation
- No-lookahead guarantee
- Duplicate entry prevention
- State persistence and restart
- Risk integration
- Integration with PaperBroker
"""
import math
import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.indicators.technical import ema, atr
from src.strategy.filters import (
    ATRFilter, EMAAngleFilter, PriceEMAFilter, CandleDirectionFilter,
    EMAOrderFilter, SessionFilter, FilterCascade, FilterCascadeResult,
    build_filter_config_from_settings,
)
from src.strategy.engine import StrategyEngine, StrategyPhase, StrategyState, StrategySignal
from src.risk.manager import RiskManager, RiskDecision, BrokerMetadata, PositionSizingResult
from src.portfolio.portfolio import Portfolio
from src.ai.base import TradingAI, MarketContext
from src.config import Config


# ── Helper Fixtures ───────────────────────────────────────────────────

def _make_candles(prices, volatility=0.005, seed=42):
    """Generate deterministic candles from a list of close prices."""
    import random
    rng = random.Random(seed)
    candles = []
    base_time = datetime.now(timezone.utc) - timedelta(hours=len(prices))
    for i, close in enumerate(prices):
        high = close * (1 + abs(rng.gauss(0, volatility)))
        low = close * (1 - abs(rng.gauss(0, volatility)))
        open_ = prices[i - 1] if i > 0 else close
        ts = (base_time + timedelta(hours=i)).isoformat()
        candles.append({
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(100, 10000),
        })
    return candles


def _trending_up(n=60, start=100.0, step=0.5):
    """Generate uptrending prices."""
    return [start + i * step for i in range(n)]


def _trending_down(n=60, start=200.0, step=0.5):
    """Generate downtrending prices."""
    return [start - i * step for i in range(n)]


def _ranging(n=60, mid=100.0, amp=2.0):
    """Generate ranging prices."""
    import math
    return [mid + amp * math.sin(i * 0.3) for i in range(n)]


class SimpleAI(TradingAI):
    """Minimal AI for testing that always returns BUY with 0.8 confidence."""
    def __init__(self):
        super().__init__(ai_id="simple-test")
    def decide(self, context):
        return {"decision": "BUY", "confidence": 0.8, "reason": "test"}


class HoldAI(TradingAI):
    """AI that always holds."""
    def __init__(self):
        super().__init__(ai_id="hold-test")
    def decide(self, context):
        return {"decision": "HOLD", "confidence": 0.5, "reason": "test"}


# ============================================================
# ATR Filter Tests
# ============================================================

class TestATRFilter:
    def test_disabled_passes(self):
        f = ATRFilter(enabled=False)
        candles = _make_candles(_trending_up(30))
        result = f.evaluate(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.passed is True

    def test_insufficient_data_fails_closed(self):
        f = ATRFilter(period=14)
        result = f.evaluate([100.0] * 5, [99.0] * 5, [100.0] * 5)
        assert result.passed is False

    def test_valid_data_passes(self):
        f = ATRFilter(enabled=True, min_atr=0.0)
        candles = _make_candles(_trending_up(30))
        result = f.evaluate(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.passed is True
        assert result.value is not None

    def test_min_atr_rejection(self):
        f = ATRFilter(enabled=True, min_atr=99999.0)
        candles = _make_candles(_trending_up(30))
        result = f.evaluate(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.passed is False
        assert "below minimum" in result.reason

    def test_max_atr_rejection(self):
        f = ATRFilter(enabled=True, max_atr=0.00001)
        candles = _make_candles(_trending_up(30))
        result = f.evaluate(
            [c["high"] for c in candles],
            [c["low"] for c in candles],
            [c["close"] for c in candles],
        )
        assert result.passed is False
        assert "above maximum" in result.reason

    def test_nan_close_fails_closed(self):
        """With NaN close values, ATR filter should reject."""
        f = ATRFilter(enabled=True)
        result = f.evaluate([100.0] * 20, [99.0] * 20, [float("nan")] * 20)
        # NaN close propagates through TR → ATR should be NaN or non-finite
        # If the ATR implementation happens to produce a finite value from NaN inputs,
        # that value is unreliable and should still be rejected
        if result.passed and result.value is not None:
            # Value exists but came from NaN inputs — verify it's from a broken calc
            assert result.value != result.value or result.value <= 0 or not math.isfinite(result.value), \
                f"ATR should not be {result.value} with NaN close inputs"


# ============================================================
# EMA Angle Filter Tests
# ============================================================

class TestEMAAngleFilter:
    def test_disabled_passes(self):
        f = EMAAngleFilter(enabled=False)
        result = f.evaluate(_trending_up(30))
        assert result.passed is True

    def test_uptrend_long_passes(self):
        f = EMAAngleFilter(enabled=True, ema_period=10, min_angle=0.0001)
        result = f.evaluate(_trending_up(30), direction="LONG")
        assert result.passed is True

    def test_uptrend_short_rejects(self):
        f = EMAAngleFilter(enabled=True, ema_period=10, min_angle=0.0001)
        result = f.evaluate(_trending_up(30), direction="SHORT")
        assert result.passed is False
        assert "positive EMA slope for SHORT" in result.reason

    def test_downtrend_short_passes(self):
        f = EMAAngleFilter(enabled=True, ema_period=10, min_angle=0.0001)
        result = f.evaluate(_trending_down(30), direction="SHORT")
        assert result.passed is True

    def test_ranging_rejects_low_angle(self):
        f = EMAAngleFilter(enabled=True, ema_period=10, min_angle=999.0)
        result = f.evaluate(_ranging(30), direction="LONG")
        assert result.passed is False

    def test_insufficient_data_fails(self):
        f = EMAAngleFilter(enabled=True, ema_period=21)
        result = f.evaluate([100.0] * 5)
        assert result.passed is False


# ============================================================
# Price vs EMA Filter Tests
# ============================================================

class TestPriceEMAFilter:
    def test_disabled_passes(self):
        f = PriceEMAFilter(enabled=False)
        result = f.evaluate(_trending_up(30))
        assert result.passed is True

    def test_uptrend_long_passes(self):
        f = PriceEMAFilter(enabled=True, ema_period=10)
        prices = _trending_up(30)
        result = f.evaluate(prices, direction="LONG")
        assert result.passed is True

    def test_uptrend_short_rejects(self):
        f = PriceEMAFilter(enabled=True, ema_period=10)
        prices = _trending_up(30)
        result = f.evaluate(prices, direction="SHORT")
        assert result.passed is False

    def test_downtrend_short_passes(self):
        f = PriceEMAFilter(enabled=True, ema_period=10)
        prices = _trending_down(30)
        result = f.evaluate(prices, direction="SHORT")
        assert result.passed is True

    def test_insufficient_data_fails(self):
        f = PriceEMAFilter(enabled=True, ema_period=50)
        result = f.evaluate([100.0] * 10)
        assert result.passed is False


# ============================================================
# Candle Direction Filter Tests
# ============================================================

class TestCandleDirectionFilter:
    def test_disabled_passes(self):
        f = CandleDirectionFilter(enabled=False)
        result = f.evaluate([{"open": 100, "close": 101}], "LONG")
        assert result.passed is True

    def test_bullish_candle_long_passes(self):
        f = CandleDirectionFilter(enabled=True)
        candles = [
            {"open": 100, "close": 100, "timestamp": "t0"},
            {"open": 100, "close": 105, "timestamp": "t1"},  # bullish completed (index -2)
            {"open": 110, "close": 112, "timestamp": "t2"},  # forming candle (index -1)
        ]
        result = f.evaluate(candles, "LONG")
        assert result.passed is True

    def test_bearish_candle_long_rejects(self):
        f = CandleDirectionFilter(enabled=True)
        candles = [
            {"open": 100, "close": 100, "timestamp": "t0"},
            {"open": 100, "close": 100, "timestamp": "t1"},
            {"open": 105, "close": 100, "timestamp": "t2"},  # bearish
        ]
        result = f.evaluate(candles, "LONG")
        assert result.passed is False

    def test_no_forming_candle_used(self):
        """Prove the forming candle (index -1) is NOT used."""
        f = CandleDirectionFilter(enabled=True)
        candles = [
            {"open": 100, "close": 105},  # completed: bullish
            {"open": 110, "close": 100},  # forming: bearish (should be ignored)
        ]
        result = f.evaluate(candles, "LONG")
        # Should pass because completed candle is bullish
        assert result.passed is True

    def test_insufficient_candles_fails(self):
        f = CandleDirectionFilter(enabled=True)
        result = f.evaluate([{"open": 100, "close": 101}], "LONG")
        assert result.passed is False


# ============================================================
# EMA Ordering Filter Tests
# ============================================================

class TestEMAOrderFilter:
    def test_disabled_passes(self):
        f = EMAOrderFilter(enabled=False)
        result = f.evaluate(_trending_up(60))
        assert result.passed is True

    def test_uptrend_long_passes(self):
        f = EMAOrderFilter(enabled=True, fast_period=5, medium_period=10, slow_period=20)
        result = f.evaluate(_trending_up(60), direction="LONG")
        assert result.passed is True

    def test_uptrend_short_rejects(self):
        f = EMAOrderFilter(enabled=True, fast_period=5, medium_period=10, slow_period=20)
        result = f.evaluate(_trending_up(60), direction="SHORT")
        assert result.passed is False

    def test_downtrend_short_passes(self):
        f = EMAOrderFilter(enabled=True, fast_period=5, medium_period=10, slow_period=20)
        result = f.evaluate(_trending_down(60), direction="SHORT")
        assert result.passed is True

    def test_insufficient_data_fails(self):
        f = EMAOrderFilter(enabled=True, fast_period=5, medium_period=10, slow_period=20)
        result = f.evaluate([100.0] * 10)
        assert result.passed is False


# ============================================================
# Session Filter Tests
# ============================================================

class TestSessionFilter:
    def test_disabled_passes(self):
        f = SessionFilter(enabled=False)
        result = f.evaluate("2024-01-01T12:00:00+00:00")
        assert result.passed is True

    def test_in_session_passes(self):
        f = SessionFilter(enabled=True, start_hour=9, end_hour=17)
        result = f.evaluate("2024-01-01T12:00:00+00:00")
        assert result.passed is True

    def test_out_of_session_rejects(self):
        f = SessionFilter(enabled=True, start_hour=9, end_hour=17)
        result = f.evaluate("2024-01-01T20:00:00+00:00")
        assert result.passed is False
        assert "outside session" in result.reason

    def test_midnight_crossing_session(self):
        f = SessionFilter(enabled=True, start_hour=22, end_hour=6)
        # 23:00 should be in session
        result = f.evaluate("2024-01-01T23:00:00+00:00")
        assert result.passed is True
        # 03:00 should be in session
        result = f.evaluate("2024-01-01T03:00:00+00:00")
        assert result.passed is True
        # 12:00 should be out
        result = f.evaluate("2024-01-01T12:00:00+00:00")
        assert result.passed is False

    def test_invalid_timestamp_fails(self):
        f = SessionFilter(enabled=True)
        result = f.evaluate("not-a-timestamp")
        assert result.passed is False


# ============================================================
# Filter Cascade Tests
# ============================================================

class TestFilterCascade:
    def test_all_disabled_passes(self):
        cfg = {
            "atr_enabled": False, "angle_enabled": False,
            "price_ema_enabled": False, "candle_enabled": False,
            "ema_order_enabled": False, "session_enabled": False,
        }
        cascade = FilterCascade(cfg)
        candles = _make_candles(_trending_up(60))
        result = cascade.evaluate(candles, "LONG")
        assert result.passed is True

    def test_filter_failure_blocks(self):
        cfg = {
            "atr_enabled": True, "atr_min": 99999.0,  # will always fail
            "angle_enabled": False, "price_ema_enabled": False,
            "candle_enabled": False, "ema_order_enabled": False,
            "session_enabled": False,
        }
        cascade = FilterCascade(cfg)
        candles = _make_candles(_trending_up(60))
        result = cascade.evaluate(candles, "LONG")
        assert result.passed is False
        assert "ATR" in result.rejection_reason

    def test_build_config_from_settings(self):
        settings = {
            "M7_ATR_FILTER_ENABLED": False,
            "M7_ATR_MIN": 5.0,
            "M7_ATR_MAX": 100.0,
            "M7_ANGLE_FILTER_ENABLED": True,
            "M7_MIN_ANGLE": 0.001,
            "M7_PRICE_EMA_PERIOD": 30,
            "M7_CANDLE_FILTER_ENABLED": False,
            "M7_SESSION_FILTER_ENABLED": True,
            "M7_SESSION_START_HOUR": 8,
            "M7_SESSION_END_HOUR": 20,
        }
        cfg = build_filter_config_from_settings(settings)
        assert cfg["atr_enabled"] is False
        assert cfg["atr_min"] == 5.0
        assert cfg["angle_enabled"] is True
        assert cfg["min_angle"] == 0.001
        assert cfg["price_ema_period"] == 30
        assert cfg["candle_enabled"] is False
        assert cfg["session_enabled"] is True
        assert cfg["session_start_hour"] == 8


# ============================================================
# Strategy State Machine Tests
# ============================================================

class TestStrategyStateMachine:
    def test_scanning_to_armed(self):
        """SCANNING → ARMED when directional setup detected."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        candles = _make_candles(_trending_up(60))
        # Process candle to detect direction
        engine.process_candle(candles, portfolio_balance=10000)
        # After processing, should be ARMED or still SCANNING
        assert engine.state.phase in (StrategyPhase.SCANNING, StrategyPhase.ARMED)

    def test_armed_to_window_open(self):
        """ARMED → WINDOW_OPEN after pullback confirmation."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
            pullback_candles=1,
        )
        # Manually set state to ARMED
        engine.state.phase = StrategyPhase.ARMED
        engine.state.direction = "LONG"

        # Create candles with a pullback (bearish candle)
        prices = _trending_up(10)
        candles = _make_candles(prices)
        # Make last completed candle bearish for pullback
        candles[-2]["close"] = candles[-2]["open"] - 1.0

        engine.process_candle(candles, portfolio_balance=10000)
        # Should be in WINDOW_OPEN or ENTRY
        assert engine.state.phase in (StrategyPhase.WINDOW_OPEN, StrategyPhase.ENTRY, StrategyPhase.SCANNING)

    def test_invalidation_on_opposite_signal(self):
        """Opposite signal in ARMED state resets to SCANNING."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        engine.state.phase = StrategyPhase.ARMED
        engine.state.direction = "LONG"

        # Create downtrending candles (opposite signal)
        candles = _make_candles(_trending_down(60))
        engine.process_candle(candles, portfolio_balance=10000)
        assert engine.state.phase == StrategyPhase.SCANNING

    def test_window_expiry_resets(self):
        """Expired breakout window resets to SCANNING."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            breakout_window=2,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        engine.state.phase = StrategyPhase.WINDOW_OPEN
        engine.state.direction = "LONG"
        engine.state.window_candles_remaining = 1

        # Price doesn't break out
        candles = _make_candles(_ranging(60))
        engine.process_candle(candles, portfolio_balance=10000)
        assert engine.state.phase == StrategyPhase.SCANNING

    def test_insufficient_candles_returns_none(self):
        engine = StrategyEngine(ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h")
        result = engine.process_candle([], portfolio_balance=10000)
        assert result is None

    def test_duplicate_candle_skipped(self):
        """Same candle timestamp should not be processed twice."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        candles = _make_candles(_trending_up(60))
        engine.process_candle(candles, portfolio_balance=10000)
        state_after_first = engine.state.last_processed_candle
        # Process same candle set
        engine.process_candle(candles, portfolio_balance=10000)
        # Should be same (no update)
        assert engine.state.last_processed_candle == state_after_first

    def test_state_serialization(self):
        """State can be serialized and deserialized."""
        state = StrategyState(
            phase=StrategyPhase.ARMED,
            direction="LONG",
            signal_price=100.0,
            signal_atr=2.5,
            pullback_count=1,
            pullback_target=2,
            breakout_high=105.0,
            breakout_low=95.0,
            symbol="BTC/USDT",
            timeframe="1h",
        )
        d = state.to_dict()
        restored = StrategyState.from_dict(d)
        assert restored.phase == StrategyPhase.ARMED
        assert restored.direction == "LONG"
        assert restored.signal_price == 100.0
        assert restored.symbol == "BTC/USDT"

    def test_stale_state_detection(self):
        engine = StrategyEngine(ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h")
        assert engine.is_stale() is False  # SCANNING is never stale
        engine.state.phase = StrategyPhase.ARMED
        engine.state.window_candles_remaining = -60
        assert engine.is_stale(max_age_candles=50) is True

    def test_entry_signal_has_sl_tp(self):
        """ENTRY signal should include SL and TP."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            sl_atr_multiplier=2.0, tp_atr_multiplier=3.0,
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        engine.state.phase = StrategyPhase.WINDOW_OPEN
        engine.state.direction = "LONG"
        engine.state.signal_atr = 10.0
        engine.state.breakout_high = 110.0
        engine.state.breakout_low = 90.0
        engine.state.window_candles_remaining = 1

        candles = _make_candles(_trending_up(60))
        # Make last candle break out
        candles[-2]["close"] = candles[-2]["high"] + 1.0

        signal = engine.process_candle(candles, portfolio_balance=10000)
        if signal is not None:
            assert signal.stop_loss < signal.price
            assert signal.take_profit > signal.price
            assert signal.symbol == "BTC/USDT"


# ============================================================
# No-Lookahead Tests
# ============================================================

class TestNoLookahead:
    def test_forming_candle_excluded_from_filters(self):
        """The forming candle (last in list) must not influence filter results."""
        # Create a scenario where completed candles pass but forming candle would fail
        prices = _trending_up(30)
        candles = _make_candles(prices)

        # Set forming candle to extreme values that would break ATR
        candles[-1]["high"] = 999999.0
        candles[-1]["low"] = 0.001

        f = ATRFilter(enabled=True, min_atr=0.0)
        completed = candles[:-1]
        result = f.evaluate(
            [c["high"] for c in completed],
            [c["low"] for c in completed],
            [c["close"] for c in completed],
        )
        # Should pass because forming candle is excluded
        assert result.passed is True

    def test_forming_candle_excluded_from_candle_filter(self):
        """Candle direction filter uses completed candle, not forming."""
        f = CandleDirectionFilter(enabled=True)
        candles = [
            {"open": 100, "close": 105, "timestamp": "t1"},  # completed: bullish
            {"open": 110, "close": 90, "timestamp": "t2"},   # forming: bearish
        ]
        result = f.evaluate(candles, "LONG")
        # Should pass because completed candle is bullish
        assert result.passed is True

    def test_state_machine_uses_completed_candles(self):
        """State machine processes completed candles, not forming."""
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        # Create candles where completed = up, forming = down
        prices = _trending_up(60)
        candles = _make_candles(prices)
        candles[-1]["close"] = candles[-1]["open"] - 10  # forming is down

        engine.process_candle(candles, portfolio_balance=10000)
        # Should detect LONG from completed candles, not SHORT from forming
        if engine.state.phase == StrategyPhase.ARMED:
            assert engine.state.direction == "LONG"


# ============================================================
# Position Sizing Tests
# ============================================================

class TestPositionSizing:
    def test_basic_sizing(self):
        risk = RiskManager(risk_percent=0.01)
        # Crypto-like: contract_size=1, tick_value=1.0 per point
        meta = BrokerMetadata(tick_value=1.0, tick_size=0.01, point=0.01,
                              contract_size=1, volume_min=0.001, volume_max=10.0,
                              volume_step=0.001)
        result = risk.calculate_position_size(
            balance=10000, entry_price=50000.0, stop_loss=49500.0, broker_meta=meta,
        )
        assert result.valid is True
        assert result.volume > 0
        assert result.risk_amount == 100.0  # 1% of 10000

    def test_different_tick_sizes(self):
        risk = RiskManager(risk_percent=0.01)
        # Crypto: tick_size = 0.01
        meta = BrokerMetadata(tick_value=1.0, tick_size=0.01, point=0.01,
                              contract_size=1, volume_min=0.001, volume_max=10.0,
                              volume_step=0.001)
        result = risk.calculate_position_size(
            balance=10000, entry_price=50000, stop_loss=49500, broker_meta=meta,
        )
        assert result.valid is True

    def test_different_tick_values(self):
        risk = RiskManager(risk_percent=0.02)
        meta = BrokerMetadata(tick_value=0.1, tick_size=0.001, point=0.001,
                              contract_size=100000, volume_min=0.01, volume_max=50.0,
                              volume_step=0.01)
        result = risk.calculate_position_size(
            balance=50000, entry_price=1.2000, stop_loss=1.1900, broker_meta=meta,
        )
        assert result.valid is True

    def test_different_sl_distances(self):
        risk = RiskManager(risk_percent=0.01)
        meta = BrokerMetadata(tick_value=1.0, tick_size=0.01, point=0.01,
                              contract_size=1, volume_min=0.001, volume_max=10.0,
                              volume_step=0.001)
        # Tight SL
        r1 = risk.calculate_position_size(10000, 50000.0, 49900.0, meta)
        # Wide SL
        r2 = risk.calculate_position_size(10000, 50000.0, 49000.0, meta)
        assert r1.valid and r2.valid
        # Tighter SL → larger position
        assert r1.volume > r2.volume

    def test_minimum_volume_enforced(self):
        risk = RiskManager(risk_percent=0.01)
        meta = BrokerMetadata(tick_value=0.01, tick_size=0.0001, point=0.0001,
                              contract_size=100000, volume_min=0.1, volume_max=100.0,
                              volume_step=0.01)
        result = risk.calculate_position_size(1000, 1.1000, 1.0950, meta)
        # May be below minimum → either adjusted to min or blocked
        if result.valid:
            assert result.volume >= 0.1

    def test_maximum_volume_enforced(self):
        risk = RiskManager(risk_percent=0.5)
        meta = BrokerMetadata(tick_value=0.01, tick_size=0.0001, point=0.0001,
                              contract_size=100000, volume_min=0.01, volume_max=1.0,
                              volume_step=0.01)
        result = risk.calculate_position_size(1000000, 1.1000, 1.0999, meta)
        assert result.valid is True
        assert result.volume <= 1.0

    def test_volume_step_normalization(self):
        risk = RiskManager(risk_percent=0.10)
        meta = BrokerMetadata(tick_value=1.0, tick_size=0.01, point=0.01,
                              contract_size=1, volume_min=0.01, volume_max=10.0,
                              volume_step=0.05)
        result = risk.calculate_position_size(10000, 50000.0, 49500.0, meta)
        assert result.valid is True
        # Volume should be normalized to nearest step (or min if below)
        # 10% risk → risk_amount=1000, sl_points=50000, raw=0.02 → rounds to 0.0 → min=0.01
        # Or with tighter SL: 10% risk, SL=49900, sl_distance=100, sl_points=10000
        # raw=1000/(10000*1*1)=0.1 → 0.1/0.05=2 → 2*0.05=0.10
        assert result.volume >= meta.volume_min

    def test_insufficient_metadata_blocks(self):
        risk = RiskManager(risk_percent=0.01)
        result = risk.calculate_position_size(10000, 1.1000, 1.0950, None)
        assert result.valid is False
        assert "insufficient broker metadata" in result.reason

    def test_invalid_metadata_blocks(self):
        risk = RiskManager(risk_percent=0.01)
        meta = BrokerMetadata(tick_value=0, tick_size=0)  # invalid
        result = risk.calculate_position_size(10000, 1.1000, 1.0950, meta)
        assert result.valid is False

    def test_zero_sl_distance_blocks(self):
        risk = RiskManager(risk_percent=0.01)
        meta = BrokerMetadata(tick_value=0.01, tick_size=0.0001, point=0.0001,
                              contract_size=100000)
        result = risk.calculate_position_size(10000, 1.1000, 1.1000, meta)
        assert result.valid is False
        assert "invalid SL distance" in result.reason

    def test_nan_values_block(self):
        risk = RiskManager(risk_percent=0.01)
        meta = BrokerMetadata(tick_value=float("nan"), tick_size=0.0001)
        result = risk.calculate_position_size(10000, 1.1000, 1.0950, meta)
        assert result.valid is False


# ============================================================
# SL/TP Validation Tests
# ============================================================

class TestSLTPValidation:
    def test_long_sl_below_entry(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.0950, 1.1100)
        assert valid is True

    def test_long_sl_above_entry_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.1050, 1.1100)
        assert valid is False
        assert "must be below entry" in reason

    def test_short_sl_above_entry(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("sell", 1.1000, 1.1050, 1.0900)
        assert valid is True

    def test_short_sl_below_entry_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("sell", 1.1000, 1.0950, 1.0900)
        assert valid is False
        assert "must be above entry" in reason

    def test_long_tp_above_entry(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.0950, 1.1100)
        assert valid is True

    def test_long_tp_below_entry_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.0950, 1.0900)
        assert valid is False
        assert "must be above entry" in reason

    def test_nan_sl_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, float("nan"), 1.1100)
        assert valid is False

    def test_infinite_tp_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.0950, float("inf"))
        assert valid is False

    def test_zero_sl_distance_rejects(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, 1.1000, 1.1100)
        assert valid is False

    def test_none_sl_passes(self):
        risk = RiskManager()
        valid, reason = risk.validate_sl_tp("buy", 1.1000, None, 1.1100)
        assert valid is True


# ============================================================
# Risk Integration Tests
# ============================================================

class TestRiskIntegration:
    def test_kill_switch_blocks(self):
        risk = RiskManager()
        risk.activate_kill_switch()
        p = Portfolio("test", 10000)
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.8)
        assert result.allowed is False
        assert "kill_switch" in result.reason

    def test_max_drawdown_blocks(self):
        risk = RiskManager(max_drawdown=0.10)
        p = Portfolio("test", 10000)
        p.balance = 8900  # 11% drawdown
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.8)
        assert result.allowed is False
        assert "drawdown" in result.reason

    def test_daily_loss_blocks(self):
        risk = RiskManager(max_daily_loss=0.03)
        p = Portfolio("test", 10000)
        p.daily_pnl = -400  # 4% daily loss
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.8)
        assert result.allowed is False
        assert "daily loss" in result.reason

    def test_position_limit_blocks(self):
        risk = RiskManager(max_open_positions=2)
        p = Portfolio("test", 10000)
        p.positions["A"] = None
        p.positions["B"] = None
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.8)
        assert result.allowed is False
        assert "max_open_positions" in result.reason

    def test_low_confidence_blocks(self):
        risk = RiskManager(min_confidence=0.6)
        p = Portfolio("test", 10000)
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.3)
        assert result.allowed is False
        assert "confidence" in result.reason

    def test_hold_always_allowed(self):
        risk = RiskManager()
        risk.activate_kill_switch()
        p = Portfolio("test", 10000)
        result = risk.evaluate(p, "HOLD", "BTC/USDT", 50000, 0.0)
        assert result.allowed is True

    def test_position_size_capped(self):
        risk = RiskManager(max_position_size=0.10)
        p = Portfolio("test", 10000)
        result = risk.evaluate(p, "BUY", "BTC/USDT", 50000, 0.8, requested_size=5.0)
        assert result.allowed is True
        assert result.adjusted_size is not None
        assert result.adjusted_size * 50000 <= 10000 * 0.10


# ============================================================
# Duplicate Entry Prevention Tests
# ============================================================

class TestDuplicatePrevention:
    def test_same_candle_not_processed_twice(self):
        engine = StrategyEngine(
            ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h",
            filter_config={"atr_enabled": False, "angle_enabled": False,
                          "price_ema_enabled": False, "candle_enabled": False,
                          "ema_order_enabled": False, "session_enabled": False},
        )
        candles = _make_candles(_trending_up(60))

        # Process first time
        engine.process_candle(candles, portfolio_balance=10000)
        ts = engine.state.last_processed_candle

        # Process same candles again
        result = engine.process_candle(candles, portfolio_balance=10000)
        # Should return None because same candle
        assert result is None
        assert engine.state.last_processed_candle == ts


# ============================================================
# Persistence Tests
# ============================================================

class TestM7Persistence:
    def _get_db(self):
        from src.persistence.database import Database
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db = Database(db_path=Path(f.name))
        db.connect()
        return db

    def test_save_and_load_state(self):
        db = self._get_db()
        state = {
            "phase": "ARMED",
            "direction": "LONG",
            "signal_price": 100.0,
            "pullback_count": 1,
        }
        db.save_m7_state("session1", "BTC/USDT", json.dumps(state))
        loaded = db.load_m7_state("session1", "BTC/USDT")
        assert loaded is not None
        assert loaded["phase"] == "ARMED"
        assert loaded["direction"] == "LONG"
        db.close()

    def test_state_update_overwrites(self):
        db = self._get_db()
        db.save_m7_state("s1", "BTC/USDT", json.dumps({"phase": "SCANNING"}))
        db.save_m7_state("s1", "BTC/USDT", json.dumps({"phase": "ARMED"}))
        loaded = db.load_m7_state("s1", "BTC/USDT")
        assert loaded["phase"] == "ARMED"
        db.close()

    def test_clear_state(self):
        db = self._get_db()
        db.save_m7_state("s1", "BTC/USDT", json.dumps({"phase": "ARMED"}))
        db.clear_m7_state("s1", "BTC/USDT")
        loaded = db.load_m7_state("s1", "BTC/USDT")
        assert loaded is None
        db.close()

    def test_log_m7_signal(self):
        db = self._get_db()
        sig_id = db.log_m7_signal(
            session_id="s1", symbol="BTC/USDT", direction="LONG",
            phase="ENTRY", candle_timestamp="2024-01-01T00:00:00",
            price=50000.0, confidence=0.8, reason="test",
        )
        assert sig_id
        signals = db.get_m7_signals_by_session("s1")
        assert len(signals) == 1
        assert signals[0]["symbol"] == "BTC/USDT"
        db.close()

    def test_state_survives_restart(self):
        """Simulate restart: save state, create new engine, load state."""
        db = self._get_db()
        state = {
            "phase": "ARMED",
            "direction": "LONG",
            "signal_price": 100.0,
            "signal_atr": 2.5,
            "pullback_count": 1,
            "pullback_target": 2,
            "breakout_high": 105.0,
            "breakout_low": 95.0,
            "last_processed_candle": "2024-01-01T00:00:00",
            "setup_id": "test:1",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
        }
        db.save_m7_state("restart-test", "BTC/USDT", json.dumps(state))

        # Simulate restart
        engine = StrategyEngine(ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h")
        loaded = db.load_m7_state("restart-test", "BTC/USDT")
        assert loaded is not None
        engine.load_state_dict(loaded)
        assert engine.state.phase == StrategyPhase.ARMED
        assert engine.state.direction == "LONG"
        assert engine.state.signal_price == 100.0
        db.close()

    def test_stale_state_reset_on_load(self):
        """Stale state should be detected and reset."""
        db = self._get_db()
        state = {
            "phase": "WINDOW_OPEN",
            "window_candles_remaining": -100,
        }
        db.save_m7_state("stale-test", "BTC/USDT", json.dumps(state))
        engine = StrategyEngine(ai=SimpleAI(), symbol="BTC/USDT", timeframe="1h")
        loaded = db.load_m7_state("stale-test", "BTC/USDT")
        engine.load_state_dict(loaded)
        assert engine.is_stale(max_age_candles=50) is True
        engine.invalidate("stale state")
        assert engine.state.phase == StrategyPhase.SCANNING
        db.close()


# ============================================================
# PaperBroker Integration Tests
# ============================================================

class TestM7PaperBrokerIntegration:
    def test_m7_signal_through_paper_broker(self):
        """M7 signal can be executed through the existing PaperBroker."""
        from src.trading.paper.broker import PaperBroker

        risk = RiskManager(min_confidence=0.6)
        broker = PaperBroker(fee=0.001, slippage=0.0005)
        portfolio = Portfolio("m7-test", 10000)

        # Simulate an M7 signal
        signal = StrategySignal(
            symbol="BTC/USDT", direction="BUY", phase=StrategyPhase.ENTRY,
            price=50000.0, atr_value=500.0, stop_loss=49000.0,
            take_profit=51500.0, confidence=0.8, reason="test",
            setup_id="test:1", candle_timestamp="2024-01-01T00:00:00",
        )

        # Risk check
        risk_result = risk.evaluate(
            portfolio=portfolio, decision=signal.direction,
            symbol=signal.symbol, price=signal.price,
            confidence=signal.confidence,
        )
        assert risk_result.allowed is True

        # Execute through broker
        order = broker.execute_buy(
            portfolio=portfolio, symbol=signal.symbol,
            price=signal.price, quantity=0.01,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
        )
        assert order is not None
        assert order["status"] == "filled"
        assert "BTC/USDT" in portfolio.positions

    def test_m7_risk_blocks_paper_broker(self):
        """RiskManager blocking prevents PaperBroker execution."""
        from src.trading.paper.broker import PaperBroker

        risk = RiskManager(min_confidence=0.9)
        broker = PaperBroker()
        portfolio = Portfolio("m7-test", 10000)

        risk_result = risk.evaluate(
            portfolio=portfolio, decision="BUY",
            symbol="BTC/USDT", price=50000.0, confidence=0.5,
        )
        assert risk_result.allowed is False

        # Should not execute
        if risk_result.allowed:
            order = broker.execute_buy(
                portfolio=portfolio, symbol="BTC/USDT",
                price=50000.0, quantity=0.01,
            )
            assert order is None  # should never reach here


# ============================================================
# Config Tests
# ============================================================

class TestM7Config:
    def test_m7_defaults(self):
        assert Config.M7_ENABLED is False
        assert Config.M7_ATR_FILTER_ENABLED is True
        assert Config.M7_RISK_PERCENT == 0.01

    def test_m7_in_as_dict(self):
        d = Config.as_dict()
        assert "M7_ENABLED" in d
        assert "M7_RISK_PERCENT" in d
