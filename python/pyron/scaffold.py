"""Generate a unique Pyron app from a name + what it is about — not a bookstore clone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Brief:
    title: str
    about: str
    noun: str
    folder: str

    @property
    def pkg(self) -> str:
        return self.folder.replace("-", "_")

    @property
    def class_name(self) -> str:
        return _class_name(self.noun)

    @property
    def slug(self) -> str:
        return _slug(self.class_name)

    @property
    def plural(self) -> str:
        return _plural_label(self.noun)

    @property
    def singular(self) -> str:
        return _singular_label(self.noun)


def slugify(text: str) -> str:
    raw = text.strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-") or "app"


def _class_name(noun: str) -> str:
    word = _singular_label(noun)
    parts = re.split(r"[^A-Za-z0-9]+", word)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Item"


def _singular_label(noun: str) -> str:
    w = noun.strip() or "item"
    low = w.lower()
    if low.endswith("ies") and len(low) > 3:
        return w[:-3] + "y"
    if low.endswith("ses") and len(low) > 3:
        return w[:-2]
    if low.endswith("s") and not low.endswith("ss") and len(low) > 1:
        return w[:-1]
    return w


def _plural_label(noun: str) -> str:
    w = noun.strip() or "items"
    if w.lower().endswith("s"):
        return w
    if w.lower().endswith("y") and len(w) > 1 and w[-2].lower() not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def _slug(class_name: str) -> str:
    out = []
    for i, ch in enumerate(class_name):
        if ch.isupper() and i and class_name[i - 1].islower():
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


_STOP = frozenset(
    "the and for with that this from your our are was were will just about into over more some "
    "them they have been also than then when what which their there here into onto such only "
    "very really using make made help helps people person".split()
)

_DOMAINS: list[tuple[tuple[str, ...], list[tuple[str, str]]]] = [
    (
        ("store", "shop", "tienda", "product", "producto", "catalogo", "catálogo", "ecommerce", "e-commerce", "mercado", "venta"),
        [
            ("Canvas tote", "Heavy cotton, one pocket inside. Holds a laptop without sagging."),
            ("Wool beanie", "Unstructured. Wash cold. The color that actually matches a black coat."),
            ("Desk lamp", "Warm bulb included. Arm stays where you put it."),
            ("Ceramic mug set", "Two cups. Thick rim. Safe in the dishwasher, not the microwave."),
            ("Notebook A5", "Numbered pages, no dated planner. Lies flat."),
            ("Leather card sleeve", "Three slots. Gets better scuffs, not worse ones."),
            ("Linen tea towel", "One for the rail, one in the drawer. They look the same on purpose."),
            ("Wall hook pair", "Brass. Screws in the bag. Holds a coat, not a bike."),
            ("Daypack 18L", "No extra straps. Water bottle on the side that you can actually reach."),
            ("Candle — cedar", "Burns even. Lid doubles as a coaster when it is out."),
        ],
    ),
    (
        ("cafe", "coffee", "espresso", "bakery", "pastry", "menu", "dish", "food", "restaurant", "kitchen"),
        [
            ("House espresso", "The everyday cup. Pulls short, drinks well with milk."),
            ("Season oat latte", "Oat milk, a pinch of salt, no syrup unless you ask."),
            ("Sourdough loaf", "Baked before open. Six loaves; when they go, they go."),
            ("Almond croissant", "Butter, not oil. Sold until noon."),
            ("Tomato toast", "Ripe tomato, olive oil, flaky salt on thick toast."),
            ("Weekend granola", "Toasted oats, seeds, yogurt if you want it."),
            ("Iced filter", "Cooled, not drowned. Lemon twist optional."),
            ("Staff soup", "Changes with whatever the market had that morning."),
            ("Dark chocolate cookie", "Sea salt on top. Two is a reasonable order."),
            ("Closing pour-over", "Last hour only. Ask who is on bar."),
        ],
    ),
    (
        ("book", "library", "novel", "poetry", "reading", "catalog", "author"),
        [
            ("First edition notes", "A working copy, not a shrine. Margin pencil welcome."),
            ("Staff shelf", "What this room actually reads, not what looks clever."),
            ("Rainy afternoon novel", "Plot enough to forget the weather."),
            ("Local history pamphlet", "One neighborhood, one decade, no filler."),
            ("Poetry for the commute", "Short enough to finish between stops."),
            ("Out of print cookbook", "Stains are part of the record."),
            ("Kids' atlas", "Maps you can unfold on the floor."),
            ("Field guide", "Leaves, birds, or stones — pick the edition."),
            ("Essay stack", "Three writers who argue in complete sentences."),
            ("The repair manual", "How the thing actually comes apart."),
        ],
    ),
    (
        ("job", "hiring", "career", "role", "vacancy", "talent"),
        [
            ("Front-of-house lead", "Open the floor, close the till, teach two people."),
            ("Weekend producer", "Ships Friday notes before anyone asks."),
            ("Junior repair tech", "You like taking things apart without losing the screws."),
            ("Community host", "Names, not funnels. Three events a month."),
            ("Inventory owner", "Counts are sacred. Spreadsheets are a tool."),
            ("Morning baker", "In at four. Out before the rush if the loaves behaved."),
            ("Support desk", "Replies in the same language the customer used."),
            ("Studio assistant", "Lights, logs, and the quiet between takes."),
            ("Route driver", "City, not highway. You already know the shortcuts."),
            ("Apprentice buyer", "Taste first, cost second, ego never."),
        ],
    ),
    (
        ("event", "meetup", "workshop", "conference", "gig", "show", "festival"),
        [
            ("Opening night", "Doors at seven. Start when the room is full enough."),
            ("Saturday workshop", "Three hours, one skill, no slides if we can help it."),
            ("Members' breakfast", "Coffee and the week ahead. Sit anywhere."),
            ("Night market stall", "Lights stay up until the last tray is empty."),
            ("Listening session", "One record, start to finish. Phones in the bowl."),
            ("Repair cafe", "Bring the broken thing. Leave with it less broken."),
            ("Kid Saturday", "Craft table, no tickets, parents stay."),
            ("Late set", "Small stage, quieter crowd, better sound."),
            ("Season close", "Thank-yous, leftovers, and the next date on the wall."),
            ("Open studio", "Walk through while work is still wet."),
        ],
    ),
    (
        ("camera", "photo", "film", "lens", "light", "studio", "video", "rental"),
        [
            ("Body + 50mm kit", "The first bag. Charge the battery the night before."),
            ("Interview light set", "Two heads, one softbox, stands that do not wander."),
            ("Field recorder", "Lav + handheld. Check the levels twice."),
            ("Tripod that survives stairs", "Not the lightest. The one you still have in a year."),
            ("Weekend drone slot", "Weather window, not a toy. License on file."),
            ("Black backdrop roll", "Seamless, taped, no wrinkles in the shot."),
            ("Audio bag", "Cables coiled the same way every time."),
            ("Student kit A", "Scratched, honest, fully listed."),
            ("Prime set", "24, 35, 85. No zooms in this bag."),
            ("Overnight charger crate", "Everything comes back at 100% or it does not leave."),
        ],
    ),
    (
        ("gym", "fitness", "yoga", "class", "coach", "training", "studio"),
        [
            ("Dawn strength", "Forty minutes. You will be at work on time."),
            ("Beginner yoga", "No performance. Mats at the back if you come late."),
            ("Lunch mobility", "Hips and thoracic. Eat after, not during."),
            ("Open gym block", "Two hours, no class. Put the plates back."),
            ("Intro to the barbell", "Empty bar until the pattern is boring."),
            ("Saturday long piece", "Conditioning. Water on the left wall."),
            ("Kids hour", "Games that happen to use muscle."),
            ("Coach office", "Fifteen minutes, one question, a next step."),
            ("Recovery night", "Breathing, not sweating. Lights down."),
            ("Foundations", "The class you repeat until you stop needing the demo."),
        ],
    ),
    (
        ("course", "lesson", "class", "school", "learn", "tutor", "cohort"),
        [
            ("Week one: tools", "Install, clone, run. No theory until it boots."),
            ("Office hours", "Bring the error, not the essay."),
            ("Reading that earns its pages", "One chapter, three questions."),
            ("Pair session", "Two people, one keyboard, a timer."),
            ("Critique night", "Work on the wall. Comments on paper."),
            ("Field trip", "We leave the room. Notes still count."),
            ("Make week", "No new lectures. Finish the thing."),
            ("Guest hour", "Someone who does this for a living, not a slide deck."),
            ("Catch-up lab", "If you missed two sessions, start here."),
            ("Show the work", "Public, short, done. Then we eat."),
        ],
    ),
    (
        ("pet", "dog", "cat", "vet", "groom", "animal", "shelter"),
        [
            ("Morning walk loop", "Neighborhood, not the highway. Water in the bag."),
            ("Intro grooming", "Nails, ears, a towel that is actually theirs."),
            ("Quiet boarding night", "One extra blanket. Lights out at the same time as home."),
            ("Meet-and-greet slot", "Thirty minutes. No pressure to leave with anyone."),
            ("Senior diet bag", "Smaller kibble, listed ingredients, no mystery gravy."),
            ("Rainy-day indoor play", "Hall, not crates. Toys that can be washed."),
            ("Vaccine Saturday", "Line is real. Bring the booklet."),
            ("Foster starter kit", "Bowls, lead, a card with the clinic number."),
            ("Cat room hour", "Sit. Do not scoop them up on sight."),
            ("Lost-and-found board", "Photo, date, neighborhood. Updated daily."),
        ],
    ),
]


def seed_items(brief: Brief) -> list[dict[str, str]]:
    hay = f"{brief.title} {brief.about} {brief.noun}".lower()
    for keys, rows in _DOMAINS:
        if any(k in hay for k in keys):
            return [{"title": t, "description": d} for t, d in rows[:10]]
    return _generic_seeds(brief)


def _generic_seeds(brief: Brief) -> list[dict[str, str]]:
    words = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}", brief.about) if w.lower() not in _STOP]
    if len(words) < 2:
        words = re.findall(r"[A-Za-z]{3,}", brief.title) or [brief.singular]
    noun = brief.singular
    about = brief.about.rstrip(".")
    patterns = [
        ("First {n}", "The starting {n} for {about}."),
        ("Featured {n}", "What we put forward when someone asks what {about} looks like."),
        ("Everyday {n}", "The one you use without thinking. Still listed, still ours."),
        ("Weekend {n}", "A slower version. Same craft, more room."),
        ("Staff {n}", "What the people who work here actually pick."),
        ("Season {n}", "Tied to now, not to a catalog photo."),
        ("Repair {n}", "Kept going on purpose. Notes on the card."),
        ("Intro {n}", "If you have never been here, start with this."),
        ("Local {n}", "From this block, or as close as we can honestly claim."),
        ("Closing {n}", "Last on the list for a reason. Ask before it is gone."),
    ]
    used: set[str] = set()
    out: list[dict[str, str]] = []
    for i, (title_pat, desc_pat) in enumerate(patterns):
        hook = words[i % len(words)]
        title = title_pat.format(n=noun) if i % 2 == 0 else f"{hook.capitalize()} {noun}"
        if title.lower() in used:
            title = f"{title} {i + 1}"
        used.add(title.lower())
        out.append(
            {
                "title": title[:200],
                "description": desc_pat.format(n=noun, about=about.lower())[:400],
            }
        )
    return out[:10]


def write_app(dest: Path, brief: Brief, *, template: str = "ssr") -> None:
    dest.mkdir(parents=True, exist_ok=True)
    app_dir = dest / "app"
    app_dir.mkdir(exist_ok=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (dest / "pyproject.toml").write_text(_PYPROJECT.format(pkg=brief.pkg), encoding="utf-8")
    (dest / "README.md").write_text(_readme(brief, template), encoding="utf-8")
    (dest / ".env.example").write_text("DATABASE_URL=sqlite:///./pyron.db\n", encoding="utf-8")
    (dest / ".gitignore").write_text(
        "__pycache__/\n.venv/\n*.db\n.env\nfrontend/node_modules/\nfrontend/dist/\n",
        encoding="utf-8",
    )
    seeds = seed_items(brief)
    if template == "api":
        (app_dir / "main.py").write_text(_api_main(brief, seeds), encoding="utf-8")
        (app_dir / "models.py").write_text(_models(brief), encoding="utf-8")
        (app_dir / "db.py").write_text(_db_py(brief, seeds), encoding="utf-8")
        return

    templates = dest / "templates"
    templates.mkdir(exist_ok=True)
    static = dest / "static"
    static.mkdir(exist_ok=True)
    (static / "style.css").write_text(_CSS, encoding="utf-8")
    (templates / "base.html").write_text(_base_html(brief), encoding="utf-8")
    (templates / "index.html").write_text(_index_html(brief), encoding="utf-8")
    (templates / "404.html").write_text(_NOT_FOUND, encoding="utf-8")
    (app_dir / "models.py").write_text(_models(brief), encoding="utf-8")
    (app_dir / "db.py").write_text(_db_py(brief, seeds), encoding="utf-8")
    (app_dir / "main.py").write_text(_ssr_main(brief), encoding="utf-8")

    if template == "fullstack":
        fe = dest / "frontend"
        src = fe / "src"
        src.mkdir(parents=True, exist_ok=True)
        (fe / "package.json").write_text(_PKG_JSON, encoding="utf-8")
        (fe / "vite.config.js").write_text(_VITE_CONFIG, encoding="utf-8")
        (fe / "index.html").write_text(_VITE_INDEX, encoding="utf-8")
        (src / "main.js").write_text(
            f'import "./style.css";\ndocument.getElementById("app").innerHTML = "<p>{_esc(brief.title)} is running with Vite.</p>";\n',
            encoding="utf-8",
        )
        (src / "style.css").write_text("body { font-family: ui-sans-serif, system-ui, sans-serif; }\n", encoding="utf-8")
        (app_dir / "main.py").write_text(_fullstack_main(brief), encoding="utf-8")


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _py_str(text: str) -> str:
    return repr(text)


def _readme(brief: Brief, template: str) -> str:
    return f"""# {brief.title}

