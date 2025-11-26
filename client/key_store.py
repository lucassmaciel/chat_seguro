from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from typing import Optional

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
    """Deriva uma chave de 32 bytes única por cliente com BLAKE2b."""

    secret = os.getenv(crypto_key)
    if not secret:
        raise RuntimeError(
            f"{crypto_key} não definido no ambiente. "
            "Defina um valor base64 de pelo menos 32 bytes para proteger as chaves privadas."
        )

    try:
        raw = base64.b64decode(secret)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"{crypto_key} deve estar em base64 seguro e ter entropia suficiente"
        ) from exc

    if len(raw) < SecretBox.KEY_SIZE:
        raise RuntimeError(f"{crypto_key} deve ter pelo menos 32 bytes de entropia")

    return hashlib.blake2b(
        raw,
        digest_size=SecretBox.KEY_SIZE,
        person=f"keystore:{client_id}".encode(),
    ).digest()


def load_private_key_bytes(client_id: str) -> Optional[tuple[bytes, Optional[bytes]]]:
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
    try:
        payload = json.loads(priv_bytes.decode())
        box_priv = base64.b64decode(payload["box_priv"])
        signing_priv = (
            base64.b64decode(payload["signing_priv"]) if payload.get("signing_priv") else None
        )
        return box_priv, signing_priv
    except Exception:
        return priv_bytes, None


def store_private_key_bytes(client_id: str, priv_bytes: bytes, signing_priv: bytes | None = None) -> None:
    """Criptografa e persiste os bytes da PrivateKey no SQLite."""

    _init_db()

    payload = {
        "box_priv": base64.b64encode(priv_bytes).decode(),
        "signing_priv": base64.b64encode(signing_priv).decode() if signing_priv else None,
    }
    key = _derive_key(client_id)
    box = SecretBox(key)
    cipher: bytes = box.encrypt(json.dumps(payload).encode())  # nonce + MAC + ciphertxt

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
