"""Per-minute scheduler tick — enqueues ``poll_profile`` for due profiles.

Runs as a TaskIQ scheduled job (cron ``* * * * *``). For every active
search profile, it checks the last successful run timestamp from
``profile_runs`` and decides whether to enqueue another ``poll_profile``
based on:

* ``poll_interval_minutes`` from the profile (default 15)
* ``active_hours`` overlay if present — profile is skipped outside
  the configured day-of-week / hour window

We deliberately keep this dumb: just decides "go / no go" and pushes
the work to ``poll_profile``. All state and side-effects live in the
poll task itself, so a missed scheduler tick at most delays a poll by
one minute — never duplicates work or corrupts state.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select

from app.db.base import get_sessionmaker
from app.db.models import ProfileRun, SearchProfile
from app.tasks.broker import broker

log = logging.getLogger(__name__)


def _is_within_active_hours(
    active_hours: dict[str, Any] | None, now: datetime
) -> bool:
    """Return True if ``now`` falls inside the profile's active window.

    Schema is intentionally flexible (the UI hasn't fully locked it down
    yet). Recognised keys:

    * ``"start"`` / ``"end"`` — integer hours 0..23 (inclusive start,
      exclusive end). Wraps midnight if start > end.
    * ``"weekdays"`` — list of weekday ints 0..6 (Mon=0). Empty/missing
      means "every day".

    Anything else / malformed input → return True (fail open: don't
    silently skip polling because the UI shipped a new schema field).
    """
    if not active_hours:
        return True
    try:
        weekdays = active_hours.get("weekdays")
        if isinstance(weekdays, list) and weekdays:
            if now.weekday() not in weekdays:
                return False
        start = active_hours.get("start")
        end = active_hours.get("end")
        if isinstance(start, int) and isinstance(end, int):
            hour = now.hour
            if start <= end:
                return start <= hour < end
            else:  # wraps midnight, e.g. start=22, end=6
                return hour >= start or hour < end
    except Exception:  # pragma: no cover — never let scheduler crash on schema drift
        log.exception("scheduler.active_hours.parse_failed")
        return True
    return True


@broker.task(
    task_name="app.tasks.scheduler.tick",
    schedule=[{"cron": "* * * * *"}],
)
async def tick() -> dict[str, int]:
    """Once-a-minute heartbeat. Enqueues poll_profile for every due profile.

    Returns a small summary dict ``{checked, due, enqueued}`` so the
    health-checker can lift it from the result backend (V2 enhancement).
    """
    sessionmaker = get_sessionmaker()
    now = datetime.now(timezone.utc)
    checked = 0
    due = 0
    enqueued = 0

    async with sessionmaker() as session:
        active_profiles = (
            await session.execute(
                select(SearchProfile).where(SearchProfile.is_active.is_(True))
            )
        ).scalars().all()

        for profile in active_profiles:
            checked += 1

            if not _is_within_active_hours(profile.active_hours, now):
                continue

            # Find the most recent run; if there is none, the profile is
            # immediately due.
            last_run = (
                await session.execute(
                    select(ProfileRun)
                    .where(ProfileRun.profile_id == profile.id)
                    .order_by(desc(ProfileRun.started_at))
                    .limit(1)
                )
            ).scalar_one_or_none()

            interval = max(int(profile.poll_interval_minutes or 15), 1)
            cutoff = now - timedelta(minutes=interval)
            if last_run is not None and last_run.started_at is not None:
                # Make tz-aware comparison safe.
                started_at = last_run.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                if started_at > cutoff:
                    continue

            due += 1
            try:
                from app.tasks.polling import poll_profile

                await poll_profile.kiq(str(profile.id))
                enqueued += 1
            except Exception:
                log.exception(
                    "scheduler.enqueue_failed profile_id=%s", profile.id
                )

    log.info(
        "scheduler.tick checked=%d due=%d enqueued=%d", checked, due, enqueued
    )
    return {"checked": checked, "due": due, "enqueued": enqueued}
