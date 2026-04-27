from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchProfile, User
from app.deps import current_user_optional, db_session, require_user
from app.schemas.search_profile import (
    SearchProfileCreate,
    SearchProfileUpdate,
)
from app.services import search_profiles as svc
from app.services.auth import authenticate

log = structlog.get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


router = APIRouter()


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

async def _layout_context(
    user: User, session: AsyncSession, active: str
) -> dict[str, Any]:
    """Common variables every _layout-extending page needs."""
    profiles_count_stmt = select(func.count(SearchProfile.id)).where(
        SearchProfile.user_id == user.id
    )
    active_count_stmt = profiles_count_stmt.where(SearchProfile.is_active.is_(True))
    total = (await session.execute(profiles_count_stmt)).scalar_one()
    active_total = (await session.execute(active_count_stmt)).scalar_one()
    return {
        "current_user": user,
        "active": active,
        "sidebar_profiles_count": total,
        "sidebar_active_profiles": active_total,
        "sidebar_listings_count": 0,  # filled by Block 4
    }


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_form(
    request: Request,
    user: User | None = Depends(current_user_optional),
) -> HTMLResponse | RedirectResponse:
    if user is not None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse | RedirectResponse:
    user = await authenticate(session, username, password)
    if user is None:
        log.info("auth.failed", username=username)
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Неверный логин или пароль"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    await session.commit()
    request.session["user_id"] = str(user.id)
    log.info("auth.success", user_id=str(user.id), username=user.username)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="dashboard")
    profiles = await svc.list_profiles(session, user.id)
    ctx["profiles"] = profiles
    return templates.TemplateResponse(request, "dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Search profiles — list + new + edit + runs
# ---------------------------------------------------------------------------

@router.get("/search-profiles", response_class=HTMLResponse)
async def profiles_list(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="profiles")
    ctx["profiles"] = await svc.list_profiles(session, user.id)
    ctx["message"] = request.query_params.get("msg")
    return templates.TemplateResponse(request, "profiles/list.html", ctx)


@router.get("/search-profiles/new", response_class=HTMLResponse)
async def profile_new(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="profiles")
    ctx.update({
        "title": "Новый профиль",
        "form_action": "/search-profiles/new",
        "submit_label": "Создать профиль",
        "profile": None,
        "regions": _load_regions(),
    })
    return templates.TemplateResponse(request, "profiles/form.html", ctx)


def _form_get_int(form: dict[str, Any], key: str) -> int | None:
    v = form.get(key)
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        v = v[0]
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _form_get_bool(form: dict[str, Any], key: str) -> bool:
    v = form.get(key)
    if isinstance(v, list):
        return any(str(x).lower() in ("true", "on", "1") for x in v)
    return str(v).lower() in ("true", "on", "1")


def _form_get_list(form: dict[str, Any], key: str) -> list[str]:
    v = form.get(key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x not in (None, "")]
    return [str(v)] if v else []


def _form_get_str(form: dict[str, Any], key: str) -> str | None:
    v = form.get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None or v == "":
        return None
    return str(v)


async def _parse_form_to_create(request: Request) -> SearchProfileCreate:
    raw = await request.form()
    form = {k: raw.getlist(k) if len(raw.getlist(k)) > 1 else raw.get(k) for k in raw}
    return SearchProfileCreate(
        name=_form_get_str(form, "name") or "Без названия",
        avito_search_url=_form_get_str(form, "avito_search_url") or "",
        region_slug=_form_get_str(form, "region_slug"),
        only_with_delivery=_form_get_bool(form, "only_with_delivery") if "only_with_delivery" in form else None,
        sort=_form_get_int(form, "sort"),
        search_min_price=_form_get_int(form, "search_min_price"),
        search_max_price=_form_get_int(form, "search_max_price"),
        alert_min_price=_form_get_int(form, "alert_min_price"),
        alert_max_price=_form_get_int(form, "alert_max_price"),
        custom_criteria=_form_get_str(form, "custom_criteria"),
        allowed_conditions=_form_get_list(form, "allowed_conditions") or ["working"],
        analyze_photos=_form_get_bool(form, "analyze_photos"),
        poll_interval_minutes=_form_get_int(form, "poll_interval_minutes") or 15,
        is_active=_form_get_bool(form, "is_active"),
        notification_channels=_form_get_list(form, "notification_channels") or ["telegram"],
    )


async def _parse_form_to_update(request: Request) -> SearchProfileUpdate:
    raw = await request.form()
    form = {k: raw.getlist(k) if len(raw.getlist(k)) > 1 else raw.get(k) for k in raw}
    return SearchProfileUpdate(
        name=_form_get_str(form, "name"),
        avito_search_url=_form_get_str(form, "avito_search_url"),
        region_slug=_form_get_str(form, "region_slug"),
        only_with_delivery=_form_get_bool(form, "only_with_delivery") if "only_with_delivery" in form else None,
        sort=_form_get_int(form, "sort"),
        search_min_price=_form_get_int(form, "search_min_price"),
        search_max_price=_form_get_int(form, "search_max_price"),
        alert_min_price=_form_get_int(form, "alert_min_price"),
        alert_max_price=_form_get_int(form, "alert_max_price"),
        custom_criteria=_form_get_str(form, "custom_criteria"),
        allowed_conditions=_form_get_list(form, "allowed_conditions") or None,
        analyze_photos=_form_get_bool(form, "analyze_photos"),
        poll_interval_minutes=_form_get_int(form, "poll_interval_minutes"),
        is_active=_form_get_bool(form, "is_active"),
        notification_channels=_form_get_list(form, "notification_channels") or None,
    )


@router.post("/search-profiles/new", response_model=None)
async def profile_create(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse | RedirectResponse:
    try:
        data = await _parse_form_to_create(request)
        profile = await svc.create_profile(session, user.id, data)
        await session.commit()
    except Exception as e:
        log.error("profile_create.failed", error=str(e))
        ctx = await _layout_context(user, session, active="profiles")
        ctx.update({
            "title": "Новый профиль",
            "form_action": "/search-profiles/new",
            "submit_label": "Создать профиль",
            "profile": None,
            "regions": _load_regions(),
            "error": f"Не удалось сохранить профиль: {e}",
        })
        return templates.TemplateResponse(
            request, "profiles/form.html", ctx,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        f"/search-profiles?msg=Профиль+«{profile.name}»+создан",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/search-profiles/parse-url-fragment", response_class=HTMLResponse)
async def parse_url_fragment(
    request: Request,
    avito_search_url: Annotated[str, Form()],
    _: User = Depends(require_user),
) -> HTMLResponse:
    try:
        preview = svc.preview_url(avito_search_url)
        return templates.TemplateResponse(
            request, "_partials/parser_preview.html",
            {"preview": preview, "error": None},
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request, "_partials/parser_preview.html",
            {"preview": None, "error": str(e)},
        )


@router.get("/search-profiles/{profile_id}", response_class=HTMLResponse)
async def profile_edit_form(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    ctx = await _layout_context(user, session, active="profiles")
    ctx.update({
        "title": "Редактирование профиля",
        "form_action": f"/search-profiles/{profile.id}",
        "submit_label": "Сохранить изменения",
        "profile": profile,
        "regions": _load_regions(),
    })
    return templates.TemplateResponse(request, "profiles/form.html", ctx)


@router.post("/search-profiles/{profile_id}", response_model=None)
async def profile_update(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    data = await _parse_form_to_update(request)
    await svc.update_profile(session, profile, data)
    await session.commit()
    return RedirectResponse(
        f"/search-profiles?msg=Профиль+«{profile.name}»+обновлён",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/search-profiles/{profile_id}/runs", response_class=HTMLResponse)
async def profile_runs(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    ctx = await _layout_context(user, session, active="profiles")
    ctx["profile"] = profile
    ctx["runs"] = await svc.list_runs(session, profile_id)
    return templates.TemplateResponse(request, "profiles/runs.html", ctx)


@router.post("/search-profiles/{profile_id}/toggle")
async def profile_toggle_web(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    await svc.toggle_profile(session, profile)
    await session.commit()
    state = "активирован" if profile.is_active else "поставлен на паузу"
    return RedirectResponse(
        f"/search-profiles?msg=Профиль+{state}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/search-profiles/{profile_id}/run-now")
async def profile_run_now_web(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    await svc.schedule_run_now(session, profile)
    await session.commit()
    return RedirectResponse(
        "/search-profiles?msg=Запрос+на+прогон+создан+(воркер+появится+в+Блоке+4)",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# Reliability — V2 Messenger Reliability §2 L5 / Stage 7
# ---------------------------------------------------------------------------

@router.get("/reliability", response_class=HTMLResponse)
async def reliability_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """Static shell for the Reliability dashboard.

    The real status data is fetched client-side from ``/api/v1/health/full``
    immediately on load and then every 30 s. Server-side we just render the
    layout + the scenario letter list so the page is meaningful even before
    the first JS fetch returns.
    """
    from app.api.health_full import SCENARIO_LABELS

    ctx = await _layout_context(user, session, active="reliability")
    ctx["scenario_labels"] = SCENARIO_LABELS
    return templates.TemplateResponse(request, "reliability.html", ctx)


# ---------------------------------------------------------------------------
# Stubs — pages that come in later blocks
# ---------------------------------------------------------------------------

@router.get("/listings", response_class=HTMLResponse)
async def listings_stub(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="listings")
    ctx.update({
        "section_title": "Лоты",
        "section_icon": "📦",
        "section_description": "Лента собранных объявлений с фильтрами по состоянию и alert-зоне.",
        "next_block": 4,
    })
    return templates.TemplateResponse(request, "_stub.html", ctx)


@router.get("/price-intelligence", response_class=HTMLResponse)
async def prices_stub(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="prices")
    ctx.update({
        "section_title": "Ценовая разведка",
        "section_icon": "💰",
        "section_description": "Анализ конкурентов: вилка цен, топ-5 дешевле/дороже, рекомендация.",
        "next_block": 7,
    })
    return templates.TemplateResponse(request, "_stub.html", ctx)


@router.get("/logs", response_class=HTMLResponse)
async def logs_stub(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="logs")
    ctx.update({
        "section_title": "Логи",
        "section_icon": "📜",
        "section_description": "Структурные события системы.",
        "next_block": 8,
    })
    return templates.TemplateResponse(request, "_stub.html", ctx)


@router.get("/settings", response_class=HTMLResponse)
async def settings_stub(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="settings")
    ctx.update({
        "section_title": "Настройки",
        "section_icon": "⚙️",
        "section_description": "Глобальные параметры: модели LLM, лимиты, мессенджеры.",
        "next_block": 8,
    })
    return templates.TemplateResponse(request, "_stub.html", ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_regions() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "avito_regions.json").read_text(encoding="utf-8"))
