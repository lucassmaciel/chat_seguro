"""
Módulo de persistência para salvar e carregar conversas e grupos
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Any


def _get_db_path(client_id: str) -> Path:
    """Retorna o caminho do arquivo de banco para um cliente."""
    return Path(f"{client_id}_state.db")

def _init_db(db_path: Path) -> None:
    """Garante que o schema do SQLite exista."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS conversations (
                conv_id   TEXT PRIMARY KEY,
                conv_type TEXT NOT NULL,
                group_key BLOB
            );

            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id   TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                sender    TEXT NOT NULL,
                message   TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_conversations(client_id: str, conversations: Dict[str, Dict[str, Any]]):
    """
    Salva o estado das conversas em SQLite.

    Estrutura esperada em `conversations`:
    {
        "alice": {
            "type": "private" | "group",
            "key": b"...",            # somente para grupo
            "history": [(ts, sender, msg), ...]
        },
        ...
    }
    """
    try:
        db_path = _get_db_path(client_id)
        _init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()

            # Estratégia simples: apaga tudo e regrava do zero.
            # Para este projeto é mais do que suficiente.
            cur.execute("DELETE FROM messages;")
            cur.execute("DELETE FROM conversations;")

            for conv_id, conv_data in conversations.items():
                conv_type = conv_data.get("type", "private")
                group_key = conv_data.get("key")  # bytes ou None

                cur.execute(
                    """
                    INSERT INTO conversations (conv_id, conv_type, group_key)
                    VALUES (?, ?, ?)
                    """,
                    (conv_id, conv_type, group_key),
                )

                for ts, sender, msg in conv_data.get("history", []):
                    cur.execute(
                        """
                        INSERT INTO messages (conv_id, timestamp, sender, message)
                        VALUES (?, ?, ?, ?)
                        """,
                        (conv_id, ts, sender, msg),
                    )

            conn.commit()
        finally:
            conn.close()

    except Exception as e:
        print(f"Erro ao salvar estado (SQLite): {e}")


def load_conversations(client_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Carrega o estado das conversas de SQLite e reconstrói o dicionário:

    { conv_id: { "type": ..., "key": bytes|None, "history": [(ts, sender, msg), ...] } }
    """
    try:
        db_path = _get_db_path(client_id)
        if not db_path.exists():
            return {}

        _init_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()

            conversations: Dict[str, Dict[str, Any]] = {}

            # Carrega conversas (tipo + chave de grupo)
            cur.execute("SELECT conv_id, conv_type, group_key FROM conversations;")
            for row in cur.fetchall():
                conv_id = row["conv_id"]
                conversations[conv_id] = {
                    "type": row["conv_type"],
                    "key": row["group_key"],  # group_key já vem como bytes ou None
                    "history": [],
                }

            # Carrega histórico de mensagens
            cur.execute(
                """
                SELECT conv_id, timestamp, sender, message
                FROM messages
                ORDER BY id ASC
                """
            )
            for row in cur.fetchall():
                conv_id = row["conv_id"]
                conv = conversations.setdefault(
                    conv_id, {"type": "private", "key": None, "history": []}
                )
                conv["history"].append(
                    (row["timestamp"], row["sender"], row["message"])
                )

            return conversations

        finally:
            conn.close()

    except Exception as e:
        print(f"Erro ao carregar estado (SQLite): {e}")
        return {}