import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from pyron import BackgroundTasks, Pyron
from pyron.checks import run_checks
from pyron.cli import app as cli


runner = CliRunner()


def test_startapp_writes_package(tmp_path):
    result = runner.invoke(cli, ["startapp", "catalog", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "catalog"
    assert (pkg / "models.py").is_file()
    assert (pkg / "routes.py").is_file()
    assert (pkg / "admin.py").is_file()
    text = (pkg / "routes.py").read_text(encoding="utf-8")
    assert "APIRouter" in text
    assert "/catalog" in text


def test_include_app_mounts_routes(tmp_path, monkeypatch):
    result = runner.invoke(cli, ["startapp", "catalog", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    monkeypatch.syspath_prepend(str(tmp_path))
    app = Pyron(title="Shop", docs_url=None, redoc_url=None)
    app.include_app("catalog")
    assert any(r.path == "/catalog/health" for r in app.routes)


def test_url_for_named_routes():
    app = Pyron(title="Urls", docs_url=None, redoc_url=None)

    @app.get("/books/{book_id}", name="book")
    async def book(book_id: int):
        return {"id": book_id}

    assert app.url_for("book", book_id=7) == "/books/7"
    with pytest.raises(KeyError):
        app.url_for("missing")
    with pytest.raises(KeyError):
        app.url_for("book")


@pytest.mark.asyncio
async def test_background_tasks_run_after_response():
    ran: list[int] = []
    app = Pyron(title="Bg", docs_url=None, redoc_url=None)

    @app.post("/ping")
    async def ping(background: BackgroundTasks):
        background.add_task(ran.append, 1)
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/ping")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    assert ran == [1]


@pytest.mark.asyncio
async def test_templates_url_for(tmp_path):
    (tmp_path / "hi.html").write_text('<a href="{{ url_for("book", book_id=3) }}">x</a>', encoding="utf-8")
    app = Pyron(title="Tpl", templates=str(tmp_path), docs_url=None, redoc_url=None)

    @app.get("/books/{book_id}", name="book")
    async def book(book_id: int):
        return {"id": book_id}

    @app.get("/page")
    async def page(request):
        return await app.render(request, "hi.html")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/page")
        assert r.status_code == 200
        assert 'href="/books/3"' in r.text


def test_check_deploy_flags_debug(tmp_path, monkeypatch):
    monkeypatch.setenv("PYRON_ENV", "dev")
    monkeypatch.setenv("PYRON_DEBUG", "1")
    monkeypatch.delenv("PYRON_SECRET", raising=False)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    rows = run_checks(tmp_path, deploy=True)
    levels = {msg: level for level, msg in rows}
    assert any(level == "warn" and "deploy" in msg for level, msg in rows)
    assert any(level == "error" and "DEBUG" in msg for level, msg in rows)
    assert any(level == "error" and "secret" in msg.lower() for level, msg in rows)


def test_check_ok_in_dev(tmp_path, monkeypatch):
    monkeypatch.setenv("PYRON_ENV", "dev")
    monkeypatch.delenv("PYRON_DEBUG", raising=False)
    monkeypatch.setenv("PYRON_SECRET", "x" * 40)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        "from pyron import Pyron\napp = Pyron(title='API')\n",
        encoding="utf-8",
    )
    rows = run_checks(tmp_path, deploy=False)
    assert all(level != "error" for level, _ in rows)
    assert any("API-only" in msg for _, msg in rows)
