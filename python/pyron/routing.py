"""Route table, APIRouter, and handler signature compilation."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints

from pyron.params import UNSET, Body, Cookie, Depends, Header, Param, Path, Query

Endpoint = Callable[..., Any]


@dataclass
class Route:
    path: str
    methods: list[str]
    endpoint: Endpoint
    name: str
    route_id: int
    status_code: int = 200
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    include_in_schema: bool = True
    response_model: Any = None
    response_class: Any = None
    compiled: CompiledEndpoint | None = None


@dataclass
class ParamSlot:
    name: str
    annotation: Any
    source: str  # path | query | header | cookie | body | request | depend | background
    alias: str
    default: Any
    required: bool
    param: Param | Depends | None
    depend: Depends | None = None


@dataclass
class CompiledEndpoint:
    is_coroutine: bool
    takes_kwargs: bool
    slots: list[ParamSlot]
    body_slot: ParamSlot | None
    request_name: str | None


class APIRouter:
    """Collect routes that can later be mounted on a `Pyron` app."""

    def __init__(
        self,
        *,
        prefix: str = "",
        tags: Sequence[str] | None = None,
    ) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags = list(tags or [])
        self.routes: list[Route] = []

    def add_api_route(
        self,
        path: str,
        endpoint: Endpoint,
        *,
        methods: Sequence[str],
        name: str | None = None,
        status_code: int = 200,
        tags: Sequence[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        include_in_schema: bool = True,
        response_model: Any = None,
        response_class: Any = None,
    ) -> None:
        full = _join(self.prefix, path)
        merged_tags = list(self.tags)
        if tags:
            merged_tags.extend(tags)
        self.routes.append(
            Route(
                path=full,
                methods=[m.upper() for m in methods],
                endpoint=endpoint,
                name=name or endpoint.__name__,
                route_id=-1,
                status_code=status_code,
                tags=merged_tags,
                summary=summary or _first_line(endpoint.__doc__),
                description=description or inspect.cleandoc(endpoint.__doc__ or "") or None,
                include_in_schema=include_in_schema,
                response_model=response_model,
                response_class=response_class,
            )
        )

    def get(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["GET"], kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["POST"], kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["PUT"], kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["PATCH"], kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["DELETE"], kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["HEAD"], kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, ["OPTIONS"], kwargs)

    def api_route(
        self, path: str, *, methods: Sequence[str], **kwargs: Any
    ) -> Callable[[Endpoint], Endpoint]:
        return self._deco(path, list(methods), kwargs)

    def include_router(self, router: APIRouter, *, prefix: str = "") -> None:
        extra = _join(self.prefix, prefix)
        for route in router.routes:
            clone = Route(
                path=_join(extra, route.path if extra else route.path),
                methods=list(route.methods),
                endpoint=route.endpoint,
                name=route.name,
                route_id=-1,
                status_code=route.status_code,
                tags=list(self.tags) + list(route.tags),
                summary=route.summary,
                description=route.description,
                include_in_schema=route.include_in_schema,
                response_model=route.response_model,
                response_class=route.response_class,
            )
            if extra:
                clone.path = _join(extra, route.path[len(router.prefix) :] or "/")
            self.routes.append(clone)

    def _deco(self, path: str, methods: list[str], kwargs: dict[str, Any]) -> Callable[[Endpoint], Endpoint]:
        def decorator(fn: Endpoint) -> Endpoint:
            self.add_api_route(path, fn, methods=methods, **kwargs)
            return fn

        return decorator


def compile_endpoint(route: Route) -> CompiledEndpoint:
    endpoint = route.endpoint
    try:
        hints = get_type_hints(endpoint)
    except Exception:
        hints = {k: v.annotation for k, v in inspect.signature(endpoint).parameters.items()}
    sig = inspect.signature(endpoint)
    path_names = set(_path_param_names(route.path))
    slots: list[ParamSlot] = []
    body_slot: ParamSlot | None = None
    request_name: str | None = None
    takes_kwargs = False

    for name, param in sig.parameters.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            takes_kwargs = True
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        annotation = hints.get(name, param.annotation)
        default = param.default
        if _is_request_type(annotation, name):
            request_name = name
            slots.append(
                ParamSlot(
                    name=name,
                    annotation=annotation,
                    source="request",
                    alias=name,
                    default=UNSET,
                    required=True,
                    param=None,
                )
            )
            continue
        if _is_background_type(annotation, name):
            slots.append(
                ParamSlot(
                    name=name,
                    annotation=annotation,
                    source="background",
                    alias=name,
                    default=UNSET,
                    required=True,
                    param=None,
                )
            )
            continue
        if isinstance(default, Depends) or _is_depends_annotation(annotation):
            depend = default if isinstance(default, Depends) else Depends(annotation)
            slots.append(
                ParamSlot(
                    name=name,
                    annotation=annotation,
                    source="depend",
                    alias=name,
                    default=UNSET,
                    required=True,
                    param=None,
                    depend=depend,
                )
            )
            continue
        if isinstance(default, Param):
            source = default.kind
            alias = default.alias or name
            required = default.required
            if source == "path" or name in path_names:
                source = "path"
            slot = ParamSlot(
                name=name,
                annotation=annotation,
                source=source,
                alias=alias,
                default=default.default,
                required=required,
                param=default,
            )
            if source == "body":
                body_slot = slot
            slots.append(slot)
            continue
        if name in path_names:
            slots.append(
                ParamSlot(
                    name=name,
                    annotation=annotation,
                    source="path",
                    alias=name,
                    default=UNSET,
                    required=True,
                    param=None,
                )
            )
            continue
        if _is_pydantic_model(annotation):
            slot = ParamSlot(
                name=name,
                annotation=annotation,
                source="body",
                alias=name,
                default=default if default is not inspect.Parameter.empty else UNSET,
                required=default is inspect.Parameter.empty,
                param=None,
            )
            body_slot = slot
            slots.append(slot)
            continue
        slots.append(
            ParamSlot(
                name=name,
                annotation=annotation,
                source="query",
                alias=name,
                default=default if default is not inspect.Parameter.empty else UNSET,
                required=default is inspect.Parameter.empty,
                param=None,
            )
        )
    return CompiledEndpoint(
        is_coroutine=inspect.iscoroutinefunction(endpoint),
        takes_kwargs=takes_kwargs,
        slots=slots,
        body_slot=body_slot,
        request_name=request_name,
    )


def _join(prefix: str, path: str) -> str:
    prefix = prefix.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    if not prefix:
        return path
    return prefix + path


def _path_param_names(path: str) -> list[str]:
    names: list[str] = []
    for part in path.strip("/").split("/"):
        if part.startswith("{*") and part.endswith("}"):
            names.append(part[2:-1])
        elif part.startswith("{") and part.endswith("}"):
            names.append(part[1:-1])
    return names


def _first_line(doc: str | None) -> str | None:
    if not doc:
        return None
    line = doc.strip().splitlines()[0].strip()
    return line or None


def _is_request_type(annotation: Any, name: str) -> bool:
    if name == "request":
        return True
    text = getattr(annotation, "__name__", "") or str(annotation)
    return text.endswith("Request") and "HTTP" not in text


def _is_background_type(annotation: Any, name: str) -> bool:
    text = getattr(annotation, "__name__", "") or str(annotation)
    return "BackgroundTasks" in str(text)


def _is_depends_annotation(annotation: Any) -> bool:
    return False


def _is_pydantic_model(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            annotation = args[0]
    return isinstance(annotation, type) and hasattr(annotation, "model_validate")


async def call_endpoint(route: Route, kwargs: dict[str, Any]) -> Any:
    compiled = route.compiled
    endpoint = route.endpoint
    if compiled is None or compiled.is_coroutine:
        return await endpoint(**kwargs) if inspect.iscoroutinefunction(endpoint) else endpoint(**kwargs)
    import anyio

    return await anyio.to_thread.run_sync(lambda: endpoint(**kwargs))
