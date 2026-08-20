from unittest.mock import AsyncMock, MagicMock

from app.core.config import settings
from app.services import email_service


def _stub_brevo_client(send_mock):
    client = MagicMock()
    client.transactional_emails.send_transac_email = send_mock
    return client


async def test_send_skips_and_logs_warning_when_no_api_key(monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", None)

    with caplog.at_level("WARNING"):
        sent = await email_service._send("customer@example.com", "Subject", "<p>Hi</p>", kind="test")

    assert sent is False
    assert "email.skipped" in caplog.text


async def test_send_calls_brevo_and_logs_success(monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    send_mock = AsyncMock(return_value=MagicMock(message_id="abc"))
    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(send_mock))

    with caplog.at_level("INFO"):
        sent = await email_service._send("customer@example.com", "Subject", "<p>Hi</p>", kind="test")

    assert sent is True
    assert "email.sent" in caplog.text
    send_mock.assert_called_once()
    call_kwargs = send_mock.call_args.kwargs
    assert call_kwargs["to"][0].email == "customer@example.com"
    assert call_kwargs["subject"] == "Subject"
    assert call_kwargs["sender"].email == "hello@leafly.com"


async def test_send_failure_is_logged_and_swallowed_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    send_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(send_mock))

    with caplog.at_level("ERROR"):
        sent = await email_service._send("customer@example.com", "Subject", "<p>Hi</p>", kind="test")

    assert sent is False
    assert "email.failed" in caplog.text


async def test_send_birthday_wish_smoke(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    send_mock = AsyncMock(return_value=MagicMock(message_id="abc"))
    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(send_mock))

    assert await email_service.send_birthday_wish("customer@example.com", "Anshu") is True
