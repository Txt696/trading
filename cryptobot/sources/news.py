"""Новости из RSS-лент крипто-СМИ и простой анализ их тональности."""
import asyncio
import re

import feedparser

from ..cache import async_ttl_cache
from .http import get_text

FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/.rss/full/",
}

POSITIVE = {
    "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains", "jump", "jumps",
    "bull", "bullish", "record", "high", "approval", "approved", "adoption", "inflow", "inflows",
    "partnership", "launch", "launches", "upgrade", "breakout", "rebound", "recover", "recovers",
    "buy", "accumulate", "accumulation", "etf", "institutional", "boost", "outperform",
}
NEGATIVE = {
    "crash", "crashes", "plunge", "plunges", "drop", "drops", "fall", "falls", "slump", "bear",
    "bearish", "hack", "hacked", "exploit", "scam", "fraud", "lawsuit", "sue", "sues", "ban",
    "bans", "outflow", "outflows", "liquidation", "liquidations", "sell-off", "selloff", "dump",
    "decline", "declines", "warning", "risk", "investigation", "delist", "delisted", "low",
}
_WORD = re.compile(r"[a-z\-]+")


def sentiment(text: str) -> int:
    words = _WORD.findall(text.lower())
    return sum(w in POSITIVE for w in words) - sum(w in NEGATIVE for w in words)


async def _fetch(source: str, url: str) -> list[dict]:
    try:
        parsed = feedparser.parse(await get_text(url))
    except Exception:
        return []
    return [{
        "source": source,
        "title": e.get("title", ""),
        "summary": re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:500],
        "link": e.get("link", ""),
    } for e in parsed.entries[:30]]


@async_ttl_cache(ttl=900)
async def all_news() -> list[dict]:
    results = await asyncio.gather(*(_fetch(s, u) for s, u in FEEDS.items()))
    return [item for feed in results for item in feed]


def _mentions(item: dict, keywords: list[str]) -> bool:
    text = f"{item['title']} {item['summary']}".lower()
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keywords)


async def coin_news(name: str, symbol: str) -> dict:
    """Новости по монете и их суммарная тональность от -1 до 1."""
    keywords = [name, symbol] if len(symbol) > 2 else [name]
    items = [n for n in await all_news() if _mentions(n, keywords)]
    scores = [sentiment(f"{n['title']} {n['summary']}") for n in items]
    for n, s in zip(items, scores):
        n["sentiment"] = s
    signed = [max(-1, min(1, s)) for s in scores]
    return {
        "items": items,
        "score": sum(signed) / len(signed) if signed else 0.0,
        "count": len(items),
        "sources": sorted({n["source"] for n in items}),
    }
