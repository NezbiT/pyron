import pytest
from httpx import ASGITransport, AsyncClient

from pyron import Pyron
from pyron.security import LoginThrottle, password_issues
from pyron.settings import load_settings


def test_password_policy():
    assert password_issues("short") 
    assert password_issues("password1")
    assert password_issues("alicealice", username="alicealice")
    assert not password_issues("correct-horse-battery")


def test_throttle_lockout():
    from pyron.cache import reset_cache

    reset_cache()
    box = LoginThrottle(max_fails=3, window=60)
    assert not box.blocked("1.1.1.1")
    box.fail("1.1.1.1")
    box.fail("1.1.1.1")
    box.fail("1.1.1.1")
    assert box.blocked("1.1.1.1")
    box.success("1.1.1.1")
    assert not box.blocked("1.1.1.1")


@pytest.mark.asyncio
async def test_security_headers_on_api():
    app = Pyron(title="sec", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.headers.get("x-frame-options") == "DENY"
        assert r.headers.get("x-content-type-options") == "nosniff"


def test_dev_settings_expose_docs(monkeypatch):
    monkeypatch.setenv("PYRON_ENV", "dev")
    monkeypatch.delenv("PYRON_EXPOSE_DOCS", raising=False)
    monkeypatch.delenv("PYRON_DEBUG", raising=False)
    cfg = load_settings()
    assert cfg.debug is True
    assert cfg.expose_docs is True
    assert cfg.production is False
