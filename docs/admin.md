# Admin panel

The admin panel is Pyron’s Django-style operator UI. It is **off** until you enable it. Your API handlers stay as they are.

## Turn it on

At construction:

```python
from pyron import ModelAdmin, Pyron

app = Pyron(title="Harbor", admin=True, admin_engine=engine)

class BookAdmin(ModelAdmin):
    list_display = ["id", "title", "author", "price"]
    search_fields = ["title", "author"]
    list_filter = ["in_stock"]

app.admin.register(Book, BookAdmin)
```

Later, on an existing app:

```python
app.enable("admin", engine=engine)
```

or from the project root:

```bash
pyron enable admin
pyron createsuperuser
```

That command writes `app/admin.py` if missing and **appends** a marked block to `app/main.py`. It does not touch `@app.get` / `@app.post` bodies.

Then open http://127.0.0.1:8000/admin

## Pages (CMS)

When the panel is on, **Pages** is already there. You do not register a model for About or Contact. Hours and the shop name live in **Settings**.

1. Open `/admin` → **Pages** → **Add Page**.
2. Title, slug (`about` → public URL `/p/about`), Markdown body (preview on the right).
3. Jinja2 generates the public view from `page.html` (your `templates/base.html` if the app has templates).

The body is Markdown (`**bold**`, lists, `[text](https://…)`). Legacy HTML (a body that starts with a tag) still renders. `{{ 7*7 }}` is shown as text — it is not a Jinja template.

## Settings

`/admin/settings` is a single form: site name, tagline, phone, email, hours, address, website. The public header uses `site.name` and `site.tagline`. The footer uses phone (`tel:`), email, hours, and address when they are set.

```html
<a class="mark" href="/">{{ site.name }}</a>
{% if site.phone %}<a href="{{ site.phone_href }}">{{ site.phone }}</a>{% endif %}
```

The desk home is **Site** (Pages + Settings) then **Data** (your registered tables).

First run seeds **About** and **Contact**. Published rows with **in nav** appear in the public header as `site_pages`. Unpublished pages 404 for visitors; a signed-in operator can still open `/p/{slug}` to preview.

```html
<nav>
  {% for p in site_pages %}
    <a href="/p/{{ p.slug }}">{{ p.title }}</a>
  {% endfor %}
</nav>
```

Override the view by adding `templates/page.html` (and `pages.html` for `/p`). `Pyron(admin=True, pages=False)` skips the built-in table and the `/p/…` routes.

| Screen | Who | What |
|---|---|---|
| First run | nobody | Create the root account |
| Sign in | operators | Session, 7 days |
| Admin panel | staff + root | Counts and shortcuts |
| Pages | staff + root | CMS views; Markdown + preview; Jinja2 renders `/p/{slug}` |
| Settings | staff + root | Site name, phone, hours; public header/footer |
| Tables | staff + root | Search, `list_filter`, paginate, add, edit, delete (named confirm) |
| Bulk | staff with delete | Checkbox rows → confirm page → `Log` entry per row |
| Change form | staff + root | Inlines (`TabularInline`) and a short history |
| Routes | staff + root | Live map of the ASGI app |
| Users | root only | Create staff / other roots |

```python
from pyron import ModelAdmin, TabularInline

class ChapterInline(TabularInline):
    model = Chapter
    fk_name = "book_id"   # optional if the FK is obvious
    extra = 1

class BookAdmin(ModelAdmin):
    list_display = ["id", "title", "in_stock"]
    list_filter = ["in_stock"]
    inlines = [ChapterInline]
```

Every add / change / delete writes a row in `pyron_log`. The last twenty show under **History** on the change form.

SQLModel tables and Mongo `Document` classes can sit on the same Desk. See [Data](data.md). Cards show `sql` or `mongo`. Inlines are SQL-only.

## Language and appearance

The admin panel ships with **four languages** and **light / dark / system** themes. Defaults:

- **Language:** `pyron_lang` cookie, else the browser `Accept-Language` header, else English.
- **Theme:** `pyron_theme` cookie, else **system** (`prefers-color-scheme`). No cookie means the OS setting wins.

Languages: English, Español, Português, Français.

Controls sit on the login/setup screens and in the rail after sign-in as **toggle groups**. Appearance applies instantly (no reload). Language stores a cookie and reloads so every label updates. Without JavaScript the same buttons still submit to `/admin/prefs`. Cookies last one year, path `/admin`. Choosing **System** follows the OS, including live changes.

`<html lang="…">` updates with the locale. `color-scheme: light dark` is set so native form controls match.

Typeface: **JetBrains Mono** (IntelliJ), self-hosted.

Light theme is IntelliJ New UI: paper `#f7f8fa`, rail white, ink `#1a1a1a`, muted `#6c707e`. No brown. Ember `#c2410c` is the only warm accent. Dark is Darcula-like `#1e1e1e` / `#2b2b2b`.

## Passwords

```bash
pyron changepassword USERNAME
```

Looks in `pyron.db` and `bookstore.db` in the current directory if you omit `--database`.
