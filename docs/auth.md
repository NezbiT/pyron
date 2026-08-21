# Auth and permissions

The same signed-in user is visible to the **API** and the **admin panel**. Routes without a decorator stay public.

## Who you are

After `app.enable("admin")` (or `admin=True`), a session cookie (`pyron_desk`, path `/`) is set at login. Middleware puts that operator on `request.state.user` and a context var, so handlers do not even need a `request` argument.

```python
from pyron import current_user, login_required, permission_required

@app.get("/me")
@login_required
async def me():
    user = current_user()
    return {"username": user.username, "root": user.is_root}

@app.delete("/books/{book_id}")
@permission_required("book.delete")
async def delete_book(book_id: int):
    ...
```

- **Root** (`is_root=True`) passes every permission check.
- **Staff** (group `staff`, created automatically) get `view`, `add`, and `change` on each registered table — **not** `delete`.
- Codename: `{slug}.{action}` e.g. `book.delete`, `widget.view`. Built-in CMS pages use `pages.view` / `pages.add` / `pages.change`.

## Responses (say what happened and what to do)

Not signed in, JSON client:

```json
{
  "detail": {
    "message": "You are not signed in.",
    "next": "Sign in, then try again.",
    "login": "/admin/login"
  }
}
```

Status `401`. Browsers asking for HTML are redirected to `/admin/login`.

Missing permission, JSON:

```json
{
  "detail": {
    "message": "You need the permission “book.delete” to do this.",
    "next": "Ask root to grant that permission, or sign in as someone who has it.",
    "permission": "book.delete"
  }
}
```

Status `403`. The admin panel shows the same copy (translated) and a “Back to the admin panel” button — not a raw code.

## Admin panel

Nav and cards only list tables you can `view`. Add / save / delete buttons follow `add` / `change` / `delete`. Operators are still root-only (`permission` `root`).

Create a staff account in **Users → Create operator** (leave Root unchecked). They join the `staff` group.

## Example

Harbor Bindings: `DELETE /api/books/{id}` requires `book.delete`. A clerk can edit a title in the admin panel and still cannot delete the row.
