import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def todo_db(tmp_path, monkeypatch):
    """每个用例一个临时 SQLite 文件，避免污染仓库里的 todos.db。"""
    monkeypatch.setenv("TODO_DB", str(tmp_path / "todos.db"))
    from store import init_db

    init_db()
    return tmp_path / "todos.db"
