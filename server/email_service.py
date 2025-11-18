"""Serviço simples para registrar códigos de MFA enviados por e-mail."""

from __future__ import annotations

import datetime as dt
from pathlib import Path


class EmailService:
    """Finge envio de e-mail registrando códigos em arquivo de log."""

    def __init__(self, log_path: str | Path = "mfa_emails.log") -> None:
        self.log_path = Path(log_path)

    def send_mfa_code(self, email: str, code: str) -> None:
        timestamp = dt.datetime.utcnow().isoformat()
        line = f"{timestamp}Z | MFA | {email} | code={code}\n"
        with self.log_path.open("a", encoding="utf-8") as fp:
            fp.write(line)


__all__ = ["EmailService"]

