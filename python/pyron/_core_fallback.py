"""Pure-Python stand-in for `pyron._core`.

Mirrors the Rust surface so the rest of the package does not care which
implementation is loaded. Used when the extension module is not built.
"""

from __future__ import annotations

import json
import re
from typing import Any

CORE = "python"
__version__ = "0.1.0"


def core_kind() -> str:
    return "python"


def prepare_request(query: str, headers: list[tuple[str, str]]) -> dict[str, dict[str, str]]:
    """Same shape as the Rust helper: first query value, first lowercased header."""
    from urllib.parse import parse_qsl

    query_map: dict[str, str] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        query_map.setdefault(key, value)
    header_map: dict[str, str] = {}
    for name, value in headers:
        header_map.setdefault(name.lower(), value)
    return {"query": query_map, "headers": header_map}


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, default=_default, separators=(",", ":")).encode("utf-8")


def dumps_str(obj: Any) -> str:
    return json.dumps(obj, default=_default, separators=(",", ":"))


def dumps_pretty(obj: Any) -> str:
    return json.dumps(obj, default=_default, indent=2)


def loads(data: bytes | str | bytearray | memoryview) -> Any:
    if isinstance(data, memoryview):
        data = data.tobytes()
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    return json.loads(data)


def dumps_batch(objs: list[Any]) -> list[bytes]:
    return [dumps(o) for o in objs]


def loads_batch(payloads: list[Any]) -> list[Any]:
    return [loads(p) for p in payloads]


def _default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"pyron: cannot serialize type {type(obj)!r}")


class Router:
    def __init__(self) -> None:
        self._routes: list[tuple[str, list[str], int]] = []
        self._size = 0

    def add(self, method: str, path: str, route_id: int) -> None:
        if not path.startswith("/"):
            raise ValueError(f"route path must start with '/': {path}")
        method = method.upper()
        segs = _split(path)
        for m, existing, _rid in self._routes:
            if m == method and existing == segs:
                raise ValueError(f"duplicate route: {method} {path}")
        self._routes.append((method, segs, int(route_id)))
        self._size += 1

    def find(self, method: str, path: str) -> tuple[int, dict[str, str]] | tuple[None, list[str]] | None:
        method = method.upper()
        segs = _split(path)
        allowed: list[str] = []
        for m, tmpl, rid in self._routes:
            params = _match(tmpl, segs)
            if params is None:
                continue
            if m == method or (method == "HEAD" and m == "GET"):
                return rid, params
            allowed.append(m)
        if allowed:
            return None, sorted(set(allowed))
        return None

    def find_batch(self, items: list[tuple[str, str]]) -> list[Any]:
        return [self.find(m, p) for m, p in items]

    def __len__(self) -> int:
        return self._size


def _split(path: str) -> list[str]:
    trimmed = path.strip("/")
    return trimmed.split("/") if trimmed else []


def _match(tmpl: list[str], segs: list[str]) -> dict[str, str] | None:
    params: dict[str, str] = {}
    ti = 0
    si = 0
    while ti < len(tmpl):
        part = tmpl[ti]
        if part.startswith("{*") and part.endswith("}"):
            params[part[2:-1]] = "/".join(segs[si:])
            return params
        if si >= len(segs):
            return None
        if part.startswith("{") and part.endswith("}"):
            params[part[1:-1]] = segs[si]
        elif part != segs[si]:
            return None
        ti += 1
        si += 1
    if si != len(segs):
        return None
    return params


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[int, dict[str, Any]] = {}
        self._next = 1

    def register(self, schema: Any) -> int:
        if isinstance(schema, (bytes, bytearray, memoryview, str)):
            schema = loads(schema)
        sid = self._next
        self._next += 1
        self._schemas[sid] = schema
        return sid

    def validate(
        self, schema_id: int, data: Any, fail_fast: bool = True
    ) -> tuple[bool, Any]:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise ValueError(f"unknown schema id {schema_id}")
        value = _coerce_data(data)
        errors: list[dict[str, Any]] = []
        _walk(schema, value, [], errors, fail_fast, schema)
        if errors:
            return False, errors
        return True, value

    def validate_batch(
        self, schema_id: int, payloads: list[Any], fail_fast: bool = True
    ) -> list[tuple[bool, Any]]:
        return [self.validate(schema_id, p, fail_fast) for p in payloads]

    def __len__(self) -> int:
        return len(self._schemas)


def _coerce_data(data: Any) -> Any:
    if isinstance(data, (bytes, bytearray, memoryview, str)):
        return loads(data)
    return data


