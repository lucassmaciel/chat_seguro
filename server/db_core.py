from __future__ import annotations

import sqlite3
from collections.abc import Iterator
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
                signing_pubkey_b64 TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tls_credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cert_pem TEXT NOT NULL,
                key_pem TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                admin TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, client_id),
                FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                blob_b64 TEXT NOT NULL,
                auth_tag TEXT,
                meta_json TEXT,
                group_id TEXT,
                msg_type TEXT NOT NULL DEFAULT 'private',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id);
            CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
            """
            ,
        )
        # Migrações leves: adiciona colunas se estiverem ausentes
        existing_public_cols = {row[1] for row in cur.execute("PRAGMA table_info(public_keys)")}
        if "signing_pubkey_b64" not in existing_public_cols:
            cur.execute("ALTER TABLE public_keys ADD COLUMN signing_pubkey_b64 TEXT")

        existing_message_cols = {row[1] for row in cur.execute("PRAGMA table_info(messages)")}
        if "auth_tag" not in existing_message_cols:
            cur.execute("ALTER TABLE messages ADD COLUMN auth_tag TEXT")

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
    cert_pem: str, key_pem: str, db_path: str | Path = DEFAULT_DB_PATH,
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
