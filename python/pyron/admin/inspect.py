"""Turn a SQLModel / Pydantic table into list columns and form fields."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, get_args, get_origin

SKIP_DEFAULT = {"password_hash"}


def primary_key(model: type) -> str:
    table = getattr(model, "__table__", None)
    if table is not None and table.primary_key.columns:
        return list(table.primary_key.columns.keys())[0]
    for name, field in getattr(model, "model_fields", {}).items():
        extra = getattr(field, "json_schema_extra", None) or {}
        if isinstance(extra, dict) and extra.get("primary_key"):
            return name
    return "id"


def slug_for(model: type) -> str:
    name = getattr(model, "__name__", "model")
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and name[i - 1].islower():
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def python_type(annotation: Any) -> type:
    origin = get_origin(annotation)
    if origin is None:
        return annotation if isinstance(annotation, type) else str
    args = [a for a in get_args(annotation) if a is not type(None)]
    if args:
        return python_type(args[0])
    return str


def field_specs(model: type, *, exclude: list[str] | None = None) -> list[dict[str, Any]]:
    skip = set(SKIP_DEFAULT) | set(exclude or [])
    pk = primary_key(model)
    specs = []
    for name, field in model.model_fields.items():
        if name in skip:
            continue
        ann = python_type(field.annotation)
        required = field.is_required()
        has_factory = field.default_factory is not None
        specs.append(
            {
                "name": name,
                "label": name.replace("_", " ").capitalize(),
                "type": ann,
                "required": required and not has_factory and name != pk,
                "primary_key": name == pk,
                "readonly": name == pk,
                "auto": name == pk or has_factory,
                "widget": _widget(ann, name, field),
                "help": _help(field),
            }
        )
    return specs


def _widget(ann: type, name: str, field: Any) -> str:
    if ann is bool:
        return "checkbox"
    if ann in (int, float):
        return "number"
    if ann is datetime:
        return "datetime"
    if ann is date:
        return "date"
    max_len = None
    extra = getattr(field, "json_schema_extra", None) or {}
    if isinstance(extra, dict):
        max_len = extra.get("max_length")
    meta = getattr(field, "metadata", None) or ()
    for m in meta:
        max_len = getattr(m, "max_length", max_len)
    if name in {"description", "body", "notes", "content"} or (max_len and max_len >= 400):
        return "textarea"
    if "password" in name:
        return "password"
    return "text"


def _help(field: Any) -> str:
    desc = getattr(field, "description", None)
    return desc or ""


def coerce(spec: dict[str, Any], raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
    widget = spec["widget"]
    typ = spec["type"]
    if widget == "checkbox":
        if isinstance(raw, bool):
            return raw
        if raw in (None, "", "0", "false", "off", "no"):
            return False
        return True
    if raw == "" or raw is None:
        if spec["required"]:
            raise ValueError(f"{spec['label']} is required.")
        return None if not spec["primary_key"] else raw
    if typ is int or widget == "number" and typ is int:
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{spec['label']} has to be a whole number.") from exc
    if typ is float:
        try:
            return float(str(raw).replace(",", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{spec['label']} has to be a number.") from exc
    if typ is datetime or widget == "datetime":
        text = str(raw).replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        raise ValueError(f"{spec['label']} needs a date and time.")
    if typ is date or widget == "date":
        try:
            return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"{spec['label']} needs a date (YYYY-MM-DD).") from exc
    return str(raw)


def display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}"
    text = str(value)
    if len(text) > 80:
        return text[:77] + "…"
    return text


def form_value(value: Any, widget: str) -> str:
    if value is None:
        return ""
    if widget == "datetime" and isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    if widget == "date" and isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    if widget == "checkbox":
        return "1" if value else ""
    return str(value)
