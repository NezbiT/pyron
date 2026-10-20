# FastAPI vs Django vs Pyron

The bet is not RPS. FastAPI already wins “JSON API in an afternoon.” Django wins “operate the product.” **Pyron is the path FastAPI leaves you to invent:** HTML pages, a CLI that scaffolds them, and an admin you can turn on later — same models, same process.

| Everyday job | FastAPI | Django | Pyron |
|---|---|---|---|
| `POST /books` + `/docs` | Minutes | More setup | Same as FastAPI |
| HTML page + form that saves | You wire Starlette + Jinja + CSRF yourself | Built in | `templates=` + `Form()` + `redirect(..., message=...)` |
| `init` → running app | Run an existing file | `startproject` (heavy) | `pyron init shop && pyron dev` |
| Edit rows without extra views | You build it | `/admin` | `/admin` when you want it |
| Add a public page from the panel | You write a route + template | FlatPages / CMS app | **Pages** in `/admin` (Markdown) → `/p/{slug}` |
| Shop name, phone, hours | You hardcode templates | sites / settings app | **Settings** in `/admin`; public header/footer read `site` |
| API-only for months, panel later | N/A | Hard | `pyron enable admin` does not rewrite handlers |
| SQL + Mongo + Redis | You wire it | SQL first | SQL default; Mongo documents; Redis cache |
| See workers and reload the process | You add a process manager | One `runserver` process | [`pyron inspect`](inspector.md) (status, reload, scale, shutdown) |

## What is 2–3× easier

After `pyron init shop` (default template is **ssr**):

1. The **home page has a form**. Submitting it writes a row. You do not open `/docs` to create the first record.
2. `/api/items` and `/admin` read **that same table**. One `Item` model.
3. A flash message confirms the save. No JS.

In FastAPI that is three tutorials (Jinja, forms, admin-or-SQLAdmin) and two extra packages. In Django it is a project full of apps before “hello.”

Pyron is not a FastAPI rewrite in Rust and not a Django clone. Layers you skip (`admin=False`, no templates) stay out of the process.