def _walk(
    schema: dict[str, Any],
    value: Any,
    loc: list[str],
    errors: list[dict[str, Any]],
    fail_fast: bool,
    root: dict[str, Any],
) -> None:
    if fail_fast and errors:
        return
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        defs = root.get("$defs") or root.get("definitions") or {}
        target = defs.get(name)
        if target is None:
            errors.append({"loc": list(loc), "msg": f"unresolved $ref: {schema['$ref']}", "type": "ref"})
            return
        _walk(target, value, loc, errors, fail_fast, root)
        return
    if "anyOf" in schema or "oneOf" in schema:
        opts = schema.get("anyOf") or schema.get("oneOf") or []
        for opt in opts:
            inner: list[dict[str, Any]] = []
            _walk(opt, value, loc, inner, True, root)
            if not inner:
                return
        errors.append(
            {"loc": list(loc), "msg": "value does not match any allowed type", "type": "union_tag_invalid"}
        )
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append({"loc": list(loc), "msg": "value is not a permitted choice", "type": "enum"})
        return
    ty = schema.get("type")
    types = [ty] if isinstance(ty, str) else list(ty or [])
    if types:
        if not _type_ok(types, value):
            errors.append({"loc": list(loc), "msg": f"must be {types[0]}", "type": f"{types[0]}_type"})
            return
    if "string" in types and isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append({"loc": list(loc), "msg": "too short", "type": "string_too_short"})
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append({"loc": list(loc), "msg": "too long", "type": "string_too_long"})
        if schema.get("format") == "email" and not re.search(r"^[^@]+@[^@]+\.[^@]+$", value):
            errors.append({"loc": list(loc), "msg": "must be a valid email address", "type": "string_pattern"})
    if types and ("number" in types or "integer" in types) and isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append({"loc": list(loc), "msg": "below minimum", "type": "greater_than_equal"})
        if "maximum" in schema and value > schema["maximum"]:
            errors.append({"loc": list(loc), "msg": "above maximum", "type": "less_than_equal"})
    if (not types or "object" in types) and isinstance(value, dict) and (
        "properties" in schema or "required" in schema
    ):
        required = schema.get("required") or []
        props = schema.get("properties") or {}
        for key in required:
            if key not in value:
                errors.append({"loc": loc + [key], "msg": "field required", "type": "missing"})
                if fail_fast:
                    return
        extra = schema.get("additionalProperties", True)
        for key, child in value.items():
            if key in props:
                _walk(props[key], child, loc + [key], errors, fail_fast, root)
            elif extra is False:
                errors.append({"loc": loc + [key], "msg": "extra field not permitted", "type": "extra_forbidden"})
    if (not types or "array" in types) and isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _walk(schema["items"], item, loc + [str(i)], errors, fail_fast, root)


def _type_ok(types: list[str], value: Any) -> bool:
    for t in types:
        if t == "null" and value is None:
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "string" and isinstance(value, str):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
    return False


class OpenApiBuilder:
    def __init__(self, title: str, version: str, description: str | None = None) -> None:
        self._doc: dict[str, Any] = {
            "openapi": "3.1.0",
            "info": {"title": title, "version": version},
            "paths": {},
            "components": {"schemas": {}},
        }
        if description:
            self._doc["info"]["description"] = description
        self._tags: list[dict[str, Any]] = []
        self._servers: list[dict[str, Any]] = []

    def add_schema(self, name: str, schema: Any) -> None:
        if isinstance(schema, (bytes, bytearray, str)):
            schema = loads(schema)
        self._doc["components"]["schemas"][name] = schema

    def add_server(self, url: str, description: str | None = None) -> None:
        item: dict[str, Any] = {"url": url}
        if description:
            item["description"] = description
        self._servers.append(item)

    def add_tag(self, name: str, description: str | None = None) -> None:
        item: dict[str, Any] = {"name": name}
        if description:
            item["description"] = description
        self._tags.append(item)

    def add_operation(self, method: str, path: str, operation: Any) -> None:
        if isinstance(operation, (bytes, bytearray, str)):
            operation = loads(operation)
        self._doc["paths"].setdefault(path, {})[method.lower()] = operation

    def build(self, pretty: bool = False) -> str:
        doc = dict(self._doc)
        if self._servers:
            doc["servers"] = self._servers
        if self._tags:
            doc["tags"] = self._tags
        if not doc["components"]["schemas"]:
            doc.pop("components", None)
        return dumps_pretty(doc) if pretty else dumps_str(doc)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.build())
