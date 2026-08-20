import logging

from brevo import AsyncBrevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem

from app.core.config import (
    CONTACT_EMAIL,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME,
    settings,
)
from app.core.timing import timed

logger = logging.getLogger(__name__)


# Simple line-art echo of a leaf mark, next to "Leafly" in the header -
# instead of a generic emoji. Built from plain table cells + CSS borders,
# NOT an <svg> or <img>: most email clients (Gmail among them) strip <svg>
# entirely and/or block images by default, which would silently leave the
# header blank - borders/border-radius on a table cell render reliably
# everywhere HTML email does.
_LOGO_ICON_HTML = (
    '<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
    '<tr><td style="width:20px;height:20px;border:2px solid #d4af37;border-bottom:none;'
    'border-radius:11px 11px 0 0;line-height:0;font-size:0;">&nbsp;</td></tr>'
    "</table>"
)


def _wrap(title: str, body_html: str) -> str:
    # Playfair Display echoes the site's heading font - loaded where the
    # email client allows external @font-face/@import (most modern
    # webmail/desktop clients do), falling back to Georgia/Times New Roman
    # serif everywhere else, same calm/premium feel either way.
    heading_font = "'Playfair Display', Georgia, 'Times New Roman', serif"
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap');
    </style>
  </head>
  <body style="margin:0;padding:0;background:#f7f3e9;font-family:Georgia,'Times New Roman',serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f3e9;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border:1px solid #d9cba8;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="background:#0d2818;padding:22px 28px;">
                <table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                  <tr>
                    <td style="vertical-align:middle;padding-right:9px;line-height:0;">{_LOGO_ICON_HTML}</td>
                    <td style="vertical-align:middle;">
                      <span style="font-family:{heading_font};font-size:23px;font-weight:700;color:#f7f3e9;letter-spacing:0.3px;">Leafly</span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;color:#1f2e26;font-size:15px;line-height:1.55;">
                <h1 style="margin:0 0 14px;font-size:20px;color:#0d2818;">{title}</h1>
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="background:#f0ead9;padding:16px 28px;color:#5b4a2f;font-size:12px;line-height:1.5;">
                Leafly · {CONTACT_EMAIL}
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


async def send_birthday_wish(to: str, guest_name: str | None) -> bool:
    body = f"""
      <p>Happy Birthday{f', {guest_name}' if guest_name else ''}! 🎉</p>
      <p>Everyone at Leafly wishes you a wonderful day. Treat yourself to a
      pot of something special - on us in spirit, if not on the bill! 🍵</p>
    """
    html = _wrap("Happy Birthday! 🎂", body)
    return await _send(to, "Happy Birthday from Leafly! 🎂", html, kind="birthday_wish")
