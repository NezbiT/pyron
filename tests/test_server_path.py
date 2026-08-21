import os
import sys

from pyron.server import ensure_import_path


def test_ensure_import_path_puts_cwd_on_pythonpath(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "")
    # Simulate a console-script launch where cwd is not on sys.path.
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))])

    root = ensure_import_path()
    assert root == str(tmp_path)
    assert str(tmp_path) in sys.path
    assert str(tmp_path) in os.environ["PYTHONPATH"].split(os.pathsep)
