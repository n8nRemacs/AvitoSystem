"""Tiny FastAPI for manual triggers / dev introspection.

NOTE: these endpoints have **no authentication** and are for in-cluster use only
(this includes scenarios E and F added in Stage 4). Add an auth dependency
before exposing this port outside the docker network.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import HealthCheck
from app.services.health_checker.alerts import send_alert
from app.services.health_checker.runner import (
    LAST_RUNS,
    run_all_once,
    run_named_once,
)
from app.services.health_checker.scenarios import REGISTRY

log = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="avito-monitor health-checker", version="0.1.0")
    started_at = time.monotonic()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "service": "health-checker",
            "uptime_sec": int(time.monotonic() - started_at),
            "last_runs": {
                name: ts.isoformat() if isinstance(ts, datetime) else None
                for name, ts in LAST_RUNS.items()
            },
            "scenarios": sorted(REGISTRY.keys()),
        }

    @app.post("/run-all")
    async def run_all() -> dict:
        results = await run_all_once()
        return {"results": [r.to_dict() for r in results]}

    @app.post("/run/{scenario}")
    async def run_one(scenario: str) -> dict:
        try:
            result = await run_named_once(scenario)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return result.to_dict()

    @app.post("/alerts/test")
    async def alerts_test() -> dict:
        """Send a synthetic Telegram alert. Used for manual smoke-tests.

        Short-circuits with ``sent=false`` when the bot token or
        ``TELEGRAM_ALLOWED_USER_IDS`` is empty, so the user can verify wiring
        before configuring the chat id.
        """
        s = get_settings()
        token = (s.telegram_bot_token or "").strip()
        chat_ids = (s.telegram_allowed_user_ids or "").strip()
        if not token:
            return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN is empty"}
        if not chat_ids:
            return {"sent": False, "reason": "TELEGRAM_ALLOWED_USER_IDS is empty"}
        text = (
            "\U0001F9EA Тест Telegram-алертов — `pong` от health-checker."
        )
        sent = await send_alert(text, settings=s)
        return {
            "sent": sent,
            "reason": None if sent else "telegram sendMessage failed (see logs)",
        }

    @app.get("/history")
    async def history(
        scenario: str | None = Query(default=None, max_length=4),
        limit: int = Query(default=20, ge=1, le=500),
    ) -> dict:
        sessionmaker = get_sessionmaker()
        stmt = select(HealthCheck).order_by(HealthCheck.ts.desc()).limit(limit)
        if scenario:
            stmt = (
                select(HealthCheck)
                .where(HealthCheck.scenario == scenario.upper())
                .order_by(HealthCheck.ts.desc())
                .limit(limit)
            )
        async with sessionmaker() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return {
            "rows": [
                {
                    "id": r.id,
                    "ts": r.ts.astimezone(UTC).isoformat() if r.ts else None,
                    "scenario": r.scenario,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "details": r.details,
                }
                for r in rows
            ],
            "count": len(rows),
        }

    return app


app = create_app()
