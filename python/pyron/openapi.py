"""OpenAPI 3.1 document + Swagger / ReDoc UI.

Route metadata is assembled in Python (where the type hints live) and
handed to the Rust `OpenApiBuilder` for the final JSON document.
"""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

from starlette.requests import Request

from pyron._bridge import OpenApiBuilder
from pyron.responses import HTMLResponse, JSONResponse
from pyron.routing import Route


def build_spec(app: Any) -> dict[str, Any]:
    builder = OpenApiBuilder(app.title, app.version, app.description)
    if app.servers:
        for server in app.servers:
            if isinstance(server, str):
                builder.add_server(server, None)
            else:
                builder.add_server(server.get("url", "/"), server.get("description"))
    seen_tags: set[str] = set()
    seen_schemas: set[str] = set()
    for route in app.routes:
        if not route.include_in_schema:
            continue
        for tag in route.tags:
            if tag not in seen_tags:
                builder.add_tag(tag, None)
                seen_tags.add(tag)
        model = route.response_model
        if model is not None and hasattr(model, "model_json_schema"):
            name = model.__name__
            if name not in seen_schemas:
                builder.add_schema(name, _strip_defs(model.model_json_schema()))
                seen_schemas.add(name)
        if route.compiled and route.compiled.body_slot is not None:
            body_model = route.compiled.body_slot.annotation
            if hasattr(body_model, "model_json_schema"):
                name = body_model.__name__
                if name not in seen_schemas:
                    builder.add_schema(name, _strip_defs(body_model.model_json_schema()))
                    seen_schemas.add(name)
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            builder.add_operation(method, route.path, _operation(route, method))
    return builder.as_dict()


def _operation(route: Route, method: str) -> dict[str, Any]:
    compiled = route.compiled
    parameters: list[dict[str, Any]] = []
    request_body = None
    if compiled:
        for slot in compiled.slots:
            if slot.source in {"path", "query", "header", "cookie"}:
                parameters.append(
                    {
                        "name": slot.alias,
                        "in": slot.source,
                        "required": slot.required or slot.source == "path",
                        "schema": _annotation_schema(slot.annotation),
                        **(
                            {"description": slot.param.description}
                            if slot.param and slot.param.description
                            else {}
                        ),
                    }
                )
        if compiled.body_slot is not None:
            body = compiled.body_slot
            schema: dict[str, Any]
            if hasattr(body.annotation, "__name__") and hasattr(body.annotation, "model_json_schema"):
                schema = {"$ref": f"#/components/schemas/{body.annotation.__name__}"}
            else:
                schema = {"type": "object"}
            request_body = {
                "required": body.required,
                "content": {"application/json": {"schema": schema}},
            }
    responses: dict[str, Any] = {
        str(route.status_code): {
            "description": "Successful Response",
        }
    }
    if route.response_model is not None and hasattr(route.response_model, "__name__"):
        responses[str(route.status_code)]["content"] = {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{route.response_model.__name__}"}
            }
        }
    responses["422"] = {
        "description": "Validation Error",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "detail": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "loc": {"type": "array", "items": {"type": "string"}},
                                    "msg": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                            },
                        }
                    },
                }
            }
        },
    }
    op: dict[str, Any] = {
        "operationId": f"{method.lower()}_{route.name}",
        "responses": responses,
    }
    if route.summary:
        op["summary"] = route.summary
    if route.description:
        op["description"] = route.description
    if route.tags:
        op["tags"] = list(route.tags)
    if parameters:
        op["parameters"] = parameters
    if request_body:
        op["requestBody"] = request_body
    return op


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if args:
            annotation = args[0]
    mapping = {
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        str: {"type": "string"},
        bytes: {"type": "string", "format": "binary"},
    }
    if annotation in mapping:
        return mapping[annotation]
    name = getattr(annotation, "__name__", "")
    if name == "UUID":
        return {"type": "string", "format": "uuid"}
    return {"type": "string"}


def _strip_defs(schema: dict[str, Any]) -> dict[str, Any]:
    return schema


def docs_html(title: str, spec_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — API docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
  <style>
    :root {{ color-scheme: dark; }}
    html, body {{ margin: 0; background: #1a1512; }}
    .topbar {{ display: none; }}
    .swagger-ui {{ font-family: "IBM Plex Sans", "Segoe UI", sans-serif; }}
    .swagger-ui .info .title {{ color: #f4ede4; }}
    .swagger-ui .info p, .swagger-ui .info li {{ color: #cbbba8; }}
    .swagger-ui .scheme-container {{ background: #241c17; box-shadow: none; }}
    .swagger-ui .opblock-tag {{ color: #f4ede4; border-color: #3a2c24; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: {json.dumps(spec_url)},
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: true,
      defaultModelsExpandDepth: 1
    }});
  </script>
</body>
</html>
"""


def redoc_html(title: str, spec_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — ReDoc</title>
  <style>body {{ margin: 0; background: #1a1512; }}</style>
</head>
<body>
  <redoc spec-url="{spec_url}"></redoc>
  <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>
"""


async def openapi_endpoint(request: Request) -> JSONResponse:
    app = request.app
    return JSONResponse(app.openapi())


async def swagger_endpoint(request: Request) -> HTMLResponse:
    app = request.app
    return HTMLResponse(docs_html(app.title, app.openapi_url))


async def redoc_endpoint(request: Request) -> HTMLResponse:
    app = request.app
    return HTMLResponse(redoc_html(app.title, app.openapi_url))
