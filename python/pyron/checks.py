"""`pyron check` — catch unsafe config before it ships."""

from __future__ import annotations

from pathlib import Path

from pyron.security import ensure_secret_file_private, secret_issues
from pyron.settings import load_settings


def run_checks(root: Path | None = None, *, deploy: bool = False) -> list[tuple[str, str]]:
    """Return (level, message) where level is ok, warn, or error."""
    root = root or Path.cwd()
    cfg = load_settings()
    out: list[tuple[str, str]] = []
    production = cfg.production or deploy

    if cfg.production:
        out.append(("ok", "PYRON_ENV=production"))
    elif deploy:
        out.append(("warn", "check --deploy: PYRON_ENV is not production; applying deploy rules anyway."))
    else:
        out.append(("ok", "PYRON_ENV=dev — docs and detailed login errors are on"))

    for msg in secret_issues(cfg.secret_key, production=production):
        out.append(("error", msg))
    if cfg.secret_key and len(cfg.secret_key) >= 32:
        out.append(("ok", "PYRON_SECRET is set and long enough"))

    for msg in ensure_secret_file_private(str(root / ".pyron_secret")):
        out.append(("warn", msg))

    if production and cfg.expose_docs:
        out.append(
            (
                "warn",
                "OpenAPI /docs is exposed in production. Set PYRON_EXPOSE_DOCS=0 or pass docs_url=None.",
            )
        )
    if production and not cfg.allowed_hosts:
        out.append(("warn", "PYRON_ALLOWED_HOSTS is empty in production. Host header spoofing is unchecked."))
    if production and not cfg.session_cookie_secure:
        out.append(
            (
                "warn",
                "Session cookies are not Secure. Set PYRON_SESSION_SECURE=1 behind HTTPS.",
            )
        )
    if cfg.debug and production:
        out.append(("error", "DEBUG is on in production (PYRON_DEBUG=1). Turn it off."))

    main = root / "app" / "main.py"
    if main.is_file():
        text = main.read_text(encoding="utf-8")
        if "admin=True" in text or 'enable("admin"' in text:
            out.append(("ok", "Admin panel is enabled in app/main.py"))
        else:
            out.append(("ok", "API-only (no admin panel). `pyron enable admin` adds it later without rewriting handlers."))
    if cfg.mongo_url:
        out.append(("ok", "MONGO_URL is set"))
    else:
        out.append(("ok", "No MONGO_URL — Document models need MONGO_URL or admin_mongo=..."))
    if cfg.redis_url:
        out.append(("ok", "REDIS_URL is set (login throttle and cache are shared)"))
    else:
        out.append(("ok", "No REDIS_URL — cache and login throttle stay in-process"))
    return out
