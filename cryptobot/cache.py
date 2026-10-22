import time
from functools import wraps

from .config import CACHE_TTL_SECONDS


def async_ttl_cache(ttl: int = CACHE_TTL_SECONDS):
    """Кэширует результаты async-функций, чтобы не упираться в лимиты API."""
    def decorator(func):
        store: dict = {}

        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            hit = store.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            result = await func(*args, **kwargs)
            if result is not None:  # неудачи не кэшируем, чтобы повторить при следующем запросе
                store[key] = (time.monotonic(), result)
            return result

        return wrapper
    return decorator