{brief.about}

This is a Pyron ({template}) app. The home form, `/docs`, and `/admin` share the same `{brief.class_name}` table. Ten starter {brief.plural} are loaded on first run. **Pages** in the admin become public views at `/p/about` (Jinja2).

```
pyron dev
```

- http://127.0.0.1:8000 — add a {brief.singular} in the form
- http://127.0.0.1:8000/docs — JSON
- http://127.0.0.1:8000/admin — panel (first visit creates root)
- http://127.0.0.1:8000/p/about — CMS page (edit under Pages)

If `sqlmodel` is missing: `python -m pip install "pyron[db]"`
"""


def _models(brief: Brief) -> str:
    return (
        "from typing import Optional\n\n"
        "from sqlmodel import Field, SQLModel\n\n\n"
        f"class {brief.class_name}(SQLModel, table=True):\n"
        "    id: Optional[int] = Field(default=None, primary_key=True)\n"
        "    title: str\n"
        '    description: str = ""\n'
    )


def _db_py(brief: Brief, seeds: list[dict[str, str]]) -> str:
    rows = ",\n        ".join(
        f"{brief.class_name}(title={_py_str(s['title'])}, description={_py_str(s['description'])})" for s in seeds
    )
    return f"""from pyron.db import create_engine, get_session, init_db
