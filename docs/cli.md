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
pyron inspect
pyron inspect reload | scale N | shutdown | call NAME --json '{}'
pyron createsuperuser
pyron changepassword USERNAME
pyron build
pyron db init | migrate | upgrade
pyron version
```

`pyron dev` puts the current directory on `PYTHONPATH` so Windows + reload can import `app`. It prints `/`, `/docs`, `/admin`, `/p/about`, `/admin/settings`, and `pyron inspect`. `pyron serve` sets `PYRON_ENV=production`.

`pyron dev` (one worker, reload on) and `pyron serve` (N workers, reload off) share one parent. That parent is the inspector. The HTTP server is a child process. See [Inspector](inspector.md).

## startapp

```
pyron startapp catalog
```

Writes `catalog/models.py`, `catalog/routes.py`, and `catalog/admin.py`. Hook it once:

```python
app.include_app("catalog")
```

That mounts the app’s `APIRouter` and, if the admin panel is on, calls `register(admin)`. Call `include_app` **after** `admin=True` / `app.enable("admin")` so the tables show up on the panel.

## inspect

```bash
pyron inspect
pyron inspect reload
pyron inspect scale 4
pyron inspect shutdown
pyron inspect call ping --json '{"name": "ada"}'
```

Reads `.pyron/inspect.json` from the current directory, or from `--app-dir`. Prints version, supervisor pid, server pid, worker count, connected worker pids, uptime, and custom command names. `reload` and `scale` restart the HTTP child (`scale` is not a live reuse of the listen socket). `shutdown` stops the child and the parent. Details: [Inspector](inspector.md).

## check --deploy

`pyron check` is safe anytime. `pyron check --deploy` applies production rules even if `PYRON_ENV` is still `dev`: secret length, `DEBUG`, exposed `/docs`, empty `PYRON_ALLOWED_HOSTS`, insecure session cookies. Exit code `1` on any `error` (missing/short secret, debug in production).
