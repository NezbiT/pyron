# Contributing

Documentation is part of the feature. Do not merge code that a user can see without updating the pages they would read.

Same commit, same turn:

| Surface | File |
|---|---|
| What changed | `CHANGELOG.md` (this site’s [Changelog](changelog.md) includes it) |
| How to use it | the `docs/*.md` page for that area |
| First-run path | `README.md`, [Quickstart](quickstart.md), [Install](install.md) if URLs changed |
| Generated apps | `python/pyron/scaffold.py`, `cli.py` “Next” URLs, `examples/*/README.md` |

Headings in these docs are links. Prefer adding a section over renaming an existing one.

`CHANGELOG.md` is included into this site. Link other pages from it as `admin.md#settings` or `contributing.md`, never `docs/admin.md` (that path is already under `docs/` on the site).

The MkDocs site is `mkdocs.yml`. After a push to `main`, GitHub Pages rebuilds https://nezbit.github.io/pyron/.
