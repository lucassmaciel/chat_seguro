import pytest

from server import db_core
from server.user_store import UserStore


def create_store(tmp_path):
    db_path = tmp_path / "users.db"
    db_core.init_db(db_path)
    return UserStore(str(db_path))


def test_create_and_verify_user(tmp_path):
    store = create_store(tmp_path)

    store.create_user("alice@example.com", "super-secret", "alice")

    stored = store.get_user("alice@example.com")
    assert stored == {
        "email": "alice@example.com",
        "client_id": "alice",
        "iterations": store.DEFAULT_ITERATIONS,
    }

    assert store.verify_user("alice@example.com", "super-secret") == {
        "email": "alice@example.com",
        "client_id": "alice",
    }
    assert store.verify_user("alice@example.com", "wrong") is None


def test_unique_constraints(tmp_path):
    store = create_store(tmp_path)

    store.create_user("alice@example.com", "pwd", "alice")

    with pytest.raises(ValueError):
        store.create_user("alice@example.com", "pwd2", "alice2")

    with pytest.raises(ValueError):
        store.create_user("bob@example.com", "pwd2", "alice")


def test_missing_fields_raise(tmp_path):
    store = create_store(tmp_path)

    with pytest.raises(ValueError):
        store.create_user("", "pwd", "cid")
