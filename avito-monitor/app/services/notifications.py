"""Notifications service stub — full implementation in T15."""
from typing import Any


async def enqueue_tg_ping(session, notif_type: str, dialog_id) -> None:
    """Persist a TG-ping notification row. Stubbed in T10 — fully implemented in T15."""
    # No-op for now; tests patch this function.
    return None
