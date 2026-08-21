"""Vite integration — proxy the dev server, resolve hashed assets in prod.

Frontend-agnostic: the same middleware works for React, Vue, Svelte, or
vanilla JS as long as Vite writes a `manifest.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


class Vite:
    def __init__(
        self,
        *,
        dev: bool = True,
        dev_server: str = "http://127.0.0.1:5173",
        manifest_path: str | Path | None = None,
        public_base: str = "/",
    ) -> None:
        self.dev = dev
        self.dev_server = dev_server.rstrip("/")
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.public_base = public_base.rstrip("/") + "/"
        self._manifest: dict[str, Any] | None = None

    def asset_url(self, entry: str) -> str:
        if self.dev:
            return f"{self.dev_server}/{entry.lstrip('/')}"
        rec = self._lookup(entry)
        file = rec.get("file", entry)
        return self.public_base + file.lstrip("/")

    def tags(self, entry: str) -> str:
        """HTML tags to drop in `<head>` / before `</body>`."""
        if self.dev:
            client = f"{self.dev_server}/@vite/client"
            src = f"{self.dev_server}/{entry.lstrip('/')}"
            return (
                f'<script type="module" src="{client}"></script>\n'
                f'<script type="module" src="{src}"></script>'
            )
        rec = self._lookup(entry)
        parts: list[str] = []
        for css in rec.get("css") or []:
            parts.append(f'<link rel="stylesheet" href="{self.public_base}{css}">')
        file = rec.get("file")
        if file:
            parts.append(f'<script type="module" src="{self.public_base}{file}"></script>')
        return "\n".join(parts)

    def _lookup(self, entry: str) -> dict[str, Any]:
        if self._manifest is None:
            self._manifest = self._load_manifest()
        if entry in self._manifest:
            return self._manifest[entry]
        # Vite keys are often "src/main.ts"
        alt = entry.lstrip("/")
        if alt in self._manifest:
            return self._manifest[alt]
        return {"file": entry}

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path or not self.manifest_path.is_file():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))


class ViteProxyMiddleware:
    """In development, forward Vite's own URLs to the Vite process."""

    PREFIXES = ("/@vite", "/@fs", "/@id", "/src/", "/node_modules/", "/vite.svg")

    def __init__(self, app: ASGIApp, vite: Vite) -> None:
        self.app = app
        self.vite = vite

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.vite.dev or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if not self._should_proxy(path):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        response = await self._proxy(request, path)
        await response(scope, receive, send)

    def _should_proxy(self, path: str) -> bool:
        if path in {"/@react-refresh", "/@vite/client"}:
            return True
        return any(path.startswith(p) for p in self.PREFIXES)

    async def _proxy(self, request: Request, path: str) -> Response:
        try:
            import httpx
        except ImportError:
            return Response(
                "Vite proxy requires httpx. pip install httpx",
                status_code=503,
                media_type="text/plain",
            )
        url = self.vite.dev_server + path
        if request.url.query:
            url += "?" + request.url.query
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                upstream = await client.request(
                    request.method,
                    url,
                    headers=_forward_headers(request),
                    content=await request.body(),
                )
        except httpx.ConnectError:
            return Response(
                f"Vite dev server is not running at {self.vite.dev_server}. Start it with `npm run dev`.",
                status_code=502,
                media_type="text/plain",
            )
        headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}
        }
        return Response(upstream.content, status_code=upstream.status_code, headers=headers)


def _forward_headers(request: Request) -> dict[str, str]:
    skip = {"host", "content-length"}
    out = {k: v for k, v in request.headers.items() if k.lower() not in skip}
    host = urlsplit(request.url._url).netloc if hasattr(request.url, "_url") else ""
    if host:
        out.setdefault("X-Forwarded-Host", host)
    return out
