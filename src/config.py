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
    CANDLE_LIMIT: int = _int(os.getenv("CANDLE_LIMIT", "500"), 500)
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
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "")

    # Tournament participants: comma-separated provider names
    AI_PARTICIPANTS: str = os.getenv("AI_PARTICIPANTS", "")

    # Data source: "synthetic" or "live"
    DATA_SOURCE: str = os.getenv("DATA_SOURCE", "synthetic")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "")

    # Experiment
    EXPERIMENT_ID: str = os.getenv("EXPERIMENT_ID", "")

    # AI Resilience Configuration
    AI_FAILOVER_ENABLED: bool = _bool(os.getenv("AI_FAILOVER_ENABLED", "false"), False)
    AI_CACHE_ENABLED: bool = _bool(os.getenv("AI_CACHE_ENABLED", "true"), True)
    AI_CACHE_MAX_SIZE: int = _int(os.getenv("AI_CACHE_MAX_SIZE", "1000"), 1000)
    AI_CACHE_TTL_SECONDS: int = _int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"), 3600)
    AI_COOLDOWN_SECONDS: float = _float(os.getenv("AI_COOLDOWN_SECONDS", "60.0"), 60.0)
    AI_MAX_FAILURES_BEFORE_COOLDOWN: int = _int(os.getenv("AI_MAX_FAILURES_BEFORE_COOLDOWN", "3"), 3)
    AI_MAX_COOLDOWN_SECONDS: float = _float(os.getenv("AI_MAX_COOLDOWN_SECONDS", "3600.0"), 3600.0)
    AI_DAILY_TOKEN_LIMIT: int = _int(os.getenv("AI_DAILY_TOKEN_LIMIT", "0"), 0)
    AI_DAILY_REQUEST_LIMIT: int = _int(os.getenv("AI_DAILY_REQUEST_LIMIT", "0"), 0)
    AI_GLOBAL_MAX_RPM: int = _int(os.getenv("AI_GLOBAL_MAX_RPM", "0"), 0)
    AI_GLOBAL_MAX_TPM: int = _int(os.getenv("AI_GLOBAL_MAX_TPM", "0"), 0)
    AI_PER_PROVIDER_MAX_RPM: int = _int(os.getenv("AI_PER_PROVIDER_MAX_RPM", "0"), 0)
    AI_PER_PROVIDER_MAX_TPM: int = _int(os.getenv("AI_PER_PROVIDER_MAX_TPM", "0"), 0)
    AI_FALLBACK_PROVIDER: str = os.getenv("AI_FALLBACK_PROVIDER", "")
    AI_FALLBACK_MODEL: str = os.getenv("AI_FALLBACK_MODEL", "")
    AI_FALLBACK_API_KEY: str = os.getenv("AI_FALLBACK_API_KEY", "")
    AI_FALLBACK_BASE_URL: str = os.getenv("AI_FALLBACK_BASE_URL", "")

    # Milestone 5: Paper-Live configuration
    PAPER_SESSION_ID: str = os.getenv("PAPER_SESSION_ID", "")
    PAPER_AUTO_RESUME: bool = _bool(os.getenv("PAPER_AUTO_RESUME", "true"), True)
    MARKET_MAX_STALE_SECONDS: int = _int(os.getenv("MARKET_MAX_STALE_SECONDS", "300"), 300)
    MARKET_RETRY_SECONDS: int = _int(os.getenv("MARKET_RETRY_SECONDS", "30"), 30)
    PAPER_HEARTBEAT_SECONDS: int = _int(os.getenv("PAPER_HEARTBEAT_SECONDS", "300"), 300)

    # Milestone 6: MT5 Demo configuration
    MT5_ENABLED: bool = _bool(os.getenv("MT5_ENABLED", "false"), False)
    MT5_DEMO_ONLY: bool = _bool(os.getenv("MT5_DEMO_ONLY", "true"), True)
    MT5_DEMO_TRADING_ENABLED: bool = _bool(os.getenv("MT5_DEMO_TRADING_ENABLED", "false"), False)
    MT5_PATH: str = os.getenv("MT5_PATH", "")
    MT5_LOGIN: int = _int(os.getenv("MT5_LOGIN", "0"), 0)
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")
    MT5_TIMEOUT: int = _int(os.getenv("MT5_TIMEOUT", "10000"), 10000)
    MT5_EXPECTED_SERVER: str = os.getenv("MT5_EXPECTED_SERVER", "")
    MT5_EXPECTED_LOGIN: int = _int(os.getenv("MT5_EXPECTED_LOGIN", "0"), 0)
    MT5_MAGIC_NUMBER: int = _int(os.getenv("MT5_MAGIC_NUMBER", "20260904"), 20260904)
    MT5_SYMBOL_MAP: str = os.getenv("MT5_SYMBOL_MAP", "")

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
        if cls.CANDLE_LIMIT < 1 or cls.CANDLE_LIMIT > 5000:
            errors.append("CANDLE_LIMIT must be between 1 and 5000")
        if cls.MT5_ENABLED and cls.LIVE_TRADING:
            errors.append("MT5_ENABLED and LIVE_TRADING cannot both be true in M6")
        if cls.MT5_ENABLED and cls.MT5_DEMO_ONLY and cls.MT5_DEMO_TRADING_ENABLED:
            # This is the allowed state: MT5 enabled, demo only, demo trading on
            pass
        return errors

    @classmethod
    def as_dict(cls) -> dict:
        return {
            "APP_ENV": cls.APP_ENV,
            "LIVE_TRADING": cls.LIVE_TRADING,
            "EXCHANGE": cls.EXCHANGE,
            "SYMBOLS": cls.SYMBOLS,
            "TIMEFRAME": cls.TIMEFRAME,
            "CANDLE_LIMIT": cls.CANDLE_LIMIT,
            "STARTING_BALANCE": cls.STARTING_BALANCE,
            "TRADING_FEE": cls.TRADING_FEE,
            "SLIPPAGE": cls.SLIPPAGE,
            "MAX_POSITION_SIZE": cls.MAX_POSITION_SIZE,
            "MAX_OPEN_POSITIONS": cls.MAX_OPEN_POSITIONS,
            "MAX_DAILY_LOSS": cls.MAX_DAILY_LOSS,
            "MAX_DRAWDOWN": cls.MAX_DRAWDOWN,
            "MIN_AI_CONFIDENCE": cls.MIN_AI_CONFIDENCE,
            "DATA_SOURCE": cls.DATA_SOURCE,
            "AI_PROVIDER": cls.AI_PROVIDER,
            "AI_BASE_URL": cls.AI_BASE_URL,
            "AI_MODEL": cls.AI_MODEL,
            "AI_FAILOVER_ENABLED": cls.AI_FAILOVER_ENABLED,
            "AI_CACHE_ENABLED": cls.AI_CACHE_ENABLED,
            "AI_CACHE_MAX_SIZE": cls.AI_CACHE_MAX_SIZE,
            "AI_CACHE_TTL_SECONDS": cls.AI_CACHE_TTL_SECONDS,
            "AI_COOLDOWN_SECONDS": cls.AI_COOLDOWN_SECONDS,
            "AI_MAX_FAILURES_BEFORE_COOLDOWN": cls.AI_MAX_FAILURES_BEFORE_COOLDOWN,
            "AI_MAX_COOLDOWN_SECONDS": cls.AI_MAX_COOLDOWN_SECONDS,
            "AI_DAILY_TOKEN_LIMIT": cls.AI_DAILY_TOKEN_LIMIT,
            "AI_DAILY_REQUEST_LIMIT": cls.AI_DAILY_REQUEST_LIMIT,
            "AI_GLOBAL_MAX_RPM": cls.AI_GLOBAL_MAX_RPM,
            "AI_GLOBAL_MAX_TPM": cls.AI_GLOBAL_MAX_TPM,
            "AI_PER_PROVIDER_MAX_RPM": cls.AI_PER_PROVIDER_MAX_RPM,
            "AI_PER_PROVIDER_MAX_TPM": cls.AI_PER_PROVIDER_MAX_TPM,
            "AI_FALLBACK_PROVIDER": cls.AI_FALLBACK_PROVIDER,
            "AI_FALLBACK_MODEL": cls.AI_FALLBACK_MODEL,
            "AI_FALLBACK_BASE_URL": cls.AI_FALLBACK_BASE_URL,
            "MT5_ENABLED": cls.MT5_ENABLED,
            "MT5_DEMO_ONLY": cls.MT5_DEMO_ONLY,
            "MT5_DEMO_TRADING_ENABLED": cls.MT5_DEMO_TRADING_ENABLED,
            "MT5_MAGIC_NUMBER": cls.MT5_MAGIC_NUMBER,
        }
