"""LLM stages of the worker pipeline — detail refresh + API killer rules.

V2 flag-based evaluator (evaluate_listing) removed in Phase 2.1 Task 4
(migration 0016_unified_criteria). All analysis now flows through the
defect-features pipeline (analyze_listing_features).

Remaining tasks:
* :func:`refresh_listing_detail` — no-LLM detail re-fetch (reservation tracking)

Helper kept for reuse by the unified-criteria pipeline (Task 5+):
* :func:`check_api_killers` — pure-Python deal-breaker scan from Avito params
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update

from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    Notification,
    SearchProfile,
)
from app.db.models.enums import (
    NotificationStatus,
    NotificationType,
)
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.db.models.listing_status_event import ListingStatusEvent
from app.tasks.broker import broker

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# API killer rules — pure-Python verdicts straight from listing.parameters.
# Avito-side structured fields ("Работа устройства" = "Не включается", etc.)
# are ground truth — no need to spend an LLM call to confirm. When any rule
# matches we skip the LLM entirely and write a synthetic evaluation right here.
# Saves cost + time, and the api criterion shows up in the UI with the rule
# that fired.
# ----------------------------------------------------------------------

# Sensors that are NOT a deal-breaker. Anything else listed under
# "Не работают датчики" is treated as red:
#   Wi-Fi / Bluetooth / Compass — motherboard-level, kills resale value
#   Face ID / Touch ID         — affects everyday use, kills resale value
# The proximity sensor ("Приближения к уху") is the lone exception per
# user feedback 2026-05-10 — most buyers don't notice it.
_API_SAFE_SENSORS = {
    "приближения к уху",
    "приближение к уху",
}


def _normalise_sensor_token(s: str) -> str:
    return s.strip().lower()


def check_api_killers(parameters: dict | None) -> list[tuple[str, str]]:
    """Inspect Avito-side parameters for unambiguous deal-breakers.

    Returns a list of ``(criterion_key, reasoning)`` tuples. An empty list
    means no killer fired and the LLM should run as usual.

    Rules (per user feedback 2026-05-10):
      Работа устройства  ∋ "Не включается" or "Не работает сенсор"  → red
      Аккумулятор        ∋ "Не заряжается"                          → red
      Не работают функции ≠ ""                                       → red
      Не работают датчики has any non-safe sensor                   → red
        (safe = только "Приближения к уху")
    """
    if not parameters:
        return []

    matches: list[tuple[str, str]] = []

    work_state = str(parameters.get("Работа устройства") or "")
    work_low = work_state.lower()
    if "не включается" in work_low:
        matches.append((
            "api:device_not_starting",
            f"Avito-параметр «Работа устройства» = «{work_state}» (не включается)",
        ))
    elif "не работает сенсор" in work_low:
        matches.append((
            "api:motherboard_sensor_dead",
            f"Avito-параметр «Работа устройства» = «{work_state}» (датчик платы)",
        ))
    elif "не звонит" in work_low or "не видит сим" in work_low or "нет сети" in work_low:
        matches.append((
            "api:modem_broken",
            f"Avito-параметр «Работа устройства» = «{work_state}» (модем/связь)",
        ))

    battery_state = str(parameters.get("Аккумулятор") or "")
    if "не заряжается" in battery_state.lower():
        matches.append((
            "api:battery_dead",
            f"Avito-параметр «Аккумулятор» = «{battery_state}»",
        ))

    broken_functions = str(parameters.get("Не работают функции") or "").strip()
    if broken_functions:
        matches.append((
            "api:functions_broken",
            f"Avito-параметр «Не работают функции» = «{broken_functions}»",
        ))

    broken_sensors = str(parameters.get("Не работают датчики") or "").strip()
    if broken_sensors:
        # CSV-like: split on common separators and check each token.
        tokens = [t for t in broken_sensors.replace(";", ",").split(",") if t.strip()]
        unsafe = [t.strip() for t in tokens if _normalise_sensor_token(t) not in _API_SAFE_SENSORS]
        if unsafe:
            matches.append((
                "api:critical_sensors_broken",
                f"Avito-параметр «Не работают датчики» включает критичные: {', '.join(unsafe)}",
            ))

    # Камера: red ТОЛЬКО если явно "Не работает <что-то>". Визуальные
    # дефекты (потёртости/пятна/трещины линзы) сами по себе НЕ киллер —
    # их LLM посмотрит как часть общей картины.
    camera_state = str(parameters.get("Камера") or "").strip()
    if camera_state and "не работает" in camera_state.lower():
        matches.append((
            "api:camera_broken",
            f"Avito-параметр «Камера» = «{camera_state}» (не работает)",
        ))

    return matches


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _make_error_notification(
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID | None,
    code: str,
    message: str,
    profile: SearchProfile | None,
) -> Notification:
    return Notification(
        user_id=profile.user_id if profile is not None else uuid.uuid4(),
        profile_id=profile_id,
        related_listing_id=listing_id,
        type=NotificationType.ERROR.value,
        channel="telegram",
        payload={"code": code, "message": message[:500]},
        status=NotificationStatus.PENDING.value,
    )


# ----------------------------------------------------------------------
# refresh_listing_detail — no-LLM detail re-fetch (reservation tracking)
# ----------------------------------------------------------------------

@broker.task(task_name="app.tasks.analysis.refresh_listing_detail")
async def refresh_listing_detail(listing_id: str) -> dict[str, Any]:
    """Pull the latest detail payload for a listing and refresh DB fields.

    Triggered by polling when ``reservation_status`` flips. Updates
    ``description``, ``parameters`` and the reservation triplet
    (``reservation_status``, ``reservation_changed_at``,
    ``reserved_at_price``) when the detail-side status differs from what
    polling already persisted. Does NOT call the LLM — reservation events
    are cheap signals, not classifications.
    """
    sessionmaker = get_sessionmaker()
    lid = uuid.UUID(listing_id)

    async with sessionmaker() as session:
        listing = await session.get(Listing, lid)
        if listing is None:
            log.warning("analysis.refresh_detail.row_missing listing=%s", listing_id)
            return {"status": "skipped", "reason": "row missing"}
        avito_id = int(listing.avito_id)
        prev_reservation = listing.reservation_status

    try:
        async with AvitoMcpClient() as mcp:
            fresh = await mcp.get_listing(avito_id)
    except Exception:
        log.exception(
            "analysis.refresh_detail.fetch_failed listing=%s", listing_id
        )
        return {"status": "failed", "reason": "fetch_failed"}

    detail_reservation = getattr(fresh, "reservation_status", None)
    now = datetime.now(timezone.utc)

    async with sessionmaker() as session:
        updates: dict[str, Any] = {
            "description": fresh.description,
            "parameters": fresh.parameters or {},
            # Detail endpoint carries the full gallery; search feed only
            # had the cover. Persist all so the lightbox shows them.
            "images": [
                img.model_dump(mode="json")
                for img in (fresh.images or [])
            ] or None,
        }
        reservation_updated = False
        if (
            detail_reservation is not None
            and detail_reservation != prev_reservation
        ):
            updates["reservation_status"] = detail_reservation
            updates["reservation_changed_at"] = now
            session.add(
                ListingStatusEvent(
                    listing_id=lid,
                    event_type="status_change",
                    old_value=prev_reservation,
                    new_value=detail_reservation,
                    at=now,
                )
            )
            if detail_reservation == "reserved":
                # Detail is the more authoritative source for the snapshot
                # (search card may lag by a refresh); prefer its price.
                captured_price = fresh.price
                updates["reserved_at_price"] = captured_price
                session.add(
                    ListingStatusEvent(
                        listing_id=lid,
                        event_type="reservation_capture",
                        old_value=None,
                        new_value=(
                            str(captured_price)
                            if captured_price is not None
                            else None
                        ),
                        at=now,
                    )
                )
            reservation_updated = True

        await session.execute(
            update(Listing).where(Listing.id == lid).values(**updates)
        )
        await session.commit()

    log.info(
        "analysis.refresh_detail.success listing=%s reservation_updated=%s",
        listing_id, reservation_updated,
    )
    return {
        "status": "success",
        "reservation_updated": reservation_updated,
        "reservation_status": detail_reservation,
    }
