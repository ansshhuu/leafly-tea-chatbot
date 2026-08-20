from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatHistoryBase(BaseModel):
    session_id: str
    role: str
    message: str


class ChatHistoryCreate(ChatHistoryBase):
    pass


class ChatHistoryRead(ChatHistoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
