# Install

Python 3.10+ and a Rust toolchain (`rustup`) for the compiled core.

```bash
cd pyron
python -m pip install maturin
```

**With a virtualenv** (what maturin prefers):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
maturin develop --release
python -m pip install -e ".[standard,db]"
```

**Without a venv** — build a wheel, then install the *exact* filename. PowerShell does not expand `*`:

```powershell
maturin build --release
python -m pip install (Get-ChildItem target\wheels\pyron-*.whl).FullName
python -m pip install ".[standard,db]"
```

```bash
# bash
python -m pip install target/wheels/pyron-*.whl
```

Check the core:

```bash
pyron version
# pyron 0.11.0  core=rust  rust=True
```

Without Rust, the same Python API works slower:

```bash
# Windows
set PYRON_PURE_PYTHON=1
python -m pip install -e ".[standard,db]"
```

Optional extras: `standard` (Granian/Uvicorn, httpx), `db` (SQLModel, Alembic), `mongo` (pymongo), `redis` (redis), `dev` (pytest), `docs` (this website: MkDocs Material).

```powershell
python -m pip install mkdocs-material
mkdocs serve
```

http://127.0.0.1:8001 — search, tabs, light/dark. GitHub Pages: enable Pages on the repo; `.github/workflows/docs.yml` publishes on push to `main`.
