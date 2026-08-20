from typing import Literal

from pydantic import BaseModel


class OrderActionRequest(BaseModel):
    session_id: str
    action: Literal["add", "remove", "modify", "view_summary", "checkout", "clear"]
    menu_item_id: int | None = None
    item_name: str | None = None
    quantity: int | None = None
    user_id: int | None = None


class OrderItemSummary(BaseModel):
    menu_item_id: int
    name: str
    quantity: int
    price_at_order: float
    line_total: float


class OrderSummaryResponse(BaseModel):
    order_id: int | None = None
    status: str | None = None
    items: list[OrderItemSummary]
    subtotal: float
    discount: float = 0.0
    coupon_code: str | None = None
    tax: float
    total: float


class OrderActionResponse(BaseModel):
    message: str
    summary: OrderSummaryResponse
