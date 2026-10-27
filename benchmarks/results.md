# Benchmark notes

Captured with `python benchmarks/bench.py` after `maturin build --release`
and installing the wheel. Machine: CPython 3.12.10, Windows x86_64,
2026-08-18. Median of 5 runs × 40 000 iterations.

```
core=rust  iters=40000  routes=200

== routing ==
  pyron_router             719 ns/op      1391454 ops/s
  python_linear          24740 ns/op        40420 ops/s

== validation ==
  pyron_validate          2666 ns/op       375041 ops/s
  pydantic_v2             2126 ns/op       470346 ops/s

== serialization ==
  pyron_dumps             1092 ns/op       915648 ops/s
  stdlib_json             2569 ns/op       389299 ops/s

== request-shaped ==
  pyron_pipeline          4277 ns/op       233825 ops/s
  pydantic_json_stdlib    5148 ns/op       194248 ops/s
```

## What is being compared

| Work | Pyron | Baseline |
|---|---|---|
| Routing | compiled segment trie (`pyron._core.Router`) | linear scan of 200 templates |
| Validation | compiled JSON Schema over raw bytes, returning a Python object | Pydantic v2 `model_validate_json` |
| Serialization | serde_json via PyO3 | `json.dumps(...).encode()` |
| Request-shaped | find + validate + dumps | `model_validate_json` + stdlib dumps |

Pydantic v2 is already a Rust extension (`pydantic-core`). On a
five-field model it is still slightly faster than Pyron's validator
(0.80×). That is expected for v0.1 and is why the README does not
claim a validation blowout.

The request-shaped path — the one that actually resembles a POST
handler — is **1.2×** the Pydantic+stdlib combination because routing
and `dumps` more than cover the validation gap.

## HTTP-level comparison (method)

Same machine, same handler (`return {"status": "ok"}`), wrk / bombardier,
keep-alive on:

```
# FastAPI + uvicorn[standard]
# Pyron  + granian
```

Expect the gap to be small on a one-line handler (the server dominates)
and larger on endpoints that look up a parameterized route, validate a
JSON body, and serialize a response.

Do not claim an end-to-end "20× FastAPI" number. That is not what this
architecture does.

## Query and header parse (0.11.0)

Captured with `python -c "from benchmarks.bench import bench_prepare"` after
`maturin develop --release`. Machine: CPython 3.12.3, Linux x86_64, 2026-10-20.
Median of 5 runs × 40 000 iterations. `core=rust`.

Input: `q=hello+world&q=second&raw=a%20b&flag=&page=3` plus four headers
(one duplicate name).

```
== query-headers ==
  rust_prepare_request    1295 ns/op       772437 ops/s
  python_parse_qsl        5095 ns/op       196275 ops/s
```

Rust `prepare_request` is **3.9×** the Python `urllib.parse.parse_qsl` path
that `_core_fallback` still uses. Both keep the first value, decode `+` and
`%HH`, and lowercase header names. Declared query and header parameters use
this parse. Handlers that read `request.query_params` or `request.headers`
still go through Starlette. The public handler signature did not change.
