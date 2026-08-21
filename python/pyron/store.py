"""Storage backends for the admin panel. SQL, Mongo, or in-memory tests."""

from __future__ import annotations

from typing import Any, Protocol


class Store(Protocol):
    kind: str

    def count(self, model: type) -> int: ...

    def list(
        self,
        model: type,
        *,
        q: str = "",
        search_fields: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        offset: int = 0,
        limit: int = 25,
        pk: str = "id",
    ) -> tuple[list[Any], int]: ...

    def get(self, model: type, pk_value: Any, pk: str = "id") -> Any | None: ...

    def insert(self, model: type, values: dict[str, Any], pk: str = "id") -> Any: ...

    def update(self, model: type, pk_value: Any, values: dict[str, Any], pk: str = "id") -> Any: ...

    def delete(self, model: type, pk_value: Any, pk: str = "id") -> None: ...

    def distinct(self, model: type, field: str, limit: int = 30) -> list[Any]: ...


def is_sql_model(model: type) -> bool:
    return getattr(model, "__table__", None) is not None


def is_document(model: type) -> bool:
    try:
        from pyron.document import Document

        return isinstance(model, type) and issubclass(model, Document) and model is not Document
    except Exception:
        return bool(getattr(model, "collection", None)) and not is_sql_model(model)


class MemoryStore:
    """Process-local rows. Tests and apps without Mongo."""

    kind = "memory"

    def __init__(self) -> None:
        self._rows: dict[type, list[Any]] = {}
        self._seq: dict[type, int] = {}

    def _bucket(self, model: type) -> list[Any]:
        return self._rows.setdefault(model, [])

    def count(self, model: type) -> int:
        return len(self._bucket(model))

    def list(
        self,
        model: type,
        *,
        q: str = "",
        search_fields: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        offset: int = 0,
        limit: int = 25,
        pk: str = "id",
    ) -> tuple[list[Any], int]:
        rows = list(self._bucket(model))
        if q and search_fields:
            needle = q.lower()
            rows = [
                r
                for r in rows
                if any(needle in str(getattr(r, f, "") or "").lower() for f in search_fields)
            ]
        for name, raw in (filters or {}).items():
            want = _coerce_memory(raw)
            rows = [r for r in rows if _match(getattr(r, name, None), want)]
        if order:
            desc = order.startswith("-")
            key = order.lstrip("-")
            rows.sort(key=lambda r: (getattr(r, key, None) is None, getattr(r, key, None)), reverse=desc)
        total = len(rows)
        return rows[offset : offset + limit], total

    def get(self, model: type, pk_value: Any, pk: str = "id") -> Any | None:
        want = str(pk_value)
        for row in self._bucket(model):
            if str(getattr(row, pk, None)) == want:
                return row
        return None

    def insert(self, model: type, values: dict[str, Any], pk: str = "id") -> Any:
        data = dict(values)
        if data.get(pk) in (None, ""):
            self._seq[model] = self._seq.get(model, 0) + 1
            n = self._seq[model]
            field = getattr(model, "model_fields", {}).get(pk)
            ann = getattr(field, "annotation", None) if field is not None else None
            data[pk] = str(n) if _wants_str_pk(ann) else n
        obj = model(**data)
        self._bucket(model).append(obj)
        return obj

    def update(self, model: type, pk_value: Any, values: dict[str, Any], pk: str = "id") -> Any:
        row = self.get(model, pk_value, pk=pk)
        if row is None:
            raise KeyError(pk_value)
        for key, val in values.items():
            setattr(row, key, val)
        return row

    def delete(self, model: type, pk_value: Any, pk: str = "id") -> None:
        want = str(pk_value)
        bucket = self._bucket(model)
        self._rows[model] = [r for r in bucket if str(getattr(r, pk, None)) != want]

    def distinct(self, model: type, field: str, limit: int = 30) -> list[Any]:
        seen: list[Any] = []
        for row in self._bucket(model):
            val = getattr(row, field, None)
            if val is not None and val not in seen:
                seen.append(val)
            if len(seen) >= limit:
                break
        return seen


