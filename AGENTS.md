# Pyron

A change is **not done** until documentation is updated. Docs are part of the same turn and the same commit — not a follow-up, not “we’ll write it later.”

## Required with every user-facing change

1. `CHANGELOG.md` — new version heading, or bullets under the current one. Dates are when the tree moved.
2. `docs/*.md` that a person would actually open (admin, API, CLI, enable, security, data, architecture, comparison, quickstart, install, index). If the feature has a screen or URL, that page must name it.
3. `README.md` when the feature is on the homepage path (`pyron init`, `/admin`, `/p/…`, Settings, extras).
4. Generated copy: `scaffold.py` READMEs, `cli.py` “Next” URLs, `examples/*/README.md` if the example gained a surface.

`docs/changelog.md` includes `CHANGELOG.md`. The docs site is MkDocs; keep headings stable so existing links still work.

If you only changed code, you are not finished.
