"""Runtime-mutable system state — pause + silent window.

Two flags backed by ``system_settings`` rows so they survive restarts
and stay visible across the bot, the worker, and the FastAPI app:

* ``runtime:system_paused`` — global on/off switch. When true,
  ``send_notification`` keeps every notification PENDING and the
  scheduler skips its tick. Reflects what ``/pause`` and ``/resume``
  toggle from Telegram.
* ``runtime:silent_until`` — ISO-8601 UTC timestamp. While ``now <
  silent_until`` notifications stay queued (the scheduler still polls
  Avito, the worker still classifies — only delivery is held).

Reads are cheap (single PK lookup) and we don't cache. The bot calls
this on every ``/silent`` invocation, the worker calls it once per
notification — that's nowhere near hot enough to need caching.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import get_sessionmaker
from app.db.models import SystemSetting

log = logging.getLogger(__name__)

KEY_PAUSED = "runtime:system_paused"
KEY_SILENT_UNTIL = "runtime:silent_until"


async def _get(key: str) -> dict | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await session.get(SystemSetting, key)
        return row.value if row else None


async def _set(key: str, value: dict) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = pg_insert(SystemSetting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SystemSetting.key], set_={"value": stmt.excluded.value}
        )
        await session.execute(stmt)
        await session.commit()


# ---------------------------------------------------------------------
# system paused
# ---------------------------------------------------------------------

async def is_paused() -> bool:
    val = await _get(KEY_PAUSED)
    return bool(val and val.get("paused") is True)


async def set_paused(paused: bool) -> None:
    await _set(KEY_PAUSED, {"paused": bool(paused)})


# ---------------------------------------------------------------------
# silent window
# ---------------------------------------------------------------------

async def silent_until() -> datetime | None:
    val = await _get(KEY_SILENT_UNTIL)
    if not val or not val.get("until"):
        return None
    raw = val["until"]
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        log.warning("runtime_state.silent_until.parse_failed value=%s", raw)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def set_silent_for(minutes: int) -> datetime:
    """Silence delivery for ``minutes`` from now. Returns the new ``until``."""
    until = datetime.now(timezone.utc) + timedelta(minutes=max(int(minutes), 0))
    await _set(KEY_SILENT_UNTIL, {"until": until.isoformat()})
    return until


async def clear_silent() -> None:
    await _set(KEY_SILENT_UNTIL, {"until": None})


async def is_silent_now() -> bool:
    until = await silent_until()
    if until is None:
        return False
    return datetime.now(timezone.utc) < until
