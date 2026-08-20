"""Bare scaffold - registered in app.main but has no active endpoints yet.
Will be filled in once the order/checkout system is rebuilt (cart
reminders, order confirmations, etc. all depended on order_service, which
was removed along with the rest of the order system)."""

from fastapi import APIRouter

router = APIRouter()
