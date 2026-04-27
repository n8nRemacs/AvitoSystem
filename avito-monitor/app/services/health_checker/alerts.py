"""V2 reliability — Stage 8: lightweight Telegram alerts.

Behaviour (TZ §2 L5 + §6):

* After every ``persist_result`` the runner calls
  :func:`check_and_alert_after_persist`. If the last N rows for the just-persisted
  scenario are all ``fail``, fire a 🚨 alert. Subsequent fails for the same
  scenario are suppressed via an in-process sentinel until the scenario passes
  again, at which point a ✅ recovery alert is sent and the sentinel cleared.

* :func:`daily_summary_loop` sleeps until ``RELIABILITY_TG_ALERT_DAILY_SUMMARY_HOUR``
  in ``Europe/Moscow`` (the user's timezone — TZ default), then sends a Markdown
  summary of the last 24 h: per-scenario pass rate, total runs, p95 latency,
  failures and any service-unreachable events.

* :func:`send_alert` is a no-op when ``TELEGRAM_BOT_TOKEN`` or the parsed
  ``TELEGRAM_ALLOWED_USER_IDS`` (chat target) is missing. Errors are logged at
  WARNING and never raised — alerting must never break the runner.

Public surface (also used by tests + ``api.py``):

* :func:`send_alert(text) -> bool`
* :func:`check_and_alert_after_persist(result) -> None`
* :func:`build_daily_summary_text(rows) -> str`  (pure)
* :func:`daily_summary_loop() -> None`
* :data:`FIRED_SENTINELS`  (in-process dict, exported for tests)
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db.base import get_sessionmaker
from app.db.models import HealthCheck
from app.services.health_checker.scenarios import ScenarioResult

log = structlog.get_logger(__name__)


def _local_tz(settings: Settings | None = None) -> ZoneInfo:
    """Resolve the timezone the user wants alerts rendered in.

    Falls back to UTC if the configured ``timezone`` setting isn't a valid
    IANA name (so a typo never crashes the alerter).
    """
    s = settings or get_settings()
    try:
        return ZoneInfo(s.timezone)
    except Exception:  # pragma: no cover — defensive
        return ZoneInfo("UTC")


def _tz_short_label(tz: ZoneInfo, ref: datetime | None = None) -> str:
    """Return a short label like 'MSK' or '+04' for the configured timezone."""
    when = ref or datetime.now(UTC)
    try:
        return when.astimezone(tz).strftime("%Z") or str(tz)
    except Exception:  # pragma: no cover
        return str(tz)

# In-process sentinel: scenario letter → ts when the fire alert was sent.
# Used to suppress repeat fires until a recovery passes.
FIRED_SENTINELS: dict[str, datetime] = {}


def _chat_id(settings: Settings) -> str | None:
    """Resolve the first id from the comma-separated allow-list, else None."""
    raw = (settings.telegram_allowed_user_ids or "").strip()
    if not raw:
        return None
    first = raw.split(",")[0].strip()
    return first or None


async def send_alert(
    text: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """POST text to ``sendMessage``. No-op when token or chat id missing.

    Returns True on a 2xx, False otherwise (including no-op short-circuits).
    Never raises.
    """
    s = settings or get_settings()
    token = (s.telegram_bot_token or "").strip()
    chat_id = _chat_id(s)
    if not token:
        log.info("alerts.skip.no_token")
        return False
    if not chat_id:
        log.info("alerts.skip.no_chat_id")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    own_client = client is None
    if client is None:
        proxy = (s.telegram_proxy_url or "").strip() or None
        http = httpx.AsyncClient(timeout=10.0, proxy=proxy)
    else:
        http = client
    try:
        resp = await http.post(url, json=payload)
        if resp.status_code >= 400:
            log.warning(
                "alerts.send.http_error",
                status_code=resp.status_code,
                body=resp.text[:200],
            )
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("alerts.send.transport_error", error=f"{type(exc).__name__}: {exc}")
        return False
    except Exception as exc:  # never let alerting bubble up
        log.warning("alerts.send.unexpected_error", error=f"{type(exc).__name__}: {exc}")
        return False
    finally:
        if own_client:
            await http.aclose()


async def _fetch_recent(
    scenario: str, limit: int
) -> list[HealthCheck]:
    """Most-recent ``limit`` rows for ``scenario``, newest first."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(HealthCheck)
            .where(HealthCheck.scenario == scenario)
            .order_by(HealthCheck.ts.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


def _format_fire_text(
    scenario: str, recent: Sequence[HealthCheck], threshold: int
) -> str:
    latest = recent[0] if recent else None
    reason = ""
    if latest and latest.details:
        for key in ("reason", "error", "detail"):
            v = latest.details.get(key)
            if v:
                reason = str(v)
                break
    tz = _local_tz()
    label = _tz_short_label(tz)
    timestamps = " · ".join(
        (r.ts.astimezone(tz).strftime("%H:%M:%S") if r.ts else "?") for r in recent
    )
    lines = [
        f"\U0001F6A8 *Сбой проверки* — сценарий `{scenario}`",
        f"{threshold} подряд результата `fail`.",
    ]
    if reason:
        lines.append(f"Причина: `{reason[:300]}`")
    lines.append(f"Последние {len(recent)} временных меток ({label}): {timestamps}")
    return "\n".join(lines)


def _format_recovery_text(scenario: str, latest: HealthCheck) -> str:
    latency = latest.latency_ms if latest and latest.latency_ms is not None else "?"
    tz = _local_tz()
    label = _tz_short_label(tz)
    ts = (
        latest.ts.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S " + label)
        if latest and latest.ts
        else "?"
    )
    return (
        f"✅ *Сценарий восстановлен* — `{scenario}`\n"
        f"`pass` в {ts}, latency {latency} мс."
    )


async def check_and_alert_after_persist(
    result: ScenarioResult,
    *,
    settings: Settings | None = None,
) -> None:
    """Inspect the most recent ``threshold`` rows for ``result.scenario``.

    Fires when all N are ``fail`` (suppressed by ``FIRED_SENTINELS``).
    Recovers when the just-persisted row is ``pass`` and a sentinel exists.
    """
    s = settings or get_settings()
    if not s.reliability_tg_alert_enabled:
        return

    threshold = max(1, int(s.reliability_tg_alert_fail_threshold))
    scenario = result.scenario

    if result.status == "pass":
        if scenario in FIRED_SENTINELS:
            FIRED_SENTINELS.pop(scenario, None)
            recent = await _fetch_recent(scenario, 1)
            latest = recent[0] if recent else None
            if latest is not None:
                await send_alert(
                    _format_recovery_text(scenario, latest), settings=s
                )
        return

    if result.status != "fail":
        # ``skip`` or anything else is neither a fire nor a recovery trigger.
        return

    if scenario in FIRED_SENTINELS:
        # Already alerted; wait for a pass before re-arming.
        return

    recent = await _fetch_recent(scenario, threshold)
    if len(recent) < threshold:
        return
    if not all(r.status == "fail" for r in recent):
        return

    text = _format_fire_text(scenario, recent, threshold)
    sent = await send_alert(text, settings=s)
    # Set sentinel even on send failure — avoids hammering on a broken bot.
    FIRED_SENTINELS[scenario] = datetime.now(UTC)
    log.info(
        "alerts.fired",
        scenario=scenario,
        threshold=threshold,
        sent=sent,
    )


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------


def _percentile(values: Sequence[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = max(0, min(len(s) - 1, round((p / 100.0) * (len(s) - 1))))
    return s[k]


def build_daily_summary_text(
    rows: Iterable[HealthCheck],
    *,
    window_hours: int = 24,
    now: datetime | None = None,
) -> str:
    """Pure formatter — keep DB-free for unit tests."""
    rows = list(rows)
    end = now or datetime.now(UTC)
    start = end - timedelta(hours=window_hours)

    by_scenario: dict[str, list[HealthCheck]] = defaultdict(list)
    unreachable_events: list[tuple[str, datetime, str]] = []
    for r in rows:
        if r.ts and r.ts < start:
            continue
        by_scenario[r.scenario].append(r)
        details = r.details or {}
        err = (details.get("error") or "") if isinstance(details, dict) else ""
        if r.status == "fail" and isinstance(err, str) and (
            "unreachable" in err.lower()
            or "ConnectError" in err
            or "TimeoutException" in err
        ):
            unreachable_events.append((r.scenario, r.ts or end, err[:120]))

    tz = _local_tz()
    label = _tz_short_label(tz, end)
    start_local = start.astimezone(tz)
    end_local = end.astimezone(tz)
    lines = [
        f"\U0001F4CA *Сводка надёжности за {window_hours} ч*",
        f"_{start_local.strftime('%Y-%m-%d %H:%M')} → {end_local.strftime('%Y-%m-%d %H:%M')} {label}_",
        "",
        "```",
        f"{'сц':<3} {'всего':>6} {'pass%':>6} {'fail':>5} {'p95мс':>7}",
    ]
    for scenario in sorted(by_scenario.keys()):
        runs = by_scenario[scenario]
        total = len(runs)
        passed = sum(1 for r in runs if r.status == "pass")
        failed = sum(1 for r in runs if r.status == "fail")
        latencies = [r.latency_ms for r in runs if r.latency_ms is not None]
        p95 = _percentile(latencies, 95) if latencies else None
        pct = (100.0 * passed / total) if total else 0.0
        lines.append(
            f"{scenario:<3} {total:>5d} {pct:>5.1f}% {failed:>5d} "
            f"{(p95 if p95 is not None else 0):>7d}"
        )
    if not by_scenario:
        lines.append("(данных нет)")
    lines.append("```")

    if unreachable_events:
        lines.append("")
        lines.append("*События недоступности сервисов:*")
        for scenario, ts, err in unreachable_events[:10]:
            ts_s = ts.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- `{scenario}` @ {ts_s} {label} — {err}")
        if len(unreachable_events) > 10:
            lines.append(f"... и ещё {len(unreachable_events) - 10}")
    else:
        lines.append("")
        lines.append("_Сервисы доступны весь период._")

    return "\n".join(lines)


async def _load_summary_rows(window_hours: int) -> list[HealthCheck]:
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(HealthCheck)
            .where(HealthCheck.ts >= cutoff)
            .order_by(HealthCheck.ts.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


def _seconds_until_next(hour: int, tz_name: str) -> float:
    """Compute seconds until the next ``HH:00`` in ``tz_name`` (Europe/Moscow)."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = datetime.now(tz)
    target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now_local:
        target = target + timedelta(days=1)
    return max(1.0, (target - now_local).total_seconds())


async def daily_summary_loop(settings: Settings | None = None) -> None:
    """Forever-loop: sleep until next 09:00 MSK, send summary, repeat.

    ``RELIABILITY_TG_ALERT_ENABLED=false`` short-circuits the send while the
    loop keeps sleeping — this matches the rest of the reliability stack.
    """
    s = settings or get_settings()
    hour = int(s.reliability_tg_alert_daily_summary_hour)
    tz_name = s.timezone or "Europe/Moscow"
    log.info(
        "alerts.daily_summary.scheduled", hour_local=hour, timezone=tz_name
    )
    while True:
        delay = _seconds_until_next(hour, tz_name)
        log.info("alerts.daily_summary.sleeping", seconds=int(delay))
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

        try:
            if not s.reliability_tg_alert_enabled:
                log.info("alerts.daily_summary.disabled")
                continue
            rows = await _load_summary_rows(window_hours=24)
            text = build_daily_summary_text(rows, window_hours=24)
            await send_alert(text, settings=s)
        except Exception:  # never crash the loop
            log.exception("alerts.daily_summary.tick_failed")


__all__ = [
    "FIRED_SENTINELS",
    "build_daily_summary_text",
    "check_and_alert_after_persist",
    "daily_summary_loop",
    "send_alert",
]
