from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("chatseguro.db")


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA foreign_keys=ON;")

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

            CREATE TABLE IF NOT EXISTS tls_credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cert_pem TEXT NOT NULL,
                key_pem TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_tls_credentials(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[str, str] | None:
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT cert_pem, key_pem FROM tls_credentials WHERE id = 1",
        )
        row = cur.fetchone()
        if row:
            return row["cert_pem"], row["key_pem"]
        return None


def store_tls_credentials(
    cert_pem: str, key_pem: str, db_path: str | Path = DEFAULT_DB_PATH
) -> None:
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tls_credentials (id, cert_pem, key_pem)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                cert_pem = excluded.cert_pem,
                key_pem = excluded.key_pem,
                created_at = CURRENT_TIMESTAMP
            """,
            (cert_pem, key_pem),
        )