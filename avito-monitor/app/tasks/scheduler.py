"""Per-minute scheduler tick — enqueues ``poll_profile`` round-robin.

Runs as a TaskIQ scheduled job (cron ``* * * * *``). For every active
user we enqueue **at most one** ``poll_profile`` per tick — picking the
least-recently-polled active profile of that user that is also due
under its own ``poll_interval_minutes``. We additionally enforce a
random 60–120 s gap between two enqueues for the same user to avoid
the bot-pattern of dispatching N profiles in the same second (Avito's
anti-fraud trips on that, see the 2026-04-28 incident: account-level
cool-off after a 7-profile sync burst).

Profile selection rules:

* skip if outside ``active_hours`` (day-of-week / hour overlay)
* skip if ``last_started_at`` is more recent than ``poll_interval_minutes``
* among the rest, pick the one with the oldest ``last_started_at``
  (NULL counts as "infinitely old" — fresh profiles get polled first)

We keep all real work in ``poll_profile``: a missed tick costs at most
one minute of latency and never duplicates work.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.base import get_sessionmaker
from app.db.models import ProfileRun, SearchProfile
from app.tasks.broker import broker

log = logging.getLogger(__name__)

# Minimum / maximum seconds between two enqueues for the same user.
# Random jitter in this band makes the polling pattern look like a real
# user opening the app every minute or two, not a script.
_GAP_MIN_SEC = 60
_GAP_MAX_SEC = 120


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


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@broker.task(
    task_name="app.tasks.scheduler.tick",
    schedule=[{"cron": "* * * * *"}],
)
async def tick() -> dict[str, int]:
    """Once-a-minute heartbeat. Enqueues at most one poll_profile per user.

    Returns ``{checked, eligible_users, enqueued, skipped_gap}``:
    ``checked`` — total active profiles seen;
    ``eligible_users`` — users with at least one due profile;
    ``enqueued`` — actual ``kiq`` calls made (0 or eligible_users);
    ``skipped_gap`` — users for whom the per-user 60–120 s gap was not
    yet over since their last poll (no kiq this tick).
    """
    sessionmaker = get_sessionmaker()
    now = datetime.now(timezone.utc)
    checked = 0
    eligible_users = 0
    enqueued = 0
    skipped_gap = 0

    async with sessionmaker() as session:
        # All currently-active profiles (skip archived, skip is_active=false).
        active_profiles = (
            await session.execute(
                select(SearchProfile).where(
                    SearchProfile.is_active.is_(True),
                    SearchProfile.archived_at.is_(None),
                )
            )
        ).scalars().all()

        # Group by owning user.
        by_user: dict[uuid.UUID, list[SearchProfile]] = {}
        for p in active_profiles:
            checked += 1
            by_user.setdefault(p.user_id, []).append(p)

        for user_id, profiles in by_user.items():
            # Latest enqueue time across ALL of this user's profiles —
            # used for the per-user 60–120 s gap.
            latest = (
                await session.execute(
                    select(func.max(ProfileRun.started_at))
                    .join(SearchProfile, SearchProfile.id == ProfileRun.profile_id)
                    .where(SearchProfile.user_id == user_id)
                )
            ).scalar_one_or_none()
            latest = _aware(latest)
            gap = random.randint(_GAP_MIN_SEC, _GAP_MAX_SEC)
            if latest is not None and (now - latest).total_seconds() < gap:
                skipped_gap += 1
                continue

            # Last started_at per profile — single grouped query.
            ids = [p.id for p in profiles]
            last_per_profile: dict[uuid.UUID, datetime] = {
                row[0]: _aware(row[1]) for row in (
                    await session.execute(
                        select(
                            ProfileRun.profile_id, func.max(ProfileRun.started_at)
                        )
                        .where(ProfileRun.profile_id.in_(ids))
                        .group_by(ProfileRun.profile_id)
                    )
                ).all()
            }

            # Pick the least-recently-polled profile that is currently due
            # (within its active_hours window AND past its poll_interval).
            EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
            candidates: list[tuple[SearchProfile, datetime]] = []
            for p in profiles:
                if not _is_within_active_hours(p.active_hours, now):
                    continue
                last = last_per_profile.get(p.id)
                interval = max(int(p.poll_interval_minutes or 15), 1)
                if last is not None and (now - last) < timedelta(minutes=interval):
                    continue
                candidates.append((p, last or EPOCH))

            if not candidates:
                continue

            eligible_users += 1
            chosen = min(candidates, key=lambda c: c[1])[0]
            try:
                from app.tasks.polling import poll_profile

                await poll_profile.kiq(str(chosen.id))
                enqueued += 1
            except Exception:
                log.exception(
                    "scheduler.enqueue_failed profile_id=%s", chosen.id
                )

    log.info(
        "scheduler.tick checked=%d eligible_users=%d enqueued=%d skipped_gap=%d",
        checked, eligible_users, enqueued, skipped_gap,
    )
    return {
        "checked": checked,
        "eligible_users": eligible_users,
        "enqueued": enqueued,
        "skipped_gap": skipped_gap,
    }
