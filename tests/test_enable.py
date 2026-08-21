from pathlib import Path

from pyron.enable import MARKER_BEGIN, enable_admin


def _tiny_api(root: Path) -> None:
    app = root / "app"
    app.mkdir()
    (app / "models.py").write_text(
        "from sqlmodel import Field, SQLModel\n"
        "class Item(SQLModel, table=True):\n"
        "    id: int | None = Field(default=None, primary_key=True)\n"
        "    title: str = ''\n",
        encoding="utf-8",
    )
    (app / "db.py").write_text("engine = None\n", encoding="utf-8")
    (app / "main.py").write_text(
        "from pyron import Pyron\n\n"
        "app = Pyron(title='API only')\n\n"
        "@app.get('/health')\n"
        "async def health():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )


def test_enable_admin_is_additive(tmp_path):
    _tiny_api(tmp_path)
    original = (tmp_path / "app" / "main.py").read_text(encoding="utf-8")
    actions = enable_admin(tmp_path)
    assert any("created app/admin.py" in a for a in actions)
    text = (tmp_path / "app" / "main.py").read_text(encoding="utf-8")
    assert "@app.get('/health')" in text
    assert "return {'ok': True}" in text
    assert MARKER_BEGIN in text
    assert original.split("@app.get")[1] in text.split("@app.get")[1] or "health" in text
    again = enable_admin(tmp_path)
    assert any("already" in a for a in again)
    assert (tmp_path / "app" / "main.py").read_text(encoding="utf-8").count(MARKER_BEGIN) == 1
