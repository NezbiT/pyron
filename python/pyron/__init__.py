"""Pyron — a hybrid Python web framework with a Rust core."""

from __future__ import annotations

from pyron._version import __version__
from pyron._bridge import CORE, core_kind, dumps, dumps_batch, loads, loads_batch
from pyron.app import Pyron
from pyron.exceptions import HTTPException, ValidationException
from pyron.params import Body, Cookie, Depends, Form, Header, Path, Query
from pyron.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pyron.flash import flash, redirect
from starlette.background import BackgroundTasks

from pyron.routing import APIRouter
from pyron.validation import SchemaRegistry, validate

from pyron.admin import AdminSite, ModelAdmin, TabularInline
from pyron.authz import (
    current_user,
    login_required,
    permission_required,
    require_root,
)
from pyron.cache import cache, redis_client
from pyron.document import Document
from pyron.mongo import mongo_client
from pyron.store import MemoryStore
from pyron.middleware import CORSMiddleware, GZipMiddleware

__all__ = [
    "APIRouter",
    "AdminSite",
    "CORSMiddleware",
    "Document",
    "Form",
    "GZipMiddleware",
    "MemoryStore",
    "ModelAdmin",
    "Page",
    "TabularInline",
    "cache",
    "mongo_client",
    "redis_client",
    "current_user",
    "login_required",
    "permission_required",
    "require_root",
    "BackgroundTasks",
    "Body",
    "CORE",
    "Cookie",
    "Depends",
    "HTMLResponse",
    "HTTPException",
    "Header",
    "JSONResponse",
    "Path",
    "PlainTextResponse",
    "Pyron",
    "Query",
    "RedirectResponse",
    "redirect",
    "SchemaRegistry",
    "ValidationException",
    "core_kind",
    "dumps",
    "dumps_batch",
    "flash",
    "loads",
    "loads_batch",
    "validate",
    "__version__",
]


def __getattr__(name: str):
    if name == "Page":
        from pyron.pages import Page

        return Page
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
