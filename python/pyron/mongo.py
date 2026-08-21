"""MongoDB client and store. Optional extra: `pip install pyron[mongo]`."""

from __future__ import annotations

from typing import Any

from pyron.settings import load_settings


def mongo_client(url: str | None = None, **kwargs: Any):
    """Return a pymongo MongoClient. Raises if the extra is not installed."""
    settings = load_settings()
    url = url or settings.mongo_url
    if not url:
        raise RuntimeError("MONGO_URL is empty. Set it or pass url= to mongo_client().")
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("MongoDB support needs pymongo. Install with: pip install pyron[mongo]") from exc
    return MongoClient(url, **kwargs)


def mongo_database(client: Any | None = None, name: str | None = None):
    client = client or mongo_client()
    settings = load_settings()
    return client[name or settings.mongo_db]


def mongo_query(
    *,
    q: str = "",
    search_fields: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a find() filter. Used by MongoStore and unit tests (no daemon)."""
    clauses: list[dict[str, Any]] = []
    if q and search_fields:
        clauses.append(
            {
                "$or": [
                    {field: {"$regex": q, "$options": "i"}}
                    for field in search_fields
                ]
            }
        )
    for name, raw in (filters or {}).items():
        clauses.append({name: _coerce(raw)})
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class MongoStore:
    kind = "mongo"

    def __init__(self, client: Any, database: str | None = None) -> None:
        self.client = client
        self.database = database or load_settings().mongo_db

    def _col(self, model: type):
        dbname = getattr(model, "database", None) or self.database
        name = getattr(model, "collection", None) or model.__name__.lower()
        if not name:
            raise RuntimeError(f"{model.__name__} needs a collection class attribute.")
        return self.client[dbname][name]

    def count(self, model: type) -> int:
        return int(self._col(model).estimated_document_count())

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
        query = mongo_query(q=q, search_fields=search_fields, filters=filters)
        col = self._col(model)
        total = col.count_documents(query)
        cursor = col.find(query)
        if order:
            desc = -1 if order.startswith("-") else 1
            field = order.lstrip("-")
            if field == pk:
                field = "_id"
            cursor = cursor.sort(field, desc)
        docs = list(cursor.skip(offset).limit(limit))
        return [_from_mongo(model, d) for d in docs], int(total)

    def get(self, model: type, pk_value: Any, pk: str = "id") -> Any | None:
        doc = self._col(model).find_one({"_id": _as_id(pk_value)})
        return _from_mongo(model, doc)

    def insert(self, model: type, values: dict[str, Any], pk: str = "id") -> Any:
        payload = _to_mongo(values, pk=pk)
        if "_id" not in payload:
            from bson import ObjectId

            payload["_id"] = ObjectId()
        self._col(model).insert_one(payload)
        return _from_mongo(model, payload)

    def update(self, model: type, pk_value: Any, values: dict[str, Any], pk: str = "id") -> Any:
        payload = _to_mongo(values, pk=pk)
        payload.pop("_id", None)
        self._col(model).update_one({"_id": _as_id(pk_value)}, {"$set": payload})
        return self.get(model, pk_value, pk=pk)

    def delete(self, model: type, pk_value: Any, pk: str = "id") -> None:
        self._col(model).delete_one({"_id": _as_id(pk_value)})

    def distinct(self, model: type, field: str, limit: int = 30) -> list[Any]:
        try:
            vals = self._col(model).distinct(field)
        except Exception:
            return []
        return [v for v in vals if v is not None][:limit]


def _coerce(raw: Any) -> Any:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return raw


def _as_id(raw: Any) -> Any:
    text = str(raw)
    try:
        from bson import ObjectId

        if ObjectId.is_valid(text) and len(text) == 24:
            return ObjectId(text)
    except Exception:
        pass
    return text


def _to_mongo(values: dict[str, Any], pk: str = "id") -> dict[str, Any]:
    data = dict(values)
    ident = data.pop(pk, None)
    if ident not in (None, ""):
        data["_id"] = _as_id(ident)
    return data


def _from_mongo(model: type, doc: dict[str, Any] | None) -> Any | None:
    if not doc:
        return None
    data = dict(doc)
    data["id"] = str(data.pop("_id"))
    if hasattr(model, "model_validate"):
        return model.model_validate(data)
    return model(**data)
