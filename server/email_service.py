"""Serviço de e-mail com suporte a SMTP autenticado e fallback em desenvolvimento."""

from __future__ import annotations

import datetime as dt
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


@dataclass(slots=True)
class SMTPSettings:
    """Configuração de SMTP autenticado."""

    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    sender: str | None = None


class EmailServiceError(RuntimeError):
    """Erro genérico do serviço de e-mail."""


class EmailDeliveryError(EmailServiceError):
    """Erro lançado ao enviar a mensagem para o provedor."""


log = logging.getLogger(__name__)


class EmailService:
    """Envia códigos MFA via SMTP autenticado ou registra em arquivo em desenvolvimento."""

    def __init__(
        self,
        *,
        settings: SMTPSettings,
        env_mode: str = "production",
        log_path: str | Path = "mfa_emails.log",
        timeout: float = 10.0,
    ) -> None:
        self.log_path = Path(log_path)
        self.env_mode = env_mode.lower()
        self.settings = settings
        self.timeout = timeout
        self._ssl_context = ssl.create_default_context()
        self._has_smtp_config = self._settings_complete()

        if self.env_mode != "development" and not self._has_smtp_config:
            missing = self._missing_settings()
            joined = ", ".join(missing)
            message = (
                "Configuração de e-mail incompleta fora do ambiente de desenvolvimento: "
                f"{joined}"
            )
            raise EmailServiceError(message)

    def send_mfa_code(self, email: str, code: str) -> None:
        if self.env_mode == "development" and not self._has_smtp_config:
            self._log_code(email, code)
            return

        message = self._build_message(email, code)
        try:
            self._send_via_smtp(message)
        except (smtplib.SMTPException, OSError) as exc:  # pragma: no cover - rede externa
            raise EmailDeliveryError("Falha ao enviar e-mail via SMTP") from exc

    def _settings_complete(self) -> bool:
        return not self._missing_settings()

    def _missing_settings(self) -> list[str]:
        return [
            name
            for name, value in (
                ("EMAIL_HOST", self.settings.host),
                ("EMAIL_PORT", self.settings.port),
                ("EMAIL_USER", self.settings.username),
                ("EMAIL_PASSWORD", self.settings.password),
                ("EMAIL_FROM", self.settings.sender),
            )
            if value in (None, "")
        ]

    def _build_message(self, recipient: str, code: str) -> EmailMessage:
        subject = "Código MFA - Chat Seguro"
        body = (
            "Olá,\n\n"
            "Segue o seu código de autenticação de dois fatores: "
            f"{code}.\n"
            "Se você não solicitou este código, ignore este e-mail."
            "\n\nEquipe Chat Seguro"
        )
        message = EmailMessage()
        message["Subject"] = subject
        sender = self.settings.sender
        if sender is None:
            raise EmailServiceError("EMAIL_FROM não configurado")
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)
        return message

    def _send_via_smtp(self, message: EmailMessage) -> None:
        host = self.settings.host
        if host is None:
            raise EmailServiceError("EMAIL_HOST não configurado")
        port = self.settings.port
        if port is None:
            raise EmailServiceError("EMAIL_PORT não configurado")
        username = self.settings.username
        if username is None:
            raise EmailServiceError("EMAIL_USER não configurado")
        password = self.settings.password
        if password is None:
            raise EmailServiceError("EMAIL_PASSWORD não configurado")
        with smtplib.SMTP(
            host,
            port,
            timeout=self.timeout,
        ) as server:
            server.starttls(context=self._ssl_context)
            server.login(username, password)
            server.send_message(message)

    def _log_code(self, email: str, code: str) -> None:
        timestamp = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
        line = f"{timestamp} | MFA | {email} | code={code}\n"
        log.info("[DEV] MFA para %s: %s", email, code)
        with self.log_path.open("a", encoding="utf-8") as fp:
            fp.write(line)


__all__ = [
    "EmailDeliveryError",
    "EmailService",
    "EmailServiceError",
    "SMTPSettings",
]

