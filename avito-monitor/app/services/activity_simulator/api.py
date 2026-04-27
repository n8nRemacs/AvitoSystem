"""Tiny FastAPI sidecar for the activity-simulator service.

NOTE: no auth — internal-only. Same convention as the health-checker sidecar.
Mount behind a private port; do NOT expose to the public internet.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import func, select

from app.db.base import get_sessionmaker
from app.db.models import ActivityLog
from app.services.activity_simulator import runner as runner_mod
from app.services.activity_simulator.actions import ACTIONS, ITEM_ID_CACHE

log = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="avito-monitor activity-simulator", version="0.1.0")
    started_at = time.monotonic()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "service": "activity-simulator",
            "uptime_sec": int(time.monotonic() - started_at),
            "last_action_ts": (
                runner_mod.LAST_ACTION_TS.isoformat()
                if runner_mod.LAST_ACTION_TS is not None
                else None
            ),
            "total_actions_today": runner_mod.TOTAL_ACTIONS_TODAY,
            "item_id_cache_size": len(ITEM_ID_CACHE),
            "actions": sorted(ACTIONS.keys()),
        }

    @app.post("/run-once")
    async def run_once(action: str | None = Query(default=None)) -> dict:
        try:
            if action is None:
                result = await runner_mod.run_random_once()
            else:
                result = await runner_mod.run_named_once(action)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return result.to_dict()

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
                .where(ActivityLog.source == "simulator")
                .where(ActivityLog.ts >= cutoff)
                .group_by(ActivityLog.action, ActivityLog.status)
                .order_by(ActivityLog.action, ActivityLog.status)
            )
            rows = (await session.execute(stmt)).all()
        counts = [
            {"action": r.action, "status": r.status, "count": int(r.n)}
            for r in rows
        ]
        return {
            "since_hours": hours,
            "since_ts": cutoff.isoformat(),
            "total": sum(c["count"] for c in counts),
            "by_action_status": counts,
        }

    return app


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


app = create_app()
