# Changelog

How Pyron actually changed. Dates are when the tree moved, not a PyPI release.

## 0.6.2 — 2026-08-21

Documentation website.

- MkDocs Material site from the existing `docs/*.md` (ember palette, JetBrains Mono, system/light/dark).
- `mkdocs serve` on port 8001; GitHub Pages workflow in `.github/workflows/docs.yml`.
- Extra: `pip install pyron[docs]`.

## 0.6.1 — 2026-08-21

Architecture cleanup after 0.6.

- One version string: `python/pyron/_version.py` (app default, `pyron.__version__`, `pyproject.toml`).
- Admin options (`ModelAdmin`, `TabularInline`) live in `admin/options.py`; `site.py` is views + binding.
- Removed unused SQL helpers left behind when Desk CRUD moved to `Store`.
- Public `CORSMiddleware` and `GZipMiddleware` (`app.add_middleware(...)`).
- Docs: architecture map, install extras, this file.

## 0.6.0 — 2026-08-21

SQL stays. Mongo and Redis become optional extras.

- `Store` protocol: `SqlStore`, `MongoStore`, `MemoryStore`. Desk CRUD goes through the store, not raw `select()`.
- `Document` (Pydantic) registers on the admin panel next to SQLModel tables.
- `MONGO_URL` / `MONGO_DB`, extra `pyron[mongo]`.
- `cache` + `REDIS_URL`, extra `pyron[redis]`. Login throttle uses the cache (shared across workers when Redis is on).
- `app.enable("mongo"|"redis")`.
- Admin cards show `sql` / `mongo` / `memory`.
- Docs: data (SQL / Mongo / Redis).

## 0.5.0 — 2026-08-20

Desk power + apps + deploy check.

- `list_filter`, bulk delete with confirm, `TabularInline`, `pyron_log` history.
- `pyron startapp` / `app.include_app`.
- `pyron check --deploy`.
- `BackgroundTasks`, `app.url_for` (and in Jinja).
- Admin copy: **Admin panel** (not “Desk”).
- Language / appearance as sliding toggles; asset `?v=` cache bust.

## 0.4.0

Auth shared between API and admin.

- Signed session cookie `pyron_desk` on path `/`.
- `current_user`, `@login_required`, `@permission_required`.
- Staff group: view/add/change, not delete. Root bypasses.
- PBKDF2, CSRF, login throttle.
- i18n en/es/pt/fr; theme system/light/dark; JetBrains Mono.

## 0.3.0

Enable later, security defaults, Granian.

- `pyron enable admin` appends; does not rewrite handlers.
- `PYRON_ENV=production`, `pyron check`, security headers, host allowlist.
- `pyron dev` / `serve` via Granian (Uvicorn fallback). Windows `PYTHONPATH` for reload.

## 0.2.0

Visual admin at `/admin`.

- Register SQLModel, first-run root, CRUD, route map, users.

## 0.1.0

Hybrid core.

- FastAPI-shaped ASGI, Rust router / JSON schema / `dumps` via PyO3.
- OpenAPI `/docs`, Jinja2, Vite, Typer CLI, SQLModel helpers.
