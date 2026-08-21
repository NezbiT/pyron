# Harbor Bindings

Example Pyron application: a used bookstore with server-rendered pages, a JSON API, and generated OpenAPI docs.

```
cd examples/bookstore
python -m pip install -e ../..[standard,db]
# from the Pyron repo root, after `maturin develop`:
pyron dev --app app.main:app
```

Then open:

- http://127.0.0.1:8000 — SSR shopfront (what a crawler sees)
- http://127.0.0.1:8000/catalog — searchable catalog
- http://127.0.0.1:8000/docs — Swagger UI from the same routes
- http://127.0.0.1:8000/api/books — JSON
- http://127.0.0.1:8000/admin — Admin panel (first visit creates the root user; language + light/dark/system theme)
- http://127.0.0.1:8000/p/about — CMS page from **Pages** in the panel (Markdown; add more there)
- http://127.0.0.1:8000/admin/settings — site name, phone, hours (header/footer)

The database is SQLite (`bookstore.db`), created and seeded on first startup via SQLModel.
