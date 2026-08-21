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
    name: Optional[str] = typer.Argument(
        None,
        help="Folder name. Use 'app' (or omit) to answer: project name, what it is about, what people add.",
    ),
    template: str = typer.Option(
        "ssr",
        "--template",
        "-t",
        help="Project shape: api | ssr | desk | fullstack.",
    ),
    title: Optional[str] = typer.Option(None, "--title", help="Project title (skips that prompt)."),
    about: Optional[str] = typer.Option(None, "--about", help="What the app is for (one or two sentences)."),
    noun: Optional[str] = typer.Option(None, "--noun", help="What people add, e.g. dishes, kits, classes."),
    force: bool = typer.Option(False, "--force", help="Overwrite the target directory if it exists."),
) -> None:
    """Create a new app. `pyron init app` asks questions and seeds 10 records."""
    from pyron.scaffold import Brief, seed_items, slugify, write_app

    if template not in TEMPLATES:
        raise typer.BadParameter(f"template must be one of {TEMPLATES}")
    label = template
    if template == "desk":
        template = "ssr"
    wizard = name is None or name.strip().lower() == "app"
    if wizard:
        title = (title or typer.prompt("Project name")).strip()
        about = (about or typer.prompt("What is it about")).strip()
        noun = (noun or typer.prompt("What do people add (one word)", default="items")).strip() or "items"
        dest = Path(slugify(title)).resolve()
    else:
        dest = Path(name).resolve()
        title = (title or dest.name.replace("-", " ").replace("_", " ")).strip()
        about = (about or f"A {title} app.").strip()
        noun = (noun or "items").strip() or "items"
    if not title:
        console.print("[red]A project name is required.[/red]")
        raise typer.Exit(1)
    brief = Brief(title=title, about=about, noun=noun, folder=dest.name)
    if dest.exists() and any(dest.iterdir()) and not force:
        console.print(f"[red]{dest} is not empty.[/red] Pass --force to overwrite.")
        raise typer.Exit(1)
    write_app(dest, brief, template=template)
    seeds = seed_items(brief)
    table = Table(title=f"Created {dest.name}", show_header=False, box=None)
    table.add_row("title", brief.title)
    table.add_row("about", brief.about)
    table.add_row(brief.plural, f"{len(seeds)} starter records")
    table.add_row("template", label)
    table.add_row("core", CORE)
    console.print(table)
    extra = "  npm install && npm run dev   (second terminal, fullstack only)\n" if template == "fullstack" else ""
    console.print(
        Panel(
            f"[bold]Next[/bold]\n"
            f"  cd {dest.name}\n"
            f"  pyron dev\n"
            f"{extra}\n"
            "Then:\n"
            "  http://127.0.0.1:8000        pages (HTML form + 10 records)\n"
            "  http://127.0.0.1:8000/docs   API\n"
            + ("  http://127.0.0.1:8000/admin  panel (first visit creates root)\n" if label in {"ssr", "desk", "app"} else ""),
            title=brief.title,
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
    console.print(f"  http://{host}:{port}/")
    console.print(f"  http://{host}:{port}/docs")
    console.print(f"  http://{host}:{port}/admin")
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

A Pyron ({template}) app: HTML pages, JSON API, optional admin — same models.

```
pyron dev
```

- http://127.0.0.1:8000 — pages (add an item in the form)
- http://127.0.0.1:8000/docs — API
- http://127.0.0.1:8000/admin — panel (first visit creates root)

If `sqlmodel` is missing: `python -m pip install "pyron[db]"`
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

_SSR_MAIN = '''from pydantic import BaseModel, Field
from sqlmodel import Session, select
from starlette.requests import Request

from app.db import engine, setup
from app.models import Item
from pyron import Form, HTTPException, ModelAdmin, Pyron, redirect

app = Pyron(
    title="Pyron",
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


def _items() -> list[Item]:
    with Session(engine) as db:
        return list(db.exec(select(Item).order_by(Item.id.desc())).all())


@app.on_event("startup")
def _startup() -> None:
    setup()


@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {"items": _items()})


@app.post("/")
async def add_item(title: str = Form(), description: str = Form("")):
    title = title.strip()
    if not title:
        return redirect("/", message="A title is required.", kind="err")
    with Session(engine) as db:
        db.add(Item(title=title, description=description.strip()))
        db.commit()
    return redirect("/", message=f"Added “{title}”.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/items")
async def list_items() -> list[dict]:
    return [{"id": i.id, "title": i.title, "description": i.description} for i in _items()]


@app.post("/api/items", status_code=201)
async def create_item(item: ItemIn) -> dict:
    with Session(engine) as db:
        row = Item(title=item.title, description=item.description)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "title": row.title, "description": row.description}


@app.get("/api/items/{item_id}")
async def get_item(item_id: int) -> dict:
    with Session(engine) as db:
        row = db.get(Item, item_id)
    if row is None:
        raise HTTPException(404, "That item does not exist.")
    return {"id": row.id, "title": row.title, "description": row.description}
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
      <a href="/docs">API</a>
      <a href="/admin">Admin</a>
    </nav>
  </header>
  <main>
    {% if flash %}
      <p class="flash flash-{{ flash.kind }}" role="status">{{ flash.text }}</p>
    {% endif %}
    {% block content %}{% endblock %}
  </main>
</body>
</html>
"""

_INDEX_HTML = """{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
  <h1>Items</h1>
  <p class="lede">This page, <a href="/docs">/docs</a>, and <a href="/admin">/admin</a> use the same table.</p>
  <form method="post" action="/" class="stack">
    <div class="field">
      <label for="title">Title</label>
      <input id="title" name="title" required maxlength="200" autocomplete="off"/>
    </div>
    <div class="field">
      <label for="description">Description <span class="opt">(optional)</span></label>
      <input id="description" name="description" maxlength="400"/>
    </div>
    <button class="btn" type="submit">Add item</button>
  </form>
  {% if items %}
    <ul class="list">
    {% for item in items %}
      <li><strong>{{ item.title }}</strong>{% if item.description %} — {{ item.description }}{% endif %}</li>
    {% endfor %}
    </ul>
  {% else %}
    <p class="empty">No items yet. Use the form — you do not need the API or the admin for the first one.</p>
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
  --ink: #1a1a1a;
  --paper: #f7f8fa;
  --ember: #c2410c;
  --muted: #6c707e;
  --line: #d3d5db;
  --card: #fff;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 ui-sans-serif, system-ui, sans-serif; }
.site-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; border-bottom: 1px solid var(--line); background: var(--card); }
.mark { font-weight: 700; color: var(--ember); text-decoration: none; letter-spacing: 0.06em; text-transform: uppercase; font-size: 0.9rem; }
nav { display: flex; gap: 1rem; }
nav a { color: var(--ink); min-height: 44px; display: inline-flex; align-items: center; }
main { max-width: 36rem; margin: 2.2rem auto; padding: 0 1.5rem 3rem; }
h1 { font-size: 1.8rem; margin: 0 0 0.35rem; }
.lede { color: var(--muted); margin: 0 0 1.4rem; }
.stack { display: flex; flex-direction: column; gap: 0.85rem; margin: 0 0 1.5rem; }
.field label { display: block; font-weight: 600; margin: 0 0 0.3rem; }
.opt { font-weight: 400; color: var(--muted); }
.field input {
  width: 100%; font: inherit; padding: 0.55rem 0.7rem;
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
}
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  min-height: 44px; padding: 0.45rem 0.95rem; width: fit-content;
  background: var(--ember); color: #fff; border: 0; font: inherit; cursor: pointer;
}
.btn:hover { filter: brightness(1.08); }
.list { padding: 0; margin: 0; list-style: none; }
.list li { padding: 0.7rem 0; border-bottom: 1px solid var(--line); }
.empty { color: var(--muted); }
.flash { padding: 0.65rem 0.9rem; margin: 0 0 1rem; border: 1px solid #2e7d32; background: #f0fdf4; }
.flash-err { border-color: var(--ember); background: #fff4ed; }
code { font-family: ui-monospace, "JetBrains Mono", Consolas, monospace; font-size: 0.9em; }
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
