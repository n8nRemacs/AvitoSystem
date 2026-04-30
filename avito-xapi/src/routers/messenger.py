from datetime import datetime, timezone
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.messenger import (
    Channel, ChannelInfo, ChannelListResponse, Message, MessagesResponse,
    SendMessageRequest, CreateChannelByItemRequest, CreateChannelByUserRequest,
    UnreadCountResponse,
)
from src.routers._avito_errors import reraise_avito_error
from src.workers.session_reader import load_active_session
from src.workers.http_client import AvitoHttpClient

router = APIRouter(prefix="/api/v1/messenger", tags=["Messenger"])


def _get_client(ctx: TenantContext) -> AvitoHttpClient:
    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


def _parse_timestamp_ns(ns: int | None) -> datetime | None:
    if not ns:
        return None
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)


def _normalize_channel(raw: dict, my_user_id: int | None = None) -> Channel:
    """Normalize Avito channel to our model."""
    users = raw.get("users", [])
    contact = None
    for u in users:
        if isinstance(u, dict) and str(u.get("id", "")) != str(my_user_id or ""):
            contact = u
            break
    if not contact and users:
        contact = users[0] if isinstance(users[0], dict) else None

    info = raw.get("info", {})
    details = info.get("details", {})
    last_msg = raw.get("lastMessage", {})
    last_text_obj = last_msg.get("body", {}).get("text", {})
    last_text = last_text_obj.get("text", "") if isinstance(last_text_obj, dict) else str(last_text_obj or "")

    images = details.get("images", [])
    first_image = images[0] if images else None

    return Channel(
        id=raw.get("id", ""),
        contact_name=contact.get("name") if contact else info.get("name"),
        contact_id=contact.get("id") if contact else None,
        is_read=raw.get("isRead", True),
        unread_count=raw.get("unreadCount", 0),
        last_message_text=last_text or None,
        last_message_at=_parse_timestamp_ns(last_msg.get("createdAt")),
        info=ChannelInfo(
            item_id=details.get("itemId"),
            item_title=details.get("title"),
            item_url=details.get("url"),
            item_price=str(details.get("price")) if details.get("price") else None,
            item_image=first_image,
        ) if details else None,
        created_at=_parse_timestamp_ns(raw.get("created")),
        updated_at=_parse_timestamp_ns(raw.get("updated")),
    )


def _normalize_message(raw: dict) -> Message:
    """Normalize Avito message to our model."""
    body = raw.get("body", {})
    text_obj = body.get("text", {})
    text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj or "")

    msg_type = "text"
    media_url = None
    media_info = None

    if body.get("image"):
        msg_type = "image"
        img = body["image"]
        media_url = img.get("url") or img.get("imageUrl")
        media_info = {"image_id": img.get("imageId"), "width": img.get("width"), "height": img.get("height")}
    elif body.get("voice"):
        msg_type = "voice"
        media_info = {"voice_id": body["voice"].get("voiceId"), "duration": body["voice"].get("duration")}
    elif body.get("video"):
        msg_type = "video"
        media_info = {"video_id": body["video"].get("videoId")}
    elif body.get("file"):
        msg_type = "file"
        f = body["file"]
        media_info = {"file_id": f.get("fileId"), "name": f.get("name"), "size": f.get("size")}
    elif body.get("location"):
        msg_type = "location"
        loc = body["location"]
        media_info = {"lat": loc.get("lat"), "lon": loc.get("lon"), "address": loc.get("address")}

    return Message(
        id=raw.get("id", ""),
        channel_id=raw.get("channelId", ""),
        author_id=raw.get("authorId", ""),
        text=text or None,
        message_type=msg_type,
        media_url=media_url,
        media_info=media_info,
        is_read=raw.get("readAt") is not None,
        is_first=raw.get("isFirstMessage", False),
        created_at=_parse_timestamp_ns(raw.get("createdAt")),
    )


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    offset_timestamp: int | None = Query(None),
    ctx: TenantContext = Depends(get_current_tenant),
):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)

    try:
        data = await client.get_channels(limit=limit, offset_timestamp=offset_timestamp)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    success = data.get("success", {})
    raw_channels = success.get("channels", [])

    session = load_active_session(ctx.tenant.id)
    my_user_id = session.user_id if session else None

    channels = [_normalize_channel(ch, my_user_id) for ch in raw_channels]
    return ChannelListResponse(
        channels=channels,
        has_more=success.get("hasMore", False),
    )


@router.get("/channels/{channel_id}", response_model=Channel)
async def get_channel(channel_id: str, request: Request,
                      ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        data = await client.get_channel_by_id(channel_id)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    raw = data.get("success", {}).get("channel", data.get("success", {}))
    session = load_active_session(ctx.tenant.id)
    return _normalize_channel(raw, session.user_id if session else None)


@router.get("/channels/{channel_id}/messages", response_model=MessagesResponse)
async def get_messages(channel_id: str, request: Request,
                       limit: int = Query(50, ge=1, le=100),
                       offset_id: str | None = Query(None),
                       ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        data = await client.get_messages(channel_id, limit=limit, offset_id=offset_id)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    success = data.get("success", {})
    raw_messages = success.get("messages", [])
    messages = [_normalize_message(m) for m in raw_messages]
    return MessagesResponse(messages=messages, has_more=len(raw_messages) >= limit)


@router.post("/channels/{channel_id}/messages")
async def send_message(channel_id: str, body: SendMessageRequest, request: Request,
                       ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        result = await client.send_text(channel_id, body.text)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    return {"status": "ok", "result": result.get("success", {})}


@router.post("/channels/{channel_id}/read")
async def read_channel(channel_id: str, request: Request,
                       ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        await client.mark_read([channel_id])
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    return {"status": "ok"}


@router.post("/channels/{channel_id}/typing")
async def typing(channel_id: str, request: Request,
                 ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        await client.send_typing(channel_id)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    return {"status": "ok"}


@router.post("/channels/by-item")
async def create_channel_by_item(body: CreateChannelByItemRequest, request: Request,
                                  ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        result = await client.create_channel_by_item(body.item_id)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    return {"status": "ok", "result": result.get("success", {})}


@router.post("/channels/by-user")
async def create_channel_by_user(body: CreateChannelByUserRequest, request: Request,
                                  ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        result = await client.create_channel_by_user(body.user_hash)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    return {"status": "ok", "result": result.get("success", {})}


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(request: Request,
                       ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.messenger")
    client = _get_client(ctx)
    try:
        data = await client.get_unread_count()
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    count = data.get("success", {}).get("unreadCount", 0)
    return UnreadCountResponse(count=count)
