# Quickstart

The default is a **page with a form**, not an API-only file. FastAPI leaves HTML, forms, and a panel as homework; `pyron init` does not.

```bash
pyron init shop
cd shop
pyron dev
```

- http://127.0.0.1:8000 — HTML form (creates a row)
- http://127.0.0.1:8000/docs — the same row as JSON
- http://127.0.0.1:8000/admin — the same row in the panel (first visit creates root)

```python
from pyron import Form, redirect

@app.post("/")
async def add_item(title: str = Form(), description: str = Form("")):
    ...
    return redirect("/", message=f"Added “{title}”.")
```

## API only

```python
from pydantic import BaseModel, Field
from pyron import Pyron

app = Pyron(title="Harbor API")


class BookIn(BaseModel):
    title: str = Field(min_length=1)
    price: float = Field(ge=0)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/books", status_code=201)
async def create_book(book: BookIn) -> BookIn:
    return book
```

```bash
pyron dev --app hello:app
```

Open:

- http://127.0.0.1:8000/docs — Swagger
- http://127.0.0.1:8000/redoc
- http://127.0.0.1:8000/openapi.json

Pydantic models on the handler **are** the contract: validation, types, and OpenAPI come from the same class.

## Scaffold

```bash
pyron init shop                     # default ssr: form + API + admin
pyron init shop --template api      # JSON + docs
pyron init shop --template desk     # same as ssr
pyron init shop --template fullstack
```

Then `cd shop`, `pyron dev`.

## Server-rendered pages

```python
from starlette.requests import Request
from pyron import Pyron

app = Pyron(templates="templates", static_dir="static")

@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {"title": "Harbor"})
```

Pages that should not appear in Swagger: `include_in_schema=False`.

## Example

```bash
cd examples/bookstore
pyron dev --app app.main:app
```

Shop at `/`, API at `/api/books`, admin panel at `/admin`.
