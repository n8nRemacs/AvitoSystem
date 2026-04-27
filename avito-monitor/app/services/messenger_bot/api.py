"""FastAPI sidecar for the messenger-bot service.

NO auth — internal-only, same convention as the health-checker / activity-
simulator sidecars. Mount behind a private port; do NOT expose publicly.

Endpoints:

* ``GET  /healthz``              — process + SSE state + counters.
* ``POST /run-once``             — manually run the handler against a synthetic
                                   ``new_message`` event for ``channel_id``.
                                   Pass ``dry_run=true`` to skip the upstream
                                   xapi POST (used by health-checker scenario G).
* ``GET  /stats?since=24h``      — bot action counts from ``activity_log``.
* ``POST /pause``                — flip in-process kill-switch off.
* ``POST /resume``               — flip in-process kill-switch on.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import FastAPI, Query
from sqlalchemy import func, select

from app.db.base import get_sessionmaker
from app.db.models import ActivityLog, ChatDialogState
from app.services.health_checker.sse_client import SseEvent
from app.services.messenger_bot import handler as handler_mod
from app.services.messenger_bot import kill_switch as kill_switch_mod
from app.services.messenger_bot import rate_limit as rate_limit_mod
from app.services.messenger_bot import runner as runner_mod
from app.services.messenger_bot.handler import handle_event

log = structlog.get_logger(__name__)


def _parse_since(since: str) -> int:
    """Accept ``Nh`` / ``Nd`` / bare integer (hours). Default 24h on parse error."""
    s = (since or "").strip().lower()
    if not s:
        return 24
    try:
        if s.endswith("h"):
            return max(1, int(s[:-1]))
        if s.endswith("d"):
            return max(1, int(s[:-1]) * 24)
        return max(1, int(s))
    except ValueError:
        return 24


def create_app() -> FastAPI:
    from app.config import get_settings  # imported here to honour test env var overrides

    app = FastAPI(title="avito-monitor messenger-bot", version="0.1.0")
    started_at = time.monotonic()

    @app.get("/healthz")
    async def healthz() -> dict:
        used = await rate_limit_mod.global_outgoing_count_last_hour()
        return {
            "service": "messenger-bot",
            "uptime_sec": int(time.monotonic() - started_at),
            "sse_state": runner_mod.SSE_STATE,
            "sse_reconnect_attempts": runner_mod.RECONNECT_ATTEMPTS,
            "last_event_ts": (
                handler_mod.LAST_EVENT_TS.isoformat()
                if handler_mod.LAST_EVENT_TS is not None
                else None
            ),
            "total_events": handler_mod.TOTAL_EVENTS,
            "total_replies": handler_mod.TOTAL_REPLIES,
            "bot_enabled": kill_switch_mod.bot_enabled(),
            "rate_used_last_hour": used,
            "rate_limit_per_hour": get_settings().messenger_bot_rate_limit_per_hour,
        }

    @app.post("/run-once")
    async def run_once(
        channel_id: str = Query(..., min_length=1, max_length=128),
        dry_run: bool = Query(default=False),
    ) -> dict:
        """Synthesise a ``new_message`` event for ``channel_id`` and dispatch.

        ``dry_run=true`` skips the upstream xapi POST — used by health-checker
        scenario G to test the dedup pipeline without sending real Avito traffic.
        """
        synthetic = SseEvent(
            event_name="new_message",
            data={
                "event": "new_message",
                "tenant_id": "manual",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "channel_id": channel_id,
                    "message_id": f"manual-{int(time.time() * 1000)}",
                    "author_id": None,
                    "text": "(synthetic /run-once trigger)",
                },
            },
            raw_data="",
        )
        client = runner_mod.make_xapi_client()
        verdict = await handle_event(synthetic, client=client, dry_run=dry_run)
        return verdict.to_dict()

    @app.get("/stats")
    async def stats(since: str = Query(default="24h")) -> dict:
        hours = _parse_since(since)
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            stmt = (
                select(
                    ActivityLog.action,
                    ActivityLog.status,
                    func.count().label("n"),
                )
                .where(ActivityLog.source == "bot")
                .where(ActivityLog.ts >= cutoff)
                .group_by(ActivityLog.action, ActivityLog.status)
                .order_by(ActivityLog.action, ActivityLog.status)
            )
            rows = (await session.execute(stmt)).all()

            ds_stmt = select(func.count()).select_from(ChatDialogState)
            ds_count = (await session.execute(ds_stmt)).scalar() or 0

        counts = [
            {"action": r.action, "status": r.status, "count": int(r.n)} for r in rows
        ]
        return {
            "since_hours": hours,
            "since_ts": cutoff.isoformat(),
            "by_action_status": counts,
            "total_events": sum(c["count"] for c in counts),
            "dialog_state_rows": int(ds_count),
        }

    @app.post("/pause")
    async def pause() -> dict:
        """Flip the in-process kill-switch OFF.

        State is in-process only — a container restart resets to the
        ``MESSENGER_BOT_ENABLED`` env var. Persisting to ``system_settings``
        is intentionally deferred (TZ §6).
        """
        new_state = kill_switch_mod.pause()
        log.info("messenger_bot.kill_switch.paused", bot_enabled=new_state)
        return {"bot_enabled": new_state}

    @app.post("/resume")
    async def resume() -> dict:
        """Flip the in-process kill-switch ON. Same persistence caveat as /pause."""
        new_state = kill_switch_mod.resume()
        log.info("messenger_bot.kill_switch.resumed", bot_enabled=new_state)
        return {"bot_enabled": new_state}

    return app


app = create_app()
