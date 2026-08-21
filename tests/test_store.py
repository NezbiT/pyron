import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Field, SQLModel

from pyron import Document, MemoryStore, ModelAdmin, Pyron
from pyron.db import create_engine, init_db
from pyron.mongo import mongo_query
from pyron.store import SqlStore, is_document


class Slip(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str = ""


class Page(Document):
    collection = "pages"
    title: str
    body: str = ""


def test_memory_store_crud():
    store = MemoryStore()
    row = store.insert(Page, {"title": "Harbor"})
    assert row.id
    assert store.count(Page) == 1
    found = store.get(Page, row.id)
    assert found.title == "Harbor"
    store.update(Page, row.id, {"title": "Tide"})
    assert store.get(Page, row.id).title == "Tide"
    rows, total = store.list(Page, q="tide", search_fields=["title"])
    assert total == 1
    store.delete(Page, row.id)
    assert store.count(Page) == 0


def test_sql_store_crud(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    init_db(engine)
    store = SqlStore(engine)
    row = store.insert(Slip, {"title": "Log"})
    assert row.id == 1
    rows, total = store.list(Slip, q="Log", search_fields=["title"])
    assert total == 1
    store.delete(Slip, row.id)
    assert store.count(Slip) == 0


def test_mongo_query_shape():
    empty = mongo_query()
    assert empty == {}
    q = mongo_query(q="tide", search_fields=["title"], filters={"published": "true"})
    assert "$or" in q or "$and" in q
    assert is_document(Page)
    assert not is_document(Slip)


@pytest.mark.asyncio
async def test_document_admin_http(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'doc2.db'}")
    init_db(engine)
    pages = MemoryStore()
    app = Pyron(
        title="Docs",
        admin=True,
        admin_engine=engine,
        admin_mongo=pages,
        docs_url=None,
        redoc_url=None,
    )
    app.admin.register(Page)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/", follow_redirects=True)
        import re

        csrf = re.search(r'name="csrf" value="([^"]+)"', gate.text).group(1)
        await client.post(
            "/admin/setup",
            data={"csrf": csrf, "username": "root", "password": "correct-horse", "confirm": "correct-horse"},
            follow_redirects=True,
        )
        form = await client.get("/admin/m/page/new")
        csrf = re.search(r'name="csrf" value="([^"]+)"', form.text).group(1)
        listed = await client.post(
            "/admin/m/page/new",
            data={"csrf": csrf, "title": "Charts", "body": "North", "intent": "save"},
            follow_redirects=True,
        )
        assert "Charts" in listed.text
        assert pages.count(Page) == 1
        home = await client.get("/admin/")
        assert "Pages" in home.text
        assert "memory" in home.text
