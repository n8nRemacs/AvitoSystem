"""Unit tests for the messenger-bot reply pipeline."""
from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.config import Settings
from app.services.health_checker.sse_client import SseEvent
from app.services.health_checker.xapi_client import XapiClient
from app.services.messenger_bot import dedup as dedup_mod
from app.services.messenger_bot import handler as handler_mod
from app.services.messenger_bot import kill_switch
from app.services.messenger_bot import rate_limit as rl_mod
from app.services.messenger_bot import whitelist as wl_mod
from app.services.messenger_bot.handler import handle_event, handle_event_safe

XAPI_BASE = "http://xapi.test"


def make_client() -> XapiClient:
    return XapiClient(base_url=XAPI_BASE, api_key="test-key")


def make_settings(**overrides) -> Settings:
    base = {
        "app_secret_key": "x" * 32,
        "database_url": "postgresql+asyncpg://t:t@localhost/t",
        "messenger_bot_enabled": True,
        "messenger_bot_template": "Hello, please wait.",
        "messenger_bot_rate_limit_per_hour": 60,
        "messenger_bot_per_channel_cooldown_sec": 60,
        "messenger_bot_whitelist_own_listings_only": True,
        "avito_own_user_id": 7,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _evt(payload: dict[str, Any] | None = None, *, event_name: str = "new_message") -> SseEvent:
    """Build an SseEvent. Pass an empty dict to test the no-channel-id branch."""
    if payload is None:
        payload = {"channel_id": "u2i-foo"}
    return SseEvent(
        event_name=event_name,
        data={"event": event_name, "payload": payload},
        raw_data="",
    )


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub every DB-touching helper with no-ops; tests override per scenario."""

    async def aok(*args, **kwargs):
        return None

    async def afalse(*args, **kwargs):
        return False

    async def aglobal_false(*args, **kwargs):
        return (False, 0)

    async def acount_zero():
        return 0

    monkeypatch.setattr(handler_mod, "already_replied", afalse)
    monkeypatch.setattr(handler_mod, "operator_already_replied", afalse)
    monkeypatch.setattr(handler_mod, "ensure_chat_row", aok)
    monkeypatch.setattr(handler_mod, "record_dialog_state", aok)
    monkeypatch.setattr(handler_mod, "record_outgoing_message", aok)
    monkeypatch.setattr(handler_mod, "is_globally_rate_limited", aglobal_false)

    async def channel_false(*args, **kwargs):
        return False

    monkeypatch.setattr(handler_mod, "is_channel_rate_limited", channel_false)

    async def whitelist_yes(*args, **kwargs):
        return "yes"

    monkeypatch.setattr(handler_mod, "is_my_listing", whitelist_yes)

    async def own_uid_seven(*args, **kwargs):
        return 7

    monkeypatch.setattr(handler_mod, "fetch_own_user_id", own_uid_seven)

    async def item_id_111(*args, **kwargs):
        return 111

    monkeypatch.setattr(handler_mod, "fetch_item_id_for_channel", item_id_111)

    # Avoid hitting the activity_log writer
    async def noop_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(handler_mod, "_persist_activity", noop_persist)


# ----------------------------------------------------------------------
# Event-type filter
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ignores_non_new_message_event(stub_pipeline):
    verdict = await handle_event(
        _evt(event_name="typing"), client=make_client(), settings=make_settings()
    )
    assert verdict.action == "ignored"
    assert verdict.reason and "typing" in verdict.reason


@pytest.mark.asyncio
async def test_ignores_event_without_channel_id(stub_pipeline):
    verdict = await handle_event(_evt(payload={}), client=make_client(), settings=make_settings())
    assert verdict.action == "ignored"
    assert verdict.reason == "no channel_id in payload"


# ----------------------------------------------------------------------
# Self-author skip
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_own_authored_echoes(stub_pipeline):
    """Avito echoes our outgoing on WS too — these must be skipped early."""
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x", "author_id": "7"}),
        client=make_client(),
        settings=make_settings(avito_own_user_id=7),
    )
    assert verdict.action == "skipped"
    assert verdict.reason and "self" in verdict.reason


# ----------------------------------------------------------------------
# Kill-switch
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kill_switch_off_skips(stub_pipeline, monkeypatch):
    kill_switch.pause()  # in-process override
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason and "kill-switch" in verdict.reason


# ----------------------------------------------------------------------
# Rate limits
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_global_rate_limit_skips(stub_pipeline, monkeypatch):
    async def limited(*args, **kwargs):
        return (True, 60)

    monkeypatch.setattr(handler_mod, "is_globally_rate_limited", limited)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason == "global rate limit"


@pytest.mark.asyncio
async def test_per_channel_cooldown_skips(stub_pipeline, monkeypatch):
    async def channel_limited(*args, **kwargs):
        return True

    monkeypatch.setattr(handler_mod, "is_channel_rate_limited", channel_limited)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason == "per-channel cooldown"


# ----------------------------------------------------------------------
# Dedup
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_when_already_replied(stub_pipeline, monkeypatch):
    async def yes(*args, **kwargs):
        return True

    monkeypatch.setattr(handler_mod, "already_replied", yes)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason and "already replied" in verdict.reason


@pytest.mark.asyncio
async def test_skips_when_operator_already_replied(stub_pipeline, monkeypatch):
    async def yes(*args, **kwargs):
        return True

    monkeypatch.setattr(handler_mod, "operator_already_replied", yes)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason and "operator" in verdict.reason


# ----------------------------------------------------------------------
# Whitelist
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_when_not_my_listing(stub_pipeline, monkeypatch):
    async def no(*args, **kwargs):
        return "no"

    monkeypatch.setattr(handler_mod, "is_my_listing", no)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason == "not my listing"


@pytest.mark.asyncio
async def test_default_allow_when_whitelist_unknown(stub_pipeline, monkeypatch):
    """``unknown`` verdict must NOT block — default-allow per TZ §6 caveat."""

    async def unknown(*args, **kwargs):
        return "unknown"

    monkeypatch.setattr(handler_mod, "is_my_listing", unknown)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
        dry_run=True,
    )
    assert verdict.action == "sent"


@pytest.mark.asyncio
async def test_whitelist_disabled_skips_lookup(stub_pipeline, monkeypatch):
    """When the flag is false, no ``is_my_listing`` call is made at all."""
    called = {"n": 0}

    async def tracker(*args, **kwargs):
        called["n"] += 1
        return "no"

    monkeypatch.setattr(handler_mod, "is_my_listing", tracker)
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(messenger_bot_whitelist_own_listings_only=False),
        dry_run=True,
    )
    assert verdict.action == "sent"
    assert called["n"] == 0


# ----------------------------------------------------------------------
# Send pathways
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_skips_xapi_post(stub_pipeline):
    """Dry-run must produce a 'sent' verdict with a synthetic message_id."""
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
        dry_run=True,
    )
    assert verdict.action == "sent"
    assert verdict.message_id is not None
    assert verdict.message_id.startswith("dry-run-")
    assert verdict.details["dry_run"] is True


@respx.mock
@pytest.mark.asyncio
async def test_real_send_returns_sent_with_message_id(stub_pipeline):
    """Non-dry-run hits the upstream POST; result.id propagates as message_id."""
    respx.post(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-x/messages").mock(
        return_value=httpx.Response(
            200, json={"status": "ok", "result": {"id": "real-msg-1"}}
        )
    )
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "sent"
    assert verdict.message_id == "real-msg-1"


@respx.mock
@pytest.mark.asyncio
async def test_send_failed_path(stub_pipeline):
    respx.post(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-x/messages").mock(
        return_value=httpx.Response(503, json={"detail": "boom"})
    )
    verdict = await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "send_failed"
    assert verdict.details["status_code"] == 503


# ----------------------------------------------------------------------
# Counter side effects
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handler_bumps_event_counter(stub_pipeline):
    assert handler_mod.TOTAL_EVENTS == 0
    await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
        dry_run=True,
    )
    assert handler_mod.TOTAL_EVENTS == 1
    assert handler_mod.TOTAL_REPLIES == 1


@pytest.mark.asyncio
async def test_handler_does_not_bump_reply_when_skipped(stub_pipeline, monkeypatch):
    async def yes(*args, **kwargs):
        return True

    monkeypatch.setattr(handler_mod, "already_replied", yes)
    await handle_event(
        _evt(payload={"channel_id": "u2i-x"}),
        client=make_client(),
        settings=make_settings(),
        dry_run=True,
    )
    assert handler_mod.TOTAL_EVENTS == 1
    assert handler_mod.TOTAL_REPLIES == 0


# ----------------------------------------------------------------------
# Safe wrapper
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_event_safe_swallows_exceptions(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("synthetic failure inside handler")

    monkeypatch.setattr(handler_mod, "handle_event", boom)

    async def noop_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(handler_mod, "_persist_activity", noop_persist)
    verdict = await handle_event_safe(_evt(), client=make_client())
    assert verdict.action == "error"
    assert "RuntimeError" in (verdict.reason or "")


# ----------------------------------------------------------------------
# V2.1: notification_intercepted → synthesised new_message
# ----------------------------------------------------------------------

def _notification_event(payload: dict[str, Any]) -> SseEvent:
    return SseEvent(
        event_name="notification_intercepted",
        data={"event": "notification_intercepted", "payload": payload},
        raw_data="",
    )


@pytest.mark.asyncio
async def test_extract_channel_id_from_notification_in_tag():
    """tag is the canonical place Avito sometimes parks the channel id."""
    cid = handler_mod._extract_channel_id_from_notification(
        {"tag": "u2i-AyuR1xA7zmtpIKN01uUfw", "title": "Иван", "body": "Готов?"}
    )
    assert cid == "u2i-AyuR1xA7zmtpIKN01uUfw"


@pytest.mark.asyncio
async def test_extract_channel_id_searches_other_text_fields():
    """If the id is buried in body/big_text we still find it."""
    cid = handler_mod._extract_channel_id_from_notification(
        {"title": "Иван", "body": "Перейти к чату u2i-XYZ123 от Ивана"}
    )
    assert cid == "u2i-XYZ123"


@pytest.mark.asyncio
async def test_extract_channel_id_returns_none_when_absent():
    cid = handler_mod._extract_channel_id_from_notification(
        {"title": "Иван", "body": "Здравствуйте, актуально?"}
    )
    assert cid is None


@pytest.mark.asyncio
async def test_extract_channel_id_scans_extras_dict():
    cid = handler_mod._extract_channel_id_from_notification(
        {"title": "Иван", "extras": {"intent_uri": "https://avito.ru/messenger/u2i-from-extras"}}
    )
    assert cid == "u2i-from-extras"


@pytest.mark.asyncio
async def test_notification_with_extractable_channel_id_drives_pipeline(
    stub_pipeline, monkeypatch
):
    """A notification carrying a u2i-* tag fans out into the normal send flow."""
    sent = []

    async def fake_send(channel_id, template, *, client, dry_run):
        sent.append((channel_id, template, dry_run))
        return True, "msg-1", None, 200, 12

    monkeypatch.setattr(handler_mod, "_send_template", fake_send)

    verdict = await handle_event(
        _notification_event(
            {
                "tag": "u2i-from-tag",
                "title": "Иван",
                "body": "Готов?",
                "db_id": 17,
                "package_name": "com.avito.android",
            }
        ),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "sent"
    assert verdict.channel_id == "u2i-from-tag"
    assert sent == [("u2i-from-tag", "Hello, please wait.", False)]


@respx.mock
@pytest.mark.asyncio
async def test_notification_without_channel_id_logs_and_skips(stub_pipeline):
    """When regex fails AND xapi has no matching unread channel, ignore."""
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [], "has_more": False})
    )
    verdict = await handle_event(
        _notification_event(
            {
                "title": "Иван",
                "body": "Здравствуйте, актуально?",
                "db_id": 99,
                "package_name": "com.avito.android",
            }
        ),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "ignored"
    assert verdict.reason == "notification without extractable channel_id"
    assert verdict.details["title"] == "Иван"
    assert verdict.details["db_id"] == 99


# ----------------------------------------------------------------------
# V2.1 Phase A: server-side fallback via /messenger/channels
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_fallback_resolves_channel_by_text_match(stub_pipeline, monkeypatch):
    """No u2i in payload → bot fetches /channels, matches body suffix
    against last_message_text of an unread channel, and replies."""
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "channels": [
                    {
                        "id": "u2i-correct",
                        "unread_count": 1,
                        "contact_name": "Рита",
                        "last_message_text": "Сможете установить?",
                    },
                    {
                        "id": "u2i-stale",
                        "unread_count": 0,
                        "contact_name": "Иван",
                        "last_message_text": "Привет",
                    },
                ],
                "has_more": False,
            },
        )
    )
    sent: list[str] = []

    async def fake_send(channel_id, template, *, client, dry_run):
        sent.append(channel_id)
        return True, "msg-A1", None, 200, 12

    monkeypatch.setattr(handler_mod, "_send_template", fake_send)

    verdict = await handle_event(
        _notification_event(
            {
                "title": "Новое сообщение",
                "body": "Рита: Сможете установить?",
                "db_id": 50,
                "package_name": "com.avito.android",
            }
        ),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "sent"
    assert verdict.channel_id == "u2i-correct"
    assert sent == ["u2i-correct"]


@respx.mock
@pytest.mark.asyncio
async def test_fallback_disambiguates_by_sender_name(stub_pipeline, monkeypatch):
    """Two unread channels with the same last_message_text → pick the one
    whose contact_name matches the prefix of the notification body."""
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "channels": [
                    {
                        "id": "u2i-rita",
                        "unread_count": 1,
                        "contact_name": "Рита",
                        "last_message_text": "+",
                    },
                    {
                        "id": "u2i-ivan",
                        "unread_count": 1,
                        "contact_name": "Иван",
                        "last_message_text": "+",
                    },
                ],
                "has_more": False,
            },
        )
    )
    sent: list[str] = []

    async def fake_send(channel_id, template, *, client, dry_run):
        sent.append(channel_id)
        return True, "msg-A2", None, 200, 12

    monkeypatch.setattr(handler_mod, "_send_template", fake_send)

    verdict = await handle_event(
        _notification_event({"body": "Иван: +", "db_id": 51}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "sent"
    assert verdict.channel_id == "u2i-ivan"
    assert sent == ["u2i-ivan"]


@respx.mock
@pytest.mark.asyncio
async def test_fallback_returns_ignored_when_no_text_matches(stub_pipeline):
    """Unread exists but last_message_text doesn't match → ignored
    (we never reply to a guess)."""
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "channels": [
                    {
                        "id": "u2i-stranger",
                        "unread_count": 1,
                        "contact_name": "X",
                        "last_message_text": "Совсем другой текст",
                    }
                ],
                "has_more": False,
            },
        )
    )
    verdict = await handle_event(
        _notification_event(
            {"body": "Рита: Сможете установить?", "db_id": 52}
        ),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "ignored"
    assert verdict.reason == "notification without extractable channel_id"


@respx.mock
@pytest.mark.asyncio
async def test_fallback_returns_ignored_when_xapi_errors(stub_pipeline):
    """xapi /channels returns 500 → fallback gives up, ignored."""
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(500, json={"detail": "upstream boom"})
    )
    verdict = await handle_event(
        _notification_event({"body": "Рита: Текст", "db_id": 53}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "ignored"
    assert verdict.reason == "notification without extractable channel_id"


@pytest.mark.asyncio
async def test_fallback_skips_xapi_when_no_body_to_match(stub_pipeline):
    """No body → nothing to match against → don't bother xapi at all.

    This test deliberately omits respx mocks: if the code calls xapi,
    respx-less httpx will hit a real DNS lookup and fail loudly.
    """
    verdict = await handle_event(
        _notification_event(
            {"title": "Avito", "db_id": 54, "package_name": "com.avito.android"}
        ),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "ignored"
    assert verdict.reason == "notification without extractable channel_id"


@pytest.mark.asyncio
async def test_notification_pipeline_respects_dedup(stub_pipeline, monkeypatch):
    """A notification whose channel was already replied-to is skipped."""

    async def yes(*args, **kwargs):
        return True

    monkeypatch.setattr(handler_mod, "already_replied", yes)
    verdict = await handle_event(
        _notification_event({"tag": "u2i-already-done", "title": "x", "body": "y"}),
        client=make_client(),
        settings=make_settings(),
    )
    assert verdict.action == "skipped"
    assert verdict.reason == "already replied (dialog_state)"
    assert verdict.channel_id == "u2i-already-done"


# Imports kept top-level avoid F401: dedup_mod, rl_mod, wl_mod are used by
# fixtures via monkeypatch.setattr above (lint-only re-export).
_ = (dedup_mod, rl_mod, wl_mod)
