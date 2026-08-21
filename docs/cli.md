# CLI

```
pyron init app                  # wizard: name, about, noun → 10 records
pyron init NAME --template api|ssr|desk|fullstack
pyron init app --title "…" --about "…" --noun kits
pyron startapp NAME
pyron enable admin          # also: app.enable("mongo"|"redis") in code
pyron check [--deploy]
pyron dev [--app app.main:app] [--host] [--port] [--app-dir]
pyron serve [--workers]
pyron createsuperuser
pyron changepassword USERNAME
pyron build
pyron db init | migrate | upgrade
pyron version
```

`pyron dev` puts the current directory on `PYTHONPATH` so Windows + reload can import `app`. `pyron serve` sets `PYRON_ENV=production`.

## startapp

```
pyron startapp catalog
```

Writes `catalog/models.py`, `catalog/routes.py`, and `catalog/admin.py`. Hook it once:

```python
app.include_app("catalog")
```

That mounts the app’s `APIRouter` and, if the admin panel is on, calls `register(admin)`. Call `include_app` **after** `admin=True` / `app.enable("admin")` so the tables show up on the panel.

## check --deploy

`pyron check` is safe anytime. `pyron check --deploy` applies production rules even if `PYRON_ENV` is still `dev`: secret length, `DEBUG`, exposed `/docs`, empty `PYRON_ALLOWED_HOSTS`, insecure session cookies. Exit code `1` on any `error` (missing/short secret, debug in production).
