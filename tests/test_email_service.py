from email.message import EmailMessage

import pytest

from server.email_service import EmailService, EmailServiceError, SMTPSettings


def test_dev_mode_logs_code(tmp_path, caplog):
    log_path = tmp_path / "mfa.log"
    caplog.set_level("INFO")
    service = EmailService(
        settings=SMTPSettings(), env_mode="development", log_path=log_path
    )

    service.send_mfa_code("user@example.com", "123456")

    content = log_path.read_text(encoding="utf-8")
    assert "user@example.com" in content
    assert "123456" in content
    assert "MFA" in caplog.text


def test_missing_configuration_raises_in_production():
    with pytest.raises(EmailServiceError):
        EmailService(settings=SMTPSettings(), env_mode="production")


def test_build_message_requires_sender():
    service = EmailService(
        settings=SMTPSettings(), env_mode="development", log_path="/tmp/ignored"
    )
    with pytest.raises(EmailServiceError):
        service._build_message("dest@example.com", "000111")


def test_build_message_populates_fields(tmp_path):
    settings = SMTPSettings(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        sender="no-reply@example.com",
    )
    service = EmailService(settings=settings, env_mode="development", log_path=tmp_path)

    message = service._build_message("dest@example.com", "000111")

    assert isinstance(message, EmailMessage)
    assert message["From"] == "no-reply@example.com"
    assert message["To"] == "dest@example.com"
    assert "Código MFA" in message["Subject"]