from sqlmodel import Session, select

from app.models import {brief.class_name}

engine = create_engine()
SessionDep = get_session(engine)


def setup() -> None:
    init_db(engine)
    with Session(engine) as db:
        if db.exec(select({brief.class_name})).first() is not None:
            return
        db.add_all(
        [
        {rows}
        ]
        )
        db.commit()
"""


def _ssr_main(brief: Brief) -> str:
    c = brief.class_name
    return f'''from pydantic import BaseModel, Field
from sqlmodel import Session, select
from starlette.requests import Request

from app.db import engine, setup
from app.models import {c}
from pyron import Form, HTTPException, ModelAdmin, Pyron, redirect

app = Pyron(
    title={_py_str(brief.title)},
    description={_py_str(brief.about)},
    templates="templates",
    static_dir="static",
    admin=True,
    admin_engine=engine,
)


class {c}Admin(ModelAdmin):
    list_display = ["id", "title"]
    search_fields = ["title"]
    verbose_name = {_py_str(brief.singular)}
    verbose_name_plural = {_py_str(brief.plural)}


app.admin.register({c}, {c}Admin)


class {c}In(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


def _rows() -> list[{c}]:
    with Session(engine) as db:
        return list(db.exec(select({c}).order_by({c}.id.desc())).all())


@app.on_event("startup")
def _startup() -> None:
    setup()


@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {{"items": _rows()}})


@app.post("/")
async def add_item(title: str = Form(), description: str = Form("")):
    title = title.strip()
    if not title:
        return redirect("/", message="A title is required.", kind="err")
    with Session(engine) as db:
        db.add({c}(title=title, description=description.strip()))
        db.commit()
    return redirect("/", message="Added “{{0}}”.".format(title))


@app.get("/health")
async def health() -> dict[str, str]:
    return {{"status": "ok"}}


@app.get("/api/items")
async def list_items() -> list[dict]:
    return [{{"id": i.id, "title": i.title, "description": i.description}} for i in _rows()]


@app.post("/api/items", status_code=201)
async def create_item(payload: {c}In) -> dict:
    with Session(engine) as db:
        row = {c}(title=payload.title, description=payload.description)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {{"id": row.id, "title": row.title, "description": row.description}}


@app.get("/api/items/{{item_id}}")
async def get_item(item_id: int) -> dict:
    with Session(engine) as db:
        row = db.get({c}, item_id)
    if row is None:
        raise HTTPException(404, "That {brief.singular} does not exist.")
    return {{"id": row.id, "title": row.title, "description": row.description}}
'''


def _api_main(brief: Brief, seeds: list[dict[str, str]]) -> str:
    seeded = ",\n    ".join(
        f"{i + 1}: {{'id': {i + 1}, 'title': {_py_str(s['title'])}, 'description': {_py_str(s['description'])}}}"
        for i, s in enumerate(seeds)
    )
    return f'''from pyron import HTTPException, Pyron
from pydantic import BaseModel, Field

app = Pyron(title={_py_str(brief.title)}, description={_py_str(brief.about)})


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


_DB: dict[int, dict] = {{
    {seeded}
}}
_NEXT = {len(seeds) + 1}


@app.get("/health")
async def health() -> dict[str, str]:
    return {{"status": "ok"}}


@app.get("/items")
async def list_items() -> list[dict]:
    return list(_DB.values())


@app.post("/items", status_code=201)
async def create_item(item: ItemIn) -> dict:
    global _NEXT
    rec = {{"id": _NEXT, **item.model_dump()}}
    _DB[_NEXT] = rec
    _NEXT += 1
    return rec


@app.get("/items/{{item_id}}")
async def get_item(item_id: int) -> dict:
    if item_id not in _DB:
        raise HTTPException(404, "That {brief.singular} does not exist.")
    return _DB[item_id]
'''


def _fullstack_main(brief: Brief) -> str:
    return f'''import os

from pyron import Pyron
from pyron.vite import Vite
from starlette.requests import Request

from app.db import setup

dev = os.environ.get("PYRON_ENV", "dev") != "production"
vite = Vite(
    dev=dev,
    dev_server="http://127.0.0.1:5173",
    manifest_path="frontend/dist/.vite/manifest.json",
    public_base="/static-fe/",
)

app = Pyron(
    title={_py_str(brief.title)},
    description={_py_str(brief.about)},
    templates="templates",
    static_dir="static",
    vite=vite,
)


@app.on_event("startup")
def _startup() -> None:
    setup()


@app.get("/")
async def home(request: Request):
    return await app.render(request, "index.html", {{"items": []}})
'''


def _base_html(brief: Brief) -> str:
    t = _html(brief.title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{% block title %}}{{{{ site.name if site and site.name else '{t}' }}}}{{% endblock %}}</title>
  <link rel="stylesheet" href="/static/style.css"/>
  {{% block head %}}{{% endblock %}}
</head>
<body>
  <header class="site-header">
    <a class="mark" href="/">{{{{ site.name if site and site.name else '{t}' }}}}</a>
    <nav>
      {{% for p in site_pages %}}
        <a href="/p/{{{{ p.slug }}}}" {{% if request and request.url.path == '/p/' ~ p.slug %}}aria-current="page"{{% endif %}}>{{{{ p.title }}}}</a>
      {{% endfor %}}
      <a href="/docs">API</a>
      <a href="/admin">Admin</a>
    </nav>
  </header>
  <main>
    {{% if flash %}}
      <p class="flash flash-{{{{ flash.kind }}}}" role="status">{{{{ flash.text }}}}</p>
    {{% endif %}}
    {{% block content %}}{{% endblock %}}
  </main>
  {{% if site and (site.phone or site.hours or site.address or site.email) %}}
  <footer class="site-footer">
    {{% if site.phone %}}<a href="{{{{ site.phone_href }}}}">{{{{ site.phone }}}}</a>{{% endif %}}
    {{% if site.email %}}<a href="mailto:{{{{ site.email }}}}">{{{{ site.email }}}}</a>{{% endif %}}
    {{% if site.hours %}}<span>{{{{ site.hours }}}}</span>{{% endif %}}
    {{% if site.address %}}<span>{{{{ site.address }}}}</span>{{% endif %}}
  </footer>
  {{% endif %}}
</body>
</html>
"""


