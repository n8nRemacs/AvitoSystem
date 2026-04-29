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
    ctx["archived"] = await svc.list_archived_profiles(session, user.id)
    ctx["message"] = request.query_params.get("msg")
    return templates.TemplateResponse(request, "profiles/list.html", ctx)


@router.post("/search-profiles/sync", response_model=None)
async def profiles_sync(
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    """Pull autosearches from Avito and reconcile with local profiles (ADR-011)."""
    from urllib.parse import quote_plus
    from app.services.autosearch_sync import sync_autosearches_for_user

    try:
        result = await sync_autosearches_for_user(user.id, session=session)
    except Exception as exc:  # pragma: no cover — surfaced to user
        return RedirectResponse(
            f"/search-profiles?msg={quote_plus(f'Sync failed: {exc}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    msg = (
        f"Sync OK: создано {result.created}, обновлено {result.updated}, "
        f"архивировано {result.archived} (всего на Avito {result.fetched})"
    )
    if result.failed:
        msg += f", не удалось получить параметры: {', '.join(result.failed)}"
    return RedirectResponse(
        f"/search-profiles?msg={quote_plus(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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


@router.get("/search-profiles/{profile_id}/stats", response_class=HTMLResponse)
async def profile_stats(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    from app.services.profile_stats import compute_stats_view, serialize_for_template

    ctx = await _layout_context(user, session, active="profiles")
    view = await compute_stats_view(session, profile)
    ctx["view"] = view
    ctx["profile"] = profile
    ctx["chart_data_json"] = json.dumps(serialize_for_template(view))
    return templates.TemplateResponse(request, "profiles/stats.html", ctx)


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


@router.post("/search-profiles/{profile_id}/delete", response_model=None)
async def profile_delete_web(
    profile_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    name = profile.name
    await svc.delete_profile(session, profile)
    await session.commit()
    from urllib.parse import quote_plus
    return RedirectResponse(
        f"/search-profiles?msg={quote_plus(f'Профиль «{name}» удалён')}",
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
async def listings_feed(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """Listings feed. Tabs «Новые / В работе» + filter chips + lazy load."""
    from app.services.listings_view import (
        ListingFilters,
        filter_summary,
        query_listings,
        tab_counts,
    )
    qp = request.query_params

    profile_ids: list[uuid.UUID] = []
    for raw in qp.getlist("profile"):
        if raw:
            try:
                profile_ids.append(uuid.UUID(raw))
            except ValueError:
                pass
    conditions = [c for c in qp.getlist("condition") if c]
    zone = qp.get("zone") or "all"
    period = qp.get("period") or "7d"
    sort = qp.get("sort") or "date"
    tab = qp.get("tab") or "new"
    if tab not in ("new", "in_progress", "rejected", "all"):
        tab = "new"
    try:
        offset = max(0, int(qp.get("offset") or 0))
    except ValueError:
        offset = 0
    limit = 30

    filters = ListingFilters(
        profile_ids=profile_ids or None,
        condition_classes=conditions or None,
        zone=zone,
        period=period,
        sort=sort,
        tab=tab,
        limit=limit,
        offset=offset,
    )

    rows, total = await query_listings(session, user.id, filters)
    summary = await filter_summary(session, user.id)
    counts = await tab_counts(session, user.id)

    # Total without filters — for the "238 / 1820" hint in the header.
    total_all_filters = ListingFilters(zone="all", period="all", tab="all", limit=1, offset=0)
    _, total_all = await query_listings(session, user.id, total_all_filters)

    def qs_builder(**overrides: str) -> str:
        """Rewrite the current query string with the given overrides.

        Keys with empty value are dropped (used for "Все" chips that
        clear a multi-select). Resets ``offset`` on any filter change
        so the user lands back on page 1.
        """
        from urllib.parse import urlencode
        keep = {
            "tab": filters.tab,
            "profile": [str(p) for p in (filters.profile_ids or [])],
            "condition": list(filters.condition_classes or []),
            "zone": filters.zone,
            "period": filters.period,
            "sort": filters.sort,
            "offset": str(filters.offset),
        }
        # Apply overrides.
        for k, v in overrides.items():
            if v == "":
                # Empty means "clear this dimension" (multi-select).
                if k in ("profile", "condition"):
                    keep[k] = []
                else:
                    keep[k] = ""
            else:
                if k in ("profile", "condition"):
                    # Toggle behaviour for multi-select chips.
                    cur = list(keep.get(k, []))
                    if v in cur:
                        cur.remove(v)
                    else:
                        cur.append(v)
                    keep[k] = cur
                else:
                    keep[k] = v
        # Reset offset if anything other than offset itself changed.
        if "offset" not in overrides:
            keep["offset"] = "0"

        flat: list[tuple[str, str]] = []
        for k, v in keep.items():
            if isinstance(v, list):
                for item in v:
                    flat.append((k, item))
            elif v not in (None, ""):
                flat.append((k, str(v)))
        return "/listings" + ("?" + urlencode(flat) if flat else "")

    ctx = await _layout_context(user, session, active="listings")
    ctx.update({
        "rows": rows,
        "total": total,
        "total_all": total_all,
        "f": filters,
        "summary": summary,
        "tab_counts": counts,
        "has_more": offset + len(rows) < total,
        "qs": qs_builder,
    })
    return templates.TemplateResponse(request, "listings.html", ctx)


@router.post("/listings/{profile_id}/{listing_id}/action", response_model=None)
async def listing_action(
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    """User accepts (→ В работу) or rejects (→ скрыт) a lot.

    Both transitions are permanent from the UI's perspective; the row stays
    in the DB so we keep history and can offer an undo path later.
    """
    from sqlalchemy import select, update, delete
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db.models import ProfileListing, SearchProfile, UserListingBlacklist
    from app.db.models.enums import UserAction

    form = await request.form()
    action_raw = (form.get("action") or "").strip().lower()
    new_action: str | None = None
    if action_raw == "accept":
        new_action = UserAction.ACCEPTED.value
    elif action_raw == "reject":
        new_action = UserAction.REJECTED.value
    elif action_raw == "undo":
        new_action = UserAction.PENDING.value
    if new_action is None:
        raise HTTPException(400, "action must be 'accept' | 'reject' | 'undo'")

    # Verify ownership before touching the link row.
    own = (await session.execute(
        select(SearchProfile.id).where(
            SearchProfile.id == profile_id, SearchProfile.user_id == user.id
        )
    )).scalar_one_or_none()
    if own is None:
        raise HTTPException(404, "Profile not found")

    res = await session.execute(
        update(ProfileListing)
        .where(
            ProfileListing.profile_id == profile_id,
            ProfileListing.listing_id == listing_id,
        )
        .values(user_action=new_action)
    )

    # Reject propagates to a per-user global blacklist so the listing never
    # appears as "Новые" again — even in a different profile or after a
    # criteria change. Undo lifts the blacklist; Accept doesn't touch it.
    if action_raw == "reject":
        await session.execute(
            pg_insert(UserListingBlacklist)
            .values(user_id=user.id, listing_id=listing_id, reason="rejected")
            .on_conflict_do_nothing(index_elements=["user_id", "listing_id"])
        )
    elif action_raw == "undo":
        await session.execute(
            delete(UserListingBlacklist).where(
                UserListingBlacklist.user_id == user.id,
                UserListingBlacklist.listing_id == listing_id,
            )
        )

    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(404, "Listing link not found")

    # After the action keep the user on the same tab they came from.
    target_tab = (form.get("from_tab") or "new").strip() or "new"
    return RedirectResponse(
        f"/listings?tab={target_tab}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/price-intelligence", response_class=HTMLResponse)
async def prices_list(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """List all PriceAnalysis configs for the current user."""
    from app.services import price_intelligence as pi_svc
    analyses = await pi_svc.list_analyses(session, user.id)
    latest_runs: dict = {}
    for a in analyses:
        latest_runs[str(a.id)] = await pi_svc.get_latest_run(session, a.id)
    ctx = await _layout_context(user, session, active="prices")
    ctx.update({"analyses": analyses, "latest_runs": latest_runs})
    return templates.TemplateResponse(request, "prices/list.html", ctx)


@router.get("/price-intelligence/new", response_class=HTMLResponse)
async def prices_new_form(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="prices")
    ctx.update({"errors": {}, "form": {}})
    return templates.TemplateResponse(request, "prices/new.html", ctx)


@router.post("/price-intelligence/new", response_model=None)
async def prices_new_submit(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse | RedirectResponse:
    from app.schemas.price_analysis import PriceAnalysisCreate
    from app.services import price_intelligence as pi_svc
    form = await request.form()
    name = (form.get("name") or "").strip()
    reference_url = (form.get("reference_listing_url") or "").strip() or None
    ref_price_raw = (form.get("reference_price") or "").strip()
    ref_title = (form.get("reference_title") or "").strip() or None
    search_url = (form.get("competitor_search_url") or "").strip()
    search_region = (form.get("search_region") or "").strip() or None
    max_competitors = int((form.get("max_competitors") or "30").strip() or 30)

    errors: dict[str, str] = {}
    if not name:
        errors["name"] = "Название обязательно"
    if not search_url:
        errors["competitor_search_url"] = "URL поиска конкурентов обязателен"

    reference_data: dict[str, Any] = {}
    if ref_price_raw:
        try:
            reference_data["price"] = int(ref_price_raw)
        except ValueError:
            errors["reference_price"] = "Цена должна быть числом"
    if ref_title:
        reference_data["title"] = ref_title
    if not reference_url and "price" not in reference_data:
        errors["reference_price"] = (
            "Без URL эталона нужна хотя бы цена для сравнения"
        )

    if errors:
        ctx = await _layout_context(user, session, active="prices")
        ctx.update({"errors": errors, "form": dict(form)})
        return templates.TemplateResponse(
            request, "prices/new.html", ctx, status_code=400
        )

    a = await pi_svc.create_analysis(
        session, user.id,
        PriceAnalysisCreate(
            name=name,
            reference_listing_url=reference_url,
            reference_data=reference_data,
            search_region=search_region,
            competitor_filters={"search_url": search_url},
            max_competitors=max_competitors,
        ),
    )
    await session.commit()
    return RedirectResponse(
        f"/price-intelligence/{a.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/price-intelligence/{analysis_id}", response_class=HTMLResponse)
async def prices_report(
    analysis_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    from app.schemas.price_analysis import PriceReport
    from app.services import price_intelligence as pi_svc
    analysis = await pi_svc.get_analysis(session, user.id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    latest = await pi_svc.get_latest_run(session, analysis.id)
    report: PriceReport | None = None
    if latest is not None and latest.report:
        try:
            report = PriceReport.model_validate(latest.report)
        except Exception:
            report = None
    ctx = await _layout_context(user, session, active="prices")
    ctx.update({
        "analysis": analysis,
        "run": latest,
        "report": report,
    })
    return templates.TemplateResponse(request, "prices/report.html", ctx)


@router.post("/price-intelligence/{analysis_id}/run", response_model=None)
async def prices_run_now_web(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    from app.api.price_analyses import _build_analyzer
    from app.integrations.avito_mcp_client.client import AvitoMcpClient
    from app.services import price_intelligence as pi_svc
    a = await pi_svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analyzer = _build_analyzer()
    async with AvitoMcpClient() as mcp:
        await pi_svc.run_analysis(session, a, mcp=mcp, analyzer=analyzer)
    await session.commit()
    return RedirectResponse(
        f"/price-intelligence/{analysis_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/price-intelligence/{analysis_id}/delete", response_model=None)
async def prices_delete_web(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    from app.services import price_intelligence as pi_svc
    a = await pi_svc.get_analysis(session, user.id, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await pi_svc.delete_analysis(session, a)
    await session.commit()
    return RedirectResponse(
        "/price-intelligence", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_view(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """Unified event log: profile_runs + notifications + audit + activity_log + errors."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import desc, select

    from app.db.models import (
        ActivityLog,
        AuditLog,
        Notification,
        ProfileRun,
        SearchProfile,
    )

    source = request.query_params.get("source") or ""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    events: list[dict[str, Any]] = []

    def _ts_local(dt) -> str:
        return dt.strftime("%d.%m %H:%M:%S") if dt else "—"

    if source in ("", "runs"):
        stmt = (
            select(ProfileRun, SearchProfile.name)
            .join(SearchProfile, SearchProfile.id == ProfileRun.profile_id)
            .where(SearchProfile.user_id == user.id, ProfileRun.started_at >= cutoff)
            .order_by(desc(ProfileRun.started_at))
            .limit(60)
        )
        for run, p_name in (await session.execute(stmt)).all():
            details_bits = []
            if run.listings_seen:
                details_bits.append(f"seen={run.listings_seen}")
            if run.listings_new:
                details_bits.append(f"new={run.listings_new}")
            if run.listings_in_alert:
                details_bits.append(f"alert={run.listings_in_alert}")
            events.append({
                "ts": run.started_at,
                "ts_local": _ts_local(run.started_at),
                "source": "runs",
                "title": f"Прогон профиля «{p_name}»",
                "details": ", ".join(details_bits) or run.error_message or "",
                "status": run.status,
                "latency_ms": int((run.finished_at - run.started_at).total_seconds() * 1000)
                    if run.finished_at and run.started_at else None,
            })

    if source in ("", "notifications", "errors"):
        stmt = (
            select(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.created_at >= cutoff,
            )
            .order_by(desc(Notification.created_at))
            .limit(60)
        )
        for n in (await session.execute(stmt)).scalars():
            if source == "errors" and n.status != "failed":
                continue
            events.append({
                "ts": n.created_at,
                "ts_local": _ts_local(n.created_at),
                "source": "notif" if n.type != "error" else "error",
                "title": f"{n.type} → {n.channel}",
                "details": (n.error_message or "")[:140] if n.status != "sent"
                    else (n.payload or {}).get("title", ""),
                "status": n.status,
                "latency_ms": None,
            })

    if source in ("", "audit"):
        stmt = (
            select(AuditLog)
            .where(AuditLog.user_id == user.id, AuditLog.created_at >= cutoff)
            .order_by(desc(AuditLog.created_at))
            .limit(40)
        )
        for a in (await session.execute(stmt)).scalars():
            events.append({
                "ts": a.created_at,
                "ts_local": _ts_local(a.created_at),
                "source": "audit",
                "title": a.action,
                "details": f"{a.entity_type}:{a.entity_id}" if a.entity_type else "",
                "status": "ok",
                "latency_ms": None,
            })

    if source in ("", "activity"):
        stmt = (
            select(ActivityLog)
            .where(ActivityLog.ts >= cutoff)
            .order_by(desc(ActivityLog.ts))
            .limit(40)
        )
        for a in (await session.execute(stmt)).scalars():
            events.append({
                "ts": a.ts,
                "ts_local": _ts_local(a.ts),
                "source": a.source or "activity",
                "title": a.action or "—",
                "details": a.target or "",
                "status": a.status,
                "latency_ms": a.latency_ms,
            })

    events.sort(key=lambda e: e["ts"], reverse=True)

    ctx = await _layout_context(user, session, active="logs")
    ctx.update({"events": events, "source": source})
    return templates.TemplateResponse(request, "logs.html", ctx)


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """Read-mostly settings page (UI Spec §4.8 — V1 simplified)."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, select

    from app.config import get_settings
    from app.db.models import LLMAnalysis
    from app.services.runtime_state import is_paused, silent_until

    s = get_settings()

    # LLM 24h spend
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    spend_stmt = select(
        func.coalesce(func.sum(LLMAnalysis.cost_usd), 0.0),
        func.count(LLMAnalysis.id),
    ).where(LLMAnalysis.created_at >= cutoff)
    spent, calls = (await session.execute(spend_stmt)).one()
    spent = float(spent or 0.0)
    avg_per_call = (spent / calls) if calls else 0.0

    # Avito session
    avito_status = {
        "session_active": False,
        "session_ttl_human": None,
        "session_error": None,
    }
    try:
        from app.services.health_checker.xapi_client import XapiClient
        client = XapiClient(base_url=s.avito_xapi_url, api_key=s.avito_xapi_api_key)
        res = await client.get("/api/v1/sessions/current")
        if res.ok and isinstance(res.body, dict):
            avito_status["session_active"] = bool(res.body.get("is_active"))
            avito_status["session_ttl_human"] = res.body.get("ttl_human")
        else:
            avito_status["session_error"] = f"HTTP {res.status_code}"
    except Exception as exc:
        avito_status["session_error"] = f"{type(exc).__name__}: {exc}"

    paused = await is_paused()
    silent = await silent_until()

    ctx = await _layout_context(user, session, active="settings")
    ctx.update({
        "message": request.query_params.get("msg"),
        "system_paused": paused,
        "silent_until": silent,
        "timezone": s.timezone,
        "app_env": s.app_env,
        "llm": {
            "text_model": s.openrouter_default_text_model,
            "vision_model": s.openrouter_default_vision_model,
            "api_key_masked": s.openrouter_api_key or "",
            "daily_limit": s.openrouter_daily_usd_limit,
            "spent_24h": spent,
            "calls_24h": calls,
            "avg_per_call": avg_per_call,
        },
        "avito": {
            "xapi_url": s.avito_xapi_url,
            "api_key": s.avito_xapi_api_key,
            **avito_status,
        },
        "tg": {
            "token": s.telegram_bot_token or "",
            "proxy_url": s.telegram_proxy_url,
            "allowed_ids": s.telegram_allowed_user_ids,
        },
    })
    return templates.TemplateResponse(request, "settings.html", ctx)


@router.post("/settings/system/pause", response_model=None)
async def settings_pause(
    user: Annotated[User, Depends(require_user)],
) -> RedirectResponse:
    from app.services.runtime_state import set_paused
    await set_paused(True)
    return RedirectResponse(
        "/settings?msg=Система+поставлена+на+паузу",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/system/resume", response_model=None)
async def settings_resume(
    user: Annotated[User, Depends(require_user)],
) -> RedirectResponse:
    from app.services.runtime_state import set_paused
    await set_paused(False)
    return RedirectResponse(
        "/settings?msg=Система+возобновлена",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/silent/set", response_model=None)
async def settings_silent_set(
    request: Request,
    user: Annotated[User, Depends(require_user)],
) -> RedirectResponse:
    from app.services.runtime_state import set_silent_for
    form = await request.form()
    try:
        minutes = max(1, min(1440, int(form.get("minutes") or 60)))
    except ValueError:
        minutes = 60
    await set_silent_for(minutes)
    return RedirectResponse(
        f"/settings?msg=Silent+на+{minutes}+минут",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/silent/clear", response_model=None)
async def settings_silent_clear(
    user: Annotated[User, Depends(require_user)],
) -> RedirectResponse:
    from app.services.runtime_state import clear_silent
    await clear_silent()
    return RedirectResponse(
        "/settings?msg=Silent+режим+снят",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/test-telegram", response_model=None)
async def settings_test_telegram(
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    from app.config import get_settings
    from app.integrations.messenger.base import MessengerError, MessengerMessage
    from app.integrations.messenger.factory import get_provider
    from urllib.parse import quote_plus

    s = get_settings()
    chat = (s.telegram_allowed_user_ids or "").split(",")[0].strip()
    if not chat or chat == "*":
        return RedirectResponse(
            "/settings?msg=" + quote_plus("TELEGRAM_ALLOWED_USER_IDS пуст"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        provider = get_provider("telegram")
        await provider.send(MessengerMessage(
            chat_id=chat,
            text="🟢 *Avito Monitor* — тестовое сообщение из настроек.",
        ))
        msg = "Тестовое сообщение отправлено в TG"
    except MessengerError as e:
        msg = f"Ошибка: {e}"
    return RedirectResponse(
        "/settings?msg=" + quote_plus(msg),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_regions() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "avito_regions.json").read_text(encoding="utf-8"))
