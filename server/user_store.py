"""Gerenciamento simples de usuários e credenciais seguras."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Dict, Optional

from .db_core import get_conn, init_db, DEFAULT_DB_PATH


class UserStore:
    """Persiste usuários em disco utilizando PBKDF2 + salt aleatório."""

    DEFAULT_ITERATIONS = 390_000

    def __init__(self, db_path: str):
        self.db_path = db_path

    # --------- internals ---------
    def _hash_password(self, password: str, salt: bytes, iterations: int | None = None) -> bytes:
        it = iterations or self.DEFAULT_ITERATIONS
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            it,
        )

    # --------- API pública ---------
    def create_user(self, email: str, password: str, client_id: str) -> None:
        email = email.lower().strip()
        client_id = client_id.strip()
        if not email or not password or not client_id:
            raise ValueError("Dados obrigatórios ausentes")

        with get_conn(self.db_path) as conn:
            cur = conn.cursor()

            # e-mail único
            cur.execute("SELECT 1 FROM users WHERE email = ?", (email,))
            if cur.fetchone():
                raise ValueError("E-mail já cadastrado")

            # client_id único
            cur.execute("SELECT 1 FROM users WHERE client_id = ?", (client_id,))
            if cur.fetchone():
                raise ValueError("ID de cliente já em uso")

            salt = secrets.token_bytes(16)
            pwd_hash = self._hash_password(password, salt, self.DEFAULT_ITERATIONS)

            cur.execute(
                """
                INSERT INTO users (email, client_id, salt, pwd_hash, iterations)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    email,
                    client_id,
                    salt,
                    pwd_hash,
                    self.DEFAULT_ITERATIONS,
                ),
            )

    def verify_user(self, email: str, password: str) -> Optional[dict]:
        email = email.lower().strip()

        with get_conn(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT email, client_id, salt, pwd_hash, iterations
                FROM users
                WHERE email = ?
                """,
                (email,),
            )
            row = cur.fetchone()

        if not row:
            return None

        salt = row["salt"]
        expected_hash = row["pwd_hash"]
        iterations = int(row["iterations"])

        pwd_hash = self._hash_password(password, salt, iterations)

        if hmac.compare_digest(pwd_hash, expected_hash):
            return {"email": row["email"], "client_id": row["client_id"]}
        return None

    def get_user(self, email: str) -> Optional[dict]:
        email = email.lower().strip()
        with get_conn(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT email, client_id, salt, pwd_hash, iterations FROM users WHERE email = ?",
                (email,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return {
            "email": row["email"],
            "client_id": row["client_id"],
            "iterations": row["iterations"],
        }


__all__ = ["UserStore"]

