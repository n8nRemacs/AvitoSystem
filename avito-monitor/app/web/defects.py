"""Admin UI for defect catalog (Project A)."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.deps import db_session, require_user

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter(prefix="/defects", tags=["defects"])


@router.get("", include_in_schema=False)
async def defects_root() -> RedirectResponse:
    return RedirectResponse(url="/defects/devices", status_code=303)


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/devices.html",
        {"active_tab": "devices", "user": user},
    )


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/catalog.html",
        {"active_tab": "catalog", "user": user},
    )
