# Signals

Signals are small named hooks around one moment in the app. They sit beside lifespan and middleware. They do not replace either.

## Lifespan, middleware, and signals

| Mechanism | When it runs | Use it for |
|---|---|---|
| Lifespan | Process start and stop. `@app.on_event("startup")` / `"shutdown"`, or the `lifespan=` context manager | Pools, connections, one-time setup |
| Middleware | Every ASGI call, wrapping the app | Headers, CORS, logging that must see the raw send/receive stream |
| Signals | A named moment you choose, after a route has matched | “This handler is about to run”, “a book was created” |

A signal listener is a normal function. It is not an ASGI middleware and it is not a startup hook. Listeners are absent from `/docs` and `/openapi.json`.

If a listener raises, the request fails the same way a handler exception does. An empty signal does no work.

## Built-in handler signals

After the router finds a route, and again after the handler returns, Pyron dispatches both names:

- `http.handler.before` and `handler.before` — `request`, `route`
- `http.handler.after` and `handler.after` — `request`, `response`, `route`

```python
@app.signal("http.handler.after")
async def log_time(request, response):
    ...
```

A listener only receives the arguments it declares. `async def log_time(response)` does not have to accept `request`. A 404 never fires these signals, because no route matched.

## Custom signals

```python
@app.signal("book.created")
async def on_book_created(book):
    ...

@app.post("/books", status_code=201)
async def create_book(book: BookIn):
    saved = save(book)
    await app.dispatch("book.created", book=saved)
    return saved
```

`await app.dispatch("book.created", book=saved)` waits for each listener, including async ones, in registration order.
