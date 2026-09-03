"""Central configuration loader for AshtradingAI."""
import os
from pathlib import Path
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)


def _bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


def _float(val: str, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class Config:
    """Immutable application configuration loaded from environment."""

    APP_ENV: str = os.getenv("APP_ENV", "paper")
    LIVE_TRADING: bool = _bool(os.getenv("LIVE_TRADING", "false"), False)
    EXCHANGE: str = os.getenv("EXCHANGE", "binance")
    SYMBOLS: list[str] = [
        s.strip() for s in os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",") if s.strip()
    ]
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    STARTING_BALANCE: float = _float(os.getenv("STARTING_BALANCE", "1000"), 1000.0)
    TRADING_FEE: float = _float(os.getenv("TRADING_FEE", "0.001"), 0.001)
    SLIPPAGE: float = _float(os.getenv("SLIPPAGE", "0.0005"), 0.0005)
    MAX_POSITION_SIZE: float = _float(os.getenv("MAX_POSITION_SIZE", "0.10"), 0.10)
    MAX_OPEN_POSITIONS: int = _int(os.getenv("MAX_OPEN_POSITIONS", "3"), 3)
    MAX_DAILY_LOSS: float = _float(os.getenv("MAX_DAILY_LOSS", "0.03"), 0.03)
    MAX_DRAWDOWN: float = _float(os.getenv("MAX_DRAWDOWN", "0.15"), 0.15)
    MIN_AI_CONFIDENCE: float = _float(os.getenv("MIN_AI_CONFIDENCE", "0.60"), 0.60)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "")

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of validation errors. Empty list means OK."""
        errors: list[str] = []
        if cls.LIVE_TRADING:
            errors.append("LIVE_TRADING must be false in this milestone")
        if cls.STARTING_BALANCE <= 0:
            errors.append("STARTING_BALANCE must be positive")
        if not cls.SYMBOLS:
            errors.append("SYMBOLS must not be empty")
        if cls.TRADING_FEE < 0 or cls.TRADING_FEE > 0.1:
            errors.append("TRADING_FEE must be between 0 and 0.1")
        if cls.SLIPPAGE < 0 or cls.SLIPPAGE > 0.05:
            errors.append("SLIPPAGE must be between 0 and 0.05")
        return errors

    @classmethod
    def as_dict(cls) -> dict:
        return {
            "APP_ENV": cls.APP_ENV,
            "LIVE_TRADING": cls.LIVE_TRADING,
            "EXCHANGE": cls.EXCHANGE,
            "SYMBOLS": cls.SYMBOLS,
            "TIMEFRAME": cls.TIMEFRAME,
            "STARTING_BALANCE": cls.STARTING_BALANCE,
            "TRADING_FEE": cls.TRADING_FEE,
            "SLIPPAGE": cls.SLIPPAGE,
            "MAX_POSITION_SIZE": cls.MAX_POSITION_SIZE,
            "MAX_OPEN_POSITIONS": cls.MAX_OPEN_POSITIONS,
            "MAX_DAILY_LOSS": cls.MAX_DAILY_LOSS,
            "MAX_DRAWDOWN": cls.MAX_DRAWDOWN,
            "MIN_AI_CONFIDENCE": cls.MIN_AI_CONFIDENCE,
        }
