# API

Pyron’s public surface matches FastAPI on purpose.

```python
from pyron import Body, CORSMiddleware, Depends, Header, HTTPException, Path, Pyron, Query

app = Pyron(title="Harbor API")
```

## Routes

```python
@app.get("/books/{book_id}")
async def get_book(book_id: int):
    ...

@app.post("/books", status_code=201)
async def create_book(book: BookIn) -> BookIn:
    return book
```

`APIRouter` groups prefixes and tags; `app.include_router(api)` mounts them. `app.include_app("catalog")` loads a package created by `pyron startapp`.

Named routes reverse with `app.url_for("book", book_id=3)` (also available in Jinja as `url_for`).

```python
from pyron import BackgroundTasks

@app.post("/ping")
async def ping(background: BackgroundTasks):
    background.add_task(send_email)
    return {"ok": True}
```

`BackgroundTasks` is Starlette’s. Tasks run after the response is sent.

CORS / gzip (Starlette, re-exported):

```python
from pyron import CORSMiddleware, GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Validation and docs

A Pydantic v2 model as a parameter is treated as JSON body:

1. Raw bytes hit the **Rust** schema (compiled once at startup).
2. The parsed object is passed to `model_validate`.
3. The same schema is written into OpenAPI 3.1.

Turn docs off (typical production):

```python
app = Pyron(title="Harbor", docs_url=None, redoc_url=None, openapi_url=None)
```

or `PYRON_EXPOSE_DOCS=0` (already the default when `PYRON_ENV=production`).

## JSON

Responses that are dicts/models go through `pyron.dumps` (Rust `serde_json` when the extension is loaded).

## Auth on selected routes

Public by default. Lock one endpoint without rewriting it:

```python
from pyron import login_required

@app.delete("/books/{book_id}")
@login_required
async def delete_book(request, book_id: int):
    ...
```

JSON clients get `401`. Browsers asking for HTML are sent to `/admin/login`.
