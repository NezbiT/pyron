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
