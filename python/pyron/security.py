"""Security defaults: headers, host check, login throttle, password rules.

These run whether the app is API-only or has the desk. Features you did not
enable stay off; headers still go out.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from pyron.settings import Settings, load_settings

COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "qwertyui",
        "qwerty123",
        "letmein1",
        "admin123",
        "welcome1",
        "passw0rd",
        "iloveyou",
    }
)

SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "same-origin"),
    ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
    ("X-DNS-Prefetch-Control", "off"),
)


def password_issues(password: str, *, username: str = "", min_length: int = 8) -> list[str]:
    issues: list[str] = []
    if len(password) < min_length:
        issues.append(f"Use at least {min_length} characters.")
    if username and password.lower() == username.lower():
        issues.append("Do not use your username as the password.")
    if password.lower() in COMMON_PASSWORDS:
        issues.append("That password is on the common-password list. Pick another.")
    return issues


class LoginThrottle:
    """Login lockout. Uses Redis when REDIS_URL is set, otherwise process memory."""

    def __init__(self, max_fails: int = 8, window: int = 900) -> None:
        self.max_fails = max_fails
        self.window = window

    def _ckey(self, key: str) -> str:
        return f"pyron:login:{key}"

    def _bucket(self, key: str) -> list[float]:
        from pyron.cache import get_cache

        raw = get_cache().get(self._ckey(key))
        if not isinstance(raw, list):
            return []
        now = time.time()
        return [float(t) for t in raw if now - float(t) < self.window]

    def _save(self, key: str, times: list[float]) -> None:
        from pyron.cache import get_cache

        get_cache().set(self._ckey(key), times, ttl=self.window)

    def blocked(self, key: str) -> bool:
        return len(self._bucket(key)) >= self.max_fails

    def fail(self, key: str) -> None:
        times = self._bucket(key)
        times.append(time.time())
        self._save(key, times)

    def success(self, key: str) -> None:
        from pyron.cache import get_cache

        get_cache().delete(self._ckey(key))

    def retry_in(self, key: str) -> int:
        times = self._bucket(key)
        if not times:
            return 0
        oldest = min(times)
        return max(0, int(self.window - (time.time() - oldest)))


login_throttle = LoginThrottle()


def client_key(scope: Scope, *, trust_proxy: bool = False) -> str:
    if trust_proxy:
        headers = Headers(scope=scope)
        forwarded = headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


class SecurityMiddleware:
    """Host allowlist + response headers. Does not change routing."""

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self.settings = settings or load_settings()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host", "")
        hostname = host.split(":")[0].strip().lower()
        allowed = [h.lower() for h in self.settings.allowed_hosts]
        if self.settings.production and allowed and hostname not in allowed:
            await self._reject(send, 400, b"Unknown host.")
            return

        async def send_wrapped(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {k.lower() for k, _ in headers}
                for name, value in SECURITY_HEADERS:
                    if name.lower().encode() not in present:
                        headers.append((name.encode(), value.encode()))
                if self.settings.session_cookie_secure:
                    headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=63072000; includeSubDomains",
                        )
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapped)

    async def _reject(self, send: Send, status: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": body})


_DUMMY_HASH: str | None = None


def dummy_password_hash() -> str:
    """Always run PBKDF2 even when the username is unknown (timing)."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        from pyron.admin.auth import hash_password

        _DUMMY_HASH = hash_password("pyron-not-a-real-account")
    return _DUMMY_HASH


def secret_issues(secret: str, *, production: bool) -> list[str]:
    issues = []
    if production and not secret:
        issues.append("PYRON_SECRET is empty in production. Set a long random value.")
    elif production and len(secret) < 32:
        issues.append("PYRON_SECRET is shorter than 32 characters.")
    return issues


def fingerprint_secret(secret: str) -> str:
    if not secret:
        return "unset"
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def constant_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def ensure_secret_file_private(path: str = ".pyron_secret") -> list[str]:
    issues = []
    if not os.path.isfile(path):
        return issues
    if os.name == "nt":
        return issues
    mode = os.stat(path).st_mode & 0o777
    if mode & 0o077:
        issues.append(f"{path} is readable by others (mode {mode:o}). chmod 600.")
    return issues
