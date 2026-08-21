---
title: Home
template: home.html
hide:
  - toc
---

Pyron is a hybrid web framework: **Python** for handlers and the product surface, **Rust** for routing, validation, and JSON on the hot path. FastAPI-shaped to write, Django-shaped to operate. The concrete gap: HTML form + CLI scaffold + optional admin on the **same model**, without a second stack.

<div class="grid cards" markdown>

-   :material-rocket-launch: **Install & run**

    ---

    [Install](install.md) · [Quickstart](quickstart.md)

-   :material-api: **JSON API**

    ---

    Pydantic bodies, `/docs`, `/redoc`. [API](api.md)

-   :material-view-dashboard: **Admin panel**

    ---

    Optional `/admin`. [Admin](admin.md) · [Auth](auth.md)

-   :material-database: **SQL, Mongo, Redis**

    ---

    One process, three roles. [Data](data.md)

-   :material-shield-check: **Ship it**

    ---

    [Security](security.md) · [`pyron check --deploy`](cli.md#check-deploy)

-   :material-source-branch: **How it is built**

    ---

    [Architecture](architecture.md) · [vs FastAPI / Django](comparison.md)

</div>

## I want to…

| Goal | Read |
|---|---|
| Install and run something | [Install](install.md) · [Quickstart](quickstart.md) |
| Expose a JSON API with `/docs` | [API](api.md) |
| Add HTML pages | [Quickstart](quickstart.md#server-rendered-pages) · [CMS Pages](admin.md#pages-cms) |
| Site name, phone, hours | [Settings](admin.md#settings) |
| Use the admin panel (`/admin`) | [Admin panel](admin.md) |
| Switch language or light/dark | [Appearance](admin.md#language-and-appearance) |
| Start API-only, enable the panel later | [Enable features](enable.md) |
| SQL, Mongo, Redis | [Data](data.md) |
| Users and permissions | [Auth](auth.md) |
| Production checklist | [Security](security.md) |
| Split the project into apps | [CLI `startapp`](cli.md#startapp) |
| CLI reference | [CLI](cli.md) |
| What changed | [Changelog](changelog.md) |

The example shop is `examples/bookstore`: public catalog, JSON API, admin panel, and CMS pages (`/p/about`) on the same process.

```bash
cd examples/bookstore
pyron dev --app app.main:app
```
