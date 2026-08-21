"""Typer CLI: init, startapp, enable, check, dev, serve, db, createsuperuser."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pyron._bridge import CORE, USING_RUST

app = typer.Typer(
    name="pyron",
    help="Pyron — hybrid Python web framework with a Rust core.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="SQLModel / Alembic database commands.")
app.add_typer(db_app, name="db")
console = Console()

TEMPLATES = ("api", "ssr", "desk", "fullstack")


@app.callback()
def _root() -> None:
    """Pyron CLI."""


@app.command()
def version() -> None:
    """Print the installed Pyron version and which core is loaded."""
    from pyron import __version__

    console.print(f"pyron {__version__}  core=[bold]{CORE}[/bold]  rust={USING_RUST}")


@app.command("init")
def init_project(
    name: str = typer.Argument(..., help="Directory (and package) name for the new app."),
    template: str = typer.Option(
        "ssr",
        "--template",
        "-t",
        help="Project shape: api | ssr | desk | fullstack.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite the target directory if it exists."),
) -> None:
    """Scaffold a new Pyron application."""
    if template not in TEMPLATES:
        raise typer.BadParameter(f"template must be one of {TEMPLATES}")
    label = template
    if template == "desk":
        template = "ssr"
    dest = Path(name).resolve()
    if dest.exists() and any(dest.iterdir()) and not force:
        console.print(f"[red]{dest} is not empty.[/red] Pass --force to overwrite.")
        raise typer.Exit(1)
    dest.mkdir(parents=True, exist_ok=True)
    _write_scaffold(dest, dest.name.replace("-", "_"), template)
    table = Table(title=f"Created {dest.name}", show_header=False, box=None)
    table.add_row("template", label)
    table.add_row("core", CORE)
    console.print(table)
    console.print(
        Panel(
            f"[bold]Next[/bold]\n"
            f"  cd {dest.name}\n"
            "  python -m pip install -e \".\\[standard,db\\]\"\n"
            f"  pyron dev\n"
            + ("  npm install && npm run dev   (in another terminal, fullstack only)\n" if template == "fullstack" else ""),
            title="Pyron",
            border_style="red",
        )
    )


@app.command()
def dev(
    target: str = typer.Option("app.main:app", "--app", "-a", help="ASGI import string."),
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
    app_dir: Optional[Path] = typer.Option(
        None,
        "--app-dir",
        help="Directory that contains the `app` package. Defaults to the current directory.",
    ),
) -> None:
    """Run the development server (Granian, or Uvicorn if Granian is missing)."""
    os.environ.setdefault("PYRON_ENV", "dev")
    console.print(f"[bold red]Pyron[/bold red]  core={CORE}  {host}:{port}  target={target}")
    from pyron.server import run

    run(
        target,
        host=host,
        port=port,
        reload=reload,
        app_dir=str(app_dir.resolve()) if app_dir else None,
    )


@app.command()
def serve(
    target: str = typer.Option("app.main:app", "--app", "-a"),
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    workers: int = typer.Option(1, "--workers", "-w"),
    app_dir: Optional[Path] = typer.Option(
        None,
        "--app-dir",
        help="Directory that contains the `app` package. Defaults to the current directory.",
    ),
) -> None:
    """Run a production ASGI server without reload."""
    os.environ.setdefault("PYRON_ENV", "production")
    from pyron.server import run

    run(
        target,
        host=host,
        port=port,
        reload=False,
        workers=workers,
        app_dir=str(app_dir.resolve()) if app_dir else None,
    )


@app.command()
def enable(
    feature: str = typer.Argument(..., help="Feature to turn on: admin."),
    root: Path = typer.Option(Path("."), "--root", help="Project root."),
) -> None:
    """Enable a layer on an existing app. Does not rewrite your API handlers."""
    if feature != "admin":
        console.print("[red]Known feature: admin[/red]")
        raise typer.Exit(1)
    from pyron.enable import enable_admin

    try:
        actions = enable_admin(root.resolve())
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    for line in actions:
        console.print(f"  • {line}")
    console.print("Then: [bold]pyron createsuperuser[/bold]  and open /admin")


@app.command()
def startapp(
    name: str = typer.Argument(..., help="Python package name, e.g. catalog."),
    root: Path = typer.Option(Path("."), "--root"),
) -> None:
    """Create a Django-style app package: models, routes, admin."""
    pkg = root / name
    if pkg.exists():
        console.print(f"[red]{pkg} already exists.[/red]")
        raise typer.Exit(1)
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "models.py").write_text(
        "from typing import Optional\n\nfrom sqlmodel import Field, SQLModel\n\n\n"
        f"class {name.capitalize()}Item(SQLModel, table=True):\n"
        "    id: Optional[int] = Field(default=None, primary_key=True)\n"
        "    title: str\n",
        encoding="utf-8",
    )
    (pkg / "routes.py").write_text(
        "from pyron import APIRouter\n\nrouter = APIRouter(prefix='/" + name + "', tags=['" + name + "'])\n\n"
        "@router.get('/health')\nasync def health():\n    return {'app': '" + name + "', 'status': 'ok'}\n",
        encoding="utf-8",
    )
    (pkg / "admin.py").write_text(
        f"from {name}.models import {name.capitalize()}Item\nfrom pyron.admin import ModelAdmin\n\n\n"
        f"class {name.capitalize()}ItemAdmin(ModelAdmin):\n    list_display = ['id', 'title']\n    search_fields = ['title']\n\n\n"
        "def register(admin):\n"
        f"    admin.register({name.capitalize()}Item, {name.capitalize()}ItemAdmin)\n",
        encoding="utf-8",
    )
    console.print(f"Created [bold]{name}/[/bold]. In main.py: [bold]app.include_app({name!r})[/bold]")


@app.command("check")
def check_project(
    root: Path = typer.Option(Path("."), "--root"),
    deploy: bool = typer.Option(False, "--deploy", help="Treat production rules as required."),
) -> None:
    """Security and config checklist. Safe to run anytime."""
    from pyron.checks import run_checks

    rows = run_checks(root.resolve(), deploy=deploy)
    worst = "ok"
    for level, msg in rows:
        color = {"ok": "green", "warn": "yellow", "error": "red"}[level]
        console.print(f"[{color}]{level.upper():5}[/{color}] {msg}")
        if level == "error":
            worst = "error"
        elif level == "warn" and worst != "error":
            worst = "warn"
    if worst == "error":
        raise typer.Exit(1)


@app.command()
def createsuperuser(
    username: str = typer.Option(..., prompt=True, help="Root username."),
    password: str = typer.Option(
        ...,
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Root password (prompted).",
    ),
    database: Optional[str] = typer.Option(None, "--database", help="SQLAlchemy URL."),
) -> None:
    """Create the first root operator for the admin panel (`/admin`)."""
    from pyron.admin import AdminSite
    from pyron.admin import auth
    from sqlmodel import select

    engine = _cli_engine(database)
    site = AdminSite(engine=engine)
    site.ensure_tables()
    Model = site.user_model()
    with site.session() as db:
        existing = db.exec(select(Model).where(Model.username == username)).first()
        if existing:
            console.print(f"[red]{username} already exists.[/red]")
            raise typer.Exit(1)
        db.add(
            Model(
                username=username,
                password_hash=auth.hash_password(password),
                is_root=True,
                is_active=True,
            )
        )
        db.commit()
    console.print(f"Root [bold]{username}[/bold] can sign in at /admin")


def _cli_engine(database: str | None):
    from pyron.db import create_engine

    if database:
        return create_engine(database)
    for name in ("bookstore.db", "pyron.db"):
        if Path(name).is_file():
            return create_engine(f"sqlite:///./{name}")
    return create_engine()


def _candidate_engines(database: str | None):
    from pyron.db import create_engine

    if database:
        return [create_engine(database)]
    engines = []
    seen = set()
    for name in ("pyron.db", "bookstore.db"):
        if Path(name).is_file():
            url = f"sqlite:///./{name}"
            if url not in seen:
                seen.add(url)
                engines.append(create_engine(url))
    return engines or [_cli_engine(None)]


@app.command()
def changepassword(
    username: str = typer.Argument(..., help="Operator username to reset."),
    password: str = typer.Option(
        ...,
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="New password (prompted twice).",
    ),
    database: Optional[str] = typer.Option(None, "--database", help="SQLAlchemy URL."),
) -> None:
    """Set a new password for an admin operator (root or staff)."""
    from pyron.admin import AdminSite
    from pyron.admin import auth
    from sqlmodel import select

    if len(password) < 8:
        console.print("[red]Use at least 8 characters.[/red]")
        raise typer.Exit(1)
    found = None
    site = None
    known: list[str] = []
    for engine in _candidate_engines(database):
        candidate = AdminSite(engine=engine)
        candidate.ensure_tables()
        Model = candidate.user_model()
        with candidate.session() as db:
            known.extend(u.username for u in db.exec(select(Model)).all())
            person = db.exec(select(Model).where(Model.username == username)).first()
        if person is not None:
            found = person
            site = candidate
            break
    if found is None or site is None:
        extra = f" Known operators: {', '.join(sorted(set(known)))}." if known else ""
        console.print(f"[red]No operator named {username}.[/red]{extra}")
        raise typer.Exit(1)
    with site.session() as db:
        Model = site.user_model()
        person = db.exec(select(Model).where(Model.username == username)).first()
        person.password_hash = auth.hash_password(password)
        db.add(person)
        db.commit()
    console.print(f"Password updated for [bold]{username}[/bold]. Sign in at /admin")


@app.command()
def build(
    frontend: Optional[Path] = typer.Option(
        None, "--frontend", help="Frontend directory containing package.json."
    ),
) -> None:
    """Build the frontend (Vite) if present; otherwise print the Python package layout."""
    root = Path.cwd()
    fe = frontend or root / "frontend"
    if (fe / "package.json").is_file():
        console.print(f"Building Vite app in {fe} …")
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            console.print("[red]npm not found on PATH.[/red]")
            raise typer.Exit(1)
        result = subprocess.run([npm, "run", "build"], cwd=fe)
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
        console.print("[green]Frontend build complete.[/green]")
        return
    console.print("No frontend/package.json — nothing to compile.")
    console.print("Python is interpreted; ship the package and the compiled pyron._core wheel.")


@db_app.command("init")
def db_init(
    root: Path = typer.Option(Path("."), "--root"),
) -> None:
    """Write alembic.ini and an env.py wired to SQLModel metadata."""
    from pyron.db import write_alembic_env, write_alembic_ini

    write_alembic_ini(root)
    write_alembic_env(root / "alembic")
    console.print(f"Wrote [bold]{root / 'alembic.ini'}[/bold] and [bold]{root / 'alembic'}[/bold]")


@db_app.command("migrate")
def db_migrate(
    message: str = typer.Option("auto", "-m", "--message"),
    root: Path = typer.Option(Path("."), "--root"),
) -> None:
    """Generate an Alembic revision from SQLModel metadata."""
    from pyron.db import alembic_command

    code = alembic_command(root, "revision", "--autogenerate", "-m", message)
    raise typer.Exit(code)


@db_app.command("upgrade")
def db_upgrade(
    revision: str = typer.Argument("head"),
    root: Path = typer.Option(Path("."), "--root"),
) -> None:
    """Apply Alembic migrations."""
    from pyron.db import alembic_command

    code = alembic_command(root, "upgrade", revision)
    raise typer.Exit(code)


def _write_scaffold(dest: Path, pkg: str, template: str) -> None:
    app_dir = dest / "app"
    app_dir.mkdir(exist_ok=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (dest / "pyproject.toml").write_text(_PYPROJECT.format(pkg=pkg), encoding="utf-8")
    (dest / "README.md").write_text(_README.format(name=dest.name, template=template), encoding="utf-8")
    (dest / ".env.example").write_text("DATABASE_URL=sqlite:///./pyron.db\n", encoding="utf-8")
    (dest / ".gitignore").write_text(
        "__pycache__/\n.venv/\n*.db\n.env\nfrontend/node_modules/\nfrontend/dist/\n",
        encoding="utf-8",
    )

    if template == "api":
        (app_dir / "main.py").write_text(_API_MAIN, encoding="utf-8")
        (app_dir / "models.py").write_text(_MODELS, encoding="utf-8")
        (app_dir / "db.py").write_text(_DB, encoding="utf-8")
        return

    templates = dest / "templates"
    templates.mkdir(exist_ok=True)
    static = dest / "static"
    static.mkdir(exist_ok=True)
    (static / "style.css").write_text(_CSS, encoding="utf-8")
    (templates / "base.html").write_text(_BASE_HTML, encoding="utf-8")
    (templates / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (templates / "404.html").write_text(_NOT_FOUND_HTML, encoding="utf-8")
    (app_dir / "main.py").write_text(_SSR_MAIN, encoding="utf-8")
    (app_dir / "models.py").write_text(_MODELS, encoding="utf-8")
    (app_dir / "db.py").write_text(_DB, encoding="utf-8")

    if template == "fullstack":
        fe = dest / "frontend"
        src = fe / "src"
        src.mkdir(parents=True, exist_ok=True)
        (fe / "package.json").write_text(_PKG_JSON, encoding="utf-8")
        (fe / "vite.config.js").write_text(_VITE_CONFIG, encoding="utf-8")
        (fe / "index.html").write_text(_VITE_INDEX, encoding="utf-8")
        (src / "main.js").write_text(_VITE_MAIN, encoding="utf-8")
        (src / "style.css").write_text("body { font-family: Georgia, serif; }\n", encoding="utf-8")
        (app_dir / "main.py").write_text(_FULLSTACK_MAIN, encoding="utf-8")


_PYPROJECT = """[project]
name = "{pkg}"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pyron[standard,db]"]

