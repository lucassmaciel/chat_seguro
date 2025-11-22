from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path("chatseguro.db")


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        cur.execute("PRAGMA journal_mode=WAL;")

        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                client_id TEXT UNIQUE NOT NULL,
                salt BLOB NOT NULL,
                pwd_hash BLOB NOT NULL,
                iterations INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS public_keys (
                client_id TEXT PRIMARY KEY,
                pubkey_b64 TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn(db_path: str | Path = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()