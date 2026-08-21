# Data: SQL, Mongo, Redis

Pyron does not own your database. SQL stays the default. Mongo and Redis are **optional extras**.

```
pip install pyron[db]       # SQLModel + Alembic
pip install pyron[mongo]    # pymongo
pip install pyron[redis]    # redis
```

| Role | Backend | Env | Admin panel |
|---|---|---|---|
| Tables, operators, logs | SQLModel (SQLite / Postgres / MySQL) | `DATABASE_URL` | Yes |
| Documents | MongoDB (Atlas, local, etc.) | `MONGO_URL`, `MONGO_DB` | Yes (`Document`) |
| Cache, login throttle | Redis, or process memory | `REDIS_URL` | No |

## SQL (unchanged)

```python
from pyron.db import create_engine

engine = create_engine()  # DATABASE_URL or sqlite:///./pyron.db
```

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/shop
```

Operators (`pyron_user`) stay on SQL in 0.6.

## Mongo documents

```python
from pyron import Document, ModelAdmin, Pyron
from pyron.db import create_engine, mongo_client

class Page(Document):
    collection = "pages"
    title: str
    body: str = ""

engine = create_engine()
mongo = mongo_client()  # MONGO_URL

app = Pyron(admin=True, admin_engine=engine, admin_mongo=mongo)
app.admin.register(Page)
```

```
MONGO_URL=mongodb+srv://user:pass@cluster.mongodb.net
MONGO_DB=pyron
```

Same Desk screens as SQL tables. The card shows `mongo`. Inlines stay SQL-only.

You can still use the pymongo client in handlers:

```python
@app.get("/pages/{page_id}")
async def get_page(page_id: str):
    doc = mongo["pyron"].pages.find_one({"_id": page_id})
    ...
```

Turn it on later: `app.enable("mongo")` after `MONGO_URL` is set.

## Redis cache

```python
from pyron import cache

cache.set("quote", "ok", ttl=60)
cache.get("quote")
```

No `REDIS_URL` → in-process memory (fine for one worker and tests). With Redis, login throttle is shared across Granian workers.

```
REDIS_URL=rediss://default:pass@host:6379
```

Redis is not a Desk table.

## Mixed app

Books in Postgres, pages in Atlas, cache in Redis Cloud: three URLs, one Pyron process. Register SQLModel tables and `Document` classes on the same admin.
