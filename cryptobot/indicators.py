"""Технические индикаторы на чистом Python."""


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(values: list[float], period: int = 14) -> float | None:
    """RSI по Уайлдеру."""
    if len(values) <= period:
        return None
    deltas = [b - a for a, b in zip(values, values[1:])]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    if len(values) < slow + signal:
        return None
    fast_s = ema_series(values, fast)
    slow_s = ema_series(values, slow)
    line = [f - s for f, s in zip(fast_s[slow - fast:], slow_s)]
    signal_s = ema_series(line, signal)
    return {
        "macd": line[-1],
        "signal": signal_s[-1],
        "hist": line[-1] - signal_s[-1],
        "prev_hist": line[-2] - signal_s[-2] if len(signal_s) > 1 else None,
    }


def bollinger(values: list[float], period: int = 20, mult: float = 2.0) -> dict | None:
    if len(values) < period:
        return None
    window = values[-period:]
    mid = sum(window) / period
    std = (sum((v - mid) ** 2 for v in window) / period) ** 0.5
    upper, lower = mid + mult * std, mid - mult * std
    pos = (values[-1] - lower) / (upper - lower) if upper != lower else 0.5
    return {"upper": upper, "mid": mid, "lower": lower, "position": pos}


def volatility(values: list[float], period: int = 30) -> float | None:
    """Стандартное отклонение дневной доходности, %."""
    if len(values) <= period:
        return None
    rets = [(b / a - 1) for a, b in zip(values[-period - 1:], values[-period:])]
    mean = sum(rets) / len(rets)
    return (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 * 100
