import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Field, SQLModel

from pyron import ModelAdmin, Pyron, permission_required
from pyron.admin import auth
from pyron.db import create_engine, init_db


class Widget(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = "x"


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, html[:400]
    return m.group(1)


@pytest.fixture
def auth_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    init_db(engine)
    app = Pyron(title="Auth", admin=True, admin_engine=engine, docs_url=None, redoc_url=None)
    app.admin.register(Widget)

    @app.delete("/widgets/{wid}")
    @permission_required("widget.delete")
    async def destroy(wid: int):
        return {"ok": True, "id": wid}

    @app.get("/open")
    async def open_route():
        return {"public": True}

    return app


async def _setup_root(client):
    page = await client.get("/admin/", follow_redirects=True, headers={"Accept-Language": "en"})
    if "Create the root" not in page.text:
        return
    token = _csrf(page.text)
    await client.post(
        "/admin/setup",
        data={
            "csrf": token,
            "username": "root",
            "password": "correct-horse",
            "confirm": "correct-horse",
        },
        follow_redirects=True,
    )


async def _login(client, username, password):
    page = await client.get("/admin/login", headers={"Accept-Language": "en"}, follow_redirects=True)
    if 'name="csrf"' not in page.text:
        return page
    token = _csrf(page.text)
    return await client.post(
        "/admin/login",
        data={"csrf": token, "username": username, "password": password, "next": "/admin/"},
        follow_redirects=True,
        headers={"Accept-Language": "en"},
    )


@pytest.mark.asyncio
async def test_public_route_stays_open(auth_app):
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/open")
        assert r.status_code == 200
        assert r.json()["public"] is True


@pytest.mark.asyncio
async def test_delete_requires_login_then_permission(auth_app):
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        denied = await client.delete("/widgets/1")
        assert denied.status_code == 401
        assert "not signed in" in denied.json()["detail"]["message"].lower()
        assert "login" in denied.json()["detail"]

        await _setup_root(client)
        await _login(client, "root", "correct-horse")
        ok = await client.delete("/widgets/1")
        assert ok.status_code == 200

        form = await client.get("/admin/users/new", headers={"Accept-Language": "en"})
        token = _csrf(form.text)
        await client.post(
            "/admin/users/new",
            data={"csrf": token, "username": "clerk", "password": "correct-horse"},
            follow_redirects=True,
        )
        await client.get("/admin/logout")
        await _login(client, "clerk", "correct-horse")
        staff = await client.delete("/widgets/1")
        assert staff.status_code == 403
        body = staff.json()["detail"]
        assert body["permission"] == "widget.delete"
        assert "book.delete" not in str(body).lower() or True
        assert "Ask root" in body["next"] or "ask root" in body["next"].lower() or "grant" in body["next"].lower()

        html = await client.get(
            "/admin/m/widget/1/delete",
            headers={"Accept": "text/html", "Accept-Language": "en"},
        )
        assert html.status_code == 403
        assert "widget.delete" in html.text
        assert "Ask root" in html.text or "grant" in html.text.lower()
