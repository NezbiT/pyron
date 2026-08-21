"""Auth for any handler. Decorators add; they do not rewrite the function."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from pyron.exceptions import HTTPException
from pyron.responses import JSONResponse, RedirectResponse

_user_var: ContextVar[Any] = ContextVar("pyron_user", default=None)
_request_var: ContextVar[Any] = ContextVar("pyron_request", default=None)


class AnonymousUser:
    username = ""
    is_root = False
    is_active = False
    is_authenticated = False
    id = None
    permissions: frozenset[str] = frozenset()

    def has_perm(self, code: str) -> bool:
        return False


class NotAuthenticated(HTTPException):
    def __init__(self, login_url: str = "/admin/login") -> None:
        self.login_url = login_url
        super().__init__(
            401,
            {
                "message": "You are not signed in.",
                "next": "Sign in, then try again.",
                "login": login_url,
            },
        )


class PermissionDenied(HTTPException):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(
            403,
            {
                "message": f"You need the permission “{permission}” to do this.",
                "next": "Ask root to grant that permission, or sign in as someone who has it.",
                "permission": permission,
            },
        )


class DeskAuthMiddleware:
    """Load the session user onto request.state and a contextvar (API + Desk)."""

    def __init__(self, app: ASGIApp, site: Any) -> None:
        self.app = app
        self.site = site

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        user_token = None
        req_token = None
        if scope["type"] == "http":
            from pyron.admin import auth

            request = Request(scope)
            try:
                sess = auth.read_session(request, self.site.secret)
                user = self.site._user_from_session(sess)
            except Exception:
                user = None
            state = scope.setdefault("state", {})
            packed = user or AnonymousUser()
            if isinstance(state, dict):
                state["user"] = packed
            else:
                setattr(state, "user", packed)
            user_token = _user_var.set(packed)
            req_token = _request_var.set(request)
        try:
            await self.app(scope, receive, send)
        finally:
            if user_token is not None:
                _user_var.reset(user_token)
            if req_token is not None:
                _request_var.reset(req_token)


def current_user(request: Request | None = None) -> Any:
    if request is not None:
        user = getattr(request.state, "user", None)
        if user is not None:
            return user
        st = getattr(request, "scope", {}).get("state") or {}
        if isinstance(st, dict) and st.get("user") is not None:
            return st["user"]
    return _user_var.get() or AnonymousUser()


def current_request() -> Request | None:
    return _request_var.get()


def _wants_html(request: Request | None) -> bool:
    if request is None:
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept.split(",")[0]


def login_required(fn: Callable[..., Any] | None = None, *, redirect: str | None = "/admin/login"):
    """Wrap an existing handler. Public routes stay public if you skip this."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any):
            request = kwargs.get("request") or _pick_request(args) or current_request()
            user = current_user(request)
            if not getattr(user, "is_authenticated", False):
                if _wants_html(request) and redirect:
                    return RedirectResponse(redirect, status_code=303)
                raise NotAuthenticated(redirect or "/admin/login")
            return await func(*args, **kwargs)

        return wrapped

    if fn is not None:
        return decorator(fn)
    return decorator


def permission_required(code: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Require a permission such as ``book.delete``. Root always passes."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any):
            request = kwargs.get("request") or _pick_request(args) or current_request()
            user = current_user(request)
            if not getattr(user, "is_authenticated", False):
                if _wants_html(request):
                    return RedirectResponse("/admin/login", status_code=303)
                raise NotAuthenticated()
            if not user.has_perm(code):
                raise PermissionDenied(code)
            return await func(*args, **kwargs)

        return wrapped

    return decorator


def require_root(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    async def wrapped(*args: Any, **kwargs: Any):
        request = kwargs.get("request") or _pick_request(args) or current_request()
        user = current_user(request)
        if not getattr(user, "is_authenticated", False):
            if _wants_html(request):
                return RedirectResponse("/admin/login", status_code=303)
            raise NotAuthenticated()
        if not getattr(user, "is_root", False):
            raise PermissionDenied("root")
        return await fn(*args, **kwargs)

    return wrapped


def _pick_request(args: tuple[Any, ...]) -> Request | None:
    for a in args:
        if isinstance(a, Request):
            return a
    return None
