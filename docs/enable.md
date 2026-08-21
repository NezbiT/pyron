# Enable features later

Pyron is layered. You can start with an API and add the admin panel without rewriting handlers.

```
pyron init shop --template api
# … ship JSON for months …
cd shop
pyron enable admin
pyron createsuperuser
```

What `pyron enable admin` does:

1. Creates `app/admin.py` from your SQLModel tables (skipped if the file exists — your edits stay).
2. If `main.py` already has `admin=True` or `app.enable("admin"`, it **stops**.
3. Otherwise it **appends** a block wrapped in `# --- pyron enable admin ---`.

The health endpoint you wrote yesterday is still there, byte-for-byte.

In code:

```python
app.enable("admin", engine=engine)
```

`app.enable("unknown")` raises `ValueError`. Known: `admin`, `mongo`, `redis`.
