"""Jinja2 server-side rendering with request-aware helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request

from pyron.responses import HTMLResponse


class Templates:
    def __init__(
        self,
        directory: str | Path,
        *,
        auto_reload: bool = True,
    ) -> None:
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Jinja2 is required for templates. pip install jinja2") from exc
        self.directory = Path(directory)
        # Keep render() usable from both async handlers and 404 fallbacks.
        # enable_async=True would make Template.render() return a coroutine.
        self.env = Environment(
            loader=FileSystemLoader(str(self.directory)),
            autoescape=select_autoescape(["html", "xml"]),
            auto_reload=auto_reload,
            enable_async=False,
        )
        self.env.globals.setdefault("vite_asset", lambda path: path)
        self._vite = None
        self._extra_dirs: list[Path] = []

    def add_search_path(self, directory: str | Path) -> None:
        path = Path(directory)
        if path in self._extra_dirs:
            return
        try:
            from jinja2 import ChoiceLoader, FileSystemLoader
        except ImportError:  # pragma: no cover
            return
        extra = FileSystemLoader(str(path))
        current = self.env.loader
        if isinstance(current, ChoiceLoader):
            loaders = list(current.loaders)
            if any(getattr(item, "searchpath", None) == extra.searchpath for item in loaders):
                self._extra_dirs.append(path)
                return
            self.env.loader = ChoiceLoader([*loaders, extra])
        else:
            self.env.loader = ChoiceLoader([current, extra])
        self._extra_dirs.append(path)

    def bind_vite(self, vite: Any) -> None:
        self._vite = vite
        self.env.globals["vite_asset"] = vite.asset_url
        self.env.globals["vite_tags"] = vite.tags

    def get_template(self, name: str):
        return self.env.get_template(name)

    async def render(
        self,
        request: Request | None,
        name: str,
        context: dict[str, Any] | None = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        ctx: dict[str, Any] = dict(context or {})
        if request is not None:
            ctx.setdefault("request", request)
            _bind_url_for(ctx, request)
            _bind_flash(ctx, request)
            _bind_site(ctx, request)
        html = self.get_template(name).render(**ctx)
        resp = HTMLResponse(html, status_code=status_code, headers=headers)
        if ctx.get("flash"):
            from pyron.flash import clear_flash

            clear_flash(resp)
        return resp

    def render_sync(
        self,
        request: Request | None,
        name: str,
        context: dict[str, Any] | None = None,
        *,
        status_code: int = 200,
    ) -> HTMLResponse:
        ctx: dict[str, Any] = dict(context or {})
        if request is not None:
            ctx.setdefault("request", request)
            _bind_url_for(ctx, request)
            _bind_flash(ctx, request)
            _bind_site(ctx, request)
        html = self.get_template(name).render(**ctx)
        resp = HTMLResponse(html, status_code=status_code)
        if ctx.get("flash"):
            from pyron.flash import clear_flash

            clear_flash(resp)
        return resp


def _bind_url_for(ctx: dict[str, Any], request: Request) -> None:
    app = request.scope.get("app")
    if app is not None and hasattr(app, "url_for"):
        ctx.setdefault("url_for", app.url_for)


def _bind_flash(ctx: dict[str, Any], request: Request) -> None:
    if "flash" in ctx:
        return
    from pyron.flash import pop_flash

    ctx["flash"] = pop_flash(request)


def _bind_site(ctx: dict[str, Any], request: Request) -> None:
    app = request.scope.get("app")
    admin = getattr(app, "admin", None)
    fallback = getattr(app, "title", None) or "Pyron"
    if "site" not in ctx:
        if admin is None:
            ctx["site"] = None
        else:
            from pyron.siteconfig import load_site

            ctx["site"] = load_site(getattr(admin, "engine", None), fallback=fallback)
    if "site_pages" in ctx:
        return
    if admin is None or not getattr(admin, "pages_enabled", False):
        ctx["site_pages"] = []
        return
    from pyron.pages import nav_pages

    ctx["site_pages"] = nav_pages(getattr(admin, "engine", None))
