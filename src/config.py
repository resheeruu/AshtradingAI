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

    # Milestone: Coins.ph Market Data Configuration
    COINSPH_ENABLED: bool = _bool(os.getenv("COINSPH_ENABLED", "false"), False)
    COINSPH_API_BASE_URL: str = os.getenv("COINSPH_API_BASE_URL", "https://api.pro.coins.ph")

    # Milestone 7: Advanced Strategy & Risk Monitor
    M7_ENABLED: bool = _bool(os.getenv("M7_ENABLED", "false"), False)
    M7_ATR_FILTER_ENABLED: bool = _bool(os.getenv("M7_ATR_FILTER_ENABLED", "true"), True)
    M7_ATR_MIN: float = _float(os.getenv("M7_ATR_MIN", "0.0"), 0.0)
    M7_ATR_MAX: float = _float(os.getenv("M7_ATR_MAX", "0.0"), 0.0)  # 0 = no max
    M7_ATR_INCREASE_THRESHOLD: float = _float(os.getenv("M7_ATR_INCREASE_THRESHOLD", "0.0"), 0.0)
    M7_ATR_DECREASE_THRESHOLD: float = _float(os.getenv("M7_ATR_DECREASE_THRESHOLD", "0.0"), 0.0)
    M7_ATR_PERIOD: int = _int(os.getenv("M7_ATR_PERIOD", "14"), 14)
    M7_ANGLE_FILTER_ENABLED: bool = _bool(os.getenv("M7_ANGLE_FILTER_ENABLED", "true"), True)
    M7_ANGLE_EMA_PERIOD: int = _int(os.getenv("M7_ANGLE_EMA_PERIOD", "21"), 21)
    M7_ANGLE_SCALE_FACTOR: float = _float(os.getenv("M7_ANGLE_SCALE_FACTOR", "10000.0"), 10000.0)
    M7_MIN_ANGLE: float = _float(os.getenv("M7_MIN_ANGLE", "0.0002"), 0.0002)
    M7_MAX_ANGLE: float = _float(os.getenv("M7_MAX_ANGLE", "0.0"), 0.0)  # 0 = no max
    M7_PRICE_EMA_FILTER_ENABLED: bool = _bool(os.getenv("M7_PRICE_EMA_FILTER_ENABLED", "true"), True)
    M7_PRICE_EMA_PERIOD: int = _int(os.getenv("M7_PRICE_EMA_PERIOD", "50"), 50)
    M7_CANDLE_FILTER_ENABLED: bool = _bool(os.getenv("M7_CANDLE_FILTER_ENABLED", "true"), True)
    M7_EMA_ORDER_FILTER_ENABLED: bool = _bool(os.getenv("M7_EMA_ORDER_FILTER_ENABLED", "true"), True)
    M7_EMA_FAST_PERIOD: int = _int(os.getenv("M7_EMA_FAST_PERIOD", "12"), 12)
    M7_EMA_MEDIUM_PERIOD: int = _int(os.getenv("M7_EMA_MEDIUM_PERIOD", "26"), 26)
    M7_EMA_SLOW_PERIOD: int = _int(os.getenv("M7_EMA_SLOW_PERIOD", "50"), 50)
    M7_SESSION_FILTER_ENABLED: bool = _bool(os.getenv("M7_SESSION_FILTER_ENABLED", "false"), False)
    M7_SESSION_START_HOUR: int = _int(os.getenv("M7_SESSION_START_HOUR", "0"), 0)
    M7_SESSION_START_MINUTE: int = _int(os.getenv("M7_SESSION_START_MINUTE", "0"), 0)
    M7_SESSION_END_HOUR: int = _int(os.getenv("M7_SESSION_END_HOUR", "23"), 23)
    M7_SESSION_END_MINUTE: int = _int(os.getenv("M7_SESSION_END_MINUTE", "59"), 59)
    M7_SESSION_TIMEZONE: str = os.getenv("M7_SESSION_TIMEZONE", "UTC")
    M7_PULLBACK_CANDLES: int = _int(os.getenv("M7_PULLBACK_CANDLES", "2"), 2)
    M7_BREAKOUT_WINDOW: int = _int(os.getenv("M7_BREAKOUT_WINDOW", "3"), 3)
    M7_RISK_PERCENT: float = _float(os.getenv("M7_RISK_PERCENT", "0.01"), 0.01)
    M7_SL_ATR_MULTIPLIER: float = _float(os.getenv("M7_SL_ATR_MULTIPLIER", "2.0"), 2.0)
    M7_TP_ATR_MULTIPLIER: float = _float(os.getenv("M7_TP_ATR_MULTIPLIER", "3.0"), 3.0)

    # Milestone 8: Phone Trading Terminal
    TERMINAL_ENABLED: bool = _bool(os.getenv("TERMINAL_ENABLED", "true"), True)
    TERMINAL_HEARTBEAT_INTERVAL: int = _int(os.getenv("TERMINAL_HEARTBEAT_INTERVAL", "30"), 30)
    TERMINAL_LEASE_DURATION: int = _int(os.getenv("TERMINAL_LEASE_DURATION", "300"), 300)
    TERMINAL_MAX_SESSION_DURATION: int = _int(os.getenv("TERMINAL_MAX_SESSION_DURATION", "14400"), 14400)

    # Milestone 9: Multi-Strategy Engine
    MULTI_STRATEGY_ENABLED: bool = _bool(os.getenv("MULTI_STRATEGY_ENABLED", "true"), True)
    MAX_STRATEGIES_PER_SYMBOL: int = _int(os.getenv("MAX_STRATEGIES_PER_SYMBOL", "3"), 3)
    SIGNAL_AGREEMENT_THRESHOLD: int = _int(os.getenv("SIGNAL_AGREEMENT_THRESHOLD", "2"), 2)
    STRATEGY_SWITCH_COOLDOWN: int = _int(os.getenv("STRATEGY_SWITCH_COOLDOWN", "300"), 300)

    # Milestone 10: AI Validation Engine
    AI_VALIDATION_ENABLED: bool = _bool(os.getenv("AI_VALIDATION_ENABLED", "true"), True)
    AI_VALIDATION_MIN_CONFIDENCE: float = _float(os.getenv("AI_VALIDATION_MIN_CONFIDENCE", "0.60"), 0.60)
    AI_VALIDATION_MAX_RISK_FLAGS: int = _int(os.getenv("AI_VALIDATION_MAX_RISK_FLAGS", "3"), 3)
    AI_VALIDATION_TIMEOUT: float = _float(os.getenv("AI_VALIDATION_TIMEOUT", "30.0"), 30.0)
    AI_MAX_CALLS_PER_SESSION: int = _int(os.getenv("AI_MAX_CALLS_PER_SESSION", "100"), 100)

    # Milestone 11: Advanced Paper Trading
    PAPER_TRAILING_STOP: bool = _bool(os.getenv("PAPER_TRAILING_STOP", "true"), True)
    PAPER_BREAK_EVEN: bool = _bool(os.getenv("PAPER_BREAK_EVEN", "true"), True)
    PAPER_TRAILING_ACTIVATION: float = _float(os.getenv("PAPER_TRAILING_ACTIVATION", "0.01"), 0.01)
    PAPER_TRAILING_DISTANCE: float = _float(os.getenv("PAPER_TRAILING_DISTANCE", "0.005"), 0.005)
    PAPER_BREAK_EVEN_ACTIVATION: float = _float(os.getenv("PAPER_BREAK_EVEN_ACTIVATION", "0.005"), 0.005)

    # Milestone 13: Session/Heartbeat Control
    SESSION_MODE: str = os.getenv("SESSION_MODE", "paper")  # paper, demo, live
    SESSION_REQUIRE_FOREGROUND: bool = _bool(os.getenv("SESSION_REQUIRE_FOREGROUND", "true"), True)
    SESSION_AUTO_STOP_BACKGROUND: bool = _bool(os.getenv("SESSION_AUTO_STOP_BACKGROUND", "true"), True)
    SESSION_ALLOW_BACKGROUND_TRADING: bool = _bool(os.getenv("SESSION_ALLOW_BACKGROUND_TRADING", "false"), False)
    SESSION_LIVE_CONFIRMATION: bool = _bool(os.getenv("SESSION_LIVE_CONFIRMATION", "true"), True)
    SESSION_LIVE_MAX_DURATION: int = _int(os.getenv("SESSION_LIVE_MAX_DURATION", "3600"), 3600)

    # Milestone 14: Broker Adapter
    BROKER_ADAPTER: str = os.getenv("BROKER_ADAPTER", "paper")  # paper, mt5_demo, mt5_live
    BROKER_HEALTH_CHECK_INTERVAL: int = _int(os.getenv("BROKER_HEALTH_CHECK_INTERVAL", "60"), 60)

    # Milestone 15: Optional Hosted Worker
    HOSTED_WORKER_ENABLED: bool = _bool(os.getenv("HOSTED_WORKER_ENABLED", "false"), False)
    HOSTED_WORKER_URL: str = os.getenv("HOSTED_WORKER_URL", "")
    HOSTED_WORKER_AUTH_TOKEN: str = os.getenv("HOSTED_WORKER_AUTH_TOKEN", "")
    HOSTED_WORKER_HEARTBEAT: int = _int(os.getenv("HOSTED_WORKER_HEARTBEAT", "30"), 30)

    # Milestone 16: Live Trading Infrastructure (disabled by default)
    LIVE_INFRASTRUCTURE_ENABLED: bool = _bool(os.getenv("LIVE_INFRASTRUCTURE_ENABLED", "false"), False)
    LIVE_BROKER_ADAPTER: str = os.getenv("LIVE_BROKER_ADAPTER", "")
    LIVE_ACCOUNT_VERIFICATION: bool = _bool(os.getenv("LIVE_ACCOUNT_VERIFICATION", "true"), True)
    LIVE_RISK_PROFILE: str = os.getenv("LIVE_RISK_PROFILE", "conservative")  # conservative, moderate, aggressive
    LIVE_EMERGENCY_STOP_ENABLED: bool = _bool(os.getenv("LIVE_EMERGENCY_STOP_ENABLED", "true"), True)

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
        if cls.COINSPH_ENABLED and cls.LIVE_TRADING:
            errors.append("COINSPH_ENABLED and LIVE_TRADING cannot both be true")
        if cls.EXCHANGE == "coinsph" and cls.LIVE_TRADING:
            errors.append("EXCHANGE=coinsph with LIVE_TRADING=true is not allowed in paper-live mode")
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
            "COINSPH_ENABLED": cls.COINSPH_ENABLED,
            "COINSPH_API_BASE_URL": cls.COINSPH_API_BASE_URL,
            "M7_ENABLED": cls.M7_ENABLED,
            "M7_RISK_PERCENT": cls.M7_RISK_PERCENT,
            "TERMINAL_ENABLED": cls.TERMINAL_ENABLED,
            "MULTI_STRATEGY_ENABLED": cls.MULTI_STRATEGY_ENABLED,
            "AI_VALIDATION_ENABLED": cls.AI_VALIDATION_ENABLED,
            "PAPER_TRAILING_STOP": cls.PAPER_TRAILING_STOP,
            "SESSION_MODE": cls.SESSION_MODE,
            "BROKER_ADAPTER": cls.BROKER_ADAPTER,
            "HOSTED_WORKER_ENABLED": cls.HOSTED_WORKER_ENABLED,
            "LIVE_INFRASTRUCTURE_ENABLED": cls.LIVE_INFRASTRUCTURE_ENABLED,
            "LIVE_TRADING": cls.LIVE_TRADING,
        }
