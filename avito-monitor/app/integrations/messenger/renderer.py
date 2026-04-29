"""Render a Notification row into a MessengerMessage.

Templates live in ``app/prompts/messenger/<type>.md`` and are plain
Jinja2 with the ``payload`` dict + a few helpers (``money``, ``pct``)
exposed as filters. Buttons come from
:func:`app.integrations.messenger.buttons.buttons_for`.

The renderer is provider-agnostic — a Max provider would re-use the
exact same MessengerMessage. Provider-specific formatting (Markdown
escapes, file IDs, …) belongs inside the provider, not here.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.db.models import Notification
from app.integrations.messenger.base import MessengerMessage
from app.integrations.messenger.buttons import buttons_for

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "prompts" / "messenger"


def _money(value: Any) -> str:
    """Format ``12500`` → ``"12 500 ₽"`` (NBSP between groups)."""
    if value is None or value == "":
        return "—"
    try:
        n = float(value) if not isinstance(value, Decimal) else float(value)
    except (TypeError, ValueError):
        return str(value)
    n_int = int(round(n))
    s = f"{n_int:,}".replace(",", " ")
    return f"{s} ₽"


def _pct(value: Any, *, signed: bool = True, digits: int = 1) -> str:
    """Format a fraction (``0.075``) as ``"+7.5%"``."""
    if value is None or value == "":
        return "—"
    try:
        n = float(value) * 100.0
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if signed and n >= 0 else ""
    return f"{sign}{n:.{digits}f}%"


def _condition_label(value: str) -> str:
    """User-facing Russian label for a ConditionClass."""
    labels = {
        "working": "рабочий ✅",
        "blocked_icloud": "iCloud-блок ☁️🔒",
        "blocked_account": "блок Apple ID 🔒",
        "not_starting": "не включается ⚠️",
        "broken_screen": "разбит экран 💥",
        "broken_other": "повреждён 💥",
        "parts_only": "на запчасти ⚙️",
        "unknown": "не определено ❔",
    }
    return labels.get(value, value or "—")


@lru_cache
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = _money
    env.filters["pct"] = _pct
    env.filters["condition_label"] = _condition_label
    return env


def render(notification: Notification, *, chat_id: str) -> MessengerMessage:
    """Turn a Notification row into a MessengerMessage ready for any provider."""
    template_name = f"{notification.type}.md"
    try:
        tmpl = _env().get_template(template_name)
    except Exception as exc:
        log.warning(
            "messenger.render.template_missing type=%s err=%s",
            notification.type, exc,
        )
        # Fallback: dump payload so we never silently swallow an alert.
        text = (
            f"*{notification.type}*\n"
            f"```\n{notification.payload}\n```"
        )
    else:
        text = tmpl.render(
            payload=notification.payload or {},
            type=notification.type,
        ).strip()

    payload = notification.payload or {}
    rows = buttons_for(
        notification.type,
        notification.id,
        listing_url=payload.get("url"),
        seller_id=payload.get("seller_id"),
    )

    raw_imgs = payload.get("images") or []
    images: list[str] = [u for u in raw_imgs if isinstance(u, str) and u][:10]

    return MessengerMessage(
        chat_id=chat_id, text=text, buttons=rows, images=images,
    )
