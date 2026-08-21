"""Microbenchmarks: Pyron core vs Pydantic / stdlib json / a Python router.

These are not HTTP-stack numbers. They isolate the work Pyron moved into Rust:
routing, JSON Schema validation, and serialization. End-to-end latency is
still dominated by the Python handler, the database, and the ASGI server.

Run from the repo root after `maturin develop --release`:

    python benchmarks/bench.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

# Prefer the installed package (which includes pyron._core). Only fall back
# to the in-tree Python sources when the extension is not on sys.path.
try:
    import pyron  # noqa: F401
except ImportError:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "python"))

from pydantic import BaseModel, Field

from pyron._bridge import CORE, Router, SchemaRegistry, dumps, loads


class BookIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=160)
    price: float = Field(ge=0, le=10_000)
    year: int = Field(default=1990, ge=0, le=2100)
    in_stock: bool = True


VALID = {
    "title": "Copper & Salt",
    "author": "J. P. Havel",
    "price": 22.5,
    "year": 1971,
    "in_stock": True,
}
VALID_JSON = json.dumps(VALID).encode()
N_ROUTES = 200
ITERS = 40_000
WARMUP = 2_000


def _time(fn, n: int) -> float:
    start = time.perf_counter()
    fn(n)
    return time.perf_counter() - start


def _stats(samples: list[float], n: int) -> dict[str, float]:
    ns = [s / n * 1e9 for s in samples]
    return {
        "ns_per_op": statistics.median(ns),
        "ops_per_s": 1e9 / statistics.median(ns),
    }


def bench_router() -> dict[str, dict[str, float]]:
    rust = Router()
    table: dict[tuple[str, str], int] = {}
    for i in range(N_ROUTES):
        rust.add("GET", f"/books/{i}/reviews/{{rid}}", i)
        table[("GET", f"/books/{i}/reviews/{{rid}}")] = i

    paths = [f"/books/{i % N_ROUTES}/reviews/{i}" for i in range(256)]

    def rust_run(n: int) -> None:
        for i in range(n):
            rust.find("GET", paths[i % 256])

    def py_run(n: int) -> None:
        # Naive linear scan — what many small frameworks still do.
        keys = list(table.keys())
        for i in range(n):
            path = paths[i % 256]
            for (_m, tmpl), _rid in zip(keys, table.values()):
                if "{rid}" in tmpl:
                    prefix = tmpl.split("{rid}")[0]
                    if path.startswith(prefix):
                        break

    rust_run(WARMUP)
    py_run(WARMUP)
    r = [_time(rust_run, ITERS) for _ in range(5)]
    p = [_time(py_run, ITERS) for _ in range(5)]
    return {"pyron_router": _stats(r, ITERS), "python_linear": _stats(p, ITERS)}


def bench_validate() -> dict[str, dict[str, float]]:
    reg = SchemaRegistry()
    sid = reg.register(BookIn.model_json_schema())

    def rust_run(n: int) -> None:
        for _ in range(n):
            reg.validate(sid, VALID_JSON, True)

    def pydantic_run(n: int) -> None:
        for _ in range(n):
            BookIn.model_validate_json(VALID_JSON)

    rust_run(WARMUP)
    pydantic_run(WARMUP)
    r = [_time(rust_run, ITERS) for _ in range(5)]
    p = [_time(pydantic_run, ITERS) for _ in range(5)]
    return {"pyron_validate": _stats(r, ITERS), "pydantic_v2": _stats(p, ITERS)}


def bench_pipeline() -> dict[str, dict[str, float]]:
    """Approximate one request: match a route, validate a body, dump a response."""
    rust = Router()
    rust.add("POST", "/books", 1)
    reg = SchemaRegistry()
    sid = reg.register(BookIn.model_json_schema())

    def pyron_run(n: int) -> None:
        for _ in range(n):
            rust.find("POST", "/books")
            reg.validate(sid, VALID_JSON, True)
            dumps(VALID)

    def fastapi_like(n: int) -> None:
        for _ in range(n):
            BookIn.model_validate_json(VALID_JSON)
            json.dumps(VALID).encode()

    pyron_run(WARMUP)
    fastapi_like(WARMUP)
    r = [_time(pyron_run, ITERS) for _ in range(5)]
    p = [_time(fastapi_like, ITERS) for _ in range(5)]
    return {"pyron_pipeline": _stats(r, ITERS), "pydantic_json_stdlib": _stats(p, ITERS)}


def bench_serialize() -> dict[str, dict[str, float]]:
    def rust_run(n: int) -> None:
        for _ in range(n):
            dumps(VALID)

    def stdlib_run(n: int) -> None:
        for _ in range(n):
            json.dumps(VALID).encode()

    rust_run(WARMUP)
    stdlib_run(WARMUP)
    r = [_time(rust_run, ITERS) for _ in range(5)]
    p = [_time(stdlib_run, ITERS) for _ in range(5)]
    return {"pyron_dumps": _stats(r, ITERS), "stdlib_json": _stats(p, ITERS)}


def main() -> None:
    print(f"core={CORE}  iters={ITERS}  routes={N_ROUTES}")
    suites = {
        "routing": bench_router(),
        "validation": bench_validate(),
        "serialization": bench_serialize(),
        "request-shaped": bench_pipeline(),
    }
    for name, rows in suites.items():
        print(f"\n== {name} ==")
        for label, stats in rows.items():
            print(f"  {label:18} {stats['ns_per_op']:9.0f} ns/op   {stats['ops_per_s']:10.0f} ops/s")
    # Derived speedups for the README table.
    rv = suites["validation"]
    speedup = rv["pydantic_v2"]["ns_per_op"] / rv["pyron_validate"]["ns_per_op"]
    print(f"\nvalidation speedup vs pydantic: {speedup:.2f}x")


if __name__ == "__main__":
    main()
