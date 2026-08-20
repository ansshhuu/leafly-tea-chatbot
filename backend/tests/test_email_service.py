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
    assert call_kwargs["sender"].email == "anshupanwar20005@gmail.com"


async def test_send_failure_is_logged_and_swallowed_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    send_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(send_mock))

    with caplog.at_level("ERROR"):
        sent = await email_service._send("customer@example.com", "Subject", "<p>Hi</p>", kind="test")

    assert sent is False
    assert "email.failed" in caplog.text


async def test_send_order_confirmation_builds_expected_subject_and_html(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    sent = await email_service.send_order_confirmation(
        "customer@example.com",
        "Anshu",
        42,
        [{"name": "Samosa", "quantity": 2, "line_total": 120.0}],
        126.0,
        "pickup",
        None,
    )

    assert sent is True
    assert "42" in captured["subject"]
    assert "Samosa" in captured["html_content"]
    assert "126.00" in captured["html_content"]
    assert "Pickup at the café" in captured["html_content"]


async def test_send_order_confirmation_includes_full_address_with_flat_number(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    # The caller (ai_service._full_delivery_address) already appends the flat
    # number into the address string before calling this - no separate param.
    sent = await email_service.send_order_confirmation(
        "customer@example.com",
        "Anshu",
        42,
        [{"name": "Samosa", "quantity": 2, "line_total": 120.0}],
        126.0,
        "delivery",
        "A-302, Sunrise Apartments, 14th Road, Bandra",
    )

    assert sent is True
    assert "A-302, Sunrise Apartments, 14th Road, Bandra" in captured["html_content"]


async def test_send_reservation_confirmation_includes_booking_details(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    sent = await email_service.send_reservation_confirmation(
        "customer@example.com", "Anshu", 7, "Aug 03, 2026", "07:00 PM", 4, "window seat"
    )

    assert sent is True
    assert "Aug 03, 2026" in captured["html_content"]
    assert "07:00 PM" in captured["html_content"]
    assert "window seat" in captured["html_content"]


async def test_send_internal_order_notification_goes_to_fixed_recipient(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    sent = await email_service.send_internal_order_notification(
        26,
        "Aug 03, 2026 04:00 PM",
        "Anshu",
        "9876543210",
        "anshu@example.com",
        [{"name": "Samosa", "quantity": 2, "line_total": 120.0}],
        subtotal=120.0,
        discount=10.0,
        coupon_code="SAVE10",
        tax=5.5,
        total=115.5,
        fulfillment="delivery",
        delivery_address="14th Road, Bandra",
    )

    assert sent is True
    assert captured["to"][0].email == email_service.CAFE_INTERNAL_EMAIL
    assert captured["subject"] == "New Order #26 - Anshu - Rs.115.50"
    assert "Samosa" in captured["html_content"]
    assert "9876543210" in captured["html_content"]
    assert "anshu@example.com" in captured["html_content"]
    assert "SAVE10" in captured["html_content"]
    assert "14th Road, Bandra" in captured["html_content"]


async def test_send_internal_order_notification_flags_unverified_address(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    sent = await email_service.send_internal_order_notification(
        27,
        "Aug 03, 2026 04:00 PM",
        "Anshu",
        "9876543210",
        "anshu@example.com",
        [{"name": "Samosa", "quantity": 2, "line_total": 120.0}],
        subtotal=120.0,
        discount=0,
        coupon_code=None,
        tax=5.5,
        total=125.5,
        fulfillment="delivery",
        delivery_address="near the old bus stand",
        delivery_flat_number="Flat 4B, Blue Gate Apartments",
        delivery_unverified=True,
    )

    assert sent is True
    assert "Flat 4B, Blue Gate Apartments" in captured["html_content"]
    assert "UNVERIFIED" in captured["html_content"]


async def test_send_internal_reservation_notification_goes_to_fixed_recipient(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    captured = {}

    async def _fake_send(**kwargs):
        captured.update(kwargs)
        return MagicMock(message_id="abc")

    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(_fake_send))

    sent = await email_service.send_internal_reservation_notification(
        7, "Aug 03, 2026", "04:00 PM", 4, "Anshu", "9876543210", "anshu@example.com", "window seat"
    )

    assert sent is True
    assert captured["to"][0].email == email_service.CAFE_INTERNAL_EMAIL
    assert captured["subject"] == "New Reservation - Anshu - Aug 03, 2026, 04:00 PM"
    assert "9876543210" in captured["html_content"]
    assert "window seat" in captured["html_content"]


async def test_send_birthday_wish_and_cart_abandonment_smoke(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "fake-key-for-tests")
    send_mock = AsyncMock(return_value=MagicMock(message_id="abc"))
    monkeypatch.setattr(email_service, "AsyncBrevo", lambda api_key: _stub_brevo_client(send_mock))

    assert await email_service.send_birthday_wish("customer@example.com", "Anshu") is True
    assert (
        await email_service.send_cart_abandonment(
            "customer@example.com", [{"name": "Chai", "quantity": 1, "line_total": 80.0}], 84.0
        )
        is True
    )