def _index_html(brief: Brief) -> str:
    return f"""{{% extends "base.html" %}}
{{% block title %}}{_html(brief.plural)}{{% endblock %}}
{{% block content %}}
  <h1>{_html(brief.plural)}</h1>
  <p class="lede">{_html(brief.about)} This page, <a href="/docs">/docs</a>, and <a href="/admin">/admin</a> share the same table. Add About or Contact under <strong>Pages</strong> in the admin — Jinja2 renders them at <code>/p/…</code>.</p>
  <form method="post" action="/" class="stack">
    <div class="field">
      <label for="title">Title</label>
      <input id="title" name="title" required maxlength="200" autocomplete="off"/>
    </div>
    <div class="field">
      <label for="description">Description <span class="opt">(optional)</span></label>
      <input id="description" name="description" maxlength="400"/>
    </div>
    <button class="btn" type="submit">Add {_html(brief.singular)}</button>
  </form>
  {{% if items %}}
    <ul class="list">
    {{% for item in items %}}
      <li><strong>{{{{ item.title }}}}</strong>{{% if item.description %}} — {{{{ item.description }}}}{{% endif %}}</li>
    {{% endfor %}}
    </ul>
  {{% else %}}
    <p class="empty">No {_html(brief.plural)} yet. Use the form — you do not need the API or the admin for the first one.</p>
  {{% endif %}}
{{% endblock %}}
"""


