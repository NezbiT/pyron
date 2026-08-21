import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Field, SQLModel

from pyron import ModelAdmin, Pyron, TabularInline
from pyron.db import create_engine, init_db


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str = ""


class NoteAdmin(ModelAdmin):
    list_display = ["id", "title"]
    search_fields = ["title"]


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "csrf field missing"
    return m.group(1)


@pytest.fixture
def admin_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'desk.db'}")
    init_db(engine)
    app = Pyron(title="DeskTest", admin=True, admin_engine=engine, docs_url=None, redoc_url=None)
    app.admin.register(Note, NoteAdmin)
    return app


@pytest.mark.asyncio
async def test_setup_login_crud(admin_app):
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/", follow_redirects=True)
        assert gate.status_code == 200
        assert "Create the root account" in gate.text

        csrf = _csrf(gate.text)
        created = await client.post(
            "/admin/setup",
            data={"csrf": csrf, "username": "root", "password": "correct-horse", "confirm": "correct-horse"},
            follow_redirects=True,
        )
        assert created.status_code == 200
        assert "Admin panel" in created.text
        assert "Notes" in created.text

        listed = await client.get("/admin/m/note")
        assert listed.status_code == 200
        assert "You have not added any Notes yet" in listed.text

        form = await client.get("/admin/m/note/new")
        csrf = _csrf(form.text)
        added = await client.post(
            "/admin/m/note/new",
            data={"csrf": csrf, "title": "Tide log", "body": "Thursday", "intent": "save"},
            follow_redirects=True,
        )
        assert added.status_code == 200
        assert "Tide log" in added.text

        edit = await client.get("/admin/m/note/1")
        csrf = _csrf(edit.text)
        saved = await client.post(
            "/admin/m/note/1",
            data={"csrf": csrf, "title": "Tide log", "body": "Friday", "intent": "save"},
            follow_redirects=True,
        )
        assert saved.status_code == 200

        confirm = await client.get("/admin/m/note/1/delete")
        assert "Delete Note" in confirm.text
        csrf = _csrf(confirm.text)
        gone = await client.post(
            "/admin/m/note/1/delete",
            data={"csrf": csrf},
            follow_redirects=True,
        )
        assert gone.status_code == 200
        assert "You have not added any Notes yet" in gone.text or "Tide log" not in gone.text


@pytest.mark.asyncio
async def test_bad_login_and_logout(admin_app):
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/setup")
        csrf = _csrf(gate.text)
        await client.post(
            "/admin/setup",
            data={"csrf": csrf, "username": "root", "password": "correct-horse", "confirm": "correct-horse"},
            follow_redirects=True,
        )
        await client.get("/admin/logout")
        login = await client.get("/admin/login")
        assert "Sign in" in login.text
        csrf = _csrf(login.text)
        bad = await client.post(
            "/admin/login",
            data={"csrf": csrf, "username": "root", "password": "nope", "next": "/admin/"},
        )
        assert bad.status_code == 200
        assert "did not match" in bad.text
        # username preserved
        assert 'value="root"' in bad.text


class Memo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    published: bool = True


class MemoAdmin(ModelAdmin):
    list_display = ["id", "title", "published"]
    list_filter = ["published"]


class Shelf(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str


class ShelfItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    shelf_id: int | None = Field(default=None, foreign_key="shelf.id")


class ShelfItemInline(TabularInline):
    model = ShelfItem
    extra = 1


class ShelfAdmin(ModelAdmin):
    list_display = ["id", "name"]
    inlines = [ShelfItemInline]


async def _bootstrap_root(client):
    gate = await client.get("/admin/", follow_redirects=True)
    csrf = _csrf(gate.text)
    await client.post(
        "/admin/setup",
        data={"csrf": csrf, "username": "root", "password": "correct-horse", "confirm": "correct-horse"},
        follow_redirects=True,
    )


@pytest.fixture
def memo_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'memo.db'}")
    init_db(engine)
    app = Pyron(title="MemoDesk", admin=True, admin_engine=engine, docs_url=None, redoc_url=None)
    app.admin.register(Memo, MemoAdmin)
    app.admin.register(Note, NoteAdmin)
    app.admin.register(Shelf, ShelfAdmin)
    return app


