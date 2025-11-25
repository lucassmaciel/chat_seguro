from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Optional
import base64
from dotenv import load_dotenv

from nacl.secret import SecretBox

from db_core import get_conn, init_db, DEFAULT_DB_PATH

load_dotenv()

# Caminho do DB local
DB_PATH = DEFAULT_DB_PATH

# Criptografia de chaves privadas.
crypto_key = "LOCAL_KEY_SECRET"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_private_keys (
               client_id   TEXT PRIMARY KEY,
               cipher      BLOB NOT NULL,
               created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
               updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _derive_key(client_id: str) -> bytes:
    """
    Deriva uma chave de 32 bytes a partir de:
      - segredo mestre (LOCAL_KEY_SECRET)
      - client_id
    Assim, cada cliente tem uma chave diferente mesmo com o mesmo segredo mestre.
    """
    secret = os.getenv(crypto_key)
    if not secret:
        raise RuntimeError(
            f"{crypto_key} não definido no ambiente. "
            "Defina um valor forte para proteger as chaves privadas."
        )

    try:

        raw = base64.b64decode(secret)
        if len(raw) == 0:
            raise ValueError
    except Exception:
        raw = secret.encode("utf-8")

    # SHA-256(secret || ":" || client_id) -> 32 bytes
    h = hashlib.sha256()
    h.update(raw)
    h.update(b":")
    h.update(client_id.encode("utf-8"))
    return h.digest()  # 32 bytes


def load_private_key_bytes(client_id: str) -> Optional[bytes]:
    """
    Retorna os bytes da PrivateKey do client_id (já decriptados),
    ou None se ainda não existir.
    """
    _init_db()

    with _get_conn() as conn:
        cur = conn.execute(
            "SELECT cipher FROM client_private_keys WHERE client_id = ?",
            (client_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    cipher: bytes = row["cipher"]
    key = _derive_key(client_id)
    box = SecretBox(key)
    priv_bytes = box.decrypt(cipher)
    return priv_bytes


def store_private_key_bytes(client_id: str, priv_bytes: bytes) -> None:
    """
    Criptografa e persiste os bytes da PrivateKey no SQLite.
    """
    _init_db()

    key = _derive_key(client_id)
    box = SecretBox(key)
    cipher: bytes = box.encrypt(priv_bytes)  # nonce + MAC + ciphertxt

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO client_private_keys (client_id, cipher)
            VALUES (?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                cipher = excluded.cipher,
                updated_at = CURRENT_TIMESTAMP
            """,
            (client_id, cipher),
        )
        conn.commit()
