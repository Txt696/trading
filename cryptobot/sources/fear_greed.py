"""Индекс страха и жадности (alternative.me)."""
from ..cache import async_ttl_cache
from .http import get_json


@async_ttl_cache(ttl=1800)
async def fear_greed() -> dict | None:
    data = await get_json("https://api.alternative.me/fng/", {"limit": 7})
    items = data.get("data") or []
    if not items:
        return None
    values = [int(i["value"]) for i in items]
    return {
        "value": values[0],
        "label": items[0]["value_classification"],
        "week_avg": sum(values) / len(values),
    }
