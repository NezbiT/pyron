"""Pyron admin panel (Django-style).

Register SQLModel tables or Mongo `Document`s, create a root user, and
operate the app from `/admin` without writing extra views. Pages are on
the panel by default; Jinja2 renders them at `/p/{slug}`.
"""

from __future__ import annotations

from pyron.admin.options import ModelAdmin, TabularInline
from pyron.admin.site import AdminSite

__all__ = ["AdminSite", "ModelAdmin", "TabularInline"]
