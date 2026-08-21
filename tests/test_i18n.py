import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Field, SQLModel

from pyron import Pyron
from pyron.admin.i18n import Translator, parse_accept_language, resolve_locale, resolve_theme
from pyron.db import create_engine, init_db


class Flag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = ""


def test_accept_language_and_cookie():
    assert parse_accept_language("es-MX,es;q=0.9,en;q=0.8") == "es"
    assert parse_accept_language("pt-BR,pt;q=0.9") == "pt"
    assert parse_accept_language("fr") == "fr"
    assert resolve_locale("es", "en-US") == "es"
    assert resolve_locale(None, "en-US,en;q=0.9") == "en"
    assert resolve_theme(None) == "system"
    assert resolve_theme("dark") == "dark"
    assert Translator("es")("sign_in") == "Entrar"
    assert Translator("en")("sign_in") == "Sign in"


@pytest.mark.asyncio
async def test_login_page_follows_accept_language_and_prefs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'i18n.db'}")
    init_db(engine)
    app = Pyron(title="i18n", admin=True, admin_engine=engine, docs_url=None, redoc_url=None)
    app.admin.register(Flag)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        es = await client.get("/admin/setup", headers={"Accept-Language": "es"})
        assert es.status_code == 200
        assert 'lang="es"' in es.text
        assert "Crear la cuenta root" in es.text
        assert "Sistema" in es.text
        assert 'data-theme="system"' in es.text
        assert 'role="radiogroup"' in es.text
        assert "toggle-thumb" in es.text
        assert "desk.css?v=" in es.text
        assert "desk.js?v=" in es.text
        assert 'data-pref="lang"' in es.text
        assert 'data-pref="theme"' in es.text

        switched = await client.get(
            "/admin/prefs?lang=fr&theme=dark&next=/admin/setup", follow_redirects=True
        )
        assert switched.status_code == 200
        assert 'lang="fr"' in switched.text
        assert "Créer le compte root" in switched.text
        assert 'data-theme="dark"' in switched.text

        live = await client.get(
            "/admin/prefs?theme=light",
            headers={"X-Pyron-Prefs": "1"},
        )
        assert live.status_code == 204
        assert "pyron_theme" in live.headers.get("set-cookie", "")
