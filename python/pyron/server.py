"""ASGI server entry — Granian first, Uvicorn as a fallback."""

from __future__ import annotations

import os
import sys
from typing import Any


def ensure_import_path(app_dir: str | None = None) -> str:
    """Put the app directory on `sys.path` and `PYTHONPATH`.

    `pyron` is installed as a console script. On Windows the reloader uses
    multiprocessing `spawn`, so the worker process does not inherit the
    parent's `sys.path` and would otherwise fail with
    `ModuleNotFoundError: No module named 'app'`. PYTHONPATH is inherited.
    """
    root = os.path.abspath(app_dir or os.getcwd())
    if root not in sys.path:
        sys.path.insert(0, root)
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if root not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([root, *parts]) if parts else root
    return root


def run(
    app: str | Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    workers: int = 1,
    interface: str = "asgi",
    log_level: str = "info",
    app_dir: str | None = None,
) -> None:
    """Serve an ASGI app.

    `app` is either a live object (`myapp:app` is preferred for reload)
    or an import string `"package.module:app"`.
    """
    root = ensure_import_path(app_dir)
    target = app if isinstance(app, str) else _object_to_target(app)
    # The HTTP child must not start another supervisor.
    if os.environ.get("PYRON_WORKER") == "1":
        serve_blocking(
            target,
            host=host,
            port=port,
            reload=reload,
            workers=workers,
            interface=interface,
            log_level=log_level,
            app_dir=root,
        )
        return
    from pyron.workers import supervise

    supervise(
        target,
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        app_dir=root,
        log_level=log_level,
    )


def serve_blocking(
    app: str | Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    workers: int = 1,
    interface: str = "asgi",
    log_level: str = "info",
    app_dir: str | None = None,
) -> None:
    """Run Granian or Uvicorn in this process. Used by the worker child."""
    root = ensure_import_path(app_dir)
    target = app if isinstance(app, str) else _object_to_target(app)
    if _try_granian(target, host, port, reload, workers, interface, log_level, root):
        return
    _try_uvicorn(target, host, port, reload, workers, log_level, root)


def _try_granian(
    target: str,
    host: str,
    port: int,
    reload: bool,
    workers: int,
    interface: str,
    log_level: str,
    app_dir: str,
) -> bool:
    try:
        from granian import Granian
        from granian.constants import Interfaces
    except ImportError:
        return False
    iface = Interfaces.ASGI if interface == "asgi" else Interfaces.ASGI
    kwargs: dict[str, Any] = {
        "address": host,
        "port": port,
        "interface": iface,
        "workers": max(1, workers),
        "reload": reload,
        "log_level": log_level,
    }
    server = Granian(target, **kwargs)
    server.serve()
    return True


def _try_uvicorn(
    target: str,
    host: str,
    port: int,
    reload: bool,
    workers: int,
    log_level: str,
    app_dir: str,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "No ASGI server found. Install one of:\n"
            "  pip install granian\n"
            "  pip install uvicorn[standard]"
        ) from exc
    uvicorn.run(
        target,
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[app_dir] if reload else None,
        workers=None if reload else max(1, workers),
        log_level=log_level,
        factory=False,
        app_dir=app_dir,
    )


def _object_to_target(app: Any) -> str:
    module = getattr(app, "__module__", None)
    name = None
    # Prefer a well-known attribute walk so reload works.
    if module and module != "__main__":
        for attr, value in sys.modules[module].__dict__.items():
            if value is app:
                name = attr
                break
    if module and name:
        return f"{module}:{name}"
    os.environ["PYRON_INLINE_APP"] = "1"
    return "pyron.server:_inline_app"


_inline_holder: Any = None


def _inline_app() -> Any:  # pragma: no cover
    return _inline_holder