[project.optional-dependencies]
dev = ["pytest", "httpx"]

[tool.pyron]
app = "app.main:app"
"""

_README = """# {name}

A Pyron ({template}) application.

```
python -m pip install -e ".[standard,db]"
pyron dev
```

Open http://127.0.0.1:8000 and http://127.0.0.1:8000/docs
"""

_MODELS = '''from typing import Optional

from sqlmodel import Field, SQLModel


class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = ""
'''

_DB = '''from pyron.db import create_engine, get_session, init_db

engine = create_engine()
SessionDep = get_session(engine)


def setup() -> None:
    from app import models as _models  # noqa: F401

    init_db(engine)
'''

_API_MAIN = '''from pyron import HTTPException, Pyron
from pydantic import BaseModel, Field

from app.db import setup

app = Pyron(title="Pyron API", version="0.1.0", description="Generated by `pyron init`.")


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


class ItemOut(ItemIn):
    id: int


_DB: dict[int, ItemOut] = {}
_NEXT = 1


@app.on_event("startup")
def _startup() -> None:
    setup()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items", response_model=list)
async def list_items() -> list[ItemOut]:
    return list(_DB.values())


@app.post("/items", status_code=201)
async def create_item(item: ItemIn) -> ItemOut:
    global _NEXT
    out = ItemOut(id=_NEXT, **item.model_dump())
    _DB[_NEXT] = out
    _NEXT += 1
    return out


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> ItemOut:
    if item_id not in _DB:
        raise HTTPException(404, "That item does not exist.")
    return _DB[item_id]
'''

_SSR_MAIN = '''from pyron import HTTPException, ModelAdmin, Pyron
from pydantic import BaseModel, Field
from starlette.requests import Request

from app.db import engine, setup
from app.models import Item

app = Pyron(
    title="Pyron",
    version="0.2.0",
    templates="templates",
    static_dir="static",
    admin=True,
    admin_engine=engine,
)

class ItemAdmin(ModelAdmin):
    list_display = ["id", "title"]
    search_fields = ["title"]

app.admin.register(Item, ItemAdmin)


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


_ITEMS: list[dict] = []


@app.on_event("startup")
def _startup() -> None:
    setup()


@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {"items": _ITEMS})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/items")
async def list_items() -> list[dict]:
    return _ITEMS


@app.post("/api/items", status_code=201)
async def create_item(item: ItemIn) -> dict:
    rec = {"id": len(_ITEMS) + 1, **item.model_dump()}
    _ITEMS.append(rec)
    return rec


@app.get("/api/items/{item_id}")
async def get_item(item_id: int) -> dict:
    for rec in _ITEMS:
        if rec["id"] == item_id:
            return rec
    raise HTTPException(404, "That item does not exist.")
'''

_FULLSTACK_MAIN = '''import os

from pyron import Pyron
from pyron.vite import Vite
from pydantic import BaseModel, Field
from starlette.requests import Request

dev = os.environ.get("PYRON_ENV", "dev") != "production"
vite = Vite(
    dev=dev,
    dev_server="http://127.0.0.1:5173",
    manifest_path="frontend/dist/.vite/manifest.json",
    public_base="/static-fe/",
)

app = Pyron(
    title="Pyron Fullstack",
    version="0.1.0",
    templates="templates",
    static_dir="static",
    vite=vite,
)


class ItemIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""


@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {"items": []})


@app.get("/api/items")
async def list_items() -> list[dict]:
    return []


@app.post("/api/items")
async def create_item(item: ItemIn) -> dict:
    return {"id": 1, **item.model_dump()}
'''

_BASE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{% block title %}Pyron{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css"/>
  {% block head %}{% endblock %}
</head>
<body>
  <header class="site-header">
    <a class="mark" href="/">Pyron</a>
    <nav>
      <a href="/docs">API docs</a>
      <a href="/admin">Admin panel</a>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
"""

