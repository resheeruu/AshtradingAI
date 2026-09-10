"""Centralized configuration center — validates all config on startup.

Invalid configuration produces BLOCKED state rather than partial running.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.config import Config
from src.core.enums import TradingMode

logger = logging.getLogger(__name__)


@dataclass
class ConfigValidation:
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class ConfigCenter:
    """Validates and centralizes all configuration at startup."""

    @staticmethod
    def validate_startup() -> ConfigValidation:
        result = ConfigValidation()

        # Safety invariants
        if Config.LIVE_TRADING:
            result.add_error("LIVE_TRADING must be false")

        # Balance
        if Config.STARTING_BALANCE <= 0:
            result.add_error("STARTING_BALANCE must be positive")

        # Symbols
        if not Config.SYMBOLS:
            result.add_error("SYMBOLS must not be empty")

        # Fee/slip
        if Config.TRADING_FEE < 0 or Config.TRADING_FEE > 0.1:
            result.add_error("TRADING_FEE must be 0-0.1")
        if Config.SLIPPAGE < 0 or Config.SLIPPAGE > 0.05:
            result.add_error("SLIPPAGE must be 0-0.05")

        # Candles
        if Config.CANDLE_LIMIT < 1 or Config.CANDLE_LIMIT > 5000:
            result.add_error("CANDLE_LIMIT must be 1-5000")

        # MT5 safety
        if Config.MT5_ENABLED and Config.LIVE_TRADING:
            result.add_error("MT5_ENABLED + LIVE_TRADING not allowed")

        # AI config
        if not Config.AI_PROVIDER and not Config.AI_PARTICIPANTS:
            result.add_warning("No AI provider configured")

        # Risk limits
        if Config.MAX_DRAWDOWN <= 0 or Config.MAX_DRAWDOWN >= 1.0:
            result.add_error("MAX_DRAWDOWN must be 0-1.0")
        if Config.MAX_DAILY_LOSS <= 0 or Config.MAX_DAILY_LOSS >= 1.0:
            result.add_error("MAX_DAILY_LOSS must be 0-1.0")

        if result.errors:
            logger.error("CONFIG VALIDATION FAILED: %s", "; ".join(result.errors))
        if result.warnings:
            logger.warning("CONFIG WARNINGS: %s", "; ".join(result.warnings))

        return result

    @staticmethod
    def get_mode() -> TradingMode:
        if Config.MT5_ENABLED and Config.MT5_DEMO_TRADING_ENABLED:
            return TradingMode.MT5_DEMO
        if Config.MT5_ENABLED:
            return TradingMode.MT5_DEMO
        if Config.DATA_SOURCE == "live":
            return TradingMode.PAPER_LIVE
        return TradingMode.PAPER

    @staticmethod
    def get_risk_config() -> Dict:
        from src.risk.advanced import RiskConfig
        return RiskConfig(
            risk_per_trade=0.01,
            max_daily_loss=Config.MAX_DAILY_LOSS,
            max_drawdown=Config.MAX_DRAWDOWN,
            max_open_positions=Config.MAX_OPEN_POSITIONS,
            min_confidence=Config.MIN_AI_CONFIDENCE,
            max_position_size=Config.MAX_POSITION_SIZE,
        )
