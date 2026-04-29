"""Resolves Avito user_id → avito_accounts row, creates if missing."""
from datetime import datetime, timezone


def resolve_or_create_account(sb, *, avito_user_id: int, device_id: str | None) -> dict:
    """Возвращает avito_accounts row для данного user_id. Создаёт если нет.

    При наличии row — обновляет last_device_id если он изменился.
    """
    res = sb.table("avito_accounts").select("*").eq("avito_user_id", avito_user_id).limit(1).execute()
    now = datetime.now(timezone.utc).isoformat()
    if res.data:
        acc = res.data[0]
        if device_id and acc.get("last_device_id") != device_id:
            sb.table("avito_accounts").update({
                "last_device_id": device_id,
                "last_session_at": now,
                "updated_at": now,
            }).eq("id", acc["id"]).execute()
            acc["last_device_id"] = device_id
        return acc
    # create
    new = sb.table("avito_accounts").insert({
        "avito_user_id": avito_user_id,
        "nickname": f"auto-{avito_user_id}",
        "last_device_id": device_id,
        "state": "active",
        "last_session_at": now,
    }).execute()
    return new.data[0]