_INDEX_HTML = """{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
  <h1>It works.</h1>
  {% if items %}
    <ul>
    {% for item in items %}
      <li>{{ item.title }}</li>
    {% endfor %}
    </ul>
  {% else %}
    <p class="empty">You have not added any items yet. POST one to <code>/api/items</code> or open <a href="/docs">the API docs</a>.</p>
  {% endif %}
{% endblock %}
"""

_NOT_FOUND_HTML = """{% extends "base.html" %}
{% block title %}Not found{% endblock %}
{% block content %}
  <h1>This page is not here</h1>
  <p>No route matches <code>{{ path }}</code>. Try the <a href="/">home page</a>.</p>
{% endblock %}
"""

_CSS = """:root {
  --ink: #1a1512;
  --paper: #f4ede4;
  --ember: #e85d04;
  --muted: #7a6a5c;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--paper); color: var(--ink); font: 18px/1.5 Georgia, "Times New Roman", serif; }
.site-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; border-bottom: 1px solid #e2d6c8; }
.mark { font-weight: 700; color: var(--ember); text-decoration: none; letter-spacing: 0.04em; }
nav a { color: var(--ink); }
main { max-width: 42rem; margin: 2.5rem auto; padding: 0 1.5rem; }
.empty { color: var(--muted); }
code { font-family: ui-monospace, Consolas, monospace; font-size: 0.9em; }
"""

_PKG_JSON = """{
  "name": "pyron-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "vite": "^6.0.0"
  }
}
"""

_VITE_CONFIG = """import { defineConfig } from "vite";

export default defineConfig({
  server: { port: 5173, strictPort: true },
  build: { manifest: true, outDir: "dist", rollupOptions: { input: "src/main.js" } },
});
"""

_VITE_INDEX = """<!doctype html>
<html>
  <head><meta charset="utf-8"/><title>Pyron frontend</title></head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
"""

_VITE_MAIN = """import "./style.css";

const root = document.getElementById("app");
root.innerHTML = "<p>Pyron + Vite is running.</p>";
"""


def main() -> None:
    app()


if __name__ == "__main__":
    main()
