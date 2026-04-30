"""Account pool router — list, claim, report, refresh-cycle, state."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.account_state import AccountState, Event, compute_next_state
from src.storage.supabase import get_supabase
from src.workers.device_switcher import DeviceSwitchError, device_switcher

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

# Bound CAS retries — bigger than any realistic burst, small enough to never hot-loop.
_CLAIM_MAX_ATTEMPTS = 3


@router.get("")
async def list_accounts():
    """List all accounts; each row enriched with `expires_at` from active session."""
    sb = get_supabase()
    res = sb.table("avito_accounts").select("*").execute()
    accounts = res.data or []
    if not accounts:
        return []

    # Bulk-fetch active sessions for all listed accounts (one query, IN clause).
    ids = [a["id"] for a in accounts]
    sess_res = (
        sb.table("avito_sessions")
        .select("account_id,expires_at")
        .in_("account_id", ids)
        .eq("is_active", True)
        .execute()
    )
    expiry_by_account = {row["account_id"]: row["expires_at"] for row in (sess_res.data or [])}
    for a in accounts:
        a["expires_at"] = expiry_by_account.get(a["id"])
    return accounts


@router.post("/poll-claim")
async def poll_claim():
    """Atomic round-robin claim of an active account for a polling worker.

    Strategy: optimistic compare-and-swap on `last_polled_at`. We pick the
    LRU active account, then UPDATE only if its `last_polled_at` matches what
    we read — if another worker beat us, the UPDATE matches 0 rows and we
    retry with the next LRU. Two concurrent claims can never return the same
    account.
    """
    sb = get_supabase()

    for _ in range(_CLAIM_MAX_ATTEMPTS):
        lru_res = (
            sb.table("avito_accounts")
            .select("*")
            .eq("state", "active")
            .order("last_polled_at", nullsfirst=True)
            .limit(1)
            .execute()
        )
        if not lru_res.data:
            # Pool drained — return diagnostic snapshot of all accounts.
            diag = (
                sb.table("avito_accounts")
                .select("nickname,state,cooldown_until,waiting_since")
                .execute()
            )
            raise HTTPException(
                status_code=409,
                detail={"error": "pool_drained", "accounts": diag.data or []},
            )

        acc = lru_res.data[0]
        old_polled = acc.get("last_polled_at")
        now_iso = datetime.now(timezone.utc).isoformat()

        upd = sb.table("avito_accounts").update({"last_polled_at": now_iso}).eq("id", acc["id"])
        if old_polled is None:
            upd = upd.is_("last_polled_at", None)
        else:
            upd = upd.eq("last_polled_at", old_polled)
        cas_res = upd.execute()

        if not cas_res.data:
            # CAS miss — another worker grabbed this account; retry next LRU.
            continue

        sess_res = (
            sb.table("avito_sessions")
            .select("*")
            .eq("account_id", acc["id"])
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not sess_res.data:
            # Account has no active session — skip and try next LRU.
            continue

        s = sess_res.data[0]
        tokens = s.get("tokens") or {}
        return {
            "account_id": acc["id"],
            "session_token": tokens.get("session_token"),
            "device_id": s.get("device_id"),
            "fingerprint": s.get("fingerprint"),
            "phone_serial": acc.get("phone_serial"),
            "android_user_id": acc.get("android_user_id"),
        }

    raise HTTPException(status_code=503, detail="poll_claim contention exhausted, retry")


# ---------------------------------------------------------------------------
# Report endpoint
# ---------------------------------------------------------------------------

class ReportPayload(BaseModel):
    status_code: int
    body_excerpt: str | None = None


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.post("/{account_id}/report", status_code=204)
async def report(account_id: str, payload: ReportPayload):
    """Apply polling result to account state machine; persist cooldown ratchet + 403 capture."""
    sb = get_supabase()
    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")
    row = res.data[0]

    curr = AccountState(
        state=row["state"],
        consecutive_cooldowns=row.get("consecutive_cooldowns", 0),
        cooldown_until=_parse_ts(row.get("cooldown_until")),
        waiting_since=_parse_ts(row.get("waiting_since")),
    )
    now = datetime.now(timezone.utc)
    next_s = compute_next_state(
        curr,
        Event(kind="report", status_code=payload.status_code),
        now=now,
    )

    update: dict = {
        "state": next_s.state,
        "consecutive_cooldowns": next_s.consecutive_cooldowns,
        "cooldown_until": next_s.cooldown_until.isoformat() if next_s.cooldown_until else None,
        "updated_at": now.isoformat(),
    }
    if payload.status_code == 403:
        update["last_403_body"] = (payload.body_excerpt or "")[:1024] or None
        update["last_403_at"] = now.isoformat()
    elif payload.status_code == 200:
        update["last_403_body"] = None
        update["last_403_at"] = None
    elif payload.status_code == 401:
        # Force health_checker to pick this account on next tick by expiring its session.
        sb.table("avito_sessions").update({
            "expires_at": now.isoformat()
        }).eq("account_id", account_id).eq("is_active", True).execute()

    sb.table("avito_accounts").update(update).eq("id", account_id).execute()

    if next_s.consecutive_cooldowns >= 5:
        _log.warning(
            "account %s consecutive_cooldowns=%d, manual review needed",
            account_id, next_s.consecutive_cooldowns,
        )


# ---------------------------------------------------------------------------
# Session-for-sync endpoint (read-only, no last_polled_at update)
# ---------------------------------------------------------------------------

@router.get("/{account_id}/session-for-sync")
async def session_for_sync(account_id: str):
    """Return the active session for a specific account.

    Unlike /poll-claim this does NOT update last_polled_at — autosearch_sync
    is owner-specific and must not compete with round-robin polling workers.
    """
    sb = get_supabase()

    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")

    row = res.data[0]
    if row["state"] != "active":
        raise HTTPException(409, detail={"state": row["state"], "id": account_id})

    s = (
        sb.table("avito_sessions")
        .select("*")
        .eq("account_id", account_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not s.data:
        raise HTTPException(409, detail={"state": "no_session", "id": account_id})

    sd = s.data[0]
    tokens = sd.get("tokens") or {}
    return {
        "account_id": account_id,
        "session_token": tokens.get("session_token"),
        "device_id": sd.get("device_id"),
        "fingerprint": sd.get("fingerprint"),
    }


# ---------------------------------------------------------------------------
# Refresh-cycle endpoint
# ---------------------------------------------------------------------------

_REFRESH_WARMUP_SEC = 8
_REFRESH_CMD_EXPIRE_SEC = 120


@router.post("/{account_id}/refresh-cycle", status_code=202)
async def refresh_cycle(account_id: str):
    """Atomic ADB switch + refresh_token command + mark account waiting_refresh.

    Flow:
      1. Load account (404 if missing).
      2. ADB health check (503 if dead).
      3. Switch Android user (503 on DeviceSwitchError).
      4. Sleep REFRESH_WARMUP_SEC to let NotificationListener warm up.
      5. Guard: last_device_id must be set (409 otherwise).
      6. Insert refresh_token device command.
      7. Update account state to waiting_refresh.
      8. Return 202 with command_id + account_id.
    """
    sb = get_supabase()

    # Step 1 — load account
    res = sb.table("avito_accounts").select("*").eq("id", account_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "account not found")
    acc = res.data[0]

    # Step 2 — ADB health
    if not await device_switcher.health(acc["phone_serial"]):
        raise HTTPException(503, detail=f"ADB-канал к {acc['phone_serial']} недоступен")

    # Step 3 — switch Android user
    try:
        await device_switcher.switch_to(acc["phone_serial"], acc["android_user_id"])
    except DeviceSwitchError as exc:
        raise HTTPException(503, detail=f"switch-user failed: {exc}")

    # Step 4 — warm-up pause
    await asyncio.sleep(_REFRESH_WARMUP_SEC)

    # Step 5 — last_device_id guard
    last_device_id = acc.get("last_device_id")
    if not last_device_id:
        raise HTTPException(409, "account has no last_device_id, cannot send refresh cmd")

    # Step 6 — insert refresh_token command. Schema (migration 006) is per-tenant,
    # not per-device — V1 known limitation. Target device_id+account_id embedded
    # in payload so V1.5 APK can filter; for now relying on device_switcher.switch_to
    # → нужный APK в foreground first long-poll'ит. tenant_id берётся из активной
    # сессии аккаунта (FK guarantee + avito_accounts само не имеет tenant_id колонки).
    sess_res = sb.table("avito_sessions").select("tenant_id").eq("account_id", account_id) \
        .eq("is_active", True).limit(1).execute()
    if not sess_res.data or not sess_res.data[0].get("tenant_id"):
        raise HTTPException(409, "account has no active session, cannot determine tenant for refresh cmd")
    tenant_id = sess_res.data[0]["tenant_id"]

    now = datetime.now(timezone.utc)
    cmd_row = {
        "tenant_id": tenant_id,
        "command": "refresh_token",
        "issued_by": "account_pool.refresh_cycle",
        "payload": {
            "timeout_sec": 90,
            "prev_exp": 0,
            "target_device_id": last_device_id,
            "target_account_id": account_id,
        },
        "expire_at": (now + timedelta(seconds=_REFRESH_CMD_EXPIRE_SEC)).isoformat(),
    }
    cmd_res = sb.table("avito_device_commands").insert(cmd_row).execute()
    if not cmd_res.data:
        raise HTTPException(500, "device command insert returned no row")
    command_id = cmd_res.data[0].get("id")

    # Step 7 — mark account waiting_refresh
    sb.table("avito_accounts").update({
        "state": "waiting_refresh",
        "waiting_since": now.isoformat(),
        "updated_at": now.isoformat(),
    }).eq("id", account_id).execute()

    # Step 8 — respond
    _log.info("refresh_cycle.started account=%s cmd=%s device=%s", account_id, command_id, last_device_id)
    return {"command_id": command_id, "account_id": account_id}


# ---------------------------------------------------------------------------
# State-patch endpoint
# ---------------------------------------------------------------------------

class StatePatchPayload(BaseModel):
    state: Literal["active", "cooldown", "needs_refresh", "waiting_refresh", "dead"]
    reason: str | None = None


@router.patch("/{account_id}/state", status_code=204)
async def patch_state(account_id: str, payload: StatePatchPayload):
    """Manually transition account state; used by monitor's health_checker."""
    sb = get_supabase()
    update = {
        "state": payload.state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.state != "waiting_refresh":
        update["waiting_since"] = None
    sb.table("avito_accounts").update(update).eq("id", account_id).execute()
    if payload.reason:
        _log.warning("account %s state→%s: %s", account_id, payload.state, payload.reason)
