"""REST API for SearchProfiles. ТЗ §6.2."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.deps import db_session, require_user
from app.schemas.search_profile import (
    ParsedUrlPreview,
    SearchProfileCreate,
    SearchProfileRead,
    SearchProfileUpdate,
)
from app.services import search_profiles as svc

router = APIRouter(prefix="/api/search-profiles", tags=["search-profiles"])


class ParseUrlRequest(BaseModel):
    url: str = Field(min_length=1)


@router.post("/parse-url", response_model=ParsedUrlPreview)
async def parse_url(body: ParseUrlRequest, _: User = Depends(require_user)) -> ParsedUrlPreview:
    try:
        return svc.preview_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[SearchProfileRead])
async def list_profiles(
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[SearchProfileRead]:
    items = await svc.list_profiles(session, user.id)
    return [SearchProfileRead.model_validate(p) for p in items]


@router.post("", response_model=SearchProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: Annotated[SearchProfileCreate, Body()],
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchProfileRead:
    profile = await svc.create_profile(session, user.id, data)
    await session.commit()
    return SearchProfileRead.model_validate(profile)


@router.get("/{profile_id}", response_model=SearchProfileRead)
async def get_profile(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchProfileRead:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return SearchProfileRead.model_validate(profile)


@router.patch("/{profile_id}", response_model=SearchProfileRead)
async def update_profile(
    profile_id: uuid.UUID,
    data: Annotated[SearchProfileUpdate, Body()],
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchProfileRead:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile = await svc.update_profile(session, profile, data)
    await session.commit()
    return SearchProfileRead.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> None:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    await svc.delete_profile(session, profile)
    await session.commit()


@router.post("/{profile_id}/toggle", response_model=SearchProfileRead)
async def toggle_profile(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchProfileRead:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile = await svc.toggle_profile(session, profile)
    await session.commit()
    return SearchProfileRead.model_validate(profile)


@router.post("/{profile_id}/run-now", status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> dict:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    run = await svc.schedule_run_now(session, profile)
    await session.commit()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "note": run.error_message,
    }