@pytest.mark.asyncio
async def test_list_filter_and_history(memo_app):
    transport = ASGITransport(app=memo_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        await _bootstrap_root(client)
        form = await client.get("/admin/m/memo/new")
        csrf = _csrf(form.text)
        await client.post(
            "/admin/m/memo/new",
            data={"csrf": csrf, "title": "Public note", "published": "1", "intent": "save"},
            follow_redirects=True,
        )
        form = await client.get("/admin/m/memo/new")
        csrf = _csrf(form.text)
        await client.post(
            "/admin/m/memo/new",
            data={"csrf": csrf, "title": "Draft note", "intent": "save"},
            follow_redirects=True,
        )
        listed = await client.get("/admin/m/memo")
        assert "Public note" in listed.text
        assert "Draft note" in listed.text
        assert "f_published=true" in listed.text
        filtered = await client.get("/admin/m/memo?f_published=true")
        assert "Public note" in filtered.text
        assert "Draft note" not in filtered.text
        assert 'class="chip is-on"' in filtered.text
        edit = await client.get("/admin/m/memo/1")
        assert "History" in edit.text
        assert "add" in edit.text
        assert "Public note" in edit.text


@pytest.mark.asyncio
async def test_bulk_delete_confirms(memo_app):
    transport = ASGITransport(app=memo_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        await _bootstrap_root(client)
        for title in ("Alpha", "Beta"):
            form = await client.get("/admin/m/note/new")
            csrf = _csrf(form.text)
            await client.post(
                "/admin/m/note/new",
                data={"csrf": csrf, "title": title, "body": "", "intent": "save"},
                follow_redirects=True,
            )
        listed = await client.get("/admin/m/note")
        csrf = _csrf(listed.text)
        confirm = await client.post(
            "/admin/m/note/action",
            data={"csrf": csrf, "action": "delete_selected", "pk": ["1", "2"]},
            follow_redirects=True,
        )
        assert confirm.status_code == 200
        assert "Delete 2" in confirm.text
        assert "Alpha" in confirm.text
        assert "Beta" in confirm.text
        csrf = _csrf(confirm.text)
        gone = await client.post(
            "/admin/m/note/action/confirm",
            data={"csrf": csrf},
            follow_redirects=True,
        )
        assert "Alpha" not in gone.text
        assert "Beta" not in gone.text


@pytest.mark.asyncio
async def test_inlines_on_change_form(memo_app):
    transport = ASGITransport(app=memo_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        await _bootstrap_root(client)
        form = await client.get("/admin/m/shelf/new")
        csrf = _csrf(form.text)
        await client.post(
            "/admin/m/shelf/new",
            data={"csrf": csrf, "name": "Poetry", "intent": "continue"},
            follow_redirects=True,
        )
        edit = await client.get("/admin/m/shelf/1")
        assert "Shelfitems" in edit.text or "New row" in edit.text
        csrf = _csrf(edit.text)
        saved = await client.post(
            "/admin/m/shelf/1",
            data={
                "csrf": csrf,
                "name": "Poetry",
                "inline-shelf-item-new0-title": "Leaves",
                "intent": "continue",
            },
            follow_redirects=True,
        )
        assert saved.status_code == 200
        assert "Leaves" in saved.text
        csrf = _csrf(saved.text)
        m = re.search(r'name="inline-shelf-item-(\d+)-title"', saved.text)
        assert m, saved.text
        kid = m.group(1)
        gone = await client.post(
            "/admin/m/shelf/1",
            data={
                "csrf": csrf,
                "name": "Poetry",
                f"inline-shelf-item-{kid}-title": "Leaves",
                f"inline-shelf-item-{kid}-DELETE": "1",
                "intent": "continue",
            },
            follow_redirects=True,
        )
        assert "Leaves" not in gone.text
