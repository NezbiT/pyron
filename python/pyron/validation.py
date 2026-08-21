"""Python façade over the Rust schema registry (with Pydantic interop)."""

from __future__ import annotations

from typing import Any

from pyron._bridge import SchemaRegistry as _CoreRegistry
from pyron.exceptions import ValidationException

_global = _CoreRegistry()


class SchemaRegistry:
    """Compile JSON Schemas once, validate many times on the Rust hot path."""

    def __init__(self) -> None:
        self._core = _CoreRegistry()
        self._names: dict[str, int] = {}

    def register(self, schema: Any, *, name: str | None = None) -> int:
        if hasattr(schema, "model_json_schema"):
            schema = schema.model_json_schema()
        sid = self._core.register(schema)
        if name:
            self._names[name] = sid
        return sid

    def id_for(self, name: str) -> int:
        return self._names[name]

    def validate(self, schema_id: int, data: Any, *, fail_fast: bool = True) -> Any:
        ok, payload = self._core.validate(schema_id, data, fail_fast)
        if not ok:
            raise ValidationException(payload)
        return payload

    def validate_batch(
        self, schema_id: int, payloads: list[Any], *, fail_fast: bool = True
    ) -> list[Any]:
        results = self._core.validate_batch(schema_id, payloads, fail_fast)
        out: list[Any] = []
        for ok, payload in results:
            if not ok:
                raise ValidationException(payload)
            out.append(payload)
        return out

    def __len__(self) -> int:
        return len(self._core)


def validate(schema: Any, data: Any, *, fail_fast: bool = True) -> Any:
    """One-shot validation. Prefer `SchemaRegistry` when the schema is reused."""
    if hasattr(schema, "model_json_schema"):
        schema = schema.model_json_schema()
    sid = _global.register(schema)
    ok, payload = _global.validate(sid, data, fail_fast)
    if not ok:
        raise ValidationException(payload)
    return payload


def register_pydantic(model: Any, registry: SchemaRegistry | None = None) -> int:
    reg = registry or SchemaRegistry()
    return reg.register(model.model_json_schema(), name=model.__name__)
