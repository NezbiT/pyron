# FastAPI vs Django vs Pyron

| Everyday question | FastAPI | Django | Pyron |
|---|---|---|---|
| `POST /books` + `/docs` in minutes | Yes | Possible, more setup | Yes, FastAPI-shaped |
| Panel to edit rows without extra views | You build it | `/admin` | Admin panel `/admin` (optional) |
| Root operator | You build it | Yes | Yes, when the admin panel is on |
| HTML for crawlers + JSON for apps | JSON easy | HTML easy | Both |
| Hot path (route + validate + JSON) | Python + pydantic-core | Python | Rust core + Python handlers |
| SQL + Mongo + Redis in one process | You wire it | SQL first | SQL default; Mongo documents; Redis cache |

Pyron is not a FastAPI rewrite in Rust and not a Django clone. Write endpoints like FastAPI; operate data like Django when you turn the admin panel on. Layers you skip (`admin=False`, no templates) stay out of the process.
