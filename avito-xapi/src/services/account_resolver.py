"""Resolves (Avito user_id, device_id) → avito_accounts row, creates if missing."""
from datetime import datetime, timezone


def resolve_or_create_account(sb, *, avito_user_id: int, device_id: str | None) -> dict:
    """Возвращает avito_accounts row для пары (user_id, device_id). Создаёт если нет.

    Multi-device на один Avito-юзер поддерживается через композитный ключ
    (avito_user_id, last_device_id) в БД (migration 008). Каждое (u, device)
    — отдельная строка в pool.
    """
    res = sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", avito_user_id) \
        .eq("last_device_id", device_id) \
        .limit(1).execute()
    now = datetime.now(timezone.utc).isoformat()
    if res.data:
        return res.data[0]
    new = sb.table("avito_accounts").insert({
        "avito_user_id": avito_user_id,
        "nickname": f"auto-{avito_user_id}-{(device_id or 'unknown')[:6]}",
        "last_device_id": device_id,
        "state": "active",
        "last_session_at": now,
    }).execute()
    return new.data[0]
