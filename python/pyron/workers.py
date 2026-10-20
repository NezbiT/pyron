"""One parent for `pyron dev` and `pyron serve`.

The parent is the worker manager and the inspector. The HTTP server is a
child process, so reload, scale, and shutdown do not need SSH.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from queue import Empty, Queue
from typing import Any

from pyron.inspector import InspectorHub, ask, state_path, write_state


def supervise(
    target: str,
    *,
    host: str,
    port: int,
    workers: int = 1,
    reload: bool = False,
    app_dir: str,
    log_level: str = "info",
) -> None:
    """Run the inspector beside the server until `inspect shutdown`."""
    hub = InspectorHub()
    hub.workers = max(1, workers)
    addr = hub.start()
    write_state(app_dir, addr, os.getpid())
    actions: Queue[tuple[str, Any]] = Queue()
    hub.on_reload = lambda: actions.put(("reload", None))
    hub.on_scale = lambda count: actions.put(("scale", count))
    hub.on_shutdown = lambda: actions.put(("shutdown", None))

    child = _spawn(target, host, port, hub.workers, reload, app_dir, log_level, addr)
    hub.server_pid = child.pid
    try:
        while True:
            if child.poll() is not None and actions.empty():
                # The server exited on its own (crash or Ctrl-C in the child).
                break
            try:
                action, arg = actions.get(timeout=0.4)
            except Empty:
                continue
            if action == "shutdown":
                _stop(child)
                break
            if action == "scale" and isinstance(arg, int):
                hub.workers = arg
            _stop(child)
            hub.reset_workers()
            child = _spawn(target, host, port, hub.workers, reload, app_dir, log_level, addr)
            hub.server_pid = child.pid
    finally:
        _stop(child)
        hub.stop()
        try:
            state_path(app_dir).unlink(missing_ok=True)
        except OSError:
            pass


def serve_child() -> None:
    """Entry point for the HTTP child. `python -m pyron.workers`."""
    from pyron.server import serve_blocking

    serve_blocking(
        os.environ["PYRON_APP"],
        host=os.environ.get("PYRON_HOST", "127.0.0.1"),
        port=int(os.environ.get("PYRON_PORT", "8000")),
        reload=os.environ.get("PYRON_RELOAD") == "1",
        workers=int(os.environ.get("PYRON_WORKERS", "1")),
        log_level=os.environ.get("PYRON_LOG_LEVEL", "info"),
        app_dir=os.environ.get("PYRON_APP_DIR") or None,
    )


def _spawn(
    target: str,
    host: str,
    port: int,
    workers: int,
    reload: bool,
    app_dir: str,
    log_level: str,
    inspect_addr: str,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "PYRON_WORKER": "1",
            "PYRON_APP": target,
            "PYRON_HOST": host,
            "PYRON_PORT": str(port),
            "PYRON_WORKERS": str(workers),
            "PYRON_RELOAD": "1" if reload else "0",
            "PYRON_APP_DIR": app_dir,
            "PYRON_LOG_LEVEL": log_level,
            "PYRON_INSPECT_ADDR": inspect_addr,
        }
    )
    return subprocess.Popen([sys.executable, "-m", "pyron.workers"], env=env, cwd=app_dir)


def _stop(child: subprocess.Popen[bytes] | None) -> None:
    if child is None or child.poll() is not None:
        return
    child.send_signal(signal.SIGTERM)
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=2)


def request(app_dir: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    from pyron.inspector import read_state

    state = read_state(app_dir)
    return ask(str(state["addr"]), payload)


if __name__ == "__main__":
    # Give the parent a moment to finish binding before we import the app.
    time.sleep(0.05)
    serve_child()
