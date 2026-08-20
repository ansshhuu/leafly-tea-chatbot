from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrderItemBase(BaseModel):
    menu_item_id: int
    quantity: int = 1
    price_at_order: float


class OrderItemCreate(OrderItemBase):
    pass


class OrderItemRead(OrderItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int


class OrderBase(BaseModel):
    user_id: int | None = None
    session_id: str | None = None
    status: str = "draft"
    total_amount: float = 0
    tax_amount: float = 0


class OrderCreate(OrderBase):
    items: list[OrderItemCreate] = []


class OrderRead(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    items: list[OrderItemRead] = []
