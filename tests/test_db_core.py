import sqlite3

import server.db_core as db_core


def test_init_db_creates_schema_and_wal(tmp_path):
    db_path = tmp_path / "test.db"

    db_core.init_db(db_path)

    with db_core.get_conn(db_path) as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].lower()

    assert {"users", "public_keys", "groups", "group_members", "messages"}.issubset(
        names
    )
    assert journal_mode == "wal"


def test_get_conn_commits_changes(tmp_path):
    db_path = tmp_path / "commit.db"
    db_core.init_db(db_path)

    with db_core.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO public_keys (client_id, pubkey_b64) VALUES (?, ?)",
            ("alice", "pubkey"),
        )

    with sqlite3.connect(db_path) as check_conn:
        row = check_conn.execute(
            "SELECT client_id, pubkey_b64 FROM public_keys WHERE client_id = ?",
            ("alice",),
        ).fetchone()

    assert row == ("alice", "pubkey")
