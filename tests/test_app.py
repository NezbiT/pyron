import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from pyron import CORSMiddleware, HTTPException, Pyron, __version__


class ItemIn(BaseModel):
    title: str = Field(min_length=1)
    price: float = Field(ge=0)


@pytest.fixture
def app() -> Pyron:
    app = Pyron(title="Test", docs_url=None, redoc_url=None, openapi_url="/openapi.json")
    items: dict[int, dict] = {}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/items/{item_id}")
    async def get_item(item_id: int):
        if item_id not in items:
            raise HTTPException(404, "missing")
        return items[item_id]

    @app.post("/items", status_code=201)
    async def create(item: ItemIn):
        rec = {"id": len(items) + 1, **item.model_dump()}
        items[rec["id"]] = rec
        return rec

    @app.get("/search")
    async def search(q: str = ""):
        return {"q": q}

    return app


def test_package_version_matches_app_default():
    app = Pyron(title="v")
    assert app.version == __version__
    assert CORSMiddleware is not None


@pytest.mark.asyncio
async def test_health_and_crud(app: Pyron):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        bad = await client.post("/items", json={"title": "", "price": -1})
        assert bad.status_code == 422

        created = await client.post("/items", json={"title": "Copper", "price": 2.5})
        assert created.status_code == 201
        item_id = created.json()["id"]

        got = await client.get(f"/items/{item_id}")
        assert got.json()["title"] == "Copper"

        missing = await client.get("/items/999")
        assert missing.status_code == 404

        q = await client.get("/search", params={"q": "salt"})
        assert q.json()["q"] == "salt"


@pytest.mark.asyncio
async def test_openapi_contains_paths(app: Pyron):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        spec = (await client.get("/openapi.json")).json()
        assert spec["openapi"].startswith("3.")
        assert "/items/{item_id}" in spec["paths"]
        assert spec["info"]["title"] == "Test"


@pytest.mark.asyncio
async def test_method_not_allowed(app: Pyron):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/health")
        assert r.status_code == 405


@pytest.mark.asyncio
async def test_ssr_and_html_404(tmp_path):
    (tmp_path / "hello.html").write_text("<h1>{{ name }}</h1>", encoding="utf-8")
    (tmp_path / "404.html").write_text("<p>missing {{ path }}</p>", encoding="utf-8")
    app = Pyron(title="SSR", docs_url=None, redoc_url=None, openapi_url=None, templates=str(tmp_path))

    @app.get("/hello")
    async def hello(request):
        return await app.render(request, "hello.html", {"name": "Ada"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/hello")
        assert r.status_code == 200
        assert r.text == "<h1>Ada</h1>"
        missing = await client.get("/nope", headers={"accept": "text/html"})
        assert missing.status_code == 404
        assert "/nope" in missing.text