class SqlStore:
    kind = "sql"

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def _session(self):
        from sqlmodel import Session

        return Session(self.engine)

    def count(self, model: type) -> int:
        from sqlmodel import func, select

        with self._session() as db:
            return int(db.exec(select(func.count()).select_from(model)).one() or 0)

    def list(
        self,
        model: type,
        *,
        q: str = "",
        search_fields: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        offset: int = 0,
        limit: int = 25,
        pk: str = "id",
    ) -> tuple[list[Any], int]:
        from sqlmodel import func, or_, select

        with self._session() as db:
            stmt = select(model)
            if order:
                col = getattr(model, order.lstrip("-"), None)
                if col is not None:
                    stmt = stmt.order_by(col.desc() if order.startswith("-") else col)
            if q and search_fields:
                clauses = []
                for field_name in search_fields:
                    col = getattr(model, field_name, None)
                    if col is not None:
                        clauses.append(col.contains(q))
                if clauses:
                    stmt = stmt.where(or_(*clauses))
            for fname, raw in (filters or {}).items():
                col = getattr(model, fname, None)
                if col is None:
                    continue
                coerced = _coerce_sql(model, fname, raw)
                if coerced is not None or str(raw).lower() in {"true", "false", "1", "0"}:
                    stmt = stmt.where(col == coerced)
            count_stmt = select(func.count()).select_from(model)
            where = getattr(stmt, "whereclause", None)
            if where is not None:
                count_stmt = count_stmt.where(where)
            try:
                total = int(db.exec(count_stmt).one() or 0)
            except Exception:
                total = len(db.exec(stmt).all())
            rows = list(db.exec(stmt.offset(offset).limit(limit)).all())
            return rows, total

    def get(self, model: type, pk_value: Any, pk: str = "id") -> Any | None:
        key = _sql_pk(model, pk, pk_value)
        with self._session() as db:
            return db.get(model, key)

    def insert(self, model: type, values: dict[str, Any], pk: str = "id") -> Any:
        obj = model(**values)
        with self._session() as db:
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj

    def update(self, model: type, pk_value: Any, values: dict[str, Any], pk: str = "id") -> Any:
        key = _sql_pk(model, pk, pk_value)
        with self._session() as db:
            row = db.get(model, key)
            if row is None:
                raise KeyError(pk_value)
            for name, val in values.items():
                setattr(row, name, val)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

    def delete(self, model: type, pk_value: Any, pk: str = "id") -> None:
        key = _sql_pk(model, pk, pk_value)
        with self._session() as db:
            row = db.get(model, key)
            if row is not None:
                db.delete(row)
                db.commit()

    def distinct(self, model: type, field: str, limit: int = 30) -> list[Any]:
        from sqlmodel import select

        col = getattr(model, field, None)
        if col is None:
            return []
        with self._session() as db:
            try:
                return [v for v in db.exec(select(col).distinct().limit(limit)).all() if v is not None]
            except Exception:
                return []


def _wants_str_pk(ann: Any) -> bool:
    text = str(ann or "")
    return "str" in text and "int" not in text.split("str")[0]


def _match(have: Any, want: Any) -> bool:
    if isinstance(want, bool):
        return bool(have) is want
    return have == want or str(have) == str(want)


def _coerce_memory(raw: Any) -> Any:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return raw


def _coerce_sql(model: type, name: str, raw: str) -> Any:
    from pyron.admin import inspect as insp

    field = model.model_fields.get(name)
    if field is None:
        return raw
    typ = insp.python_type(field.annotation)
    if typ is bool:
        return str(raw).lower() in {"1", "true", "yes", "on"}
    if typ is int:
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


def _sql_pk(model: type, pk: str, raw: Any) -> Any:
    field = getattr(model, "model_fields", {}).get(pk)
    if field is None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    from pyron.admin import inspect as insp

    if insp.python_type(field.annotation) is int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    return raw
