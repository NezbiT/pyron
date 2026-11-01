# Pyron

A change is **not done** until documentation is updated. Docs are part of the same turn and the same commit — not a follow-up, not “we’ll write it later.”

## Required with every user-facing change

1. `CHANGELOG.md` — new version heading, or bullets under the current one. Dates are when the tree moved.
2. `docs/*.md` that a person would actually open (admin, API, CLI, enable, security, data, architecture, comparison, quickstart, install, index). If the feature has a screen or URL, that page must name it.
3. `README.md` when the feature is on the homepage path (`pyron init`, `/admin`, `/p/…`, Settings, extras).
4. Generated copy: `scaffold.py` READMEs, `cli.py` “Next” URLs, `examples/*/README.md` if the example gained a surface.

`docs/changelog.md` includes `CHANGELOG.md`. The docs site is MkDocs; keep headings stable so existing links still work. In `CHANGELOG.md`, link other pages as MkDocs paths (`admin.md#settings`, `contributing.md`) — not `docs/admin.md`, or the site build warns that the target is missing.

If you only changed code, you are not finished.

## Cursor Cloud specific instructions

The base image ships Rust 1.83. `Cargo.lock` needs Rust 1.99.1 because `hashbrown` 0.17 uses edition 2024. The environment install runs `rustup default 1.99.1`.

Pyron lives in `/opt/pyron-venv`. `python`, `python3`, `pyron`, `pytest`, `ruff`, `mkdocs`, and `maturin` on `PATH` use that environment. `python` and `python3` are wrappers that exec the venv interpreter. A symlink to the venv `python` binary drops `site-packages`.

SQLModel is held at 0.0.44 and SQLAlchemy at 2.0 (`<2.1`). SQLModel 0.0.45 and later reject the naive datetimes this tree stores, and admin setup then returns 500.

Checks from the repo root: `pytest`, `cargo test --lib`, `mkdocs build --strict`. After Rust edits, run `maturin develop --release`, then `pytest`.

A scaffolded app uses SQLite and needs no extra services. `pyron init`, then `pyron dev` in that folder. The home form, `/api/items`, `/docs`, and `/admin` share the same rows. See [quickstart.md](docs/quickstart.md).
