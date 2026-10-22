"""CoinGecko: цены, капитализация, история, тренды, глобальные данные рынка."""
from ..cache import async_ttl_cache
from ..config import COINGECKO_API_KEY
from .http import get_json

BASE = "https://api.coingecko.com/api/v3"


def _headers() -> dict:
    return {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}


@async_ttl_cache()
async def markets(ids: tuple[str, ...]) -> list[dict]:
    return await get_json(f"{BASE}/coins/markets", {
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "price_change_percentage": "1h,24h,7d,30d",
    }, _headers())


@async_ttl_cache()
async def history(coin_id: str, days: int = 120) -> dict:
    """Дневные цены и объёмы: {'prices': [...], 'volumes': [...]}"""
    data = await get_json(f"{BASE}/coins/{coin_id}/market_chart", {
        "vs_currency": "usd", "days": days, "interval": "daily",
    }, _headers())
    return {
        "prices": [p[1] for p in data.get("prices", [])],
        "volumes": [v[1] for v in data.get("total_volumes", [])],
    }


@async_ttl_cache()
async def trending() -> list[dict]:
    data = await get_json(f"{BASE}/search/trending", headers=_headers())
    return [c["item"] for c in data.get("coins", [])]


@async_ttl_cache()
async def global_data() -> dict:
    data = await get_json(f"{BASE}/global", headers=_headers())
    return data.get("data", {})


@async_ttl_cache(ttl=24 * 3600)
async def resolve_coin(query: str) -> dict | None:
    """Находит монету по тикеру, названию или id (btc, Bitcoin, bitcoin)."""
    q = query.strip().lower()
    data = await get_json(f"{BASE}/search", {"query": q}, _headers())
    coins = data.get("coins", [])
    if not coins:
        return None
    # Точное совпадение тикера/id важнее; среди них — самая крупная монета.
    exact = [c for c in coins if q in (c["symbol"].lower(), c["id"], c["name"].lower())]
    pool = exact or coins
    return min(pool, key=lambda c: c.get("market_cap_rank") or 10**9)
