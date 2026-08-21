"""Process-wide settings. Env vars first; nothing here rewrites your handlers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class Settings:
    env: str = "dev"
    debug: bool = True
    secret_key: str = ""
    allowed_hosts: list[str] = field(default_factory=list)
    expose_docs: bool = True
    session_cookie_secure: bool = False
    login_max_attempts: int = 8
    login_lockout_seconds: int = 900
    password_min_length: int = 8
    trust_proxy_headers: bool = False
    mongo_url: str = ""
    mongo_db: str = "pyron"
    redis_url: str = ""

    @property
    def production(self) -> bool:
        return self.env == "production"


def load_settings() -> Settings:
    env = os.environ.get("PYRON_ENV", "dev").strip().lower()
    if env in {"prod", "production"}:
        env = "production"
    else:
        env = "dev"
    production = env == "production"
    return Settings(
        env=env,
        debug=_bool("PYRON_DEBUG", default=not production),
        secret_key=os.environ.get("PYRON_SECRET", ""),
        allowed_hosts=_list("PYRON_ALLOWED_HOSTS"),
        expose_docs=_bool("PYRON_EXPOSE_DOCS", default=not production),
        session_cookie_secure=_bool("PYRON_SESSION_SECURE", default=False),
        login_max_attempts=int(os.environ.get("PYRON_LOGIN_MAX_ATTEMPTS", "8")),
        login_lockout_seconds=int(os.environ.get("PYRON_LOGIN_LOCKOUT", "900")),
        password_min_length=int(os.environ.get("PYRON_PASSWORD_MIN", "8")),
        trust_proxy_headers=_bool("PYRON_TRUST_PROXY", default=False),
        mongo_url=os.environ.get("MONGO_URL", ""),
        mongo_db=os.environ.get("MONGO_DB", "pyron") or "pyron",
        redis_url=os.environ.get("REDIS_URL", ""),
    )


settings = load_settings()
