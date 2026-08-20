from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.email import CartReminderRequest, CartReminderResponse
from app.services import email_service, order_service, session_context_service

router = APIRouter()


@router.post("/cart-reminder", response_model=CartReminderResponse)
async def cart_reminder(payload: CartReminderRequest, db: AsyncSession = Depends(get_db)) -> CartReminderResponse:
    """Fire-and-forget from the frontend's perspective (see
    ChatContext.jsx's inactivity timer) - the backend is the source of
    truth for whether a send actually makes sense: an email must be known
    for this session, there must be an active (non-empty) draft cart, and
    this exact cart must not have already gotten a reminder."""
    email = await session_context_service.get_email(db, payload.session_id)
    if not email:
        return CartReminderResponse(sent=False, reason="no_email_known")

    order = await order_service.get_active_draft_order(db, payload.session_id)
    if order is None:
        return CartReminderResponse(sent=False, reason="no_active_cart")

    summary = await order_service.get_order_summary(db, order.id)
    if not summary["items"]:
        return CartReminderResponse(sent=False, reason="cart_empty")

    if order.cart_reminder_sent:
        return CartReminderResponse(sent=False, reason="already_sent")
    order.cart_reminder_sent = True
    await db.commit()

    await email_service.send_cart_abandonment(email, summary["items"], summary["total"])
    return CartReminderResponse(sent=True, reason=None)
