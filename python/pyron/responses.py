"""Re-export Starlette responses plus a JSON helper that uses the Rust serializer."""

from __future__ import annotations

from typing import Any

from starlette.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from pyron._bridge import dumps


class JSONResponse(Response):
    media_type = "application/json"

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        super().__init__(content, status_code, headers, media_type)

    def render(self, content: Any) -> bytes:
        if content is None:
            return b"null"
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        return dumps(content)


__all__ = [
    "FileResponse",
    "HTMLResponse",
    "JSONResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "Response",
    "StreamingResponse",
]
