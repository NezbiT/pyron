"""Built-in CMS pages: operators add them in /admin, Jinja2 renders the public views.

The body is Markdown (legacy HTML still works). It is never compiled as a Jinja
template (that would be SSTI). Unpublished rows 404 for visitors; signed-in
operators can still preview them.
"""

from __future__ import annotations

import html as htmlmod
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Field, Session, SQLModel, col, select

TEMPLATES_DIR = Path(__file__).resolve().parent / "page_templates"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class Page(SQLModel, table=True):
    __tablename__ = "pyron_page"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=200, description="Heading on the public page.")
    slug: str = Field(
        max_length=80,
        unique=True,
        index=True,
        description="Public URL: /p/your-slug. Letters, numbers, hyphens.",
    )
    body: str = Field(
        default="",
        description="Markdown: **bold**, lists, [links](https://…). Jinja tags stay as text.",
    )
    published: bool = Field(default=True, description="Off → visitors get 404.")
    in_nav: bool = Field(default=True, description="Show a link in the public header.")
    nav_order: int = Field(default=0, description="Lower numbers first in the header.")


@dataclass(frozen=True)
class PageView:
    id: int | None
    title: str
    slug: str
    body: str
    html: str
    published: bool
    in_nav: bool
    nav_order: int


def slugify_page(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = _SLUG_RE.sub("-", raw).strip("-")
    return raw[:80] or "page"


_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
_UL_ITEM = re.compile(r"^[-*]\s+(.+)$")
_SAFE_URL = re.compile(r"^(https?:\/\/|\/|mailto:)", re.I)
_HTML_START = re.compile(
    r"^<(p|h[1-6]|ul|ol|div|article|section|blockquote|table)(\s|/?>)",
    re.I,
)


def _looks_like_html(raw: str) -> bool:
    return bool(_HTML_START.match(raw.lstrip()))


def _safe_url(url: str) -> bool:
    url = htmlmod.unescape(url).strip()
    if url.lower().startswith(("javascript:", "data:")):
        return False
    return bool(_SAFE_URL.match(url))


def _inline(text: str) -> str:
    text = htmlmod.escape(text, quote=False)

    def code(match: re.Match[str]) -> str:
        return f"<code>{match.group(1)}</code>"

    text = re.sub(r"`([^`]+)`", code, text)

    def link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if not _safe_url(url):
            return label
        href = htmlmod.escape(htmlmod.unescape(url), quote=True)
        return f'<a href="{href}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    return text


def render_page_body(source: str) -> str:
    """Markdown → HTML. Legacy bodies that start with a tag pass through."""
    raw = (source or "").replace("\r\n", "\n")
    if not raw.strip():
        return ""
    if _looks_like_html(raw):
        return raw
    chunks: list[str] = []
    for block in re.split(r"\n{2,}", raw.strip()):
        lines = block.split("\n")
        heading = _HEADING.match(lines[0]) if len(lines) == 1 else None
        if heading:
            level = len(heading.group(1)) + 1
            chunks.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue
        items = [_UL_ITEM.match(ln) for ln in lines]
        if items and all(items):
            lis = "".join(f"<li>{_inline(m.group(1).strip())}</li>" for m in items if m)
            chunks.append(f"<ul>{lis}</ul>")
            continue
        para = "<br/>".join(_inline(ln) for ln in lines)
        chunks.append(f"<p>{para}</p>")
    return "\n".join(chunks)


def _as_view(row: Page) -> PageView:
    body = row.body or ""
    return PageView(
        id=row.id,
        title=row.title,
        slug=row.slug,
        body=body,
        html=render_page_body(body),
        published=bool(row.published),
        in_nav=bool(row.in_nav),
        nav_order=int(row.nav_order or 0),
    )


def load_page(engine: Any, slug: str) -> PageView | None:
    if engine is None or not slug:
        return None
    try:
        with Session(engine) as db:
            row = db.exec(select(Page).where(col(Page.slug) == slug)).first()
            return _as_view(row) if row is not None else None
    except Exception:
        return None


def published_pages(engine: Any) -> list[PageView]:
    if engine is None:
        return []
    try:
        with Session(engine) as db:
            rows = db.exec(
                select(Page)
                .where(col(Page.published) == True)  # noqa: E712
                .order_by(col(Page.nav_order), col(Page.title))
            ).all()
            return [_as_view(r) for r in rows]
    except Exception:
        return []


def nav_pages(engine: Any) -> list[dict[str, str]]:
    if engine is None:
        return []
    try:
        with Session(engine) as db:
            rows = db.exec(
                select(Page)
                .where(col(Page.published) == True, col(Page.in_nav) == True)  # noqa: E712
                .order_by(col(Page.nav_order), col(Page.title))
            ).all()
            return [{"title": r.title, "slug": r.slug} for r in rows]
    except Exception:
        return []


def seed_pages(engine: Any, title: str = "Pyron") -> None:
    if engine is None:
        return
    name = (title or "Pyron").strip() or "Pyron"
    with Session(engine) as db:
        try:
            if db.exec(select(Page).limit(1)).first() is not None:
                return
        except Exception:
            return
        db.add(
            Page(
                title="About",
                slug="about",
                body=(
                    f"{name} is this site. Operators add pages in the admin panel; "
                    "Jinja2 renders them for visitors.\n\n"
                    "Edit this text under **Pages**. Contact details belong in **Settings** "
                    "so the header and footer stay in sync."
                ),
                published=True,
                in_nav=True,
                nav_order=10,
            )
        )
        db.add(
            Page(
                title="Contact",
                slug="contact",
                body=(
                    "Replace this with how a visitor should reach you.\n\n"
                    "Phone, hours, and address also live in **Settings** — "
                    "the public footer reads them."
                ),
                published=True,
                in_nav=True,
                nav_order=20,
            )
        )
        db.commit()


def make_page_admin() -> type:
    from pyron.admin.options import ModelAdmin

    class _PageAdmin(ModelAdmin):
        slug = "pages"
        list_display = ["id", "title", "slug", "published", "in_nav"]
        search_fields = ["title", "slug", "body"]
        list_filter = ["published", "in_nav"]
        ordering = "nav_order"
        verbose_name = "Page"
        verbose_name_plural = "Pages"

        def clean(self, values: dict[str, Any]) -> dict[str, Any]:
            title = str(values.get("title") or "").strip()
            if not title:
                raise ValueError("A title is required.")
            values["title"] = title
            raw_slug = str(values.get("slug") or "").strip() or title
            values["slug"] = slugify_page(raw_slug)
            if values["slug"] in {"admin", "docs", "redoc", "static", "api"}:
                raise ValueError("That slug is reserved. Pick another.")
            return values

        def view_on_site(self, obj: Any) -> str | None:
            slug = getattr(obj, "slug", None)
            if slug:
                return f"/p/{slug}"
            return None

    return _PageAdmin


