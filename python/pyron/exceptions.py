"""HTTP and validation errors raised by handlers and the framework."""

from __future__ import annotations

from typing import Any


class HTTPException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = "Not Found" if detail is None and status_code == 404 else detail
        if self.detail is None:
            self.detail = _phrase(status_code)
        self.headers = headers or {}
        super().__init__(f"{status_code}: {self.detail}")


class ValidationException(HTTPException):
    def __init__(self, errors: list[dict[str, Any]], *, status_code: int = 422) -> None:
        self.errors = errors
        super().__init__(status_code=status_code, detail=errors)


def _phrase(code: int) -> str:
    return {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        415: "Unsupported Media Type",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }.get(code, "Error")
