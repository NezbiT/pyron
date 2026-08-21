"""Turn features on in an existing project without rewriting handlers.

`pyron enable admin` only:
- writes `app/admin.py` if missing
- appends a marked block to `app/main.py` if that block is not there
- never touches `@app.get` / `@app.post` bodies
"""

from __future__ import annotations

import re
from pathlib import Path

MARKER_BEGIN = "# --- pyron enable admin ---"
MARKER_END = "# --- end pyron enable admin ---"

ENABLE_BLOCK = '''
{begin}
# Added by `pyron enable admin`. Your API handlers above are unchanged.
from app.db import engine as _pyron_engine
from app.admin import register as _pyron_register_admin

app.enable("admin", engine=_pyron_engine)
_pyron_register_admin(app.admin)
{end}
'''


def enable_admin(root: Path) -> list[str]:
    """Mutate the project. Returns human-readable actions taken."""
    actions: list[str] = []
    app_dir = root / "app"
    if not app_dir.is_dir():
        raise FileNotFoundError("No app/ directory. Run this from a Pyron project root.")
    main = app_dir / "main.py"
    if not main.is_file():
        raise FileNotFoundError("No app/main.py.")

    admin_py = app_dir / "admin.py"
    if not admin_py.is_file():
        admin_py.write_text(_admin_module(app_dir), encoding="utf-8")
        actions.append("created app/admin.py")
    else:
        actions.append("left app/admin.py in place (already exists)")

    text = main.read_text(encoding="utf-8")
    if MARKER_BEGIN in text or "app.enable(\"admin\"" in text or "admin=True" in text:
        actions.append("main.py already has the admin panel enabled — no edit")
        return actions
    if "app = Pyron" not in text:
        raise RuntimeError("Could not find `app = Pyron(...)` in app/main.py. Enable it by hand.")

    block = ENABLE_BLOCK.format(begin=MARKER_BEGIN, end=MARKER_END)
    if not text.endswith("\n"):
        text += "\n"
    main.write_text(text + block, encoding="utf-8")
    actions.append("appended enable-admin block to app/main.py")
    return actions


def _admin_module(app_dir: Path) -> str:
    models = _model_names(app_dir / "models.py")
    if not models:
        models = ["Item"]
    imports = ", ".join(models)
    registers = "\n    ".join(
        f"admin.register({name}, {name}Admin)" for name in models
    )
    classes = "\n\n".join(
        f"class {name}Admin(ModelAdmin):\n    list_display = [\"id\", \"title\"]\n    search_fields = [\"title\"]"
        for name in models
    )
    return (
        '"""Admin panel registration. Safe to edit; `pyron enable admin` will not overwrite this file."""\n\n'
        f"from app.models import {imports}\n"
        "from pyron.admin import ModelAdmin\n\n"
        f"{classes}\n\n\n"
        "def register(admin) -> None:\n"
        "    if admin is None:\n"
        "        return\n"
        f"    {registers}\n"
    )


def _model_names(models_py: Path) -> list[str]:
    if not models_py.is_file():
        return []
    text = models_py.read_text(encoding="utf-8")
    return re.findall(r"^class (\w+)\(.*table\s*=\s*True", text, re.M)
