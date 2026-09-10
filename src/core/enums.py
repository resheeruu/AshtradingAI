"""Shared enumerations for the AshtradingAI platform."""
import enum


class TradingMode(enum.Enum):
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    PAPER_LIVE = "PAPER_LIVE"
    MT5_DEMO = "MT5_DEMO"
    LIVE_LOCKED = "LIVE_LOCKED"

    @property
    def allows_execution(self) -> bool:
        return self in (TradingMode.PAPER, TradingMode.PAPER_LIVE, TradingMode.MT5_DEMO)

    @property
    def is_live_data(self) -> bool:
        return self in (TradingMode.PAPER_LIVE, TradingMode.MT5_DEMO)

    @property
    def requires_broker(self) -> bool:
        return self in (TradingMode.MT5_DEMO,)


class MarketHealthStatus(enum.Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    INVALID = "INVALID"
    RECOVERING = "RECOVERING"


class AssetClass(enum.Enum):
    FOREX = "FOREX"
    METALS = "METALS"
    INDICES = "INDICES"
    ENERGY = "ENERGY"
    CRYPTO = "CRYPTO"
    OTHER = "OTHER"


class SignalDirection(enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class OrderSide(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(enum.Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class RiskGate(enum.Enum):
    MODE = "MODE"
    MARKET_HEALTH = "MARKET_HEALTH"
    SYMBOL = "SYMBOL"
    SESSION = "SESSION"
    SPREAD = "SPREAD"
    VOLATILITY = "VOLATILITY"
    RISK_REWARD = "RISK_REWARD"
    POSITION_SIZE = "POSITION_SIZE"
    EXPOSURE = "EXPOSURE"
    CORRELATION = "CORRELATION"
    DAILY_LOSS = "DAILY_LOSS"
    DRAWDOWN = "DRAWDOWN"
    MARGIN = "MARGIN"
    TRADE_FREQUENCY = "TRADE_FREQUENCY"
    COOLDOWN = "COOLDOWN"
    KILL_SWITCH = "KILL_SWITCH"
    WEEKEND = "WEEKEND"


class RegimeType(enum.Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    UNCERTAIN = "UNCERTAIN"


class Timeframe(enum.Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def minutes(self) -> int:
        mapping = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 60, "H4": 240, "D1": 1440,
        }
        return mapping[self.value]

    @classmethod
    def from_string(cls, s: str) -> "Timeframe":
        try:
            return cls(s.upper())
        except ValueError:
            return cls.H1


class WatchdogStatus(enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class AIProviderStatus(enum.Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    FALLBACK = "FALLBACK"
    UNAVAILABLE = "UNAVAILABLE"
