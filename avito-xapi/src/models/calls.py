from pydantic import BaseModel
from datetime import datetime
from typing import Any


class CallRecord(BaseModel):
    id: str
    caller: str | None = None
    receiver: str | None = None
    duration: str | None = None
    has_record: bool = False
    is_new: bool = False
    is_spam: bool = False
    is_callback: bool = False
    create_time: datetime | None = None
    item_id: str | None = None
    item_title: str | None = None


class CallHistoryResponse(BaseModel):
    calls: list[CallRecord]
    total: int
