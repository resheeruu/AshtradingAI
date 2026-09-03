"""Technical indicators using pure Python (no numpy/pandas)."""
import math
from typing import List, Optional


def sma(data: List[float], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(data)
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1 : i + 1]) / period
    return result


def ema(data: List[float], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(data)
    if len(data) < period:
        return result
    k = 2 / (period + 1)
    result[period - 1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(data)
    if len(data) < period + 1:
        return result

    gains = []
    losses = []
    for i in range(1, len(data)):
        delta = data[i] - data[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = 100 - 100 / (1 + avg_gain / avg_loss)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            result[i + 1] = 100 - 100 / (1 + avg_gain / avg_loss)
    return result


def macd(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)
    macd_line: List[Optional[float]] = [None] * len(data)
    for i in range(len(data)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    macd_vals = [v for v in macd_line if v is not None]
    signal_line = ema(macd_vals, signal) if len(macd_vals) >= signal else [None] * len(macd_vals)
    histogram: List[Optional[float]] = [None] * len(data)

    j = 0
    for i in range(len(data)):
        if macd_line[i] is not None:
            if j < len(signal_line) and signal_line[j] is not None:
                histogram[i] = macd_line[i] - signal_line[j]
            j += 1

    return macd_line, signal_line, histogram


def atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(close)
    if len(close) < period + 1:
        return result

    trs: List[float] = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        trs.append(tr)

    if len(trs) < period:
        return result

    atr_val = sum(trs[:period]) / period
    result[period] = atr_val
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        result[i + 1] = atr_val
    return result


def bollinger_bands(data: List[float], period: int = 20, std_dev: float = 2.0):
    middle = sma(data, period)
    upper: List[Optional[float]] = [None] * len(data)
    lower: List[Optional[float]] = [None] * len(data)

    for i in range(period - 1, len(data)):
        window = data[i - period + 1 : i + 1]
        mean = middle[i]
        if mean is None:
            continue
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mean + std_dev * std
        lower[i] = mean - std_dev * std
    return upper, middle, lower


def compute_all_indicators(candles: List[dict]) -> dict:
    """Compute all indicators from a list of candle dicts. Returns dict of indicator lists."""
    close = [c["close"] for c in candles]
    high = [c["high"] for c in candles]
    low = [c["low"] for c in candles]
    volume = [c["volume"] for c in candles]

    macd_line, signal_line, histogram = macd(close)

    return {
        "sma_20": sma(close, 20),
        "sma_50": sma(close, 50),
        "ema_12": ema(close, 12),
        "ema_26": ema(close, 26),
        "rsi_14": rsi(close, 14),
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_hist": histogram,
        "atr_14": atr(high, low, close, 14),
        "bb_upper": bollinger_bands(close)[0],
        "bb_middle": bollinger_bands(close)[1],
        "bb_lower": bollinger_bands(close)[2],
        "vol_sma_20": sma(volume, 20),
    }
