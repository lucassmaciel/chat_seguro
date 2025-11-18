"""Gerenciamento simples de usuários e credenciais seguras."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Dict, Optional


class UserStore:
    """Persiste usuários em disco utilizando PBKDF2 + salt aleatório."""

    DEFAULT_ITERATIONS = 390_000

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text(json.dumps({}, indent=2), encoding="utf-8")

    def _load(self) -> Dict[str, dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: Dict[str, dict]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, self.DEFAULT_ITERATIONS
        )

    def create_user(self, email: str, password: str, client_id: str) -> None:
        email = email.lower().strip()
        client_id = client_id.strip()
        if not email or not password or not client_id:
            raise ValueError("Dados obrigatórios ausentes")

        data = self._load()

        if email in data:
            raise ValueError("E-mail já cadastrado")

        if any(u.get("client_id") == client_id for u in data.values()):
            raise ValueError("ID de cliente já em uso")

        salt = secrets.token_bytes(16)
        pwd_hash = self._hash_password(password, salt)

        data[email] = {
            "client_id": client_id,
            "salt": base64.b64encode(salt).decode(),
            "pwd_hash": base64.b64encode(pwd_hash).decode(),
            "iterations": self.DEFAULT_ITERATIONS,
        }
        self._save(data)

    def verify_user(self, email: str, password: str) -> Optional[dict]:
        email = email.lower().strip()
        data = self._load()
        user = data.get(email)
        if not user:
            return None

        salt = base64.b64decode(user["salt"].encode())
        expected_hash = base64.b64decode(user["pwd_hash"].encode())
        iterations = int(user.get("iterations", self.DEFAULT_ITERATIONS))

        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        if hmac.compare_digest(pwd_hash, expected_hash):
            return {"email": email, "client_id": user["client_id"]}
        return None

    def get_user(self, email: str) -> Optional[dict]:
        data = self._load()
        return data.get(email.lower().strip())


__all__ = ["UserStore"]

