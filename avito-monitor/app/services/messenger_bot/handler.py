"""Core reply pipeline + activity_log writer.

One public entry point: :func:`handle_event`. Everything else here is
implementation detail. The pipeline is intentionally linear and explicit so
the verdict reasons map 1:1 onto TZ §8 acceptance gates ("0 double-replies").
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import Settings, get_settings
from app.db.base import get_sessionmaker
from app.db.models import ActivityLog
from app.services.health_checker.sse_client import SseEvent
from app.services.health_checker.xapi_client import XapiClient
from app.services.messenger_bot.dedup import (
    already_replied,
    ensure_chat_row,
    operator_already_replied,
    record_dialog_state,
    record_outgoing_message,
)
from app.services.messenger_bot.kill_switch import bot_enabled
from app.services.messenger_bot.rate_limit import (
    is_channel_rate_limited,
    is_globally_rate_limited,
)
from app.services.messenger_bot.whitelist import (
    fetch_item_id_for_channel,
    fetch_own_user_id,
    is_my_listing,
)

log = structlog.get_logger(__name__)


# Module-level event counters for the /healthz sidecar.
TOTAL_EVENTS: int = 0
TOTAL_REPLIES: int = 0
LAST_EVENT_TS: datetime | None = None


def _bump_event() -> None:
    global TOTAL_EVENTS, LAST_EVENT_TS
    TOTAL_EVENTS += 1
    LAST_EVENT_TS = datetime.now(UTC)


def _bump_reply() -> None:
    global TOTAL_REPLIES
    TOTAL_REPLIES += 1


def reset_counters_for_tests() -> None:
    """Reset module-level counters; used by unit tests only."""
    global TOTAL_EVENTS, TOTAL_REPLIES, LAST_EVENT_TS
    TOTAL_EVENTS = 0
    TOTAL_REPLIES = 0
    LAST_EVENT_TS = None


@dataclass
class HandlerVerdict:
    """Structured outcome of one ``handle_event`` invocation."""

    action: str  # 'sent' | 'skipped' | 'ignored' | 'send_failed' | 'error'
    reason: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "details": self.details,
        }


async def _persist_activity(
    *,
    action: str,
    target: str | None,
    status: str,
    details: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> None:
    """Insert a row into ``activity_log`` with ``source='bot'``. Never raises."""
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            row = ActivityLog(
                source="bot",
                action=action,
                target=target,
                status=status,
                latency_ms=latency_ms,
                details=details or None,
            )
            session.add(row)
            await session.commit()
    except Exception:  # pragma: no cover — defensive
        log.exception("messenger_bot.activity_log.persist_failed", action=action)


def _extract_channel_id(payload: dict[str, Any]) -> str | None:
    """Pull the channel_id out of the ws_manager-normalised payload.

    xapi WsManager normalises ``messenger.newMessage`` into
    ``{event: 'new_message', payload: {channel_id, message_id, author_id, text, ...}}``.
    We accept ``channelId`` too as a fallback for any future shape drift.
    """
    if not isinstance(payload, dict):
        return None
    cid = payload.get("channel_id") or payload.get("channelId")
    if isinstance(cid, str) and cid:
        return cid
    return None


# Avito channel ids are of the form ``u2i-<random>`` or ``u2u-<random>``. The
# alphabet observed in the wild includes A-Z a-z 0-9 plus ~_- separators.
_AVITO_CHANNEL_RE = re.compile(r"u2[iu]-[A-Za-z0-9~_\-]+")


def _extract_channel_id_from_notification(payload: dict[str, Any]) -> str | None:
    """Best-effort recovery of an Avito channel_id from an Android notification.

    Avito's mobile app does not consistently expose the channel id in any
    single notification field — it lives in the click PendingIntent extras
    which are not always reflected in EXTRA_TEXT. We scan every string-ish
    field with a permissive regex and return the first match, falling back
    to ``None`` so the caller can decide what to do (log + skip, or trigger
    a catch-up REST poll).
    """
    if not isinstance(payload, dict):
        return None
    candidates: list[str] = []
    for key in ("tag", "sub_text", "body", "title", "big_text"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    extras = payload.get("extras")
    if isinstance(extras, dict):
        for value in extras.values():
            if isinstance(value, str) and value:
                candidates.append(value)
    for candidate in candidates:
        match = _AVITO_CHANNEL_RE.search(candidate)
        if match:
            return match.group(0)
    return None


def _split_sender_prefix(body: str) -> tuple[str, str]:
    """Parse ``"Имя: текст"`` → ``("Имя", "текст")``. No colon → ``("", body)``."""
    if ":" not in body:
        return "", body.strip()
    sender, _, text = body.partition(":")
    return sender.strip(), text.strip()


async def _resolve_channel_via_xapi(
    payload: dict[str, Any], client: XapiClient
) -> str | None:
    """Server-side fallback used when the in-payload regex finds no u2i.

    Avito's mobile app stores the chat id inside the click PendingIntent
    rather than EXTRA_TEXT, so a plain NotificationListener never sees it.
    Instead we ask xapi for unread channels and try to single one out by
    matching ``last_message_text`` against the notification body.

    Returns ``None`` whenever the match is empty or ambiguous — the caller
    must skip rather than reply to the wrong channel.
    """
    body_raw = payload.get("body") or payload.get("big_text") or ""
    if not isinstance(body_raw, str) or not body_raw.strip():
        return None
    sender, expected_text = _split_sender_prefix(body_raw)
    if not expected_text:
        return None

    call = await client.get("/api/v1/messenger/channels", params={"limit": 10})
    if not call.ok or not isinstance(call.body, dict):
        return None
    channels = call.body.get("channels") or []
    if not isinstance(channels, list):
        return None

    text_matches: list[dict[str, Any]] = []
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        # NB: we deliberately do NOT filter by unread_count. A push notification
        # is the trigger here, and Avito sometimes reports unread_count=0 even
        # when a brand-new message has just landed (e.g. user already saw the
        # heads-up popup, or another client read it microseconds ago). The
        # downstream ``already_replied`` / ``operator_already_replied`` gates
        # already prevent duplicate replies, so a wider net is safe.
        last_text = str(ch.get("last_message_text") or "").strip()
        if last_text == expected_text:
            text_matches.append(ch)

    def _id_or_none(ch: dict[str, Any]) -> str | None:
        cid = ch.get("id")
        return cid if isinstance(cid, str) and cid else None

    if len(text_matches) == 1:
        return _id_or_none(text_matches[0])

    if len(text_matches) > 1 and sender:
        narrowed = [
            ch for ch in text_matches
            if str(ch.get("contact_name") or "").strip() == sender
        ]
        if len(narrowed) == 1:
            return _id_or_none(narrowed[0])

    return None


async def _synthesize_new_message_from_notification(
    event: SseEvent, client: XapiClient
) -> SseEvent | None:
    """Convert a ``notification_intercepted`` SSE event into a synthetic
    ``new_message`` event, or return ``None`` if no channel id can be derived.

    The synthesised event re-uses the existing reply pipeline (dedup,
    whitelist, rate-limit, send) so the bot reacts to a phone notification
    the same way it reacts to a live WS push.

    Two-step extraction:

    1. Permissive regex over notification text/extras (cheap, no network).
    2. xapi ``/messenger/channels`` lookup that matches ``last_message_text``
       against the body — required because Avito hides the chat id inside
       the PendingIntent extras of the notification.
    """
    payload = event.data.get("payload") if isinstance(event.data, dict) else None
    if not isinstance(payload, dict):
        return None
    extraction_source = "regex"
    channel_id = _extract_channel_id_from_notification(payload)
    if not channel_id:
        channel_id = await _resolve_channel_via_xapi(payload, client)
        if not channel_id:
            return None
        extraction_source = "xapi_fallback"
    synthetic_payload = {
        "channel_id": channel_id,
        "text": payload.get("body") or payload.get("big_text") or "",
        "_via_notification": True,
        "_notification_title": payload.get("title"),
        "_notification_db_id": payload.get("db_id"),
        "_extraction_source": extraction_source,
    }
    return SseEvent(
        event_name="new_message",
        data={"event": "new_message", "payload": synthetic_payload},
        raw_data=event.raw_data,
    )


def _extract_author_id(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    aid = payload.get("author_id") or payload.get("authorId") or payload.get("fromUid")
    if isinstance(aid, (str, int)) and str(aid):
        return str(aid)
    return None


async def _send_template(
    channel_id: str,
    template: str,
    *,
    client: XapiClient,
    dry_run: bool,
) -> tuple[bool, str | None, str | None, int | None, int | None]:
    """Wrap the xapi ``POST /messenger/channels/{id}/messages`` call.

    Returns ``(ok, message_id, error, status_code, latency_ms)``. In ``dry_run``
    mode the upstream call is skipped and a synthetic message_id is returned;
    everything else (dedup, persist, rate-limit) still runs so scenario G can
    exercise the real DB plumbing.
    """
    if dry_run:
        return True, f"dry-run-{uuid.uuid4().hex[:12]}", None, None, 0

    call = await client.post(
        f"/api/v1/messenger/channels/{channel_id}/messages",
        json_body={"text": template},
    )
    if not call.ok:
        return False, None, call.error, call.status_code, call.latency_ms

    # xapi shape: {"status": "ok", "result": {...avito message obj...}}
    body = call.body if isinstance(call.body, dict) else {}
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    msg_id = (
        result.get("id")
        or result.get("messageId")
        or body.get("id")
        or f"sent-{uuid.uuid4().hex[:12]}"  # last resort: synthetic id
    )
    return True, str(msg_id), None, call.status_code, call.latency_ms


async def handle_event(
    event: SseEvent,
    *,
    client: XapiClient,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> HandlerVerdict:
    """One inbound SSE event → one verdict.

    The pipeline mirrors TZ §1 / §2 L4 scenario G acceptance:

    1. Skip non-``new_message`` events.
    2. Pull ``channel_id`` from the payload; bail if missing.
    3. Kill-switch / rate-limit gates (cheap, in-memory + DB).
    4. Dedup gate via ``chat_dialog_state`` (DB).
    5. Operator-already-replied gate via ``messenger_messages`` (DB).
    6. Whitelist gate (best-effort; default-allow on ``unknown``).
    7. Send template; on success persist dialog_state + outgoing message.

    Every branch writes to ``activity_log`` for observability.
    """
    settings = settings or get_settings()
    _bump_event()

    # V2.1: phone NotificationListener forwards Android notifications via xapi
    # → SSE event ``notification_intercepted``. Try to derive a channel_id and
    # then fall through to the standard new_message pipeline. If extraction
    # fails the event is logged for later analysis and the bot stays silent —
    # we never want to reply to the wrong channel based on a guess.
    if event.event_name == "notification_intercepted":
        synthetic = await _synthesize_new_message_from_notification(event, client)
        notification_payload = (
            event.data.get("payload") if isinstance(event.data, dict) else None
        ) or {}
        if synthetic is None:
            verdict = HandlerVerdict(
                action="ignored",
                reason="notification without extractable channel_id",
                details={
                    "title": notification_payload.get("title"),
                    "body": notification_payload.get("body"),
                    "tag": notification_payload.get("tag"),
                    "package": notification_payload.get("package_name"),
                    "db_id": notification_payload.get("db_id"),
                },
            )
            await _persist_activity(
                action="notification", target=None, status="ok", details=verdict.to_dict()
            )
            return verdict
        log.info(
            "messenger_bot.notification.channel_extracted",
            channel_id=synthetic.data["payload"]["channel_id"],
            db_id=notification_payload.get("db_id"),
            title=notification_payload.get("title"),
            source=synthetic.data["payload"].get("_extraction_source"),
        )
        event = synthetic  # fall through to the regular new_message pipeline

    if event.event_name != "new_message":
        verdict = HandlerVerdict(
            action="ignored", reason=f"event_type={event.event_name}"
        )
        await _persist_activity(action="reply", target=None, status="ok", details=verdict.to_dict())
        return verdict

    payload = event.data.get("payload") if isinstance(event.data, dict) else None
    if not isinstance(payload, dict):
        payload = event.data if isinstance(event.data, dict) else {}

    channel_id = _extract_channel_id(payload)
    if not channel_id:
        verdict = HandlerVerdict(action="ignored", reason="no channel_id in payload")
        await _persist_activity(
            action="reply", target=None, status="error", details=verdict.to_dict()
        )
        return verdict

    # Author = self? Avito echoes our own outgoing messages on WS too. We rely
    # on operator_already_replied for the durable check, but skipping the
    # echo here saves an unnecessary xapi round-trip.
    author_id = _extract_author_id(payload)
    own_user_id_str = (
        str(settings.avito_own_user_id) if settings.avito_own_user_id is not None else None
    )
    if author_id is not None and own_user_id_str is not None and author_id == own_user_id_str:
        verdict = HandlerVerdict(
            action="skipped", reason="author is self (echoed outgoing)", channel_id=channel_id
        )
        await _persist_activity(
            action="reply", target=channel_id, status="ok", details=verdict.to_dict()
        )
        return verdict

    # 3. Kill-switch first (cheapest, in-process).
    if not bot_enabled():
        verdict = HandlerVerdict(
            action="skipped", reason="bot disabled (kill-switch)", channel_id=channel_id
        )
        await _persist_activity(
            action="reply", target=channel_id, status="ok", details=verdict.to_dict()
        )
        return verdict

    # 4. DB dedup gates BEFORE rate-limit gates so the second call to the same
    # channel reports the durable "already replied" reason rather than the
    # transient "per-channel cooldown" — this is what scenario G asserts.
    if await already_replied(channel_id):
        verdict = HandlerVerdict(
            action="skipped", reason="already replied (dialog_state)", channel_id=channel_id
        )
        await _persist_activity(
            action="reply", target=channel_id, status="ok", details=verdict.to_dict()
        )
        return verdict

    if await operator_already_replied(channel_id):
        verdict = HandlerVerdict(
            action="skipped",
            reason="operator outgoing message present (already replied manually)",
            channel_id=channel_id,
        )
        await _persist_activity(
            action="reply", target=channel_id, status="ok", details=verdict.to_dict()
        )
        return verdict

    # 5. Rate-limit gates (DB-backed, run after dedup).
    limited, used = await is_globally_rate_limited(settings)
    if limited:
        verdict = HandlerVerdict(
            action="skipped",
            reason="global rate limit",
            channel_id=channel_id,
            details={"used_last_hour": used, "limit": settings.messenger_bot_rate_limit_per_hour},
        )
        await _persist_activity(
            action="reply", target=channel_id, status="rate_limited", details=verdict.to_dict()
        )
        return verdict

    if await is_channel_rate_limited(channel_id, settings):
        verdict = HandlerVerdict(
            action="skipped",
            reason="per-channel cooldown",
            channel_id=channel_id,
            details={"cooldown_sec": settings.messenger_bot_per_channel_cooldown_sec},
        )
        await _persist_activity(
            action="reply", target=channel_id, status="rate_limited", details=verdict.to_dict()
        )
        return verdict

    # 6. Whitelist (best-effort; default-allow on unknown).
    item_id: int | None = None
    if settings.messenger_bot_whitelist_own_listings_only:
        item_id = await fetch_item_id_for_channel(channel_id, client)
        own_user_id = await fetch_own_user_id(client, settings)
        verdict_w = await is_my_listing(item_id, own_user_id, client)
        if verdict_w == "no":
            verdict = HandlerVerdict(
                action="skipped",
                reason="not my listing",
                channel_id=channel_id,
                details={"item_id": item_id, "own_user_id": own_user_id},
            )
            await _persist_activity(
                action="reply", target=channel_id, status="ok", details=verdict.to_dict()
            )
            return verdict
        if verdict_w == "unknown":
            log.info(
                "messenger_bot.whitelist.unknown_default_allow",
                channel_id=channel_id,
                item_id=item_id,
                own_user_id=own_user_id,
            )

    # 7. Make sure the FK target exists, then send.
    await ensure_chat_row(channel_id, item_id=item_id)

    template = settings.messenger_bot_template
    ok, message_id, error, status_code, latency_ms = await _send_template(
        channel_id, template, client=client, dry_run=dry_run
    )
    if not ok:
        verdict = HandlerVerdict(
            action="send_failed",
            reason=error or f"HTTP {status_code}",
            channel_id=channel_id,
            details={"status_code": status_code},
        )
        # Even on send failure, mark dialog_state so we don't loop forever.
        # Use 'no_action' so the row isn't claiming we replied.
        try:
            await record_dialog_state(
                channel_id,
                state="no_action",
                message_id=None,
                notes={"reason": "send_failed", "error": error, "status_code": status_code},
            )
        except Exception:  # pragma: no cover — defensive
            log.exception("messenger_bot.dialog_state.persist_failed", channel_id=channel_id)
        await _persist_activity(
            action="reply",
            target=channel_id,
            status="error",
            latency_ms=latency_ms,
            details=verdict.to_dict(),
        )
        return verdict

    # Success path.
    assert message_id is not None
    await record_outgoing_message(channel_id, message_id=message_id, text=template)
    await record_dialog_state(
        channel_id,
        state="replied_with_template",
        message_id=message_id,
        notes={"dry_run": dry_run, "template_chars": len(template)},
    )
    _bump_reply()

    verdict = HandlerVerdict(
        action="sent",
        channel_id=channel_id,
        message_id=message_id,
        details={"dry_run": dry_run, "status_code": status_code},
    )
    await _persist_activity(
        action="reply",
        target=channel_id,
        status="ok",
        latency_ms=latency_ms,
        details=verdict.to_dict(),
    )
    return verdict


async def handle_event_safe(
    event: SseEvent, *, client: XapiClient, settings: Settings | None = None
) -> HandlerVerdict:
    """``handle_event`` wrapper that never raises out of the runner loop."""
    try:
        return await handle_event(event, client=client, settings=settings)
    except Exception as exc:
        log.exception("messenger_bot.handle_event.crashed", event_name=event.event_name)
        verdict = HandlerVerdict(
            action="error",
            reason=f"{type(exc).__name__}: {exc}",
        )
        await _persist_activity(
            action="reply", target=None, status="error", details=verdict.to_dict()
        )
        return verdict
