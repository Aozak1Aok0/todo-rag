"""store.py 的纯数据层测试：不需要 API key、不需要模型。"""

import pytest

import store


def test_init_db_is_idempotent(todo_db):
    store.init_db()
    store.init_db()
    rows = store.list_todos()
    assert len(rows) == 3
    assert [r["name"] for r in rows] == ["学 Express", "接前端", "学 Python + FastAPI"]
    assert rows[0]["completed"] is True


def test_add_and_get(todo_db):
    created = store.add_todo("  写评测  ")
    assert created["name"] == "写评测"
    assert created["completed"] is False
    assert store.get_todo(created["id"])["name"] == "写评测"


def test_add_empty_name_rejected(todo_db):
    with pytest.raises(ValueError):
        store.add_todo("   ")


def test_set_completed(todo_db):
    todo = store.add_todo("跑 pytest")
    assert store.set_completed(todo["id"], True) is True
    assert store.get_todo(todo["id"])["completed"] is True
    assert store.set_completed(todo["id"], False) is True
    assert store.get_todo(todo["id"])["completed"] is False


def test_remove(todo_db):
    todo = store.add_todo("临时")
    assert store.remove_todo(todo["id"]) is True
    assert store.get_todo(todo["id"]) is None
    assert store.remove_todo(todo["id"]) is False


def test_db_path_follows_env(todo_db):
    assert store.db_path() == todo_db
