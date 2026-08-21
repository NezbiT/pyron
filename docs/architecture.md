# Architecture

```
  20–30% Rust          70–80% Python
  ─────────────        ────────────────────────
  radix router         handlers / Depends
  schema validator     Pydantic, business rules
  serde JSON           Jinja2 SSR, Vite, CLI, admin panel
  OpenAPI assembler    SQLModel · Mongo Document · Redis cache
           ▲           Granian (Uvicorn fallback)
           └── PyO3 + maturin
               batch calls · zero-copy bytes · buffer protocol
```

## Request path

1. Granian or Uvicorn (ASGI)
2. Security headers / host allowlist (`SecurityMiddleware`)
3. Admin session → `request.state.user` (if the panel is enabled)
4. Mounts (`/admin/assets`, `/static`)
5. Rust router → `route_id`
6. Rust schema on the body bytes (if a Pydantic body is declared)
7. Bind path/query/header/cookie/`BackgroundTasks`
8. Python handler
9. Rust `dumps` for JSON (or Jinja2 for HTML)

FFI rules: compile schemas and routes once; batch when you can; borrow `bytes`/`str`; release the GIL around validate.

Without a compiled extension (`PYRON_PURE_PYTHON=1`) a Python fallback loads. Call shapes do not change.

## Python package (`python/pyron/`)

| Module | Role |
|---|---|
| `app.py` | ASGI app, routing table, middleware stack |
| `routing.py` | `APIRouter`, signature compile |
| `store.py` | Desk storage protocol (SQL / Mongo / memory) |
| `document.py` | Pydantic `Document` for Mongo |
| `mongo.py` | `mongo_client`, `MongoStore` |
| `cache.py` | Redis or process memory |
| `db.py` | SQLModel engine, Alembic wrappers |
| `admin/site.py` | Admin views; CRUD via `bound.store` |
| `admin/options.py` | `ModelAdmin`, `TabularInline` |
| `admin/auth.py` | Operators, PBKDF2, session cookie, log |
| `security.py` | Headers, throttle, password rules |
| `settings.py` | Env (`PYRON_*`, `DATABASE_URL`, `MONGO_URL`, `REDIS_URL`) |
| `_bridge.py` | Load `pyron._core` or `_core_fallback` |
| `_version.py` | Package version |

Rust crate: `src/` (`router`, `validator`, `serialize`, `openapi`). Version of the extension is independent; the product version is `_version.py`.

## Data

Operators and `pyron_log` stay on SQL. Application tables may be SQLModel or `Document`. Redis is cache and login throttle only — never a Desk table. Details: [data.md](data.md).

## Layers you skip stay out

`admin=False` → no panel, no session middleware. No `MONGO_URL` → no pymongo import on the hot path. No `REDIS_URL` → in-process cache. Docs off in production unless you set `PYRON_EXPOSE_DOCS=1`.
