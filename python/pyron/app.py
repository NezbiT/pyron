"""ASGI application. Handlers stay in Python; routing and validation hit Rust."""

from __future__ import annotations

import traceback
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from pyron._bridge import Router, SchemaRegistry
from pyron._version import __version__ as _PKG_VERSION
from pyron.exceptions import HTTPException, ValidationException
from pyron.openapi import build_spec, redoc_endpoint, swagger_endpoint
from pyron.params import UNSET
from pyron.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from pyron.routing import APIRouter, Route, call_endpoint, compile_endpoint
from pyron.templates import Templates
from pyron.vite import Vite, ViteProxyMiddleware

Lifespan = Callable[["Pyron"], AbstractAsyncContextManager[None]]


class Pyron:
    """A FastAPI-shaped ASGI app backed by the Pyron Rust core."""

    def __init__(
        self,
        title: str = "Pyron",
        version: str = _PKG_VERSION,
        description: str | None = None,
        *,
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        openapi_url: str | None = "/openapi.json",
        templates: str | None = None,
        static_dir: str | None = None,
        static_url: str = "/static",
        vite: Vite | None = None,
        lifespan: Lifespan | None = None,
        servers: list[Any] | None = None,
        redirect_slashes: bool = True,
        admin: bool | Any = False,
        admin_engine: Any = None,
        admin_mongo: Any = None,
        admin_path: str = "/admin",
        settings: Any = None,
    ) -> None:
        self.title = title
        self.version = version
        self.description = description
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url
        self.servers = servers or []
        self.redirect_slashes = redirect_slashes
        if settings is None:
            from pyron.settings import load_settings

            settings = load_settings()
        self.settings = settings
        self.debug = bool(settings.debug)

        self._router = Router()
        self._registry = SchemaRegistry()
        self._routes: dict[int, Route] = {}
        self.routes: list[Route] = []
        self._next_id = 1
        self._middleware_stack: ASGIApp | None = None
        self.user_middleware: list[tuple[type, dict[str, Any]]] = []
        self.exception_handlers: dict[Any, Callable[..., Awaitable[Response]]] = {}
        self._openapi: dict[str, Any] | None = None
        self._mounts: list[tuple[str, ASGIApp]] = []
        self._lifespan = lifespan
        self.state: dict[str, Any] = {}

        self.templates = Templates(templates) if templates else None
        self.vite = vite
        if self.templates and self.vite:
            self.templates.bind_vite(self.vite)
        if static_dir:
            self.mount(static_url, StaticFiles(directory=static_dir), name="static")

        self.admin = None
        if self.settings.expose_docs:
            self._install_docs_routes()
        else:
            self.docs_url = None
            self.redoc_url = None
            self.openapi_url = None
        if admin:
            self.mount_admin(
                admin if admin is not True else None,
                path=admin_path,
                engine=admin_engine,
                mongo=admin_mongo,
            )

    def enable(self, feature: str, **kwargs: Any) -> Any:
        """Turn a layer on later. Existing routes are not rewritten."""
        if feature == "admin":
            if self.admin is None:
                return self.mount_admin(
                    engine=kwargs.get("engine"),
                    mongo=kwargs.get("mongo"),
                    path=kwargs.get("path", "/admin"),
                )
            if kwargs.get("engine") is not None:
                self.admin.bind(kwargs["engine"])
            if kwargs.get("mongo") is not None:
                self.admin.bind_mongo(kwargs["mongo"])
            return self.admin
        if feature == "mongo":
            from pyron.mongo import mongo_client

            client = kwargs.get("client") or mongo_client(kwargs.get("url"))
            if self.admin is not None:
                self.admin.bind_mongo(client)
            return client
        if feature == "redis":
            from pyron.cache import redis_client, reset_cache

            client = redis_client(kwargs.get("url"))
            reset_cache()
            return client
        raise ValueError(f"unknown feature {feature!r}. Known: admin, mongo, redis")

    def include_app(self, module: str) -> None:
        """Load models/admin/routes from a package created by `pyron startapp`."""
        import importlib

        try:
            pkg = importlib.import_module(module)
        except ImportError as exc:
            raise ImportError(f"Cannot import app {module!r}") from exc
        router = getattr(pkg, "router", None)
        if router is not None:
            self.include_router(router)
        register = getattr(pkg, "register", None)
        if callable(register) and self.admin is not None:
            register(self.admin)
        try:
            routes_mod = importlib.import_module(f"{module}.routes")
            if getattr(routes_mod, "router", None) is not None:
                self.include_router(routes_mod.router)
        except ImportError:
            pass
        try:
            admin_mod = importlib.import_module(f"{module}.admin")
            if callable(getattr(admin_mod, "register", None)) and self.admin is not None:
                admin_mod.register(self.admin)
        except ImportError:
            pass

    def url_for(self, name: str, **path_params: Any) -> str:
        for route in self.routes:
            if route.name != name:
                continue
            path = route.path
            for key, value in path_params.items():
                token = "{" + key + "}"
                wild = "{*" + key + "}"
                if token in path:
                    path = path.replace(token, str(value))
                elif wild in path:
                    path = path.replace(wild, str(value))
                else:
                    raise KeyError(f"Route {name!r} has no path parameter {key!r}")
            if "{" in path:
                raise KeyError(f"Missing path parameters for route {name!r}: {path}")
            return path
        raise KeyError(f"No route named {name!r}")

    def mount_admin(
        self,
        site: Any | None = None,
        *,
        path: str = "/admin",
        engine: Any = None,
        mongo: Any = None,
    ) -> Any:
        """Mount the visual desk at `path` (Django-style admin)."""
        from pyron.admin import AdminSite

        if site is None or site is True:
            site = AdminSite(engine=engine, title=self.title, mongo=mongo)
        else:
            if engine is not None:
                site.bind(engine)
            if mongo is not None:
                site.bind_mongo(mongo)
        site.attach(self, prefix=path)
        from pyron.authz import DeskAuthMiddleware

        self.add_middleware(DeskAuthMiddleware, site=site)
        return site

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        methods: Sequence[str],
        **kwargs: Any,
    ) -> None:
        tmp = APIRouter()
        tmp.add_api_route(path, endpoint, methods=methods, **kwargs)
        self._register(tmp.routes[0])

    def include_router(self, router: APIRouter, *, prefix: str = "") -> None:
        if prefix:
            wrapper = APIRouter(prefix=prefix, tags=router.tags)
            wrapper.include_router(router)
            for route in wrapper.routes:
                self._register(route)
        else:
            for route in router.routes:
                clone_path = route.path
                if router.prefix and not clone_path.startswith(router.prefix):
                    clone_path = router.prefix.rstrip("/") + (
                        route.path if route.path.startswith("/") else "/" + route.path
                    )
                route.path = clone_path
                self._register(route)

    def get(self, path: str, **kwargs: Any):
        return self._deco(path, ["GET"], kwargs)

    def post(self, path: str, **kwargs: Any):
        return self._deco(path, ["POST"], kwargs)

    def put(self, path: str, **kwargs: Any):
        return self._deco(path, ["PUT"], kwargs)

    def patch(self, path: str, **kwargs: Any):
        return self._deco(path, ["PATCH"], kwargs)

    def delete(self, path: str, **kwargs: Any):
        return self._deco(path, ["DELETE"], kwargs)

    def head(self, path: str, **kwargs: Any):
        return self._deco(path, ["HEAD"], kwargs)

    def options(self, path: str, **kwargs: Any):
        return self._deco(path, ["OPTIONS"], kwargs)

    def api_route(self, path: str, *, methods: Sequence[str], **kwargs: Any):
        return self._deco(path, list(methods), kwargs)

    def _deco(self, path: str, methods: list[str], kwargs: dict[str, Any]):
        def decorator(fn):
            self.add_api_route(path, fn, methods=methods, **kwargs)
            return fn

        return decorator

    def _register(self, route: Route) -> None:
        route.route_id = self._next_id
        self._next_id += 1
        route.compiled = compile_endpoint(route)
        route._schema_id = None  # type: ignore[attr-defined]
        if route.compiled.body_slot is not None:
            model = route.compiled.body_slot.annotation
            if hasattr(model, "model_json_schema"):
                try:
                    route._schema_id = self._registry.register(model.model_json_schema())  # type: ignore[attr-defined]
                except Exception:
                    route._schema_id = None  # type: ignore[attr-defined]
        for method in route.methods:
            self._router.add(method, route.path, route.route_id)
        self._routes[route.route_id] = route
        self.routes.append(route)
        self._openapi = None
        self._middleware_stack = None

    def mount(self, path: str, app: ASGIApp, name: str | None = None) -> None:
        self._mounts.append((path.rstrip("/") or "/", app))
        self._middleware_stack = None

    def add_middleware(self, cls: type, **kwargs: Any) -> None:
        self.user_middleware.insert(0, (cls, kwargs))
        self._middleware_stack = None

    def add_exception_handler(self, exc_class: Any, handler: Callable[..., Awaitable[Response]]) -> None:
        self.exception_handlers[exc_class] = handler

    def exception_handler(self, exc_class: Any):
        def decorator(fn):
            self.add_exception_handler(exc_class, fn)
            return fn

        return decorator

    def on_event(self, event: str):
        handlers = getattr(self, f"_{event}_handlers", None)
        if handlers is None:
            handlers = []
            setattr(self, f"_{event}_handlers", handlers)

        def decorator(fn):
            handlers.append(fn)
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Docs / templates
    # ------------------------------------------------------------------

    def _install_docs_routes(self) -> None:
        if self.openapi_url:
            self.add_api_route(
                self.openapi_url,
                self._openapi_route,
                methods=["GET"],
                include_in_schema=False,
                name="openapi",
            )
        if self.docs_url:
            self.add_api_route(
                self.docs_url,
                swagger_endpoint,
                methods=["GET"],
                include_in_schema=False,
                name="swagger",
            )
        if self.redoc_url:
            self.add_api_route(
                self.redoc_url,
                redoc_endpoint,
                methods=["GET"],
                include_in_schema=False,
                name="redoc",
            )

    async def _openapi_route(self, request: Request) -> JSONResponse:
        return JSONResponse(self.openapi())

    def openapi(self) -> dict[str, Any]:
        if self._openapi is None:
            self._openapi = build_spec(self)
        return self._openapi

    async def render(
        self,
        request: Request | None,
        name: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> HTMLResponse:
        if self.templates is None:
            raise RuntimeError("No templates directory configured on this Pyron app")
        return await self.templates.render(request, name, context, **kwargs)

    # ------------------------------------------------------------------
    # ASGI
    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["app"] = self
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return
        if self._middleware_stack is None:
            self._middleware_stack = self._build_middleware()
        await self._middleware_stack(scope, receive, send)

    def _build_middleware(self) -> ASGIApp:
        from pyron.security import SecurityMiddleware

        app: ASGIApp = self._app
        if self.vite and self.vite.dev:
            app = ViteProxyMiddleware(app, self.vite)
        for cls, kwargs in reversed(self.user_middleware):
            app = cls(app, **kwargs)
        app = SecurityMiddleware(app, self.settings)
        return app

    async def _app(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path = scope.get("path") or "/"
        for mount_path, mounted in self._mounts:
            if path == mount_path or path.startswith(mount_path + "/"):
                tail = path[len(mount_path) :] or "/"
                child = dict(scope)
                child["path"] = tail
                child["root_path"] = (scope.get("root_path") or "") + mount_path
                await mounted(child, receive, send)
                return
        request = Request(scope, receive)
        try:
            response = await self._dispatch(request)
        except Exception as exc:
            response = await self._handle_exception(request, exc)
        await response(scope, receive, send)

    async def _dispatch(self, request: Request) -> Response:
        found = self._router.find(request.method, request.url.path)
        if found is None:
            if self.redirect_slashes:
                alt = _slash_alt(request.url.path)
                if alt is not None and self._router.find(request.method, alt) is not None:
                    url = str(request.url.replace(path=alt))
                    return Response(status_code=307, headers={"location": url})
            return self._not_found(request)
        if found[0] is None:
            allowed = found[1] or []
            return JSONResponse(
                {"detail": "Method Not Allowed"},
                status_code=405,
                headers={"allow": ", ".join(allowed)},
            )
        route_id, path_params = found
        route = self._routes[route_id]
        kwargs = await self._bind(request, route, path_params)
        raw = await call_endpoint(route, kwargs)
        response = self._normalize(raw, route)
        _attach_background(route, kwargs, response)
        return response

    async def _bind(self, request: Request, route: Route, path_params: dict[str, str]) -> dict[str, Any]:
        compiled = route.compiled
        assert compiled is not None
        kwargs: dict[str, Any] = {}
        cache: dict[Any, Any] = {}
        body_bytes: bytes | None = None
        for slot in compiled.slots:
            if slot.source == "request":
                kwargs[slot.name] = request
                continue
            if slot.source == "background":
                from starlette.background import BackgroundTasks

                kwargs[slot.name] = BackgroundTasks()
                continue
            if slot.source == "depend":
                assert slot.depend is not None
                dep = slot.depend.dependency
                if slot.depend.use_cache and dep in cache:
                    kwargs[slot.name] = cache[dep]
                else:
                    result = dep(request) if _takes_request(dep) else dep()
                    if hasattr(result, "__await__"):
                        result = await result
                    cache[dep] = result
                    kwargs[slot.name] = result
                continue
            if slot.source == "path":
                raw = path_params.get(slot.alias)
                if raw is None:
                    raise HTTPException(422, [{"loc": ["path", slot.alias], "msg": "missing", "type": "missing"}])
                kwargs[slot.name] = _coerce(raw, slot.annotation)
                continue
            if slot.source == "query":
                raw = request.query_params.get(slot.alias)
                if raw is None:
                    if slot.required:
                        raise ValidationException(
                            [{"loc": ["query", slot.alias], "msg": "field required", "type": "missing"}]
                        )
                    kwargs[slot.name] = None if slot.default is UNSET else slot.default
                else:
                    kwargs[slot.name] = _coerce(raw, slot.annotation)
                continue
            if slot.source == "header":
                raw = request.headers.get(slot.alias)
                if raw is None:
                    if slot.required:
                        raise ValidationException(
                            [{"loc": ["header", slot.alias], "msg": "field required", "type": "missing"}]
                        )
                    kwargs[slot.name] = None if slot.default is UNSET else slot.default
                else:
                    kwargs[slot.name] = _coerce(raw, slot.annotation)
                continue
            if slot.source == "cookie":
                raw = request.cookies.get(slot.alias)
                if raw is None:
                    if slot.required:
                        raise ValidationException(
                            [{"loc": ["cookie", slot.alias], "msg": "field required", "type": "missing"}]
                        )
                    kwargs[slot.name] = None if slot.default is UNSET else slot.default
                else:
                    kwargs[slot.name] = raw
                continue
            if slot.source == "body":
                if body_bytes is None:
                    body_bytes = await request.body()
                kwargs[slot.name] = self._parse_body(route, slot, body_bytes)
        return kwargs

    def _parse_body(self, route: Route, slot: Any, body: bytes) -> Any:
        if not body:
            if not slot.required:
                return None if slot.default is UNSET else slot.default
            raise ValidationException([{"loc": ["body"], "msg": "JSON body required", "type": "missing"}])
        schema_id = getattr(route, "_schema_id", None)
        parsed: Any = None
        if schema_id is not None:
            ok, payload = self._registry.validate(schema_id, body, True)
            if not ok:
                raise ValidationException(payload)
            parsed = payload
        model = slot.annotation
        if hasattr(model, "model_validate"):
            try:
                return model.model_validate(parsed if parsed is not None else _loads_or_raise(body))
            except Exception as exc:
                errs = getattr(exc, "errors", None)
                if callable(errs):
                    raise ValidationException(_pydantic_errors(errs())) from exc
                raise ValidationException(
                    [{"loc": ["body"], "msg": str(exc), "type": "value_error"}]
                ) from exc
        if parsed is not None:
            return parsed
        return _loads_or_raise(body)

    def _normalize(self, raw: Any, route: Route) -> Response:
        if isinstance(raw, Response):
            return raw
        if raw is None:
            return Response(status_code=route.status_code)
        if route.response_class is not None and not isinstance(raw, Response):
            return route.response_class(raw, status_code=route.status_code)
        if isinstance(raw, (bytes, str)) and route.response_class is None:
            if isinstance(raw, bytes):
                return Response(raw, status_code=route.status_code, media_type="application/octet-stream")
            return PlainTextResponse(raw, status_code=route.status_code)
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        return JSONResponse(raw, status_code=route.status_code)

    def _not_found(self, request: Request) -> Response:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and self.templates:
            try:
                return self.templates.render_sync(
                    request,
                    "404.html",
                    {"path": request.url.path},
                    status_code=404,
                )
            except Exception:
                pass
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response:
        for cls, handler in self.exception_handlers.items():
            if isinstance(exc, cls):
                result = handler(request, exc)
                if hasattr(result, "__await__"):
                    result = await result
                return result
        from pyron.authz import NotAuthenticated, PermissionDenied

        accept = request.headers.get("accept", "")
        html = "text/html" in accept
        if isinstance(exc, NotAuthenticated):
            if html and self.admin is not None:
                return RedirectResponse(exc.login_url, status_code=303)
            return JSONResponse({"detail": exc.detail}, status_code=401)
        if isinstance(exc, PermissionDenied):
            if html and self.admin is not None:
                return self.admin.render_denied(request, exc.permission)
            return JSONResponse({"detail": exc.detail}, status_code=403)
        if isinstance(exc, ValidationException):
            return JSONResponse({"detail": exc.errors}, status_code=exc.status_code)
        if isinstance(exc, HTTPException):
            headers = dict(exc.headers)
            if isinstance(exc.detail, (dict, list)):
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
        tb = traceback.format_exc()
        if self.debug:
            return PlainTextResponse(tb, status_code=500)
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    async def _handle_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False
        try:
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await self._startup()
                    if self._lifespan is not None:
                        self._lifespan_cm = self._lifespan(self)  # type: ignore[attr-defined]
                        await self._lifespan_cm.__aenter__()  # type: ignore[attr-defined]
                    started = True
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    if self._lifespan is not None and started:
                        await self._lifespan_cm.__aexit__(None, None, None)  # type: ignore[attr-defined]
                    await self._shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        except Exception as exc:
            kind = "lifespan.startup.failed" if not started else "lifespan.shutdown.failed"
            await send({"type": kind, "message": str(exc)})

    async def _startup(self) -> None:
        for fn in getattr(self, "_startup_handlers", []):
            result = fn()
            if hasattr(result, "__await__"):
                await result

    async def _shutdown(self) -> None:
        for fn in getattr(self, "_shutdown_handlers", []):
            result = fn()
            if hasattr(result, "__await__"):
                await result


def _attach_background(route: Route, kwargs: dict[str, Any], response: Response) -> None:
    compiled = route.compiled
    if compiled is None:
        return
    for slot in compiled.slots:
        if slot.source != "background":
            continue
        tasks = kwargs.get(slot.name)
        if tasks is None:
            return
        existing = getattr(response, "background", None)
        if existing is None:
            response.background = tasks
            return
        if existing is tasks:
            return
        for item in getattr(tasks, "tasks", []):
            existing.add_task(item.func, *item.args, **item.kwargs)
        return


def _slash_alt(path: str) -> str | None:
    if path == "/":
        return None
    if path.endswith("/"):
        return path[:-1]
    return path + "/"


def _coerce(raw: str, annotation: Any) -> Any:
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = [a for a in getattr(annotation, "__args__", ()) if a is not type(None)]
        if args:
            annotation = args[0]
    if annotation is inspect_empty() or annotation is Any:
        return raw
    if annotation is str:
        return raw
    if annotation is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ValidationException(
                [{"loc": ["path"], "msg": f"not a valid integer: {raw}", "type": "int_parsing"}]
            ) from exc
    if annotation is float:
        try:
            return float(raw)
        except ValueError as exc:
            raise ValidationException(
                [{"loc": ["path"], "msg": f"not a valid number: {raw}", "type": "float_parsing"}]
            ) from exc
    if annotation is bool:
        return raw.lower() in {"1", "true", "yes", "on"}
    return raw


def inspect_empty() -> Any:
    import inspect

    return inspect.Parameter.empty


def _takes_request(fn: Callable[..., Any]) -> bool:
    try:
        import inspect

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        return bool(params) and params[0].name in {"request", "req"}
    except (TypeError, ValueError):
        return False


def _loads_or_raise(body: bytes) -> Any:
    from pyron._bridge import loads

    try:
        return loads(body)
    except Exception as exc:
        raise ValidationException(
            [{"loc": ["body"], "msg": f"invalid JSON: {exc}", "type": "json_invalid"}]
        ) from exc


def _pydantic_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in errors:
        loc = [str(x) for x in e.get("loc", ())]
        out.append({"loc": loc, "msg": e.get("msg", "invalid"), "type": e.get("type", "value_error")})
    return out


def create_app(*args: Any, **kwargs: Any) -> Pyron:
    return Pyron(*args, **kwargs)
