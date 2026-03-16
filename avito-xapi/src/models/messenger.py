from pydantic import BaseModel
from datetime import datetime
from typing import Any


class Author(BaseModel):
    id: str
    name: str | None = None
    avatar_url: str | None = None


class Message(BaseModel):
    id: str
    channel_id: str
    author_id: str
    author_name: str | None = None
    text: str | None = None
    message_type: str = "text"
    media_url: str | None = None
    media_info: dict[str, Any] | None = None
    is_read: bool = False
    is_first: bool = False
    created_at: datetime | None = None


class ChannelInfo(BaseModel):
    item_id: str | None = None
    item_title: str | None = None
    item_url: str | None = None
    item_price: str | None = None
    item_image: str | None = None


class Channel(BaseModel):
    id: str
    contact_name: str | None = None
    contact_id: str | None = None
    is_read: bool = True
    unread_count: int = 0
    last_message_text: str | None = None
    last_message_at: datetime | None = None
    info: ChannelInfo | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChannelListResponse(BaseModel):
    channels: list[Channel]
    has_more: bool = False
    total: int | None = None


class MessagesResponse(BaseModel):
    messages: list[Message]
    has_more: bool = False


class SendMessageRequest(BaseModel):
    text: str


class CreateChannelByItemRequest(BaseModel):
    item_id: str


class CreateChannelByUserRequest(BaseModel):
    user_hash: str


class UnreadCountResponse(BaseModel):
    count: int
