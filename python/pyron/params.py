"""FastAPI-style parameter declarations."""

from __future__ import annotations

from typing import Any

_UNSET = object()


class Param:
    kind: str = "query"

    def __init__(
        self,
        default: Any = _UNSET,
        *,
        alias: str | None = None,
        description: str | None = None,
        gt: float | None = None,
        ge: float | None = None,
        lt: float | None = None,
        le: float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> None:
        self.default = default
        self.alias = alias
        self.description = description
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.min_length = min_length
        self.max_length = max_length

    @property
    def required(self) -> bool:
        return self.default is _UNSET


class Query(Param):
    kind = "query"


class Path(Param):
    kind = "path"


class Header(Param):
    kind = "header"


class Cookie(Param):
    kind = "cookie"


class Body(Param):
    kind = "body"


class Depends:
    def __init__(self, dependency: Any, *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache


UNSET = _UNSET
