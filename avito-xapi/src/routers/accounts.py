"""Account pool router — list, claim, report, refresh-cycle, state."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.account_state import AccountState, Event, compute_next_state
from src.storage.supabase import get_supabase

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

# Bound CAS retries — bigger than any realistic burst, small enough to never hot-loop.
_CLAIM_MAX_ATTEMPTS = 3


@router.get("")
async def list_accounts():
    sb = get_supabase()
    res = sb.table("avito_accounts").select("*").execute()
    return res.data or []


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
