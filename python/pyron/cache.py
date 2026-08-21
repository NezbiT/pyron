"""Cache: Redis when REDIS_URL is set, otherwise process memory."""

from __future__ import annotations

import json
import time
from typing import Any

from pyron.settings import load_settings

_CACHE: "Cache | None" = None


def redis_client(url: str | None = None, **kwargs: Any):
    settings = load_settings()
    url = url if url is not None else settings.redis_url
    if not url:
        return None
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Redis support needs redis. Install with: pip install pyron[redis]") from exc
    return redis.Redis.from_url(url, decode_responses=True, **kwargs)


class MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, exp = item
        if exp is not None and exp < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        exp = time.time() + ttl if ttl else None
        self._data[key] = (value, exp)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def incr(self, key: str, amount: int = 1) -> int:
        current = self.get(key)
        n = int(current or 0) + amount
        _, exp = self._data.get(key, (None, None))
        ttl = int(exp - time.time()) if exp else None
        self.set(key, n, ttl=ttl if ttl and ttl > 0 else None)
        return n


class RedisBackend:
    def __init__(self, client: Any) -> None:
        self.client = client

    def get(self, key: str) -> Any | None:
        raw = self.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value)
        if ttl:
            self.client.setex(key, int(ttl), payload)
        else:
            self.client.set(key, payload)

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def incr(self, key: str, amount: int = 1) -> int:
        return int(self.client.incrby(key, amount))


class Cache:
    def __init__(self, backend: Any | None = None) -> None:
        self.backend = backend or MemoryBackend()

    def get(self, key: str) -> Any | None:
        return self.backend.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.backend.set(key, value, ttl=ttl)

    def delete(self, key: str) -> None:
        self.backend.delete(key)

    def incr(self, key: str, amount: int = 1) -> int:
        return self.backend.incr(key, amount)


def get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        _CACHE = build_cache()
    return _CACHE


def build_cache(url: str | None = None) -> Cache:
    settings = load_settings()
    target = url if url is not None else settings.redis_url
    if not target:
        return Cache(MemoryBackend())
    client = redis_client(target)
    if client is None:
        return Cache(MemoryBackend())
    return Cache(RedisBackend(client))


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


class _CacheProxy:
    """Module-level `cache` always uses the current backend (Redis or memory)."""

    def get(self, key: str) -> Any | None:
        return get_cache().get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        get_cache().set(key, value, ttl=ttl)

    def delete(self, key: str) -> None:
        get_cache().delete(key)

    def incr(self, key: str, amount: int = 1) -> int:
        return get_cache().incr(key, amount)


cache = _CacheProxy()
