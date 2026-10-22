"""Прогон сигналов бота по истории и расчёт метрик.

Каждый день сигнал считается только по данным, доступным на закрытие этого дня
(последние HISTORY_DAYS свечей — как в живом боте), без заглядывания в будущее.
Новостной фактор не участвует: архива новостей нет.
"""
import math
from dataclasses import dataclass, field

from ..analyzer import WEIGHTS, combine, market_signals, verdict

HISTORY_DAYS = 120   # столько истории бот берёт из CoinGecko
WARMUP = 100         # минимум для SMA100
HORIZONS = (1, 7, 30)
VERDICTS = ["АКТИВНО ПОКУПАТЬ", "ПОКУПАТЬ", "ДЕРЖАТЬ / ЖДАТЬ", "ПРОДАВАТЬ", "АКТИВНО ПРОДАВАТЬ"]


@dataclass
class Day:
    date: str
    close: float
    score: float
    factors: dict[str, float]


@dataclass
class StrategyResult:
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float
    trades: int
    win_rate: float | None
    exposure: float
    equity: list[float] = field(default_factory=list)


@dataclass
class CoinReport:
    symbol: str
    start: str
    end: str
    days: int
    buckets: dict[str, dict]       # вердикт -> {count, avg_N, hit_N}
    baseline: dict[str, float]     # средняя доходность за N дней по всем дням
    factor_ic: dict[str, float]    # корреляция фактора с доходностью за 7 дней
    strategy: StrategyResult
    buy_hold: StrategyResult


def score_history(candles: list[dict], fg_history: dict[str, dict], weights: dict = WEIGHTS) -> list[Day]:
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    days = []
    for t in range(WARMUP, len(candles)):
        lo = max(0, t + 1 - HISTORY_DAYS)
        signals = market_signals(closes[lo:t + 1], volumes[lo:t + 1], fg_history.get(candles[t]["date"]))
        days.append(Day(candles[t]["date"], closes[t], combine(signals, weights), {s.name: s.score for s in signals}))
    return days


def _fwd(days: list[Day], t: int, h: int) -> float | None:
    return days[t + h].close / days[t].close - 1 if t + h < len(days) else None


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / math.sqrt(vx * vy) if vx and vy else 0.0


def signal_quality(days: list[Day]) -> tuple[dict, dict]:
    """Средняя будущая доходность и доля верных направлений для каждого вердикта."""
    buckets = {v: {"count": 0} for v in VERDICTS}
    baseline = {}
    for h in HORIZONS:
        all_rets = [r for t in range(len(days)) if (r := _fwd(days, t, h)) is not None]
        baseline[f"avg_{h}"] = sum(all_rets) / len(all_rets) if all_rets else 0.0
    for v in VERDICTS:
        idx = [t for t, d in enumerate(days) if verdict(d.score) == v]
        buckets[v]["count"] = len(idx)
        for h in HORIZONS:
            rets = [r for t in idx if (r := _fwd(days, t, h)) is not None]
            buckets[v][f"avg_{h}"] = sum(rets) / len(rets) if rets else None
            if "ПОКУП" in v:
                hits = [r > 0 for r in rets]
            elif "ПРОДАВ" in v:
                hits = [r < 0 for r in rets]
            else:
                hits = []
            buckets[v][f"hit_{h}"] = sum(hits) / len(hits) if hits else None
    return buckets, baseline


def factor_ic(days: list[Day], horizon: int = 7) -> dict[str, float]:
    """Насколько каждый фактор в отдельности предсказывает доходность (корреляция Пирсона)."""
    result = {}
    for name in WEIGHTS:
        pairs = [(d.factors[name], r) for t, d in enumerate(days)
                 if name in d.factors and (r := _fwd(days, t, horizon)) is not None]
        if pairs:
            result[name] = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    return result


def _stats(equity: list[float], daily: list[float], trades: list[float], exposure: float) -> StrategyResult:
    years = len(daily) / 365
    total = equity[-1] / equity[0] - 1
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    mean = sum(daily) / len(daily) if daily else 0
    std = math.sqrt(sum((r - mean) ** 2 for r in daily) / len(daily)) if daily else 0
    return StrategyResult(
        total_return=total,
        cagr=(equity[-1] / equity[0]) ** (1 / years) - 1 if years > 0 and equity[-1] > 0 else -1.0,
        max_drawdown=mdd,
        sharpe=mean / std * math.sqrt(365) if std else 0.0,
        trades=len(trades),
        win_rate=sum(t > 0 for t in trades) / len(trades) if trades else None,
        exposure=exposure,
        equity=equity,
    )


def simulate(days: list[Day], buy: float = 15, sell: float = -15, fee: float = 0.001) -> StrategyResult:
    """Только покупки (без шортов): входим, когда оценка >= buy, выходим, когда <= sell.

    Решение принимается на закрытии дня t по сигналу дня t, доходность — с t до t+1.
    Комиссия fee списывается при каждом входе и выходе.
    """
    equity, daily, trades = [1.0], [], []
    in_pos, entry_eq, held = False, 1.0, 0
    for t in range(len(days) - 1):
        r = 0.0
        if not in_pos and days[t].score >= buy:
            in_pos, r, entry_eq = True, -fee, equity[-1]
        elif in_pos and days[t].score <= sell:
            in_pos, r = False, -fee
            trades.append(equity[-1] * (1 - fee) / entry_eq - 1)
        if in_pos:
            held += 1
            r = (1 + r) * (days[t + 1].close / days[t].close) - 1
        equity.append(equity[-1] * (1 + r))
        daily.append(r)
    if in_pos:
        trades.append(equity[-1] / entry_eq - 1)
    return _stats(equity, daily, trades, held / max(1, len(days) - 1))


def buy_and_hold(days: list[Day], fee: float = 0.001) -> StrategyResult:
    equity, daily = [1.0], []
    for t in range(len(days) - 1):
        r = days[t + 1].close / days[t].close - 1
        if t == 0:
            r = (1 - fee) * (1 + r) - 1
        equity.append(equity[-1] * (1 + r))
        daily.append(r)
    return _stats(equity, daily, [equity[-1] - 1], 1.0)


def run(symbol: str, candles: list[dict], fg_history: dict, buy: float = 15, sell: float = -15,
        fee: float = 0.001, start: str | None = None, weights: dict = WEIGHTS, end: str | None = None) -> CoinReport:
    days = score_history(candles, fg_history, weights)
    days = [d for d in days if (not start or d.date >= start) and (not end or d.date <= end)]
    if len(days) < 60:
        raise ValueError(f"{symbol}: слишком короткая история ({len(days)} дн.)")
    buckets, baseline = signal_quality(days)
    return CoinReport(
        symbol=symbol,
        start=days[0].date,
        end=days[-1].date,
        days=len(days),
        buckets=buckets,
        baseline=baseline,
        factor_ic=factor_ic(days),
        strategy=simulate(days, buy, sell, fee),
        buy_hold=buy_and_hold(days, fee),
    )
