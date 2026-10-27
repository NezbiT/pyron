# Inspector

`pyron inspect` talks to a running `pyron dev` or `pyron serve`. The parent process is the inspector. The HTTP server is a child. Reload, scale, and shutdown do not need a second login.

The control socket listens on `127.0.0.1` only. The address is written to `.pyron/inspect.json` in the app directory (gitignored). Point `--app-dir` at that directory when you are not already there.

```bash
pyron inspect
pyron inspect reload
pyron inspect scale 4
pyron inspect shutdown
pyron inspect call ping --json '{"name": "ada"}'
```

## Status

`pyron inspect` prints:

- package version
- supervisor pid (the `pyron dev` / `pyron serve` process)
- server pid (the HTTP child)
- configured worker count
- pids of workers that have connected
- uptime
- custom command names

If `.pyron/inspect.json` is missing, the CLI says to start the app with `pyron dev` or `pyron serve` and exits `1`.

## Reload, scale, shutdown

`pyron dev` is one worker with reload on. `pyron serve` is N workers with reload off. Both use the same parent.

`reload` and `scale N` stop the HTTP child and start it again. Scale is a restart with a new worker count, so the port is briefly down. `shutdown` stops the child and the inspector, and removes `.pyron/inspect.json`.

## Custom commands

```python
@app.inspector.command("ping")
def ping(name: str = "ada"):
    return {"name": name}
```

```bash
pyron inspect call ping --json '{"name": "bea"}'
```

The command runs inside a worker. Async commands run on the app’s event loop. The return value must be JSON, or Pyron sends `str(result)`. Extra JSON keys that the function does not accept are ignored. Register commands while the app is being built (module body or startup). They are not HTTP routes and they do not appear in OpenAPI.

## What it does not do

The inspector is not middleware and not a request log. It does not sit on the path that serves `GET /books`. Workers connect out to the parent; the parent does not inject a proxy in front of Granian.
