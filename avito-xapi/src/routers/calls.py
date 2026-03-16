from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
import io

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.calls import CallRecord, CallHistoryResponse
from src.workers.session_reader import load_active_session
from src.workers.http_client import AvitoHttpClient

router = APIRouter(prefix="/api/v1/calls", tags=["Calls"])


def _get_client(ctx: TenantContext) -> AvitoHttpClient:
    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


def _normalize_call(raw: dict) -> CallRecord:
    return CallRecord(
        id=str(raw.get("id", "")),
        caller=raw.get("caller"),
        receiver=raw.get("receiver"),
        duration=raw.get("duration"),
        has_record=raw.get("hasRecord", False),
        is_new=raw.get("isNew", False),
        is_spam=raw.get("isSpamTagged", False),
        is_callback=raw.get("isCallback", False),
        create_time=raw.get("createTime"),
        item_id=str(raw.get("itemId", "")) if raw.get("itemId") else None,
        item_title=raw.get("itemTitle"),
    )


@router.get("/history", response_model=CallHistoryResponse)
async def call_history(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(get_current_tenant),
):
    require_feature(request, "avito.calls")
    client = _get_client(ctx)
    data = await client.get_call_history(date_from=date_from, date_to=date_to,
                                          limit=limit, offset=offset)
    result = data.get("result", {})
    items = result.get("items", [])
    calls = [_normalize_call(c) for c in items]
    return CallHistoryResponse(calls=calls, total=result.get("total", len(calls)))


@router.get("/{call_id}/recording")
async def call_recording(call_id: str, request: Request,
                         ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.calls")
    client = _get_client(ctx)
    audio = await client.get_call_recording(call_id)
    return StreamingResponse(
        io.BytesIO(audio),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="call_{call_id}.mp3"'},
    )
