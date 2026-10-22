"""Объединяет сигналы из всех источников в итоговую оценку монеты.

Каждый фактор даёт вклад в диапазоне примерно [-w, +w], где w — его вес.
Сумма нормируется в шкалу от -100 до +100.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from . import indicators as ind
from .config import BTC_FILTER_DAYS
from .sources import coingecko, fear_greed, news

log = logging.getLogger(__name__)

# Вердикт, когда BTC ниже своей долгосрочной средней. В бэктесте выход из всех монет
# в такие периоды заметно снижал просадки (python -m cryptobot.backtest --btc-filter 200).
BEAR_VERDICT = "ВНЕ РЫНКА"

WEIGHTS = {
    "trend": 25,      # положение цены относительно EMA20/EMA50/SMA100
    "momentum": 20,   # MACD
    "rsi": 15,        # перекупленность / перепроданность
    "bollinger": 10,  # положение в канале Боллинджера
    "volume": 10,     # подтверждение движения объёмом
    "news": 10,       # тональность новостей
    "sentiment": 10,  # индекс страха и жадности (контрарный)
}


@dataclass
class Signal:
    name: str
    score: float  # от -1 до 1
    note: str


@dataclass
class Analysis:
    coin_id: str
    name: str
    symbol: str
    price: float
    change_24h: float | None
    change_7d: float | None
    change_30d: float | None
    market_cap_rank: int | None
    score: float
    verdict: str
    confidence: str
    signals: list[Signal] = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    headlines: list[dict] = field(default_factory=list)
    news_sources: list[str] = field(default_factory=list)
    news_summary: str | None = None
    regime: dict | None = None


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def trend_signal(prices: list[float]) -> Signal | None:
    price = prices[-1]
    e20, e50, s100 = ind.ema(prices, 20), ind.ema(prices, 50), ind.sma(prices, 100)
    if e20 is None or e50 is None:
        return None
    parts = [1 if price > e20 else -1, 1 if price > e50 else -1, 1 if e20 > e50 else -1]
    if s100 is not None:
        parts.append(1 if price > s100 else -1)
    score = sum(parts) / len(parts)
    if score >= 0.5:
        note = "восходящий тренд: цена выше скользящих средних"
    elif score <= -0.5:
        note = "нисходящий тренд: цена ниже скользящих средних"
    else:
        note = "тренд не выражен, цена между скользящими средними"
    return Signal("trend", score, note)


def momentum_signal(prices: list[float]) -> Signal | None:
    m = ind.macd(prices)
    if m is None:
        return None
    rel = m["hist"] / prices[-1] * 100  # гистограмма в % от цены
    score = _clamp(rel / 1.5)
    if m["prev_hist"] is not None and (m["prev_hist"] < 0) != (m["hist"] < 0):
        cross = "бычье" if m["hist"] > 0 else "медвежье"
        return Signal("momentum", _clamp(score + (0.5 if m["hist"] > 0 else -0.5)), f"MACD: свежее {cross} пересечение")
    return Signal("momentum", score, f"MACD {'выше' if m['hist'] > 0 else 'ниже'} сигнальной линии")


def rsi_signal(prices: list[float]) -> Signal | None:
    r = ind.rsi(prices)
    if r is None:
        return None
    if r < 30:
        return Signal("rsi", (30 - r) / 15 + 0.3, f"RSI {r:.0f} — перепроданность, возможен отскок")
    if r > 70:
        return Signal("rsi", -((r - 70) / 15 + 0.3), f"RSI {r:.0f} — перекупленность, риск коррекции")
    return Signal("rsi", (r - 50) / 50, f"RSI {r:.0f} — нейтральная зона")


def bollinger_signal(prices: list[float]) -> Signal | None:
    b = ind.bollinger(prices)
    if b is None:
        return None
    pos = b["position"]
    if pos < 0.1:
        return Signal("bollinger", 0.7, "цена у нижней границы Боллинджера")
    if pos > 0.9:
        return Signal("bollinger", -0.7, "цена у верхней границы Боллинджера")
    return Signal("bollinger", (0.5 - pos) * 0.6, f"цена внутри канала Боллинджера ({pos:.0%})")


def volume_signal(prices: list[float], volumes: list[float]) -> Signal | None:
    if len(volumes) < 31 or len(prices) < 8:
        return None
    recent = sum(volumes[-7:]) / 7
    base = sum(volumes[-31:-1]) / 30
    if base == 0:
        return None
    ratio = recent / base
    direction = 1 if prices[-1] > prices[-8] else -1
    if ratio > 1.2:
        return Signal("volume", _clamp(direction * (ratio - 1)),
                      f"объём вырос в {ratio:.1f}× и подтверждает {'рост' if direction > 0 else 'падение'}")
    if ratio < 0.8:
        return Signal("volume", -direction * 0.2, f"объём упал ({ratio:.1f}× от среднего) — движение слабое")
    return Signal("volume", 0.0, "объём на среднем уровне")


IMPACT_SCALE = {"low": 0.4, "medium": 0.75, "high": 1.0}
IMPACT_RU = {"low": "слабое", "medium": "среднее", "high": "сильное"}


def news_signal(coin_news: dict) -> Signal:
    if coin_news["count"] == 0:
        return Signal("news", 0.0, "свежих новостей не найдено")
    v = coin_news.get("ai")
    if v is not None:
        score = _clamp(v.sentiment * IMPACT_SCALE[v.impact])
        mood = "позитивный" if score > 0.15 else "негативный" if score < -0.15 else "нейтральный"
        return Signal("news", score,
                      f"ИИ: фон {mood}, влияние {IMPACT_RU[v.impact]} "
                      f"({v.relevant_count} из {coin_news['count']} новостей по делу)")
    s = coin_news["score"]
    mood = "позитивный" if s > 0.15 else "негативный" if s < -0.15 else "нейтральный"
    return Signal("news", _clamp(s * 1.5), f"{coin_news['count']} новостей, фон {mood}")


def sentiment_signal(fg: dict | None) -> Signal | None:
    if not fg:
        return None
    v = fg["value"]
    # Контрарный подход: крайний страх — возможность, крайняя жадность — риск.
    score = _clamp((50 - v) / 40)
    return Signal("sentiment", score, f"индекс страха и жадности: {v} ({fg['label']})")


def market_signals(prices: list[float], volumes: list[float], fg: dict | None) -> list[Signal]:
    """Все факторы, кроме новостей. Используется и ботом, и бэктестом."""
    return [s for s in (
        trend_signal(prices),
        momentum_signal(prices),
        rsi_signal(prices),
        bollinger_signal(prices),
        volume_signal(prices, volumes),
        sentiment_signal(fg),
    ) if s is not None]


def combine(signals: list[Signal], weights: dict[str, float] = WEIGHTS) -> float:
    used = [s for s in signals if s is not None]
    total_w = sum(weights.get(s.name, 0) for s in used)
    if not total_w:
        return 0.0
    return sum(_clamp(s.score) * weights.get(s.name, 0) for s in used) / total_w * 100


def verdict(score: float) -> str:
    if score >= 45:
        return "АКТИВНО ПОКУПАТЬ"
    if score >= 15:
        return "ПОКУПАТЬ"
    if score > -15:
        return "ДЕРЖАТЬ / ЖДАТЬ"
    if score > -45:
        return "ПРОДАВАТЬ"
    return "АКТИВНО ПРОДАВАТЬ"


def apply_regime(v: str, regime: dict | None) -> str:
    """В медвежьем режиме покупки запрещены: «покупать» и «держать» превращаются в «вне рынка»."""
    if regime and not regime["bullish"] and "ПРОДАВ" not in v:
        return BEAR_VERDICT
    return v


async def btc_regime() -> dict | None:
    """Фильтр рынка: выше ли BTC своей BTC_FILTER_DAYS-дневной средней."""
    if BTC_FILTER_DAYS <= 0:
        return None
    try:
        prices = (await coingecko.history("bitcoin", days=365))["prices"]
    except Exception:
        log.warning("BTC regime unavailable", exc_info=True)
        return None
    sma = ind.sma(prices, BTC_FILTER_DAYS)
    if sma is None:
        return None
    return {"bullish": prices[-1] > sma, "price": prices[-1], "sma": sma,
            "distance": prices[-1] / sma - 1, "days": BTC_FILTER_DAYS}


def confidence(signals: list[Signal], score: float) -> str:
    """Уверенность — насколько факторы согласны с итоговым направлением."""
    directional = [s for s in signals if abs(s.score) > 0.1]
    if not directional or abs(score) < 15:
        return "низкая"
    agree = sum((s.score > 0) == (score > 0) for s in directional) / len(directional)
    return "высокая" if agree >= 0.8 else "средняя" if agree >= 0.6 else "низкая"


async def analyze(coin_id: str, market: dict | None = None) -> Analysis:
    hist, fg, regime, mkts = await asyncio.gather(
        coingecko.history(coin_id),
        fear_greed.fear_greed(),
        btc_regime(),
        coingecko.markets((coin_id,)) if market is None else asyncio.sleep(0, [market]),
    )
    if not mkts:
        raise ValueError(f"Нет рыночных данных для {coin_id}")
    m = mkts[0]
    prices, volumes = list(hist["prices"]), hist["volumes"]
    if len(prices) < 30:
        raise ValueError("Слишком короткая история цен для анализа")
    prices[-1] = m["current_price"]  # самая свежая цена

    cn = await news.coin_news(m["name"], m["symbol"])
    signals = market_signals(prices, volumes, fg)
    signals.insert(5, news_signal(cn))
    score = combine(signals)

    vol = ind.volatility(prices) or 0
    price = prices[-1]
    # Ожидаемый недельный диапазон (±1σ); стоп ~2σ и цель ~3σ — для сигналов на покупку.
    weekly = vol / 100 * (7 ** 0.5)
    risk = {
        "volatility": vol,
        "range_low": price * (1 - weekly),
        "range_high": price * (1 + weekly),
        "stop_loss": price * (1 - 2 * weekly),
        "take_profit": price * (1 + 3 * weekly),
    }

    return Analysis(
        coin_id=coin_id,
        name=m["name"],
        symbol=m["symbol"].upper(),
        price=price,
        change_24h=m.get("price_change_percentage_24h_in_currency"),
        change_7d=m.get("price_change_percentage_7d_in_currency"),
        change_30d=m.get("price_change_percentage_30d_in_currency"),
        market_cap_rank=m.get("market_cap_rank"),
        score=score,
        verdict=apply_regime(verdict(score), regime),
        confidence=confidence(signals, score),
        signals=signals,
        risk=risk,
        headlines=_headlines(cn),
        news_sources=cn["sources"],
        news_summary=cn["ai"].summary if cn["ai"] else None,
        regime=regime,
    )


def _headlines(cn: dict) -> list[dict]:
    """Ключевые события от ИИ, а без него — новости с самой яркой тональностью."""
    items = cn["items"]
    if cn["ai"]:
        picked = []
        for e in cn["ai"].key_events:
            if 0 <= e.index < len(items):
                picked.append({**items[e.index], "title": e.title, "impact": e.impact})
        if picked:
            return picked[:3]
    return sorted(items, key=lambda n: -abs(n["sentiment"]))[:3]


async def analyze_many(coin_ids: list[str]) -> list[Analysis]:
    mkts = {m["id"]: m for m in await coingecko.markets(tuple(coin_ids))}
    results = []
    for cid in coin_ids:  # последовательно, чтобы не превысить лимиты CoinGecko
        if cid not in mkts:
            continue
        try:
            results.append(await analyze(cid, mkts[cid]))
        except Exception:
            continue
    return sorted(results, key=lambda a: a.score, reverse=True)
