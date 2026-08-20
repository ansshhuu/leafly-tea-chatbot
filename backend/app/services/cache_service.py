import time

TTL_SECONDS = 60 * 60

_cache: dict[str, tuple[float, dict]] = {}


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def get_cached(query: str) -> dict | None:
    key = _normalize(query)
    entry = _cache.get(key)
    if entry is None:
        return None

    expires_at, value = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None

    return value


def set_cached(query: str, value: dict) -> None:
    key = _normalize(query)
    _cache[key] = (time.monotonic() + TTL_SECONDS, value)


def clear() -> None:
    _cache.clear()
