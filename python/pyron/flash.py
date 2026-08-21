"""One-shot messages for HTML pages. Survives a 303 redirect. No admin required."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, unquote

from starlette.requests import Request
from starlette.responses import Response

from pyron.responses import RedirectResponse

COOKIE = "pyron_flash"


def set_flash(response: Response, text: str, *, kind: str = "ok") -> None:
    payload = quote(json.dumps({"kind": kind, "text": text}, ensure_ascii=False), safe="")
    response.set_cookie(COOKIE, payload, httponly=True, samesite="lax", path="/", max_age=120)


def pop_flash(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        data = json.loads(unquote(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("text"):
        return None
    return {"kind": str(data.get("kind") or "ok"), "text": str(data["text"])}


def clear_flash(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def flash(response: Response, text: str, *, kind: str = "ok") -> Response:
    """Attach a message to any response (usually a redirect)."""
    set_flash(response, text, kind=kind)
    return response


def redirect(url: str, *, message: str | None = None, kind: str = "ok", status_code: int = 303) -> RedirectResponse:
    """303 to `url`, optionally with a flash the next page can show."""
    resp = RedirectResponse(url, status_code=status_code)
    if message:
        set_flash(resp, message, kind=kind)
    return resp
