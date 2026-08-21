# Pyron

A hybrid Python web framework with a Rust core.

FastAPI gets you `/docs` in minutes, then you assemble Jinja, forms, a CLI, and an admin yourself. **Pyron is that whole path:** HTML form, JSON API, and optional `/admin` on the **same model**, from `pyron init`.

[![License: MIT](https://img.shields.io/badge/license-MIT-c2410c.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-1a1a1a.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-mkdocs-c2410c.svg)](https://nezbit.github.io/pyron/)

**Docs:** [website](https://nezbit.github.io/pyron/) · [docs/index.md](docs/index.md) · local: `mkdocs serve` → http://127.0.0.1:8001

```
  20–30% Rust                70–80% Python
  routing · validation       handlers · Pydantic · Jinja2
  JSON · OpenAPI assemble    admin panel · CLI · SQLModel · Granian
```

## Features

- Pydantic bodies → validation **and** automatic OpenAPI (`/docs`, `/redoc`)
- Jinja2 pages + `Form()` + flash (`redirect("/", message="Saved.")`) — no extra packages
- Optional Vite for React / Vue / Svelte
- Optional **admin panel** at `/admin` (Django-style): **Site** (Pages + Settings) and **Data** (your tables); Markdown pages with preview; public header/footer from settings
- Same `request.user` on API and the panel; `@permission_required("book.delete")`; staff cannot delete by default
- Admin panel UI: **English / Español / Português / Français**, **light / dark / system** (system is the default)
- Enable the panel later with `pyron enable admin` — does not rewrite your API handlers
- `pyron startapp` + `app.include_app(...)` for Django-shaped packages
- Typer CLI, SQLModel + Alembic, optional Mongo documents + Redis cache, Granian (Uvicorn fallback)
- `BackgroundTasks`, `app.url_for`, production checks: `pyron check --deploy`

## Install

```powershell
cd pyron
python -m pip install maturin
maturin build --release
python -m pip install (Get-ChildItem target\wheels\pyron-*.whl).FullName
python -m pip install ".[standard,db]"
pyron version
```

PowerShell does not expand `pyron-*.whl` for pip; use `Get-ChildItem` or the exact wheel name. Full steps: [docs/install.md](docs/install.md).

## 30 seconds (pages + API + admin)

```bash
pyron init app           # asks name + what it is about; 10 starter records
cd <folder>
pyron dev
```

Open http://127.0.0.1:8000 — add an item in the form. Same row appears in `/docs` and `/admin`. **Pages** in the panel become public views at `/p/about` (Jinja2).

## 30-second API only

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
pyron init shop --template api    # JSON only; add the panel later with `pyron enable admin`
pyron dev --app app.main:app
```

## Admin panel later, without destroying code

```bash
pyron enable admin
pyron createsuperuser
```

Or in code: `app.enable("admin", engine=engine)`. Details: [docs/enable.md](docs/enable.md) · [docs/admin.md](docs/admin.md).

## Security

`PYRON_ENV=production` plus `pyron check`. Passwords are PBKDF2; logins are throttled; admin panel POSTs are CSRF-protected. See [docs/security.md](docs/security.md).

## Example

[`examples/bookstore`](examples/bookstore) — catalog SSR, `/api/books`, admin panel at `/admin`.

```bash
cd examples/bookstore
pyron dev --app app.main:app
```

## Benchmarks vs FastAPI

Measured on CPython 3.12, Windows x86_64, release wheel (re-run `python benchmarks/bench.py` before quoting):

| Task | Pyron Rust core | Baseline | Ratio |
|---|---|---|---|
| Route match, 200 templates | 719 ns | 24.7 µs linear Python | **34×** |
| Validate small JSON | 2.67 µs | 2.13 µs Pydantic v2 | 0.80× |
| Dump small dict | 1.09 µs | 2.57 µs stdlib | **2.4×** |
| Route + validate + dump | 4.28 µs | Pydantic JSON + stdlib | **1.2×** |

Pydantic v2 is already Rust. Pyron does not claim a validation blowout; routing and `dumps` are the clear wins. Method: [benchmarks/results.md](benchmarks/results.md). Comparison in words: [docs/comparison.md](docs/comparison.md).

## Documentation website

The markdown in `docs/` is also a publishable site (MkDocs Material, Pyron colors).

```powershell
python -m pip install mkdocs-material
mkdocs serve
```

Opens http://127.0.0.1:8001 (8000 is reserved for the app). Push to `main` with GitHub Pages (Actions) enabled; `.github/workflows/docs.yml` publishes to https://nezbit.github.io/pyron/.

## Tests

```bash
pytest
cargo test --lib
```

## Status

v0.7.2. Alpha. MIT. See [CHANGELOG.md](CHANGELOG.md) · [docs/auth.md](docs/auth.md) · [docs/admin.md](docs/admin.md) · [docs/data.md](docs/data.md).
