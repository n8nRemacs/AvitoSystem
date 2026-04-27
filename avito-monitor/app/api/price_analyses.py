"""REST API for Price Intelligence (TZ §6.4, Block 7)."""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import User
from app.deps import db_session, require_user
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.integrations.messenger.base import MessengerError, MessengerMessage
from app.integrations.messenger.factory import get_provider
from app.integrations.openrouter import OpenRouterClient
from app.schemas.price_analysis import (
    PriceAnalysisCreate,
    PriceAnalysisRead,
    PriceAnalysisRunRead,
    PriceAnalysisUpdate,
    RunNowResult,
)
from app.services import price_intelligence as svc
from app.services.llm_analyzer import LLMAnalyzer
from app.services.llm_cache import DBLLMCache

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/price-analyses", tags=["price-intelligence"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PriceAnalysisRead])
async def list_analyses(
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[PriceAnalysisRead]:
    items = await svc.list_analyses(session, user.id)
    return [PriceAnalysisRead.model_validate(i) for i in items]


@router.post("", response_model=PriceAnalysisRead, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    data: Annotated[PriceAnalysisCreate, Body()],
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> PriceAnalysisRead:
    a = await svc.create_analysis(session, user.id, data)
    await session.commit()
    return PriceAnalysisRead.model_validate(a)


@router.get("/{analysis_id}", response_model=PriceAnalysisRead)
async def get_analysis(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> PriceAnalysisRead:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return PriceAnalysisRead.model_validate(a)


@router.patch("/{analysis_id}", response_model=PriceAnalysisRead)
async def update_analysis(
    analysis_id: uuid.UUID,
    data: Annotated[PriceAnalysisUpdate, Body()],
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> PriceAnalysisRead:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    a = await svc.update_analysis(session, a, data)
    await session.commit()
    return PriceAnalysisRead.model_validate(a)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> None:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await svc.delete_analysis(session, a)
    await session.commit()


# ---------------------------------------------------------------------------
# Run + report
# ---------------------------------------------------------------------------

def _build_analyzer() -> LLMAnalyzer:
    s = get_settings()
    if not s.openrouter_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY не задан — анализ невозможен",
        )
    openrouter = OpenRouterClient(
        api_key=s.openrouter_api_key,
        app_base_url=s.app_base_url,
        app_title="Avito Monitor",
    )
    cache = DBLLMCache(get_sessionmaker())
    return LLMAnalyzer(
        openrouter=openrouter,
        cache=cache,
        default_text_model=s.openrouter_default_text_model,
        default_vision_model=s.openrouter_default_vision_model,
    )


@router.post("/{analysis_id}/run", response_model=RunNowResult, status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RunNowResult:
    """Synchronous V1 run: fetches competitors, compares via LLM, builds report.

    Acceptance criterion (TZ §4.2): ≤3 min on 30 competitors. Heavy work
    runs inside the request to keep V1 simple — no TaskIQ enqueue.
    """
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analyzer = _build_analyzer()
    async with AvitoMcpClient() as mcp:
        run = await svc.run_analysis(session, a, mcp=mcp, analyzer=analyzer)
    await session.commit()
    return RunNowResult(
        run_id=run.id,
        status=run.status,
        competitors_found=run.competitors_found,
        comparable_count=run.comparable_count,
        error_message=run.error_message,
    )


@router.get("/{analysis_id}/runs", response_model=list[PriceAnalysisRunRead])
async def list_runs(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[PriceAnalysisRunRead]:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    runs = await svc.list_runs(session, analysis_id)
    return [PriceAnalysisRunRead.model_validate(r) for r in runs]


@router.get("/{analysis_id}/runs/{run_id}", response_model=PriceAnalysisRunRead)
async def get_run(
    analysis_id: uuid.UUID,
    run_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> PriceAnalysisRunRead:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    run = await svc.get_run(session, run_id)
    if run is None or run.analysis_id != analysis_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return PriceAnalysisRunRead.model_validate(run)


@router.post("/{analysis_id}/runs/{run_id}/send-to-telegram")
async def send_to_telegram(
    analysis_id: uuid.UUID,
    run_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> dict:
    a = await svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    run = await svc.get_run(session, run_id)
    if run is None or run.analysis_id != analysis_id:
        raise HTTPException(status_code=404, detail="Run not found")

    settings = get_settings()
    chat_id = (settings.telegram_allowed_user_ids or "").split(",")[0].strip()
    if not chat_id or chat_id == "*":
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_ALLOWED_USER_IDS пуст — некому слать",
        )
    text = svc.export_report_markdown(a, run)
    try:
        provider = get_provider("telegram")
        await provider.send(MessengerMessage(chat_id=chat_id, text=text))
    except MessengerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"sent": True, "chat_id": chat_id}
