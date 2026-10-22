import os
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WATCHLIST = [c.strip() for c in os.getenv(
    "WATCHLIST",
    "bitcoin,ethereum,solana,binancecoin,ripple,cardano,dogecoin,avalanche-2,chainlink,toncoin",
).split(",") if c.strip()]
DIGEST_HOUR_UTC = int(os.getenv("DIGEST_HOUR_UTC", "8"))
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
SUBSCRIBERS_FILE = Path(os.getenv("SUBSCRIBERS_FILE", "subscribers.json"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
BTC_FILTER_DAYS = int(os.getenv("BTC_FILTER_DAYS", "200"))  # 0 — фильтр рынка выключен
