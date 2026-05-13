"""Admin UI for defect catalog (Project A)."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.deps import db_session, require_user
from app.services.defect_catalog.repository import (
    create_binding,
    create_device_node,
    create_feature_node,
    delete_binding,
    delete_device_node,
    delete_feature_node,
    get_binding,
    get_device_node,
    list_device_children,
    list_feature_children,
    update_binding,
    update_device_node,
    update_feature_node,
    _UNSET,
)
from app.services.defect_catalog.resolver import (
    _feature_path,
    resolve_applicable_defects,
)
# Imported lazily inside handlers to avoid circular import at module level
# (routers.py is loaded first by main.py; defects.py is a sibling)
from app.web.routers import _layout_context

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

_SEVERITY_RU = {
    "block": "блок",
    "info": "инфо",
    "ask": "уточнить",
    "skip": "пропустить",
}


def severity_ru(value: str) -> str:
    """Translate DB severity values (block/info/ask/skip) to Russian UI labels.
    Unknown values pass through unchanged for defensive rendering."""
    return _SEVERITY_RU.get(value, value)


templates.env.filters["severity_ru"] = severity_ru

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
    ctx = await _layout_context(user, session, active="defects")
    ctx["active_tab"] = "devices"
    return templates.TemplateResponse(request, "defects/devices.html", ctx)


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="defects")
    ctx["active_tab"] = "catalog"
    return templates.TemplateResponse(request, "defects/catalog.html", ctx)


async def _build_device_tree(session, parent_id):
    """Pre-compute the device tree as nested dicts for the template.
    This avoids requiring async-Jinja support."""
    nodes = await list_device_children(session, parent_id=parent_id)
    return [{"node": n, "children": await _build_device_tree(session, n.id)} for n in nodes]


@router.get("/devices/tree", response_class=HTMLResponse)
async def devices_tree(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


async def _build_feature_tree(session, parent_id):
    nodes = await list_feature_children(session, parent_id=parent_id)
    return [{"node": n, "children": await _build_feature_tree(session, n.id)} for n in nodes]


@router.get("/catalog/tree", response_class=HTMLResponse)
async def catalog_tree(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )


@router.get("/devices/new", response_class=HTMLResponse)
async def device_form_add_root(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "device", "parent_id": None, "prefill": None},
    )


@router.get("/devices/cancel-form", response_class=HTMLResponse)
async def device_form_cancel(
    user: Annotated[User, Depends(require_user)],
) -> HTMLResponse:
    return HTMLResponse("")


@router.get("/devices/{parent_id}/new", response_class=HTMLResponse)
async def device_form_add_child(
    parent_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "device", "parent_id": str(parent_id), "prefill": None},
    )


@router.get("/devices/{node_id}/edit", response_class=HTMLResponse)
async def device_form_edit(
    node_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    device = await get_device_node(session, node_id)
    if device is None:
        return HTMLResponse("Устройство не найдено", status_code=404)
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {
            "mode": "edit", "kind": "device", "node_id": str(node_id),
            "prefill": {"slug": device.slug, "title": device.title},
        },
    )


@router.get("/devices/{device_id}", response_class=HTMLResponse)
async def device_detail(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    device = await get_device_node(session, device_id)
    if device is None:
        return HTMLResponse("Device not found", status_code=404)
    resolved = await resolve_applicable_defects(session, device_id)
    ctx = await _layout_context(user, session, active="defects")
    ctx["active_tab"] = "devices"
    ctx["device"] = device
    ctx["bindings"] = resolved
    return templates.TemplateResponse(
        request, "defects/_partials/device_detail.html", ctx,
    )


@router.post("/bindings", response_class=HTMLResponse)
async def create_binding_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    device_node_id: Annotated[str, Form()],
    feature_node_id: Annotated[str, Form()],
    defect_action: Annotated[str, Form()] = "block",
    unknown_action: Annotated[str, Form()] = "ask",
) -> HTMLResponse:
    """Create an explicit override binding at the given device node."""
    bid = await create_binding(
        session,
        device_node_id=uuid.UUID(device_node_id),
        feature_node_id=uuid.UUID(feature_node_id),
        defect_action=defect_action,
        unknown_action=unknown_action,
    )
    b = await get_binding(session, bid)
    if b is None:
        return HTMLResponse("", status_code=500)
    fp = await _feature_path(session, b.feature_node_id)
    view = {
        "binding_id": b.id,
        "feature_node_id": b.feature_node_id,
        "feature_path": fp,
        "defect_action": b.defect_action,
        "unknown_action": b.unknown_action,
        "inherited_from": None,
    }
    return templates.TemplateResponse(
        request, "defects/_partials/binding_row.html",
        {"b": view, "target_device_id": device_node_id},
    )


@router.patch("/bindings/{binding_id}", response_class=HTMLResponse)
async def patch_binding(
    binding_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    defect_action: Annotated[str | None, Form()] = None,
    unknown_action: Annotated[str | None, Form()] = None,
    disabled: Annotated[bool | None, Form()] = None,
    target_device_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    await update_binding(
        session, binding_id,
        defect_action=defect_action,
        unknown_action=unknown_action,
        disabled=disabled,
    )
    b = await get_binding(session, binding_id)
    if b is None:
        return HTMLResponse("", status_code=200)
    fp = await _feature_path(session, b.feature_node_id)
    view = {
        "binding_id": b.id,
        "feature_node_id": b.feature_node_id,
        "feature_path": fp,
        "defect_action": b.defect_action,
        "unknown_action": b.unknown_action,
        "inherited_from": None,
    }
    return templates.TemplateResponse(
        request, "defects/_partials/binding_row.html",
        {"b": view, "target_device_id": target_device_id or str(b.device_node_id)},
    )


@router.delete("/bindings/{binding_id}", response_class=HTMLResponse)
async def delete_binding_endpoint(
    binding_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_binding(session, binding_id)
    return HTMLResponse("", status_code=200)


# ---------------------------------------------------------------------------
# Task 25: POST endpoints for device / feature creation
# ---------------------------------------------------------------------------

@router.post("/devices", response_class=HTMLResponse)
async def create_device_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    parent_id: Annotated[str | None, Form()] = None,
    slug: Annotated[str, Form()] = ...,
    title: Annotated[str, Form()] = ...,
    kind: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else None
    try:
        await create_device_node(session, parent_id=pid, slug=slug, title=title, kind=kind)
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.post("/catalog", response_class=HTMLResponse)
async def create_feature_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    parent_id: Annotated[str | None, Form()] = None,
    kind: Annotated[str, Form()] = ...,
    slug: Annotated[str, Form()] = ...,
    title: Annotated[str, Form()] = ...,
    prompt_hint: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else None
    try:
        await create_feature_node(
            session, parent_id=pid, kind=kind, slug=slug, title=title,
            prompt_hint=prompt_hint,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )


# ---------------------------------------------------------------------------
# Task 26: PATCH/DELETE endpoints for device and feature nodes
# ---------------------------------------------------------------------------

@router.patch("/devices/{device_id}/edit", response_class=HTMLResponse)
async def patch_device_endpoint(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    title: Annotated[str | None, Form()] = None,
    slug: Annotated[str | None, Form()] = None,
    parent_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else _UNSET
    try:
        await update_device_node(session, device_id, title=title, slug=slug, parent_id=pid)
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.delete("/devices/{device_id}", response_class=HTMLResponse)
async def delete_device_endpoint(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_device_node(session, device_id)
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.patch("/catalog/{feature_id}/edit", response_class=HTMLResponse)
async def patch_feature_endpoint(
    feature_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    title: Annotated[str | None, Form()] = None,
    slug: Annotated[str | None, Form()] = None,
    prompt_hint: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    try:
        await update_feature_node(
            session, feature_id, title=title, slug=slug, prompt_hint=prompt_hint,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )


@router.delete("/catalog/{feature_id}", response_class=HTMLResponse)
async def delete_feature_endpoint(
    feature_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_feature_node(session, feature_id)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )
