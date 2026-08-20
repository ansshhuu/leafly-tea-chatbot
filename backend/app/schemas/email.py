from pydantic import BaseModel


class CartReminderRequest(BaseModel):
    session_id: str


class CartReminderResponse(BaseModel):
    sent: bool
    reason: str | None = None
