"""Tests for dialog_topics service layer."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch


def test_slugify_generates_unique_key_from_question_text():
    from app.services.dialog_topics.service import slugify_topic_key

    out = slugify_topic_key("Сколько раз падал телефон?")
    # Must be lowercase, alnum + underscore, ends with short uuid suffix.
    assert out.startswith("skolko_raz_padal_telefon")
    assert len(out) <= 64
    parts = out.rsplit("_", 1)
    assert len(parts[1]) >= 4  # uuid-ish suffix


@pytest.mark.asyncio
async def test_quick_add_creates_topic_and_links_to_profile():
    from app.services.dialog_topics.service import quick_add_topic

    session = AsyncMock()
    profile_id = uuid.uuid4()
    with patch("app.services.dialog_topics.service.slugify_topic_key",
               return_value="how_many_drops_abcd"):
        topic_key = await quick_add_topic(
            session,
            profile_id=profile_id,
            question_text="Сколько раз падал?",
        )
    assert topic_key == "how_many_drops_abcd"
    # Two execute() calls — one INSERT dialog_topics, one INSERT profile_dialog_topics
    assert session.execute.await_count == 2
    assert session.commit.await_count == 1
