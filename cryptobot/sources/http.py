import asyncio

import httpx

HEADERS = {"User-Agent": "cryptobot/1.0 (+telegram)"}


async def get_json(url: str, params: dict | None = None, headers: dict | None = None, retries: int = 3):
    async with httpx.AsyncClient(timeout=20, headers={**HEADERS, **(headers or {})}, follow_redirects=True) as client:
        for attempt in range(retries):
            resp = await client.get(url, params=params)
            if resp.status_code == 429 and attempt < retries - 1:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()


async def get_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
