import asyncio

import httpx

HEADERS = {"User-Agent": "cryptobot/1.0 (+telegram)"}


async def get_json(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 4):
    async with httpx.AsyncClient(timeout=20, headers={**HEADERS, **(headers or {})}, follow_redirects=True) as client:
        for attempt in range(retries):
            resp = await client.get(url, params=params)
            if resp.status_code == 429 and attempt < retries - 1:
                # Бесплатный CoinGecko быстро упирается в лимит — ждём, сколько просит сервер.
                retry_after = resp.headers.get("retry-after", "")
                await asyncio.sleep(min(float(retry_after), 60) if retry_after.isdigit() else 5 * 2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()


async def get_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
