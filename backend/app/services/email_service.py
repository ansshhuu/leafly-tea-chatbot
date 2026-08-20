import logging

from brevo import AsyncBrevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem

from app.core.config import (
    CAFE_ADDRESS,
    CAFE_INTERNAL_EMAIL,
    CAFE_PHONE,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME,
    get_location,
    settings,
)
from app.core.timing import timed

logger = logging.getLogger(__name__)


# Simple line-art echo of the site's arched logo mark, next to "Rasa Café"
# in the header - instead of the generic ☕ emoji this used to use. Built
# from plain table cells + CSS borders, NOT an <svg> or <img>: most email
# clients (Gmail among them) strip <svg> entirely and/or block images by
# default, which would silently leave the header blank - borders/
# border-radius on a table cell render reliably everywhere HTML email does.
_LOGO_ICON_HTML = (
    '<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
    '<tr><td style="width:20px;height:20px;border:2px solid #fbf3e7;border-bottom:none;'
    'border-radius:11px 11px 0 0;line-height:0;font-size:0;">&nbsp;</td></tr>'
    "</table>"
)


def _wrap(title: str, body_html: str, location_name: str | None = None) -> str:
    # Footer shows the branch actually fulfilling this booking/order, falling
    # back to Bandra West (CAFE_ADDRESS/CAFE_PHONE) when no location was
    # recorded (e.g. older flows, or an email type with no branch context).
    branch = get_location(location_name) if location_name else {"address": CAFE_ADDRESS, "phone": CAFE_PHONE}
    # Playfair Display echoes the site's actual "Rasa Café" heading font -
    # loaded where the email client allows external @font-face/@import
    # (most modern webmail/desktop clients do), falling back to Georgia/Times
    # New Roman serif everywhere else, same warm serif feel either way.
    heading_font = "'Playfair Display', Georgia, 'Times New Roman', serif"
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap');
    </style>
  </head>
  <body style="margin:0;padding:0;background:#fbf3e7;font-family:Georgia,'Times New Roman',serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fbf3e7;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border:1px solid #e8d5b7;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="background:#c1440e;padding:22px 28px;">
                <table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                  <tr>
                    <td style="vertical-align:middle;padding-right:9px;line-height:0;">{_LOGO_ICON_HTML}</td>
                    <td style="vertical-align:middle;">
                      <span style="font-family:{heading_font};font-size:23px;font-weight:700;color:#fbf3e7;letter-spacing:0.3px;">Rasa Café</span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;color:#3a2a1d;font-size:15px;line-height:1.55;">
                <h1 style="margin:0 0 14px;font-size:20px;color:#4a3222;">{title}</h1>
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="background:#f3ece1;padding:16px 28px;color:#6f4e37;font-size:12px;line-height:1.5;">
                Rasa Café · {branch["address"]}<br />
                {branch["phone"]}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


async def _send(to: str, subject: str, html: str, kind: str) -> bool:
    if not settings.brevo_api_key:
        logger.warning("email.skipped kind=%s to=%s reason=BREVO_API_KEY not configured", kind, to)
        return False

    client = AsyncBrevo(api_key=settings.brevo_api_key)

    try:
        async with timed(f"brevo.send kind={kind}"):
            await client.transactional_emails.send_transac_email(
                sender=SendTransacEmailRequestSender(email=EMAIL_FROM_ADDRESS, name=EMAIL_FROM_NAME),
                to=[SendTransacEmailRequestToItem(email=to)],
                subject=subject,
                html_content=html,
            )
    except Exception:
        logger.exception("email.failed kind=%s to=%s subject=%r", kind, to, subject)
        return False

    logger.info("email.sent kind=%s to=%s subject=%r", kind, to, subject)
    return True


def _detail_row(label: str, value: str) -> str:
    return f'<tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">{label}</td><td><strong>{value}</strong></td></tr>'


