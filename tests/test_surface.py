"""Signals, inspector, registry, custom request, and WebSockets."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from pyron import Header, Pyron, create_app
from pyron._core_fallback import prepare_request as prepare_python
from pyron._bridge import prepare_request
from pyron.inspector import InspectorHub, ask, read_state, write_state


def _quiet_app(**kwargs) -> Pyron:
    defaults = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    defaults.update(kwargs)
    return Pyron(**defaults)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_prepare_request_matches_python_fallback():
    query = "q=hello+world&q=second&raw=a%20b&flag"
    headers = [("X-User", "Ada"), ("x-user", "Bea"), ("Accept", "text/plain")]
    rust = prepare_request(query, headers)
    py = prepare_python(query, headers)
    assert rust["query"]["q"] == "hello world"
    assert rust["query"]["raw"] == "a b"
    assert rust["query"]["flag"] == ""
    assert "second" not in rust["query"].values()
    assert rust["headers"]["x-user"] == "Ada"
    assert rust["headers"]["accept"] == "text/plain"
    assert rust == py


def test_registry_names_only_explicit_apps():
    anonymous = _quiet_app()
    assert anonymous.name is None
    assert anonymous not in Pyron._apps.values()
    named = _quiet_app(name="surface-main")
    try:
        assert Pyron.get_app("surface-main") is named
        assert create_app(name="surface-factory", docs_url=None, redoc_url=None, openapi_url=None)
        assert Pyron.get_app("surface-factory").name == "surface-factory"
        again = _quiet_app()
        again.register("surface-main")
        raise AssertionError("duplicate name should fail")
    except RuntimeError:
        pass
    finally:
        Pyron._apps.pop("surface-main", None)
        Pyron._apps.pop("surface-factory", None)
    with pytest.raises(LookupError):
        Pyron.get_app("surface-missing")


def test_custom_request_class_reaches_handler():
    class PyronRequest(Request):
        @property
        def user_id(self) -> str | None:
            return getattr(self.state, "user_id", None)

    app = _quiet_app(request_class=PyronRequest)

    @app.get("/me")
    async def me(request):
        request.state.user_id = "u-9"
        return {"id": request.user_id, "type": type(request).__name__}

    with TestClient(app) as client:
        body = client.get("/me").json()
    assert body == {"id": "u-9", "type": "PyronRequest"}


@pytest.mark.asyncio
async def test_signals_are_not_middleware_or_openapi():
    app = _quiet_app(openapi_url="/openapi.json")
    seen: list[tuple] = []

    @app.signal("http.handler.before")
    async def before(request):
        seen.append(("http.before", request.url.path))

    @app.signal("handler.before")
    def before_short(request):
        seen.append(("before", request.url.path))

    @app.signal("handler.after")
    async def after(response):
        seen.append(("after", response.status_code))

    @app.signal("book.created")
    async def on_book(book):
        seen.append(("book", book["id"]))

    @app.signal("book.created")
    async def on_book_bare():
        seen.append(("bare", None))

    @app.get("/search")
    async def search(q: str = ""):
        await app.dispatch("book.created", book={"id": 7})
        return {"q": q}

    @app.get("/boom")
    async def boom():
        return {"ok": True}

    @app.signal("http.handler.before")
    async def explode(request):
        if request.url.path == "/boom":
            raise RuntimeError("signal failed")

    class Stamp:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            async def send_wrap(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers") or [])
                    headers.append((b"x-stamp", b"1"))
                    message = {**message, "headers": headers}
                await send(message)

            await self.inner(scope, receive, send_wrap)

    app.add_middleware(Stamp)
    started: list[str] = []

    @app.on_event("startup")
    async def boot():
        started.append("up")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        found = await client.get("/search", params={"q": "hello world"})
        assert found.status_code == 200
        assert found.json()["q"] == "hello world"
        assert found.headers["x-stamp"] == "1"
        missing = await client.get("/nope")
        assert missing.status_code == 404
        assert not any(item[1] == "/nope" for item in seen)
        failed = await client.get("/boom")
        assert failed.status_code == 500
        spec = (await client.get("/openapi.json")).json()
    assert ("book", 7) in seen
    assert ("bare", None) in seen
    assert ("http.before", "/search") in seen
    assert ("before", "/search") in seen
    assert ("after", 200) in seen
    assert "/search" in spec["paths"]
    assert "/feed" not in spec["paths"]
    assert "book.created" not in str(spec)
    # httpx ASGITransport does not enter lifespan; startup stays on its own hook.
    assert started == []


def test_lifespan_still_runs_startup():
    app = _quiet_app()
    started: list[str] = []

    @app.on_event("startup")
    async def boot():
        started.append("up")

    @app.get("/health")
    async def health():
        return {"up": started == ["up"]}

    with TestClient(app) as client:
        assert client.get("/health").json()["up"] is True


def test_websocket_echo_and_path_param():
    app = _quiet_app()

    @app.websocket("/feed")
    async def feed(request, ws):
        assert request.url.path == "/feed"
        async for msg in ws:
            await ws.send(msg)

    @app.websocket("/rooms/{room}")
    async def room(ws, room):
        await ws.send({"room": room})

    with TestClient(app) as client:
        with client.websocket_connect("/feed") as ws:
            ws.send_text("hi")
            assert ws.receive_text() == "hi"
            ws.send_bytes(b"bin")
            assert ws.receive_bytes() == b"bin"
        with client.websocket_connect("/rooms/north") as ws:
            assert ws.receive_json() == {"room": "north"}
        with pytest.raises(Exception):
            with client.websocket_connect("/missing"):
                pass
    spec = app.openapi()
    assert "/feed" not in spec["paths"]


def test_inspector_hub_status_and_call():
    hub = InspectorHub()
    addr = hub.start()
    reloaded: list[int] = []
    scaled: list[int] = []
    hub.on_reload = lambda: reloaded.append(1)
    hub.on_scale = lambda count: scaled.append(count)

    def worker():
        host, port_s = addr.rsplit(":", 1)
        conn = socket.create_connection((host, int(port_s)), timeout=2)
        conn.settimeout(None)
        from pyron.inspector import _readline, _write

        _write(conn, {"op": "hello", "pid": 4242, "commands": ["ping"]})
        assert _readline(conn)
        while True:
            raw = _readline(conn)
            if not raw:
                break

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline and not hub.worker_pids:
        time.sleep(0.02)
    status = ask(addr, {"op": "status"})
    assert status["ok"] is True
    assert status["result"]["worker_pids"] == [4242]
    assert status["result"]["commands"] == ["ping"]
    assert status["result"]["version"]
    assert ask(addr, {"op": "reload"})["result"]["reloaded"] is True
    assert reloaded == [1]
    assert ask(addr, {"op": "scale", "workers": 3})["result"]["workers"] == 3
    assert scaled == [3]
    assert ask(addr, {"op": "scale", "workers": 0})["ok"] is False
    assert ask(addr, {"op": "nope"})["ok"] is False
    hub.reset_workers()
    assert hub.worker_pids == []
    assert ask(addr, {"op": "call", "name": "ping", "payload": {}})["ok"] is False
    hub.stop()


def test_custom_inspector_command_runs_in_the_app(monkeypatch):
    hub = InspectorHub()
    addr = hub.start()
    monkeypatch.setenv("PYRON_INSPECT_ADDR", addr)
    app = _quiet_app()

    @app.inspector.command("ping")
    def ping(name: str = "ada"):
        return {"name": name}

    @app.inspector.command("later")
    async def later():
        return {"async": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            deadline = time.time() + 2
            status = {}
            while time.time() < deadline:
                status = ask(addr, {"op": "status"})["result"]
                if "ping" in status["commands"] and "later" in status["commands"]:
                    break
                time.sleep(0.05)
            assert "ping" in status["commands"]
            got = ask(addr, {"op": "call", "name": "ping", "payload": {"name": "bea", "extra": 1}})
            assert got["result"] == {"name": "bea"}
            got = ask(addr, {"op": "call", "name": "later", "payload": {}})
            assert got["result"] == {"async": True}
            missing = ask(addr, {"op": "call", "name": "absent", "payload": {}})
            assert missing["ok"] is False
    finally:
        hub.stop()


def test_inspect_cli_reads_state(tmp_path: Path):
    from typer.testing import CliRunner

    from pyron.cli import app as cli

    hub = InspectorHub()
    addr = hub.start()
    write_state(tmp_path, addr, os.getpid())
    runner = CliRunner()
    try:
        result = runner.invoke(cli, ["inspect", "--app-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "version" in result.output
        assert "supervisor" in result.output
        reloaded = runner.invoke(cli, ["inspect", "--app-dir", str(tmp_path), "reload"])
        assert reloaded.exit_code == 0, reloaded.output
        assert "reloaded" in reloaded.output
        missing = runner.invoke(cli, ["inspect", "--app-dir", str(tmp_path / "empty")])
        assert missing.exit_code == 1
        assert "No running Pyron app" in missing.output
    finally:
        hub.stop()


def test_read_state_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="No running Pyron app"):
        read_state(tmp_path)


def test_run_supervises_unless_already_a_worker(tmp_path, monkeypatch):
    monkeypatch.delenv("PYRON_WORKER", raising=False)
    seen: dict = {}

    def fake_supervise(target, **kwargs):
        seen["target"] = target
        seen.update(kwargs)

    monkeypatch.setattr("pyron.workers.supervise", fake_supervise)
    from pyron.server import run

    run("pkg:app", host="127.0.0.1", port=9, workers=4, reload=True, app_dir=str(tmp_path))
    assert seen["target"] == "pkg:app"
    assert seen["workers"] == 4
    assert seen["reload"] is True

    monkeypatch.setenv("PYRON_WORKER", "1")
    blocked: dict = {}

    def fake_block(*args, **kwargs):
        blocked["kwargs"] = kwargs

    monkeypatch.setattr("pyron.server.serve_blocking", fake_block)
    run("pkg:app", workers=2, app_dir=str(tmp_path))
    assert blocked["kwargs"]["workers"] == 2
    assert seen["target"] == "pkg:app"


def test_header_binding_is_case_insensitive():
    app = _quiet_app()

    @app.get("/who")
    async def who(user: str = Header(alias="X-User")):
        return {"user": user}

    with TestClient(app) as client:
        response = client.get("/who", headers={"x-user": "Ada"})
    assert response.json() == {"user": "Ada"}


def test_supervise_serves_and_answers_inspect(tmp_path: Path):
    app_path = tmp_path / "probe_app.py"
    app_path.write_text(
        "from pyron import Pyron\n\n"
        "app = Pyron(title='probe', docs_url=None, redoc_url=None, openapi_url=None)\n\n"
        "@app.get('/health')\n"
        "async def health():\n"
        "    return {'ok': True}\n\n"
        "@app.inspector.command('ping')\n"
        "def ping():\n"
        "    return 'pong'\n",
        encoding="utf-8",
    )
    port = _free_port()
    from pyron.workers import request, supervise

    def _run() -> None:
        supervise(
            "probe_app:app",
            host="127.0.0.1",
            port=port,
            workers=1,
            reload=False,
            app_dir=str(tmp_path),
            log_level="warning",
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 20
        health = None
        while time.time() < deadline:
            try:
                health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.4)
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                health = None
            time.sleep(0.1)
        assert health is not None and health.status_code == 200
        status = {}
        while time.time() < deadline:
            status = request(str(tmp_path), {"op": "status"})["result"]
            if status.get("worker_pids") and "ping" in status.get("commands", []):
                break
            time.sleep(0.1)
        assert "ping" in status["commands"]
        assert request(str(tmp_path), {"op": "call", "name": "ping", "payload": {}})["result"] == "pong"
        scaled = request(str(tmp_path), {"op": "scale", "workers": 2})
        assert scaled["result"]["workers"] == 2
        time.sleep(0.3)
        again = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert again.status_code == 200
    finally:
        try:
            request(str(tmp_path), {"op": "shutdown"})
        except OSError:
            pass
        thread.join(20)
    assert not thread.is_alive()
    assert not (tmp_path / ".pyron" / "inspect.json").exists()


def test_dispatch_unknown_signal_is_quiet():
    app = _quiet_app()

    async def go() -> None:
        await app.dispatch("nothing.happened", book=1)

    asyncio.run(go())
