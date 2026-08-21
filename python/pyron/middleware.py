"""Thin wrappers around Starlette middleware used by the framework."""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

__all__ = [
    "CORSMiddleware",
    "GZipMiddleware",
    "Middleware",
    "TrustedHostMiddleware",
]
