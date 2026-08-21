"""Load the Rust extension, falling back to a pure-Python core.

The hot path lives in `pyron._core` (PyO3). If the extension is missing —
no Rust toolchain, or `PYRON_PURE_PYTHON=1` — we load `_core_fallback`
so the framework still runs, just slower.
"""

from __future__ import annotations

import os
from typing import Any

_FORCE_PURE = os.environ.get("PYRON_PURE_PYTHON", "").strip() in {"1", "true", "yes"}

_using_rust = False
Router: Any
SchemaRegistry: Any
OpenApiBuilder: Any
dumps: Any
dumps_str: Any
dumps_pretty: Any
loads: Any
dumps_batch: Any
loads_batch: Any
core_kind: Any
CORE: str

if not _FORCE_PURE:
    try:
        from pyron import _core as _ext  # type: ignore

        Router = _ext.Router
        SchemaRegistry = _ext.SchemaRegistry
        OpenApiBuilder = _ext.OpenApiBuilder
        dumps = _ext.dumps
        dumps_str = _ext.dumps_str
        dumps_pretty = _ext.dumps_pretty
        loads = _ext.loads
        dumps_batch = _ext.dumps_batch
        loads_batch = _ext.loads_batch
        core_kind = _ext.core_kind
        CORE = getattr(_ext, "CORE", "rust")
        _using_rust = True
    except Exception:
        _using_rust = False

if not _using_rust:
    from pyron._core_fallback import (  # noqa: F401
        CORE,
        OpenApiBuilder,
        Router,
        SchemaRegistry,
        core_kind,
        dumps,
        dumps_batch,
        dumps_pretty,
        dumps_str,
        loads,
        loads_batch,
    )

USING_RUST = _using_rust
