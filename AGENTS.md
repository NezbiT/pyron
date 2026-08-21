# Pyron

Every user-facing change updates **documentation and the changelog in the same turn**. Do not leave that as a follow-up.

1. `CHANGELOG.md` — new version heading, or add bullets under the current one. Dates are when the tree moved.
2. `docs/*.md` that the change touches (admin, API, CLI, enable, security, data, architecture, comparison, quickstart, install, index).
3. `README.md` when the feature is listed on the homepage path (`pyron init`, `/admin`, `/p/…`, extras).
4. Generated copy: `scaffold.py` READMEs, `cli.py` “Next” URLs, `examples/*/README.md` if the example gained a surface.

`docs/changelog.md` includes `CHANGELOG.md`. The docs site is MkDocs; keep headings stable so existing links still work.
