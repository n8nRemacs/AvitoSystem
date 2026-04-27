"""Aggregated reliability snapshot — V2 Messenger Reliability §2 L5 / Stage 7.

Exposes ``GET /api/v1/health/full`` with the latest per-scenario status from
the ``health_checks`` table plus a fan-out ping to every sidecar's ``/healthz``.

This is consumed by:

* the ``/reliability`` web page (auto-refresh every 30 s),
* the AvitoSessionManager APK on the user's phone (status banner),
* any external monitor (e.g. uptime-kuma).

Auth: re-uses the same ``require_user`` dependency the rest of the dashboard
uses — same session cookie, same gate. The endpoint is exposed under ``app``
(port 8000) only; sidecar ports stay docker-internal.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HealthCheck, User
from app.deps import db_session, require_user

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["reliability"])


# ---------------------------------------------------------------------------
# Configuration — sidecar URLs.
#
# Inside docker-compose the services see each other by name. From the host
# (and from the few unit tests that hit this aggregator) we fall back to
# localhost:port. The env-vars below let docker override per-service URL.
# ---------------------------------------------------------------------------

_DEFAULT_SERVICES: dict[str, dict[str, str]] = {
    "health-checker": {
        "url": "http://health-checker:9100/healthz",
        "fallback": "http://localhost:9100/healthz",
    },
    "messenger-bot": {
        "url": "http://messenger-bot:9102/healthz",
        "fallback": "http://localhost:9102/healthz",
    },
    "activity-simulator": {
        "url": "http://activity-simulator:9101/healthz",
        "fallback": "http://localhost:9101/healthz",
    },
    "avito-mcp": {
        "url": "http://avito-mcp:9000/healthz",
        "fallback": "http://localhost:9000/healthz",
    },
    "xapi": {
        "url": "",  # filled at runtime from settings
        "fallback": "",
    },
}

_SERVICE_TIMEOUT_SEC = 2.0


def _resolve_service_urls() -> dict[str, str]:
    """Pick the right healthcheck URL for each sidecar.

    Order of precedence per service:

    1. ``RELIABILITY_<SERVICE>_HEALTH_URL`` env var if set;
    2. The compose-internal hostname (``http://health-checker:9100/healthz``);
    3. The localhost fallback (only used by host-side dev / tests).

    For ``xapi`` we use the project-level ``AVITO_XAPI_URL`` setting and append
    ``/health`` (not ``/healthz`` — xapi exposes the legacy path).
    """
    from app.config import get_settings

    settings = get_settings()
    out: dict[str, str] = {}
    for name, cfg in _DEFAULT_SERVICES.items():
        env_key = f"RELIABILITY_{name.upper().replace('-', '_')}_HEALTH_URL"
        override = os.getenv(env_key)
        if override:
            out[name] = override
            continue
        if name == "xapi":
            out[name] = f"{settings.avito_xapi_url.rstrip('/')}/health"
            continue
        # In tests / dev outside docker we use the localhost fallback.
        out[name] = cfg["url"] or cfg["fallback"]
    return out


# ---------------------------------------------------------------------------
# Latest scenario rows.
# ---------------------------------------------------------------------------

# Friendly names per scenario letter (kept in sync with TZ §2 L4).
SCENARIO_LABELS: dict[str, str] = {
    "A": "Token freshness",
    "B": "Token rotation",
    "C": "WS connection alive",
    "D": "WS round-trip getUnreadCount",
    "E": "SSE bridge / push",
    "F": "Messenger HTTP send",
    "G": "Bot template + dedup",
}


def _summarise_details(scenario: str, details: dict[str, Any] | None) -> str | None:
    """Pick one short, human-readable highlight from a scenario's details JSON.

    The scenarios store rich diagnostic info; here we just pull the most useful
    bit per scenario so the dashboard card stays one line long.
    """
    if not isinstance(details, dict):
        return None
    if scenario == "A":
        h = details.get("hours_left")
        if isinstance(h, (int, float)):
            return f"TTL {h:.1f}h"
    if scenario == "B":
        n = details.get("rotations_24h")
        if isinstance(n, int):
            return f"{n} rot/24h"
    if scenario in {"C", "D", "F"}:
        if details.get("status_code") is not None:
            return f"HTTP {details['status_code']}"
    if scenario == "E":
        rtt = details.get("round_trip_ms") or details.get("rtt_ms")
        if isinstance(rtt, (int, float)):
            return f"RTT {int(rtt)} ms"
    if scenario == "G":
        replies = details.get("replies")
        if isinstance(replies, int):
            return f"{replies} replies"
    # Generic fallbacks — pick reason or error.
    if details.get("reason"):
        return str(details["reason"])[:60]
    if details.get("error"):
        return str(details["error"])[:60]
    return None


async def _fetch_latest_scenarios(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """One row per scenario, picking the most recent ``ts``.

    Uses Postgres ``DISTINCT ON`` (the deployed DB) but stays compatible with
    SQLite by sorting in Python — important because some unit tests stand up an
    in-memory SQLite-style fake.
    """
    stmt = select(HealthCheck).order_by(HealthCheck.scenario, HealthCheck.ts.desc())
    rows = (await session.execute(stmt)).scalars().all()

    seen: dict[str, HealthCheck] = {}
    for row in rows:
        if row.scenario not in seen:
            seen[row.scenario] = row

    out: dict[str, dict[str, Any]] = {}
    for letter in SCENARIO_LABELS:
        row = seen.get(letter)
        if row is None:
            out[letter] = {
                "status": "unknown",
                "label": SCENARIO_LABELS[letter],
                "latency_ms": None,
                "ts": None,
                "details_summary": None,
                "details": None,
            }
            continue
        out[letter] = {
            "status": row.status,
            "label": SCENARIO_LABELS[letter],
            "latency_ms": row.latency_ms,
            "ts": row.ts.astimezone(UTC).isoformat() if row.ts else None,
            "details_summary": _summarise_details(letter, row.details),
            "details": row.details,
        }
    return out


# ---------------------------------------------------------------------------
# Sidecar /healthz fan-out.
# ---------------------------------------------------------------------------


async def _ping_one(client: httpx.AsyncClient, name: str, url: str) -> dict[str, Any]:
    """Call a single sidecar /healthz; never raise. Returns a dict ready to merge."""
    if not url:
        return {"reachable": False, "error": "no url configured"}
    try:
        resp = await client.get(url, timeout=_SERVICE_TIMEOUT_SEC)
        if resp.status_code >= 400:
            return {
                "reachable": False,
                "status_code": resp.status_code,
                "error": f"HTTP {resp.status_code}",
                "url": url,
            }
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:200]}
        if not isinstance(body, dict):
            body = {"raw": str(body)[:200]}
        return {"reachable": True, "url": url, **body}
    except httpx.HTTPError as exc:
        return {
            "reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
        }


async def _fetch_services() -> dict[str, dict[str, Any]]:
    """Fan out to every sidecar in parallel, 2s timeout each."""
    urls = _resolve_service_urls()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_ping_one(client, name, url) for name, url in urls.items()]
        )
    return dict(zip(urls.keys(), results, strict=True))


# ---------------------------------------------------------------------------
# Summary helper.
# ---------------------------------------------------------------------------


def _build_summary(
    scenarios: dict[str, dict[str, Any]],
    services: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fail_scenarios = sorted(
        letter for letter, row in scenarios.items() if row.get("status") == "fail"
    )
    unknown_scenarios = sorted(
        letter for letter, row in scenarios.items() if row.get("status") == "unknown"
    )
    unreachable_services = sorted(
        name for name, payload in services.items() if not payload.get("reachable")
    )
    warnings: list[str] = []
    for letter in unknown_scenarios:
        warnings.append(f"scenario {letter} has never run yet")
    for name in unreachable_services:
        err = services[name].get("error") or "unreachable"
        warnings.append(f"service {name}: {err}")
    return {
        "all_green": not fail_scenarios and not unreachable_services,
        "fail_scenarios": fail_scenarios,
        "unreachable_services": unreachable_services,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Route.
# ---------------------------------------------------------------------------


@router.get("/full")
async def health_full(
    _user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> dict[str, Any]:
    """Return the aggregated reliability snapshot.

    See module docstring for the response shape — schema-stable for
    the AvitoSessionManager APK.
    """
    scenarios = await _fetch_latest_scenarios(session)
    services = await _fetch_services()
    summary = _build_summary(scenarios, services)
    return {
        "ts": datetime.now(UTC).isoformat(),
        "scenarios": scenarios,
        "services": services,
        "summary": summary,
    }


@router.get("/scenario/{letter}")
async def scenario_history(
    letter: str,
    _user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    limit: int = 10,
) -> dict[str, Any]:
    """Last N rows for one scenario — feeds the per-card "expand" UX."""
    key = letter.upper()
    if key not in SCENARIO_LABELS:
        return {"scenario": key, "label": None, "rows": [], "error": "unknown scenario"}
    capped = max(1, min(limit, 50))
    stmt = (
        select(HealthCheck)
        .where(HealthCheck.scenario == key)
        .order_by(HealthCheck.ts.desc())
        .limit(capped)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "scenario": key,
        "label": SCENARIO_LABELS[key],
        "rows": [
            {
                "id": r.id,
                "ts": r.ts.astimezone(UTC).isoformat() if r.ts else None,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "details": r.details,
            }
            for r in rows
        ],
    }
