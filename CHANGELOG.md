# Changelog

How Pyron actually changed. Dates are when the tree moved, not a PyPI release.

A user-facing change is unfinished until this file **and** the matching `docs/*.md` are updated in the same commit (plus README / scaffold copy when that surface is listed there). See `AGENTS.md` and [Contributing](docs/contributing.md).

## 0.10.0 — 2026-08-21

Small polish before calling this a 0.10.

- Version strings were still 0.7.x in the README and bookstore example; they follow the package now.
- First-run flash tells you to open **Settings** or **Pages**.
- Page slug fills from the title until you edit the slug yourself.
- Public header shows `site.tagline` when set.
- `pyron init` / `pyron dev` print `/admin/settings`.

## 0.9.0 — 2026-08-21

Operate the site from the admin panel, not only the SQL tables.

- Desk is split into **Site** (Pages, Settings) and **Data** (your models).
- **Settings**: name, tagline, phone, email, hours, address, website. Public header/footer read `site`.
- **Pages** body is Markdown, with a live preview. Legacy HTML bodies still render. Jinja in the body stays text.
- Phone in the public footer is a `tel:` link.
- Docs: [Settings](docs/admin.md#settings), CLI, comparison, enable, security, architecture, README, example bookstore. Docs ship in the same commit as the feature ([Contributing](docs/contributing.md)).

## 0.8.0 — 2026-08-21

CMS pages on the admin panel, rendered by Jinja2.

- `Page` is registered by default when the admin is on (`Pages` in the rail). Add / edit title, slug, HTML body, published, in nav.
- Public views: `/p/{slug}` and `/p`. Jinja2 wraps the body in `page.html` (app `base.html` if you have one). The body is **not** executed as Jinja (no SSTI).
- First run seeds **About** and **Contact**. Published pages with “in nav” show in the public header (`site_pages`).
- Operators can preview unpublished pages while signed in; visitors get 404.
- `Pyron(..., pages=False)` turns the built-in pages off.
- Docs: [Admin — Pages](docs/admin.md#pages-cms), quickstart, enable, CLI, security, comparison, architecture, README, example bookstore. `pyron init` / `pyron dev` print `/p/about`.

## 0.7.2 — 2026-08-21

GitHub Pages: enable Actions as the source (`build_type=workflow`). Docs workflow uses checkout@v5 and setup-python@v6 (Node 24).

## 0.7.1 — 2026-08-21

`pyron init app` asks for the project name, what it is about, and what people add. It generates a unique app (form, API, admin) and **10 starter records** for that topic — not a Harbor Bindings copy.

Flags for scripts: `--title` `--about` `--noun`.

## 0.7.0 — 2026-08-21

The FastAPI gap: HTML form, CLI, templates — one model.

- `Form()` for HTML posts; `redirect("/", message="Saved.")` flash (no admin required).
- `pyron init` (default **ssr**): home form writes the same SQL `Item` as `/api/items` and `/admin`. No more in-memory list vs admin table.
- Scaffold CSS matches the admin (ember, no brown Georgia).
- `pyron init` / `pyron dev` print `/`, `/docs`, `/admin`.

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
