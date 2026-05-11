"""Dialog topics service — CRUD + ad-hoc creation."""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SLUG_CYR = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


def slugify_topic_key(question_text: str) -> str:
    """Generate a unique snake_case key under 64 chars from arbitrary text.

    Translit Cyrillic → ASCII, strip punctuation, append 4-hex uuid suffix.
    """
    s = (question_text or "").lower().strip()
    s = s.translate(_SLUG_CYR)
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    suffix = uuid.uuid4().hex[:4]
    head_max = 64 - 1 - len(suffix)
    return f"{s[:head_max]}_{suffix}"


async def quick_add_topic(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    question_text: str,
    category: str = "other",
    expected_format: str = "text",
) -> str:
    """Create a new ad-hoc topic AND auto-link to the given profile.
    Returns the generated topic_key.
    """
    key = slugify_topic_key(question_text)
    title = question_text.strip()[:200]
    await session.execute(
        text(
            "INSERT INTO dialog_topics (key, title, category, default_phrasing, "
            "expected_format, created_by) "
            "VALUES (:key, :title, :category, :phrasing, :fmt, 'operator')"
        ),
        {"key": key, "title": title, "category": category,
         "phrasing": question_text, "fmt": expected_format},
    )
    await session.execute(
        text(
            "INSERT INTO profile_dialog_topics (profile_id, topic_key) "
            "VALUES (:pid, :key) ON CONFLICT DO NOTHING"
        ),
        {"pid": profile_id, "key": key},
    )
    await session.commit()
    return key


async def list_topics(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all active topics ordered by title."""
    rows = await session.execute(text(
        "SELECT key, title, category, expected_format, default_phrasing, "
        "created_by, is_active FROM dialog_topics ORDER BY title"
    ))
    return [dict(r._mapping) for r in rows.all()]


async def topics_for_profile(session: AsyncSession, profile_id: uuid.UUID) -> list[dict]:
    """Return baseline topics linked to a profile."""
    rows = await session.execute(text(
        "SELECT dt.key, dt.title, dt.category, dt.expected_format, dt.default_phrasing "
        "FROM profile_dialog_topics pdt "
        "JOIN dialog_topics dt ON dt.key = pdt.topic_key "
        "WHERE pdt.profile_id = :pid AND dt.is_active = true "
        "ORDER BY pdt.priority, dt.title"
    ), {"pid": profile_id})
    return [dict(r._mapping) for r in rows.all()]
