"""Исторические данные для бэктеста: дневные свечи OKX и индекс страха и жадности.

Данные кэшируются на диск, чтобы повторные прогоны не ходили в сеть.
"""
import asyncio
import datetime as dt
import json
import time
from pathlib import Path

from ..sources.http import get_json

CACHE_DIR = Path(".cache/backtest")
CACHE_TTL = 12 * 3600


def _load(path: Path):
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        return json.loads(path.read_text())
    return None


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


async def candles(symbol: str) -> list[dict]:
    """Все закрытые дневные свечи пары SYMBOL-USDT от старых к новым: date, close, volume (в USDT)."""
    symbol = symbol.upper()
    path = CACHE_DIR / f"{symbol}.json"
    if (cached := _load(path)) is not None:
        return cached
    rows, after = [], None
    while True:
        params = {"instId": f"{symbol}-USDT", "bar": "1Dutc", "limit": 100}
        if after:
            params["after"] = after
        data = await get_json("https://www.okx.com/api/v5/market/history-candles", params)
        if data.get("code") != "0":
            raise ValueError(f"OKX: {data.get('msg') or 'нет такой пары'} ({symbol}-USDT)")
        batch = data["data"]
        if not batch:
            break
        rows += batch
        after = batch[-1][0]
        await asyncio.sleep(0.15)  # лимит OKX — 20 запросов за 2 секунды
    result = [{
        "date": dt.datetime.fromtimestamp(int(r[0]) / 1000, dt.timezone.utc).date().isoformat(),
        "close": float(r[4]),
        "volume": float(r[7]),
    } for r in reversed(rows) if r[8] == "1"]
    _save(path, result)
    return result


async def fear_greed_history() -> dict[str, dict]:
    """Индекс страха и жадности по датам: {'2024-01-31': {'value': 63, 'label': 'Greed', 'week_avg': ...}}."""
    path = CACHE_DIR / "fear_greed.json"
    if (cached := _load(path)) is not None:
        return cached
    data = await get_json("https://api.alternative.me/fng/", {"limit": 0})
    items = sorted(data["data"], key=lambda i: int(i["timestamp"]))
    result, window = {}, []
    for i in items:
        date = dt.datetime.fromtimestamp(int(i["timestamp"]), dt.timezone.utc).date().isoformat()
        window = (window + [int(i["value"])])[-7:]
        result[date] = {"value": int(i["value"]), "label": i["value_classification"],
                        "week_avg": sum(window) / len(window)}
    _save(path, result)
    return result