def _html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_NOT_FOUND = """{% extends "base.html" %}
{% block title %}Not found{% endblock %}
{% block content %}
  <h1>This page is not here</h1>
  <p>No route matches <code>{{ path }}</code>. Try the <a href="/">home page</a>.</p>
{% endblock %}
"""

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
.site-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; border-bottom: 1px solid var(--line); background: var(--card); gap: 1rem; flex-wrap: wrap; }
.mark { font-weight: 700; color: var(--ember); text-decoration: none; letter-spacing: 0.06em; text-transform: uppercase; font-size: 0.9rem; }
nav { display: flex; gap: 0.75rem 1rem; flex-wrap: wrap; }
nav a { color: var(--ink); min-height: 44px; display: inline-flex; align-items: center; text-decoration: none; }
nav a[aria-current="page"] { color: var(--ember); font-weight: 600; }
.page-body p { margin: 0 0 1rem; }
.page-article h1 { margin: 0 0 0.8rem; }
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
.site-footer { max-width: 36rem; margin: 0 auto; padding: 1.2rem 1.5rem 2.4rem; color: var(--muted); font-size: 0.92rem; display: flex; flex-wrap: wrap; gap: 0.5rem 1.1rem; }
.site-footer a { min-height: 44px; display: inline-flex; align-items: center; }
"""

_PKG_JSON = """{
  "name": "pyron-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build" },
  "devDependencies": { "vite": "^6.0.0" }
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
  <head><meta charset="utf-8"/><title>frontend</title></head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
"""
