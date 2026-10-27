"""Control channel for a live Pyron process.

The worker manager owns the socket. `pyron inspect` is a client.
Workers connect, say hello, and run custom commands inside the app.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyron._version import __version__

STATE_NAME = "inspect.json"


class Inspector:
    """Commands a running app can answer. Attach one to each `Pyron`."""

    def __init__(self) -> None:
        self.commands: dict[str, Callable[..., Any]] = {}

    def command(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.commands[name] = fn
            return fn

        return decorator


class InspectorHub:
    """Sibling control server. One thread accepts clients and workers."""

    def __init__(self) -> None:
        self.started = time.time()
        self.workers = 1
        self.server_pid: int | None = None
        self.worker_pids: list[int] = []
        self.command_names: list[str] = []
        self.on_reload: Callable[[], None] | None = None
        self.on_scale: Callable[[int], None] | None = None
        self.on_shutdown: Callable[[], None] | None = None
        self._workers: list[socket.socket] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self.addr = ""

    def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(16)
        sock.settimeout(0.4)
        self._sock = sock
        bound = sock.getsockname()
        self.addr = f"{bound[0]}:{bound[1]}"
        self._thread = threading.Thread(target=self._serve, name="pyron-inspect", daemon=True)
        self._thread.start()
        return self.addr

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        with self._lock:
            for conn in self._workers:
                try:
                    conn.close()
                except OSError:
                    pass
            self._workers.clear()

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(30)
        try:
            raw = _readline(conn)
            if not raw:
                return
            msg = json.loads(raw)
            op = msg.get("op")
            if op == "hello":
                self._remember_worker(conn, msg)
                conn.settimeout(None)
                _write(conn, {"ok": True})
                return
            _write(conn, self._client(msg))
        except Exception as exc:  # noqa: BLE001 — control plane must answer
            try:
                _write(conn, {"ok": False, "error": str(exc)})
            except OSError:
                pass
        finally:
            if conn not in self._workers:
                try:
                    conn.close()
                except OSError:
                    pass

    def _remember_worker(self, conn: socket.socket, msg: dict[str, Any]) -> None:
        pid = int(msg.get("pid") or 0)
        names = [str(n) for n in msg.get("commands") or []]
        with self._lock:
            self._workers.append(conn)
            if pid and pid not in self.worker_pids:
                self.worker_pids.append(pid)
            for name in names:
                if name not in self.command_names:
                    self.command_names.append(name)

    def _client(self, msg: dict[str, Any]) -> dict[str, Any]:
        op = msg.get("op")
        if op == "status":
            return {"ok": True, "result": self.status()}
        if op == "reload":
            if self.on_reload:
                self.on_reload()
            return {"ok": True, "result": {"reloaded": True}}
        if op == "scale":
            count = int(msg.get("workers") or 0)
            if count < 1:
                return {"ok": False, "error": "workers must be >= 1"}
            self.workers = count
            if self.on_scale:
                self.on_scale(count)
            return {"ok": True, "result": {"workers": count}}
        if op == "shutdown":
            if self.on_shutdown:
                self.on_shutdown()
            return {"ok": True, "result": {"shutdown": True}}
        if op == "call":
            return self._call(str(msg.get("name") or ""), msg.get("payload") or {})
        return {"ok": False, "error": f"unknown op {op!r}"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            pids = list(self.worker_pids)
            commands = list(self.command_names)
        return {
            "version": __version__,
            "pid": os.getpid(),
            "server_pid": self.server_pid,
            "workers": self.workers,
            "worker_pids": pids,
            "uptime_s": round(time.time() - self.started, 3),
            "commands": commands,
            "addr": self.addr,
        }

    def reset_workers(self) -> None:
        """Drop worker sockets after the server child has been stopped."""
        with self._lock:
            for conn in self._workers:
                try:
                    conn.close()
                except OSError:
                    pass
            self._workers.clear()
            self.worker_pids.clear()
            self.command_names.clear()

    def _call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._workers:
                return {"ok": False, "error": "no worker is connected"}
            conn = self._workers[0]
            try:
                conn.settimeout(30)
                _write(conn, {"op": "call", "name": name, "payload": payload})
                raw = _readline(conn)
                conn.settimeout(None)
            except OSError as exc:
                self._drop(conn)
                return {"ok": False, "error": str(exc)}
        if not raw:
            self._drop(conn)
            return {"ok": False, "error": "worker closed"}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": str(exc)}

    def _drop(self, conn: socket.socket) -> None:
        with self._lock:
            if conn in self._workers:
                self._workers.remove(conn)
        try:
            conn.close()
        except OSError:
            pass


def _readline(conn: socket.socket) -> str:
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 1_000_000:
            break
    return buf.split(b"\n", 1)[0].decode("utf-8")


def _write(conn: socket.socket, payload: dict[str, Any]) -> None:
    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def state_path(app_dir: str | os.PathLike[str] | None = None) -> Path:
    root = Path(app_dir or os.getcwd())
    return root / ".pyron" / STATE_NAME


def write_state(app_dir: str | os.PathLike[str], addr: str, pid: int) -> Path:
    path = state_path(app_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"addr": addr, "pid": pid, "app_dir": str(app_dir)}), encoding="utf-8")
    return path


def read_state(app_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    path = state_path(app_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"No running Pyron app at {path}. Start one with `pyron dev` or `pyron serve`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def ask(addr: str, payload: dict[str, Any], timeout: float = 5) -> dict[str, Any]:
    host, port_s = addr.rsplit(":", 1)
    conn = socket.create_connection((host, int(port_s)), timeout=timeout)
    try:
        _write(conn, payload)
        raw = _readline(conn)
        if not raw:
            return {"ok": False, "error": "empty reply"}
        return json.loads(raw)
    finally:
        conn.close()