def _item_rows_html(items: list[dict]) -> str:
    rows = "".join(
        f"""<tr>
              <td style="padding:6px 0;border-bottom:1px solid #f3ece1;">{item['quantity']} x {item['name']}</td>
              <td style="padding:6px 0;border-bottom:1px solid #f3ece1;text-align:right;">Rs.{item['line_total']:.2f}</td>
            </tr>"""
        for item in items
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:14px 0;">{rows}</table>'


async def send_order_confirmation(
    to: str,
    guest_name: str | None,
    order_id: int,
    items: list[dict],
    total: float,
    fulfillment: str | None,
    delivery_address: str | None,
    location: str | None = None,
) -> bool:
    # delivery_address already has the customer's house/flat number appended
    # by the caller (see ai_service._full_delivery_address) - a single
    # complete address string, nothing extra to graft on here.
    fulfillment_line = (
        f"Delivery to: {delivery_address}" if fulfillment == "delivery" else "Pickup at the café - see you soon!"
    )
    location_line = f"<p style=\"color:#6f4e37;\">Branch: {location}</p>" if location else ""
    body = f"""
      <p>Hi {guest_name or 'there'}, thanks for your order! Here's your confirmation:</p>
      {_item_rows_html(items)}
      <p style="font-size:17px;font-weight:bold;color:#c1440e;margin:14px 0;">Total: Rs.{total:.2f}</p>
      <p>{fulfillment_line}</p>
      {location_line}
      <p style="color:#6f4e37;">Order ID: #{order_id}</p>
    """
    html = _wrap("Order Confirmed! 🎉", body, location_name=location)
    # Plain "Cafe" here, not "Café" - unlike the HTML body (which declares
    # UTF-8 via <meta charset>), the Subject header goes out over SMTP with
    # no charset control from us, and non-ASCII subjects have shown up
    # mangled ("Rasa Caf<?>") in delivery logs. Sidestep it entirely rather
    # than depend on the mail relay's header encoding.
    return await _send(to, f"Your Rasa Cafe order #{order_id} is confirmed", html, kind="order_confirmation")


async def send_reservation_confirmation(
    to: str,
    guest_name: str | None,
    reservation_id: int,
    date_label: str,
    time_label: str,
    guests: int,
    special_requests: str | None,
    location: str | None = None,
) -> bool:
    requests_line = f"<p>Special requests: {special_requests}</p>" if special_requests else ""
    location_line = f"<p style=\"color:#6f4e37;\">Branch: {location}</p>" if location else ""
    body = f"""
      <p>Hi {guest_name or 'there'}, your table is booked! Here's your confirmation:</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0;font-size:15px;">
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Date</td><td><strong>{date_label}</strong></td></tr>
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Time</td><td><strong>{time_label}</strong></td></tr>
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Guests</td><td><strong>{guests}</strong></td></tr>
      </table>
      {location_line}
      {requests_line}
      <p style="color:#6f4e37;">Reservation ID: #{reservation_id}</p>
      <p>We'll see you then!</p>
    """
    html = _wrap("Table Confirmed! 🎉", body, location_name=location)
    return await _send(to, "Your Rasa Cafe reservation is confirmed", html, kind="reservation_confirmation")


async def send_reservation_reminder(
    to: str, guest_name: str | None, reservation_id: int, date_label: str, time_label: str, guests: int
) -> bool:
    body = f"""
      <p>Hi {guest_name or 'there'}, just a friendly reminder - your table is coming up soon!</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0;font-size:15px;">
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Date</td><td><strong>{date_label}</strong></td></tr>
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Time</td><td><strong>{time_label}</strong></td></tr>
        <tr><td style="padding:3px 12px 3px 0;color:#6f4e37;">Guests</td><td><strong>{guests}</strong></td></tr>
      </table>
      <p style="color:#6f4e37;">Reservation ID: #{reservation_id}</p>
      <p>See you soon!</p>
    """
    html = _wrap("See You in About 2 Hours! ⏰", body)
    return await _send(to, "Reminder: your Rasa Cafe table is coming up", html, kind="reservation_reminder")


async def send_birthday_wish(to: str, guest_name: str | None) -> bool:
    body = f"""
      <p>Happy Birthday{f', {guest_name}' if guest_name else ''}! 🎉</p>
      <p>Everyone at Rasa Café wishes you a wonderful day. Treat yourself to
      something sweet from the menu - on us in spirit, if not on the bill! 🎂</p>
    """
    html = _wrap("Happy Birthday! 🎂", body)
    return await _send(to, "Happy Birthday from Rasa Cafe! 🎂", html, kind="birthday_wish")


async def send_cart_abandonment(to: str, items: list[dict], total: float) -> bool:
    body = f"""
      <p>You left some delicious items waiting in your cart!</p>
      {_item_rows_html(items)}
      <p style="font-size:17px;font-weight:bold;color:#c1440e;margin:14px 0;">Total: Rs.{total:.2f}</p>
      <p>Come back and finish your order whenever you're ready - we'll have it waiting.</p>
    """
    html = _wrap("You Left Something Behind! 🛍️", body)
    return await _send(to, "You left items in your Rasa Cafe cart", html, kind="cart_abandonment")


async def send_internal_order_notification(
    order_id: int,
    timestamp: str,
    guest_name: str | None,
    guest_phone: str | None,
    guest_email: str | None,
    items: list[dict],
    subtotal: float,
    discount: float,
    coupon_code: str | None,
    tax: float,
    total: float,
    fulfillment: str | None,
    delivery_address: str | None,
    location: str | None = None,
    delivery_flat_number: str | None = None,
    delivery_unverified: bool = False,
) -> bool:
    unverified_suffix = " ⚠️ UNVERIFIED - please confirm with customer" if delivery_unverified else ""
    fulfillment_line = (
        f"Delivery to: {delivery_address} (nearest branch: {location}){unverified_suffix}"
        if fulfillment == "delivery"
        else f"Pickup at {location or 'the café'}"
    )
    flat_number_row = (
        _detail_row("Flat/House No.", delivery_flat_number)
        if fulfillment == "delivery" and delivery_flat_number
        else ""
    )
    discount_line = (
        _detail_row("Discount", f"-Rs.{discount:.2f} (coupon {coupon_code})") if discount else _detail_row("Discount", "none")
    )
    body = f"""
      <p>New order placed - here are the details for the kitchen/front desk:</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0;font-size:15px;">
        {_detail_row("Order ID", f"#{order_id}")}
        {_detail_row("Placed", timestamp)}
        {_detail_row("Customer", guest_name or "N/A")}
        {_detail_row("Phone", guest_phone or "N/A")}
        {_detail_row("Email", guest_email or "N/A")}
        {flat_number_row}
      </table>
      {_item_rows_html(items)}
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0;font-size:15px;">
        {_detail_row("Subtotal", f"Rs.{subtotal:.2f}")}
        {discount_line}
        {_detail_row("Tax", f"Rs.{tax:.2f}")}
      </table>
      <p style="font-size:17px;font-weight:bold;color:#c1440e;margin:14px 0;">Total: Rs.{total:.2f}</p>
      <p>{fulfillment_line}</p>
    """
    html = _wrap("New Order Received 🧾", body, location_name=location)
    subject = f"New Order #{order_id} - {guest_name or 'Guest'} - Rs.{total:.2f}"
    return await _send(CAFE_INTERNAL_EMAIL, subject, html, kind="internal_order_notification")


async def send_internal_reservation_notification(
    reservation_id: int,
    date_label: str,
    time_label: str,
    guests: int,
    guest_name: str | None,
    guest_phone: str | None,
    guest_email: str | None,
    special_requests: str | None,
    location: str | None = None,
) -> bool:
    requests_line = f"<p>Special requests: {special_requests}</p>" if special_requests else ""
    body = f"""
      <p>New reservation booked - here are the details for the front desk:</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0;font-size:15px;">
        {_detail_row("Reservation ID", f"#{reservation_id}")}
        {_detail_row("Branch", location or "N/A")}
        {_detail_row("Date", date_label)}
        {_detail_row("Time", time_label)}
        {_detail_row("Guests", str(guests))}
        {_detail_row("Customer", guest_name or "N/A")}
        {_detail_row("Phone", guest_phone or "N/A")}
        {_detail_row("Email", guest_email or "N/A")}
      </table>
      {requests_line}
    """
    html = _wrap("New Reservation Booked 📅", body, location_name=location)
    subject = f"New Reservation - {guest_name or 'Guest'} - {date_label}, {time_label}"
    return await _send(CAFE_INTERNAL_EMAIL, subject, html, kind="internal_reservation_notification")
