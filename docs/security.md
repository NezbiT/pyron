# Security

Security is on by default. Features you did not enable stay off; headers still go out.

## Production env

```
PYRON_ENV=production
PYRON_SECRET=<at least 32 random characters>
PYRON_ALLOWED_HOSTS=your.domain
PYRON_EXPOSE_DOCS=0
PYRON_SESSION_SECURE=1
```

Then:

```bash
pyron check --deploy
pyron serve
```

`pyron check` is always safe. `--deploy` treats production rules as required even on a dev machine. Exit code `1` if `DEBUG` is on in production or the secret is missing/short. It also reports whether `MONGO_URL` / `REDIS_URL` are set (missing Redis is OK: throttle stays in-process).

| Control | Behaviour |
|---|---|
| Passwords | PBKDF2-SHA256, unique salt |
| Unknown username | Still runs PBKDF2 (timing) |
| Login throttle | 8 failures → 15 minutes / IP |
| Production login errors | Generic; no “user missing” vs “bad password” |
| Admin panel CSRF | Hidden token + session |
| Session cookie | HttpOnly, SameSite=Lax; Secure when `PYRON_SESSION_SECURE=1` |
| Headers | `X-Frame-Options: DENY`, `nosniff`, referrer policy |
| Host allowlist | `PYRON_ALLOWED_HOSTS` in production |
| Docs | Off in production unless you set `PYRON_EXPOSE_DOCS=1` |

Do **not** set `PYRON_TRUST_PROXY=1` unless a reverse proxy you control sets `X-Forwarded-For`. Otherwise clients can spoof the throttle key.

`PYRON_SESSION_SECURE=1` on plain `http://127.0.0.1` will prevent the browser from storing the cookie. Use it behind HTTPS.
