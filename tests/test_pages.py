import re

import pytest
from httpx import ASGITransport, AsyncClient

from pyron import Pyron
from pyron.admin.inspect import field_specs
from pyron.db import create_engine, init_db
from pyron.pages import Page, render_page_body, slugify_page


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "csrf field missing"
    return m.group(1)


@pytest.fixture
def pages_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'pages.db'}")
    init_db(engine)
    app = Pyron(
        title="Tide Shop",
        admin=True,
        admin_engine=engine,
        templates=str(tmp_path),
        docs_url=None,
        redoc_url=None,
    )
    (tmp_path / "base.html").write_text(
        "<html><body><p class='brand'>{{ site.name }}</p><nav>{% for p in site_pages %}"
        '<a href="/p/{{ p.slug }}">{{ p.title }}</a>{% endfor %}</nav>'
        "{% block content %}{% endblock %}"
        "{% if site and site.phone %}<a href='{{ site.phone_href }}'>{{ site.phone }}</a>{% endif %}"
        "</body></html>",
        encoding="utf-8",
    )
    return app


def test_slugify_page():
    assert slugify_page("About Us") == "about-us"
    assert slugify_page("  Hello!!  ") == "hello"


def test_markdown_body_is_escaped_and_not_jinja():
    html = render_page_body("Hello **Tide** and {{ 7*7 }}.\n\n- one\n- two")
    assert "<strong>Tide</strong>" in html
    assert "{{ 7*7 }}" in html
    assert "49" not in html
    assert "<ul>" in html
    assert "<script>" not in render_page_body("<script>alert(1)</script>")
    legacy = render_page_body("<p>Legacy HTML {{ 7*7 }}</p>")
    assert legacy.startswith("<p>")
    assert "{{ 7*7 }}" in legacy


def test_page_body_widget_is_markdown():
    specs = {s["name"]: s for s in field_specs(Page)}
    assert specs["body"]["widget"] == "markdown"


@pytest.mark.asyncio
async def test_default_pages_render_with_jinja(pages_app):
    transport = ASGITransport(app=pages_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        about = await client.get("/p/about")
        assert about.status_code == 200
        assert "<h1>About</h1>" in about.text
        assert "Tide Shop" in about.text
        assert 'href="/p/about"' in about.text
        assert 'href="/p/contact"' in about.text

        listing = await client.get("/p")
        assert listing.status_code == 200
        assert "About" in listing.text
        assert "Contact" in listing.text


@pytest.mark.asyncio
async def test_pages_on_admin_and_custom_page(pages_app):
    transport = ASGITransport(app=pages_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/", follow_redirects=True)
        csrf = _csrf(gate.text)
        desk = await client.post(
            "/admin/setup",
            data={
                "csrf": csrf,
                "username": "root",
                "password": "correct-horse",
                "confirm": "correct-horse",
            },
            follow_redirects=True,
        )
        assert desk.status_code == 200
        assert "Pages" in desk.text
        assert "Site" in desk.text
        assert "Data" in desk.text
        assert "Settings" in desk.text

        listed = await client.get("/admin/m/pages")
        assert listed.status_code == 200
        assert "About" in listed.text

        form = await client.get("/admin/m/pages/new")
        assert 'name="published"' in form.text
        assert "checked" in form.text
        assert "data-md-preview" in form.text
        csrf = _csrf(form.text)
        added = await client.post(
            "/admin/m/pages/new",
            data={
                "csrf": csrf,
                "title": "Hours",
                "slug": "Hours & Open",
                "body": "<p>Nine to five. {{ 7*7 }} stays literal.</p>",
                "published": "1",
                "in_nav": "1",
                "nav_order": "5",
                "intent": "save",
            },
            follow_redirects=True,
        )
        assert added.status_code == 200
        assert "Hours" in added.text

        public = await client.get("/p/hours-open")
        assert public.status_code == 200
        assert "<h1>Hours</h1>" in public.text
        assert "Nine to five" in public.text
        assert "{{ 7*7 }}" in public.text
        assert "49" not in public.text.replace("200", "")

        md = await client.post(
            "/admin/m/pages/new",
            data={
                "csrf": _csrf((await client.get("/admin/m/pages/new")).text),
                "title": "Markdown hours",
                "slug": "md-hours",
                "body": "Open **nine** to five. {{ 7*7 }}",
                "published": "1",
                "in_nav": "1",
                "nav_order": "6",
                "intent": "save",
            },
            follow_redirects=True,
        )
        assert md.status_code == 200
        rendered = await client.get("/p/md-hours")
        assert "<strong>nine</strong>" in rendered.text
        assert "{{ 7*7 }}" in rendered.text
        assert "49" not in rendered.text.replace("200", "")


@pytest.mark.asyncio
async def test_unpublished_is_404_for_visitors(pages_app):
    transport = ASGITransport(app=pages_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/", follow_redirects=True)
        csrf = _csrf(gate.text)
        await client.post(
            "/admin/setup",
            data={
                "csrf": csrf,
                "username": "root",
                "password": "correct-horse",
                "confirm": "correct-horse",
            },
            follow_redirects=True,
        )
        listed = await client.get("/admin/m/pages")
        assert listed.status_code == 200
        edit = await client.get("/admin/m/pages/1")
        csrf = _csrf(edit.text)
        await client.post(
            "/admin/m/pages/1",
            data={
                "csrf": csrf,
                "title": "About",
                "slug": "about",
                "body": "<p>Hidden draft.</p>",
                "nav_order": "10",
                "intent": "save",
            },
            follow_redirects=True,
        )
        signed_in = await client.get("/p/about")
        assert signed_in.status_code == 200
        assert "Hidden draft" in signed_in.text

        await client.get("/admin/logout")
        visitor = await client.get("/p/about")
        assert visitor.status_code == 404


@pytest.mark.asyncio
async def test_pages_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'nopages.db'}")
    init_db(engine)
    app = Pyron(
        title="API",
        admin=True,
        admin_engine=engine,
        pages=False,
        docs_url=None,
        redoc_url=None,
    )
    assert "pages" not in [b.slug for b in app.admin.models()]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/p/about")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_settings_show_on_the_public_site(pages_app):
    transport = ASGITransport(app=pages_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Accept-Language": "en"}
    ) as client:
        gate = await client.get("/admin/", follow_redirects=True)
        csrf = _csrf(gate.text)
        await client.post(
            "/admin/setup",
            data={
                "csrf": csrf,
                "username": "root",
                "password": "correct-horse",
                "confirm": "correct-horse",
            },
            follow_redirects=True,
        )
        form = await client.get("/admin/settings")
        assert form.status_code == 200
        assert "Site name" in form.text
        csrf = _csrf(form.text)
        saved = await client.post(
            "/admin/settings",
            data={
                "csrf": csrf,
                "name": "Harbor Bindings",
                "tagline": "Used books",
                "phone": "(281) 555-0134",
                "email": "shop@example.com",
                "hours": "Tue–Sat 11–6",
                "address": "The chandlery",
                "website": "example.com",
            },
            follow_redirects=True,
        )
        assert saved.status_code == 200
        assert "Harbor Bindings" in saved.text
        about = await client.get("/p/about")
        assert "Harbor Bindings" in about.text
        assert "tel:2815550134" in about.text
        assert "(281) 555-0134" in about.text

        preview = await client.post(
            "/admin/preview-markdown",
            data={"csrf": _csrf((await client.get("/admin/settings")).text), "body": "**Hi** {{ 7*7 }}"},
        )
        assert preview.status_code == 200
        assert "<strong>Hi</strong>" in preview.text
        assert "{{ 7*7 }}" in preview.text
