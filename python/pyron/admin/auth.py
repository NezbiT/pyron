"""Root/staff accounts, password hashing, and signed session cookies."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import Response

COOKIE = "pyron_desk"
CSRF_COOKIE = "pyron_csrf"
SESSION_DAYS = 7
PBKDF2_ROUNDS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, hash_hex = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def load_secret(path: str | Path | None = None) -> bytes:
    env = os.environ.get("PYRON_SECRET")
    if env:
        return env.encode("utf-8")
    file = Path(path) if path else Path(".pyron_secret")
    if file.is_file():
        return file.read_bytes()
    secret = os.urandom(32)
    file.write_bytes(secret)
    try:
        file.chmod(0o600)
    except OSError:
        pass
    return secret


def sign_payload(payload: dict[str, Any], secret: bytes) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64(raw)
    sig = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def unsign_payload(token: str, secret: bytes) -> dict[str, Any] | None:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expect = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        data = json.loads(_unb64(body))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    exp = data.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    return data


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def session_cookie_kwargs(prefix: str | None = None) -> dict[str, Any]:
    from pyron.settings import load_settings

    settings = load_settings()
    # Path "/" so the same cookie is visible to the API and the Desk.
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": bool(settings.session_cookie_secure),
        "path": "/",
        "max_age": SESSION_DAYS * 24 * 3600,
    }


def read_session(request: Request, secret: bytes) -> dict[str, Any]:
    token = request.cookies.get(COOKIE)
    if not token:
        return {}
    return unsign_payload(token, secret) or {}


def write_session(response: Response, payload: dict[str, Any], secret: bytes, prefix: str = "/") -> None:
    payload = dict(payload)
    payload.setdefault("exp", int(time.time()) + SESSION_DAYS * 24 * 3600)
    response.set_cookie(COOKIE, sign_payload(payload, secret), **session_cookie_kwargs())


def clear_session(response: Response, prefix: str = "/") -> None:
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path=prefix or "/")


def _b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(body: str) -> bytes:
    import base64

    pad = "=" * (-len(body) % 4)
    return base64.urlsafe_b64decode(body + pad)


class AuthUser:
    """Signed-in operator. Root bypasses permission checks."""

    def __init__(self, row: Any, perms: frozenset[str] | set[str] = frozenset()) -> None:
        self.id = row.id
        self.username = row.username
        self.is_root = bool(row.is_root)
        self.is_active = bool(row.is_active)
        self.is_authenticated = True
        self.permissions: frozenset[str] = frozenset(perms)

    def has_perm(self, code: str) -> bool:
        if self.is_root:
            return True
        return code in self.permissions


_SCHEMA: Any = None


def user_model():
    return _schema().User


def group_model():
    return _schema().Group


def permission_model():
    return _schema().Permission


def user_group_link():
    return _schema().UserGroup


def group_permission_link():
    return _schema().GroupPermission


def auth_table_classes() -> list[Any]:
    s = _schema()
    return [s.User, s.Group, s.Permission, s.UserGroup, s.GroupPermission, s.Log]


def log_model():
    return _schema().Log


def write_log(session: Any, *, username: str, action: str, slug: str, pk: Any, label: str) -> None:
    Log = log_model()
    session.add(
        Log(
            username=username or "",
            action=action,
            slug=slug,
            object_pk=str(pk),
            label=(label or "")[:240],
        )
    )


def _schema():
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA
    from types import SimpleNamespace

    from sqlmodel import Field, SQLModel

    class PyronUser(SQLModel, table=True):
        __tablename__ = "pyron_user"
        id: Optional[int] = Field(default=None, primary_key=True)
        username: str = Field(index=True, unique=True, max_length=80)
        password_hash: str
        is_root: bool = False
        is_active: bool = True
        created_at: datetime = Field(default_factory=datetime.utcnow)

    class PyronGroup(SQLModel, table=True):
        __tablename__ = "pyron_group"
        id: Optional[int] = Field(default=None, primary_key=True)
        name: str = Field(index=True, unique=True, max_length=80)

    class PyronPermission(SQLModel, table=True):
        __tablename__ = "pyron_permission"
        id: Optional[int] = Field(default=None, primary_key=True)
        codename: str = Field(index=True, unique=True, max_length=120)
        label: str = Field(default="", max_length=200)

    class PyronUserGroup(SQLModel, table=True):
        __tablename__ = "pyron_user_group"
        user_id: int = Field(foreign_key="pyron_user.id", primary_key=True)
        group_id: int = Field(foreign_key="pyron_group.id", primary_key=True)

    class PyronGroupPermission(SQLModel, table=True):
        __tablename__ = "pyron_group_permission"
        group_id: int = Field(foreign_key="pyron_group.id", primary_key=True)
        permission_id: int = Field(foreign_key="pyron_permission.id", primary_key=True)

    class PyronLog(SQLModel, table=True):
        __tablename__ = "pyron_log"
        id: Optional[int] = Field(default=None, primary_key=True)
        username: str = Field(default="", max_length=80)
        action: str = Field(max_length=40)
        slug: str = Field(default="", max_length=80)
        object_pk: str = Field(default="", max_length=80)
        label: str = Field(default="", max_length=240)
        created_at: datetime = Field(default_factory=datetime.utcnow)

    _SCHEMA = SimpleNamespace(
        User=PyronUser,
        Group=PyronGroup,
        Permission=PyronPermission,
        UserGroup=PyronUserGroup,
        GroupPermission=PyronGroupPermission,
        Log=PyronLog,
    )
    return _SCHEMA


STAFF_GROUP = "staff"
STAFF_ACTIONS = ("view", "add", "change")
ALL_ACTIONS = ("view", "add", "change", "delete")


def load_auth_user(session: Any, user_id: int) -> AuthUser | None:
    from sqlmodel import select

    User = user_model()
    row = session.get(User, int(user_id))
    if row is None or not row.is_active:
        return None
    if row.is_root:
        return AuthUser(row, frozenset())
    UG = user_group_link()
    GP = group_permission_link()
    Perm = permission_model()
    gids = list(session.exec(select(UG.group_id).where(UG.user_id == row.id)).all())
    if not gids:
        return AuthUser(row, frozenset())
    pids = list(session.exec(select(GP.permission_id).where(GP.group_id.in_(gids))).all())
    if not pids:
        return AuthUser(row, frozenset())
    codes = list(session.exec(select(Perm.codename).where(Perm.id.in_(pids))).all())
    return AuthUser(row, frozenset(str(c) for c in codes))


def ensure_staff_group(session: Any) -> Any:
    from sqlmodel import select

    Group = group_model()
    row = session.exec(select(Group).where(Group.name == STAFF_GROUP)).first()
    if row is None:
        row = Group(name=STAFF_GROUP)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def ensure_permission(session: Any, codename: str, label: str = "") -> Any:
    from sqlmodel import select

    Perm = permission_model()
    row = session.exec(select(Perm).where(Perm.codename == codename)).first()
    if row is None:
        row = Perm(codename=codename, label=label or codename)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def grant_group_permission(session: Any, group: Any, perm: Any) -> None:
    from sqlmodel import select

    GP = group_permission_link()
    existing = session.exec(
        select(GP).where(GP.group_id == group.id, GP.permission_id == perm.id)
    ).first()
    if existing is None:
        session.add(GP(group_id=group.id, permission_id=perm.id))


def add_user_to_staff(session: Any, user: Any) -> None:
    from sqlmodel import select

    group = ensure_staff_group(session)
    UG = user_group_link()
    existing = session.exec(
        select(UG).where(UG.user_id == user.id, UG.group_id == group.id)
    ).first()
    if existing is None:
        session.add(UG(user_id=user.id, group_id=group.id))

