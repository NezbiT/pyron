from pyron.cache import Cache, MemoryBackend, get_cache, reset_cache
from pyron.security import LoginThrottle


def test_memory_cache_ttl():
    box = Cache(MemoryBackend())
    box.set("k", "v", ttl=60)
    assert box.get("k") == "v"
    box.delete("k")
    assert box.get("k") is None
    assert box.incr("n") == 1
    assert box.incr("n") == 2


def test_module_cache_and_throttle(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    reset_cache()
    from pyron import cache

    cache.set("quote", "ok")
    assert cache.get("quote") == "ok"
    box = LoginThrottle(max_fails=2, window=60)
    assert not box.blocked("9.9.9.9")
    box.fail("9.9.9.9")
    box.fail("9.9.9.9")
    assert box.blocked("9.9.9.9")
    box.success("9.9.9.9")
    assert not box.blocked("9.9.9.9")
    reset_cache()
