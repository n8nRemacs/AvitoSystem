# Phase B — Опрос autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship stages `questions_setup` (operator-driven topic picker via modal) and `questions` (bot auto pipeline: opening line → questions one-at-a-time → recap → SUGGEST) so accepted lots automatically progress from `contact` through `questions` to `price_negotiation` with minimal operator input.

**Architecture:** Mirror Phase A patterns. New `dialog_topics` library (mirrored from YAML seed) + per-profile baseline + per-dialog topic state machine driven by a single `dialog_tick_questions` TaskIQ task. 4 LLM dispatchers extend `llm_analyzer.py`. UI gets a 3rd kanban column "Опрос" + profile filter dropdown + setup modal triggered from `questions_setup` cards. 2 TG transition-pings.

**Tech Stack:** FastAPI + HTMX (minimal vanilla JS for modal) + SQLAlchemy 2.0 async + Alembic + TaskIQ/Redis + aiogram TG bot + OpenRouter `google/gemini-2.5-flash-lite`.

**Spec:** `DOCS/superpowers/specs/2026-05-11-seller-dialog-phase-b-design.md` (commit `e83ede4`).

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `avito-monitor/alembic/versions/20260511_2000_phase_b_topics.py` | Migration 0014: 3 tables + 3 cols on seller_dialogs + data-migration upsert from YAML |
| `avito-monitor/app/data/dialog_topics.yaml` | Seed 11 baseline topics |
| `avito-monitor/app/db/models/dialog_topic.py` | SQLAlchemy `DialogTopic` model |
| `avito-monitor/app/db/models/profile_dialog_topic.py` | `ProfileDialogTopic` model |
| `avito-monitor/app/db/models/seller_dialog_topic.py` | `SellerDialogTopic` model |
| `avito-monitor/app/services/dialog_topics/__init__.py` | Package marker |
| `avito-monitor/app/services/dialog_topics/seed.py` | YAML loader (used both at migration time and at startup for refresh) |
| `avito-monitor/app/services/dialog_topics/service.py` | CRUD + ad-hoc upsert with key slugify |
| `avito-monitor/app/services/dialog_topics/state.py` | seller_dialog_topics state machine helpers (pick_next_pending, mark_answered, mark_skipped, all_closed) |
| `avito-monitor/app/prompts/dialog_formulate_question.md` | LLM prompt for first dispatcher |
| `avito-monitor/app/prompts/dialog_parse_topic_answer.md` | LLM prompt for second dispatcher |
| `avito-monitor/app/prompts/dialog_formulate_recap.md` | LLM prompt for third dispatcher |
| `avito-monitor/app/prompts/dialog_parse_seller_agreement.md` | LLM prompt for fourth dispatcher |
| `avito-monitor/app/web/templates/_partials/kanban_card_questions.html` | Card partial for 3rd column |
| `avito-monitor/app/web/templates/_partials/setup_modal.html` | Modal fragment (rendered by HTMX) |
| `avito-monitor/app/web/templates/dialog_topics.html` | Topic library page |
| `avito-monitor/tests/dialog_topics/__init__.py` | Package marker |
| `avito-monitor/tests/dialog_topics/test_seed.py` | YAML parse + load semantics |
| `avito-monitor/tests/dialog_topics/test_service.py` | CRUD + ad-hoc upsert + slugify |
| `avito-monitor/tests/seller_dialog/test_dialog_tick_questions.py` | Worker state machine branches |
| `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py` | 4 new dispatchers mocked |
| `avito-monitor/tests/seller_dialog/test_handler_phase_b.py` | Handler stage='questions' branch |
| `avito-monitor/tests/seller_dialog/test_view_phase_b.py` | view returns 3rd column + profile filter |

**Modify:**

| Path | Change |
|---|---|
| `avito-monitor/app/db/models/__init__.py` | Export new models |
| `avito-monitor/app/db/models/seller_dialog.py` | Add `recap_text`, `recap_msg_id`, `recap_status` columns |
| `avito-monitor/app/services/seller_dialog/constants.py` | Add `OPENING_LINE` |
| `avito-monitor/app/services/seller_dialog/handler.py` | Extend `handle_seller_inbound` with stage='questions' branch |
| `avito-monitor/app/services/seller_dialog/transitions.py` | Add transition helpers for questions_setup → questions |
| `avito-monitor/app/services/llm_analyzer.py` | Append 4 dispatchers |
| `avito-monitor/app/services/seller_dialog_view.py` | Add `STAGE_QUESTIONS` to `PHASE_A_STAGES` (rename or expand) + ensure profile filter exposed in template |
| `avito-monitor/app/tasks/seller_dialog_tasks.py` | Add `dialog_tick_questions` task |
| `avito-monitor/app/tasks/broker.py` | Register `dialog_tick_questions` in `_register_tasks` |
| `avito-monitor/app/tasks/notifications.py` | Add `seller_dialog_ready_to_setup` + `seller_dialog_ready_to_negotiate` types |
| `avito-monitor/app/web/routers.py` | Add 5 endpoints (setup modal render, start-questions, quick-add, topic-library view, topic-library add) |
| `avito-monitor/app/web/templates/listings_kanban.html` | 3rd column + profile filter dropdown |
| `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html` | Add modal trigger link |

---

## Waves

- **Wave 1 (parallel)** — Foundation: schema, models, seed, constants
- **Wave 2 (parallel)** — 4 LLM dispatchers (independent files)
- **Wave 3 (sequential w/ Wave 1+2)** — Service layer + Worker + Handler
- **Wave 4 (parallel)** — HTTP endpoints, Kanban view, Templates
- **Wave 5 (sequential)** — TG pings + broker registration + smoke

---

## Wave 1 — Foundation

### Task 1: Migration `0014_phase_b_topics` + YAML seed

**Files:**
- Create: `avito-monitor/alembic/versions/20260511_2000_phase_b_topics.py`
- Create: `avito-monitor/app/data/dialog_topics.yaml`
- Modify: existing alembic chain head will be `0013_seller_dialogs` → `0014_phase_b_topics`

- [ ] **Step 1: Write YAML seed**

File `avito-monitor/app/data/dialog_topics.yaml`:

```yaml
- key: battery_health
  title: АКБ здоровье (%)
  category: battery
  expected_format: percent
  default_phrasing: "Спроси точный процент здоровья АКБ из настроек"
- key: face_id_works
  title: Face ID работает
  category: function
  expected_format: yesno
  default_phrasing: "Уточни, работает ли Face ID без сбоев"
- key: icloud_unlinked
  title: iCloud отвязан
  category: function
  expected_format: yesno
  default_phrasing: "Спроси, отвязан ли iCloud с прошлого аккаунта"
- key: replaced_display
  title: Дисплей менялся
  category: damage
  expected_format: yesno
  default_phrasing: "Уточни — менялся ли дисплей (оригинальный или замена)"
- key: broken_glass
  title: Разбито стекло дисплея
  category: damage
  expected_format: yesno
  default_phrasing: "Спроси, целое ли стекло дисплея (трещины, сколы)"
- key: display_stains_stripes
  title: Пятна/полосы на дисплее
  category: damage
  expected_format: yesno
  default_phrasing: "Уточни — есть ли пятна, полосы, битые пиксели на дисплее"
- key: broken_back
  title: Разбита задняя крышка
  category: damage
  expected_format: yesno
  default_phrasing: "Спроси, целая ли задняя крышка телефона"
- key: cameras_work
  title: Все камеры работают
  category: function
  expected_format: text
  default_phrasing: "Уточни — все ли камеры работают (основная, широкоугольная, теле, фронт); если есть дефекты — какая именно"
- key: charging_stability
  title: Зарядка и стабильность
  category: function
  expected_format: text
  default_phrasing: "Спроси — стабильно ли заряжается, не перезагружается ли, не греется ли при использовании"
- key: replaced_parts
  title: Что ещё менялось
  category: damage
  expected_format: text
  default_phrasing: "Уточни — менялись ли какие-то части помимо дисплея (АКБ, камеры, плата и т.п.)"
- key: complectness
  title: Комплект (коробка/кабель/зарядка)
  category: complectness
  expected_format: text
  default_phrasing: "Спроси, что есть в комплекте: коробка, кабель, зарядка (адаптер)"
```

- [ ] **Step 2: Write migration scaffold**

File `avito-monitor/alembic/versions/20260511_2000_phase_b_topics.py`:

```python
"""phase_b_topics — dialog topic library + per-dialog topic state + recap.

Revision ID: 0014_phase_b_topics
Revises: 0013_seller_dialogs
Create Date: 2026-05-11 20:00:00
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
import yaml
from alembic import op


revision: str = "0014_phase_b_topics"
down_revision: Union[str, None] = "0013_seller_dialogs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dialog_topics",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("default_phrasing", sa.Text, nullable=True),
        sa.Column("expected_format", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=False, server_default="system_seed"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "profile_dialog_topics",
        sa.Column("profile_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("search_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("topic_key", sa.String(64),
                  sa.ForeignKey("dialog_topics.key", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("profile_id", "topic_key",
                                name="pk_profile_dialog_topics"),
    )
    op.create_table(
        "seller_dialog_topics",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dialog_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("seller_dialogs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("topic_key", sa.String(64),
                  sa.ForeignKey("dialog_topics.key"), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("question_text", sa.Text, nullable=True),
        sa.Column("question_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True),
        sa.Column("answer_text", sa.Text, nullable=True),
        sa.Column("answer_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "status IN ('pending','asked','answered','skipped')",
            name="ck_seller_dialog_topics_status",
        ),
    )
    op.create_index("ix_seller_dialog_topics_dialog", "seller_dialog_topics", ["dialog_id"])
    op.create_index("ix_seller_dialog_topics_status", "seller_dialog_topics", ["status"])

    op.add_column("seller_dialogs", sa.Column("recap_text", sa.Text, nullable=True))
    op.add_column("seller_dialogs", sa.Column("recap_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True))
    op.add_column("seller_dialogs", sa.Column("recap_status", sa.String(16), nullable=True))

    # Data migration: upsert seed YAML into dialog_topics + auto-link to existing
    # profile "iPhone 12 Pro max 10500-13500".
    seed_path = Path(__file__).resolve().parents[2] / "app" / "data" / "dialog_topics.yaml"
    with seed_path.open(encoding="utf-8") as f:
        topics = yaml.safe_load(f)
    bind = op.get_bind()
    for t in topics:
        bind.execute(sa.text(
            "INSERT INTO dialog_topics (key, title, category, default_phrasing, "
            "expected_format, created_by) "
            "VALUES (:key, :title, :category, :default_phrasing, :expected_format, 'system_seed') "
            "ON CONFLICT (key) DO UPDATE SET title = EXCLUDED.title, "
            "category = EXCLUDED.category, default_phrasing = EXCLUDED.default_phrasing, "
            "expected_format = EXCLUDED.expected_format"
        ), t)
    # Auto-link to all profiles (currently 1: iPhone 12 Pro max 10500-13500).
    bind.execute(sa.text(
        "INSERT INTO profile_dialog_topics (profile_id, topic_key) "
        "SELECT p.id, t.key FROM search_profiles p CROSS JOIN dialog_topics t "
        "ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.drop_column("seller_dialogs", "recap_status")
    op.drop_column("seller_dialogs", "recap_msg_id")
    op.drop_column("seller_dialogs", "recap_text")
    op.drop_index("ix_seller_dialog_topics_status", table_name="seller_dialog_topics")
    op.drop_index("ix_seller_dialog_topics_dialog", table_name="seller_dialog_topics")
    op.drop_table("seller_dialog_topics")
    op.drop_table("profile_dialog_topics")
    op.drop_table("dialog_topics")
```

- [ ] **Step 3: Verify migration ID and chain head**

Run: `cd avito-monitor && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; c=Config('alembic.ini'); s=ScriptDirectory.from_config(c); print(s.get_current_head())"`

Expected: `0014_phase_b_topics`

- [ ] **Step 4: Commit**

```bash
git add avito-monitor/alembic/versions/20260511_2000_phase_b_topics.py avito-monitor/app/data/dialog_topics.yaml
git commit -m "feat(schema): phase_b_topics migration + 11-topic seed for iPhone 12 Pro Max"
```

---

### Task 2: SQLAlchemy models for new tables

**Files:**
- Create: `avito-monitor/app/db/models/dialog_topic.py`
- Create: `avito-monitor/app/db/models/profile_dialog_topic.py`
- Create: `avito-monitor/app/db/models/seller_dialog_topic.py`
- Modify: `avito-monitor/app/db/models/__init__.py`
- Modify: `avito-monitor/app/db/models/seller_dialog.py` — add recap_* columns

- [ ] **Step 1: Write `DialogTopic` model**

File `avito-monitor/app/db/models/dialog_topic.py`:

```python
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DialogTopic(Base):
    """Global library of questions the bot can ask sellers."""

    __tablename__ = "dialog_topics"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(32))
    default_phrasing: Mapped[str | None] = mapped_column(Text)
    expected_format: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 2: Write `ProfileDialogTopic` model**

File `avito-monitor/app/db/models/profile_dialog_topic.py`:

```python
import uuid
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ProfileDialogTopic(Base):
    """Which baseline topics a profile includes."""

    __tablename__ = "profile_dialog_topics"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dialog_topics.key", ondelete="CASCADE"),
        primary_key=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 3: Write `SellerDialogTopic` model**

File `avito-monitor/app/db/models/seller_dialog_topic.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SellerDialogTopic(Base):
    """Per-dialog state of a topic — pending/asked/answered/skipped."""

    __tablename__ = "seller_dialog_topics"
    __table_args__ = (
        Index("ix_seller_dialog_topics_dialog", "dialog_id"),
        Index("ix_seller_dialog_topics_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
    )
    dialog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("seller_dialogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_key: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dialog_topics.key"),
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    question_text: Mapped[str | None] = mapped_column(Text)
    question_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

- [ ] **Step 4: Extend `SellerDialog` model with recap columns**

In `avito-monitor/app/db/models/seller_dialog.py`, append after existing columns:

```python
    recap_text: Mapped[str | None] = mapped_column(Text)
    recap_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    recap_status: Mapped[str | None] = mapped_column(String(16))
```

(Import `Text`, `ForeignKey`, `String` if not already.)

- [ ] **Step 5: Wire exports in `__init__.py`**

In `avito-monitor/app/db/models/__init__.py`, add imports + `__all__`:

```python
from app.db.models.dialog_topic import DialogTopic
from app.db.models.profile_dialog_topic import ProfileDialogTopic
from app.db.models.seller_dialog_topic import SellerDialogTopic
```

And add `"DialogTopic"`, `"ProfileDialogTopic"`, `"SellerDialogTopic"` to `__all__`.

- [ ] **Step 6: Smoke test — import all models**

Run inside avito-monitor container:
```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor python -c "from app.db.models import DialogTopic, ProfileDialogTopic, SellerDialogTopic; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add avito-monitor/app/db/models/dialog_topic.py avito-monitor/app/db/models/profile_dialog_topic.py avito-monitor/app/db/models/seller_dialog_topic.py avito-monitor/app/db/models/seller_dialog.py avito-monitor/app/db/models/__init__.py
git commit -m "feat(models): DialogTopic + ProfileDialogTopic + SellerDialogTopic + seller_dialogs.recap_*"
```

---

### Task 3: Constants — `OPENING_LINE`

**Files:**
- Modify: `avito-monitor/app/services/seller_dialog/constants.py`

- [ ] **Step 1: Append OPENING_LINE constant**

In `avito-monitor/app/services/seller_dialog/constants.py`, append:

```python
OPENING_LINE = (
    "У меня есть несколько вопросов по Вашему аппарату, "
    "ответьте пожалуйста, если Вас это не затруднит."
)

# Recap status enum values for seller_dialogs.recap_status
RECAP_PENDING_ANSWER = "pending_answer"
RECAP_CONFIRMED = "confirmed"
RECAP_DISPUTED = "disputed"
```

- [ ] **Step 2: Commit**

```bash
git add avito-monitor/app/services/seller_dialog/constants.py
git commit -m "feat(constants): OPENING_LINE + recap status enum"
```

---

## Wave 2 — LLM Dispatchers (parallel)

### Task 4: `formulate_question` dispatcher

**Files:**
- Create: `avito-monitor/app/prompts/dialog_formulate_question.md`
- Modify: `avito-monitor/app/services/llm_analyzer.py`
- Test: `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py`

- [ ] **Step 1: Write the prompt file**

File `avito-monitor/app/prompts/dialog_formulate_question.md`:

```markdown
<!-- version: 1 -->
# system
Ты помогаешь байеру б/у iPhone задавать продавцу вопрос на Avito.

Тон: живой, вежливый, на "Вы". Без бот-формулировок. Без приветствия (диалог уже идёт).
Один короткий вопрос (1-2 предложения).

Из подсказки сформулируй именно вопрос для продавца, не пересказ инструкции.

# user
Тема: {{topic_title}}
Подсказка LLM: {{topic_hint}}
Ожидаемый формат ответа: {{topic_format}}

Последние сообщения переписки (для контекста, не цитируй):
{{history_tail}}

Сформулируй вопрос. Ответ — JSON: {"question": "..."}
```

- [ ] **Step 2: Write the failing test**

File `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py`:

```python
"""Tests for Phase B LLM dispatchers."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_formulate_question_returns_text():
    from app.services.llm_analyzer import formulate_question

    fake_topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="Спроси про % АКБ",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={"question": "Подскажите процент здоровья АКБ?"}),
    ):
        out = await formulate_question(fake_topic, history_tail=[])
    assert out == "Подскажите процент здоровья АКБ?"


@pytest.mark.asyncio
async def test_formulate_question_falls_back_on_llm_error():
    from app.services.llm_analyzer import formulate_question

    fake_topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="Спроси про % АКБ",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("openrouter 503")),
    ):
        out = await formulate_question(fake_topic, history_tail=[])
    # Falls back to default_phrasing wrapped as a question.
    assert "АКБ" in out or "%" in out
```

- [ ] **Step 3: Run the test, watch it fail**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_llm_dispatchers_phase_b.py::test_formulate_question_returns_text -v
```

Expected: FAIL with `ImportError: cannot import name 'formulate_question'`.

- [ ] **Step 4: Implement `formulate_question` in `llm_analyzer.py`**

In `avito-monitor/app/services/llm_analyzer.py`, append:

```python
async def formulate_question(topic, history_tail: list[dict] | None = None) -> str:
    """Generate natural-sounding question text for one topic.
    Uses topic.default_phrasing as hint. Live & polite tone (Phase A greeting style).
    Returns the question string. Falls back to default_phrasing on LLM failure.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_formulate_question.md"
    ).read_text(encoding="utf-8")
    history_text = "\n".join(
        f"{m.get('direction', '?')}: {m.get('text', '')}"
        for m in (history_tail or [])[-10:]
    ) or "(пусто)"
    prompt = (
        prompt_template
        .replace("{{topic_title}}", topic.title or "")
        .replace("{{topic_hint}}", topic.default_phrasing or "")
        .replace("{{topic_format}}", topic.expected_format or "text")
        .replace("{{history_tail}}", history_text)
    )
    try:
        result = await _llm_call_json(prompt, max_tokens=200)
    except Exception:
        return topic.default_phrasing or topic.title or "Подскажите, пожалуйста?"
    if isinstance(result, dict) and isinstance(result.get("question"), str):
        return result["question"].strip()
    return topic.default_phrasing or topic.title or "Подскажите, пожалуйста?"
```

- [ ] **Step 5: Re-run tests, watch them pass**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_llm_dispatchers_phase_b.py -v -k formulate_question
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/prompts/dialog_formulate_question.md avito-monitor/app/services/llm_analyzer.py avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py
git commit -m "feat(llm): formulate_question dispatcher for phase B"
```

---

### Task 5: `parse_topic_answer` dispatcher

**Files:**
- Create: `avito-monitor/app/prompts/dialog_parse_topic_answer.md`
- Modify: `avito-monitor/app/services/llm_analyzer.py`
- Test: `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py` (append)

- [ ] **Step 1: Write the prompt file**

File `avito-monitor/app/prompts/dialog_parse_topic_answer.md`:

```markdown
<!-- version: 1 -->
# system
Ты парсишь ответ продавца б/у iPhone на конкретный вопрос байера.

Возможные исходы:
- "answered": продавец ответил по теме. extracted — короткая нормализованная сводка (e.g. "87%" или "работает" или "не менялся").
- "unclear": продавец ответил, но из текста нельзя понять что (вода, "хз", уклоняется).
- "off_topic": продавец отвечает на что-то другое (не на этот вопрос).

Также — если продавец сам затронул другие темы из списка open, заполни side_topics.

# user
Текущая тема: {{topic_title}} ({{topic_format}})
Подсказка: {{topic_hint}}

Открытые другие темы (для side_topics, если seller их затронул):
{{open_topics}}

Ответ продавца:
"{{seller_text}}"

Верни JSON:
{
  "status": "answered" | "unclear" | "off_topic",
  "extracted": "<строка>" | null,
  "side_topics": [{"topic_key": "<key>", "extracted": "<строка>"}, ...]
}
```

- [ ] **Step 2: Write the failing test (append to existing file)**

Append to `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py`:

```python
@pytest.mark.asyncio
async def test_parse_topic_answer_extracts_and_classifies():
    from app.services.llm_analyzer import parse_topic_answer

    topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="х",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={
            "status": "answered",
            "extracted": "87%",
            "side_topics": [],
        }),
    ):
        out = await parse_topic_answer(topic, "87 процентов", open_topics=[])
    assert out["status"] == "answered"
    assert out["extracted"] == "87%"
    assert out["side_topics"] == []


@pytest.mark.asyncio
async def test_parse_topic_answer_returns_unclear_on_llm_failure():
    from app.services.llm_analyzer import parse_topic_answer

    topic = type("T", (), dict(title="x", default_phrasing="", expected_format="text"))()
    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await parse_topic_answer(topic, "blah", open_topics=[])
    assert out["status"] == "unclear"
    assert out["extracted"] is None
    assert out["side_topics"] == []
```

- [ ] **Step 3: Run, watch fail**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_llm_dispatchers_phase_b.py -v -k parse_topic_answer
```

Expected: FAIL `ImportError: cannot import name 'parse_topic_answer'`.

- [ ] **Step 4: Implement**

Append to `avito-monitor/app/services/llm_analyzer.py`:

```python
async def parse_topic_answer(topic, seller_text: str, open_topics: list[dict] | None = None) -> dict:
    """Parse seller's reply to a specific topic question.
    Returns {"status": "answered"|"unclear"|"off_topic", "extracted": str|None, "side_topics": list}.
    On LLM failure returns unclear so caller may re-ask.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_parse_topic_answer.md"
    ).read_text(encoding="utf-8")
    open_text = "\n".join(
        f"- {ot.get('key')}: {ot.get('title')}" for ot in (open_topics or [])
    ) or "(нет)"
    prompt = (
        prompt_template
        .replace("{{topic_title}}", topic.title or "")
        .replace("{{topic_hint}}", topic.default_phrasing or "")
        .replace("{{topic_format}}", topic.expected_format or "text")
        .replace("{{open_topics}}", open_text)
        .replace("{{seller_text}}", seller_text or "")
    )
    safe_default = {"status": "unclear", "extracted": None, "side_topics": []}
    try:
        result = await _llm_call_json(prompt, max_tokens=400)
    except Exception:
        return safe_default
    if not isinstance(result, dict):
        return safe_default
    status = result.get("status")
    if status not in {"answered", "unclear", "off_topic"}:
        return safe_default
    extracted = result.get("extracted")
    side = result.get("side_topics") if isinstance(result.get("side_topics"), list) else []
    # Sanitize side topics — keep only items with both topic_key and extracted strings.
    side_clean = [
        {"topic_key": s["topic_key"], "extracted": s.get("extracted")}
        for s in side
        if isinstance(s, dict) and isinstance(s.get("topic_key"), str)
    ]
    return {"status": status, "extracted": extracted if isinstance(extracted, str) else None,
            "side_topics": side_clean}
```

- [ ] **Step 5: Re-run, pass**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_llm_dispatchers_phase_b.py -v -k parse_topic_answer
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/prompts/dialog_parse_topic_answer.md avito-monitor/app/services/llm_analyzer.py avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py
git commit -m "feat(llm): parse_topic_answer dispatcher with side_topics"
```

---

### Task 6: `formulate_recap` dispatcher

**Files:**
- Create: `avito-monitor/app/prompts/dialog_formulate_recap.md`
- Modify: `avito-monitor/app/services/llm_analyzer.py`
- Test: `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py` (append)

- [ ] **Step 1: Write the prompt**

File `avito-monitor/app/prompts/dialog_formulate_recap.md`:

```markdown
<!-- version: 1 -->
# system
Ты помогаешь байеру подвести итоги диалога с продавцом б/у iPhone.

Составь короткий пересказ в виде одного сообщения, в формате:
"Итак: <ответ_тема_1>, <ответ_тема_2>, ...
Всё правильно понял? Проверьте, пожалуйста, и подтвердите или поправьте меня."

Тон — живой, вежливый, на "Вы". Не "уважаемый продавец". Не "коллега".
Без лишних слов про "я ваш менеджер" — просто пересказ.

# user
Темы и ответы:
{{topics_table}}

Верни JSON: {"recap": "..."}
```

- [ ] **Step 2: Write the failing test**

Append to `tests/seller_dialog/test_llm_dispatchers_phase_b.py`:

```python
@pytest.mark.asyncio
async def test_formulate_recap_returns_message():
    from app.services.llm_analyzer import formulate_recap

    topic_a = type("T", (), dict(title="АКБ здоровье (%)"))()
    topic_b = type("T", (), dict(title="Face ID работает"))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={
            "recap": "Итак: АКБ 87%, Face ID работает. Всё правильно понял? Проверьте, пожалуйста.",
        }),
    ):
        out = await formulate_recap([(topic_a, "87%"), (topic_b, "да")])
    assert "Итак" in out
    assert "АКБ" in out


@pytest.mark.asyncio
async def test_formulate_recap_falls_back_on_llm_error():
    from app.services.llm_analyzer import formulate_recap

    topic_a = type("T", (), dict(title="АКБ здоровье (%)"))()
    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await formulate_recap([(topic_a, "87%")])
    # Fallback: deterministic template
    assert "Итак" in out
    assert "АКБ" in out
    assert "правильно понял" in out.lower()
```

- [ ] **Step 3: Run, fail**

Expected: ImportError.

- [ ] **Step 4: Implement**

Append to `app/services/llm_analyzer.py`:

```python
async def formulate_recap(answered: list[tuple]) -> str:
    """Compose a recap message for the seller summarising what they answered.
    Falls back to deterministic template on LLM failure.
    """
    table_text = "\n".join(
        f"- {topic.title}: {answer}" for topic, answer in answered
    )
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_formulate_recap.md"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{topics_table}}", table_text)

    fallback = (
        "Итак: "
        + ", ".join(f"{topic.title.lower()} — {answer}" for topic, answer in answered)
        + ". Всё правильно понял? Проверьте, пожалуйста, и подтвердите или поправьте меня."
    )
    try:
        result = await _llm_call_json(prompt, max_tokens=400)
    except Exception:
        return fallback
    if isinstance(result, dict) and isinstance(result.get("recap"), str):
        return result["recap"].strip()
    return fallback
```

- [ ] **Step 5: Re-run, pass**

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/prompts/dialog_formulate_recap.md avito-monitor/app/services/llm_analyzer.py avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py
git commit -m "feat(llm): formulate_recap dispatcher with deterministic fallback"
```

---

### Task 7: `parse_seller_agreement` dispatcher

**Files:**
- Create: `avito-monitor/app/prompts/dialog_parse_seller_agreement.md`
- Modify: `avito-monitor/app/services/llm_analyzer.py`
- Test: `avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py` (append)

- [ ] **Step 1: Write the prompt**

File `avito-monitor/app/prompts/dialog_parse_seller_agreement.md`:

```markdown
<!-- version: 1 -->
# system
Ты классифицируешь ответ продавца на recap-сообщение от байера.

Recap содержал summary всех ответов продавца + вопрос "всё правильно понял?".
Продавец мог:
- "yes": подтвердить что всё верно
- "no": исправить что-то конкретное
- "unclear": ответить не по делу / промолчать

# user
Ответ продавца:
"{{seller_text}}"

JSON:
{
  "agreement": "yes" | "no" | "unclear",
  "corrections": "<строка с исправлениями>" | null
}
```

- [ ] **Step 2: Write the failing test**

Append to test file:

```python
@pytest.mark.asyncio
async def test_parse_seller_agreement_yes():
    from app.services.llm_analyzer import parse_seller_agreement

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={"agreement": "yes", "corrections": None}),
    ):
        out = await parse_seller_agreement("Да, все верно")
    assert out["agreement"] == "yes"
    assert out["corrections"] is None


@pytest.mark.asyncio
async def test_parse_seller_agreement_unclear_on_llm_failure():
    from app.services.llm_analyzer import parse_seller_agreement

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await parse_seller_agreement("...")
    assert out["agreement"] == "unclear"
    assert out["corrections"] is None
```

- [ ] **Step 3: Run, fail.**

- [ ] **Step 4: Implement**

Append to `app/services/llm_analyzer.py`:

```python
async def parse_seller_agreement(text: str) -> dict:
    """Classify seller's reply to the recap message.
    Returns {"agreement": "yes"|"no"|"unclear", "corrections": str|None}.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_parse_seller_agreement.md"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{seller_text}}", text or "")
    safe = {"agreement": "unclear", "corrections": None}
    try:
        result = await _llm_call_json(prompt, max_tokens=200)
    except Exception:
        return safe
    if not isinstance(result, dict):
        return safe
    agreement = result.get("agreement")
    if agreement not in {"yes", "no", "unclear"}:
        return safe
    corrections = result.get("corrections")
    return {
        "agreement": agreement,
        "corrections": corrections if isinstance(corrections, str) else None,
    }
```

- [ ] **Step 5: Re-run, pass.**

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/prompts/dialog_parse_seller_agreement.md avito-monitor/app/services/llm_analyzer.py avito-monitor/tests/seller_dialog/test_llm_dispatchers_phase_b.py
git commit -m "feat(llm): parse_seller_agreement dispatcher"
```

---

## Wave 3 — Service layer + Worker + Handler

### Task 8: Dialog topics service (CRUD + ad-hoc + state)

**Files:**
- Create: `avito-monitor/app/services/dialog_topics/__init__.py`
- Create: `avito-monitor/app/services/dialog_topics/service.py`
- Create: `avito-monitor/app/services/dialog_topics/state.py`
- Create: `avito-monitor/tests/dialog_topics/__init__.py`
- Test: `avito-monitor/tests/dialog_topics/test_service.py`

- [ ] **Step 1: Write failing tests**

File `avito-monitor/tests/dialog_topics/__init__.py`: empty.

File `avito-monitor/tests/dialog_topics/test_service.py`:

```python
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
```

- [ ] **Step 2: Run, fail.**

Expected: `ImportError: cannot import name 'slugify_topic_key'`.

- [ ] **Step 3: Implement `service.py`**

File `avito-monitor/app/services/dialog_topics/__init__.py`: empty.

File `avito-monitor/app/services/dialog_topics/service.py`:

```python
"""Dialog topics service — CRUD + ad-hoc creation."""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SLUG_CYR = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "abvgdeezziyklmnoprstufhcss_y_eua",
)


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
```

- [ ] **Step 4: Implement `state.py` for per-dialog topic state machine**

File `avito-monitor/app/services/dialog_topics/state.py`:

```python
"""Per-dialog topic state helpers (pure DB, no LLM)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SellerDialogTopic, DialogTopic


async def init_dialog_topics(
    session: AsyncSession,
    *,
    dialog_id: uuid.UUID,
    topic_keys: list[str],
) -> None:
    """Insert one SellerDialogTopic per checked key with status='pending'.
    Priority equals position in the list."""
    for i, key in enumerate(topic_keys):
        session.add(SellerDialogTopic(
            id=uuid.uuid4(),
            dialog_id=dialog_id,
            topic_key=key,
            priority=i,
            status="pending",
        ))
    await session.flush()


async def pick_next_pending(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> SellerDialogTopic | None:
    """Return the highest-priority pending topic or None."""
    stmt = (
        select(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "pending",
        )
        .order_by(SellerDialogTopic.priority)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_asked_topic(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> SellerDialogTopic | None:
    """Return the topic currently awaiting an answer (status='asked', no answer)."""
    stmt = (
        select(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "asked",
            SellerDialogTopic.answer_text.is_(None),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_asked(
    session: AsyncSession, topic_id: uuid.UUID, *,
    question_text: str, question_msg_id: str | None,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(
            status="asked",
            question_text=question_text,
            question_msg_id=question_msg_id,
            asked_at=datetime.now(tz=timezone.utc),
        )
    )


async def mark_answered(
    session: AsyncSession, topic_id: uuid.UUID, *,
    answer_text: str, answer_msg_id: str | None = None,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(
            status="answered",
            answer_text=answer_text,
            answer_msg_id=answer_msg_id,
            answered_at=datetime.now(tz=timezone.utc),
        )
    )


async def mark_skipped(
    session: AsyncSession, topic_id: uuid.UUID,
) -> None:
    await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(status="skipped", answered_at=datetime.now(tz=timezone.utc))
    )


async def increment_retry(
    session: AsyncSession, topic_id: uuid.UUID,
) -> int:
    """Increment retry_count and return new value."""
    res = await session.execute(
        update(SellerDialogTopic)
        .where(SellerDialogTopic.id == topic_id)
        .values(retry_count=SellerDialogTopic.retry_count + 1)
        .returning(SellerDialogTopic.retry_count)
    )
    return res.scalar_one()


async def all_open_topics(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> list[dict]:
    """List open topics for context in parse_topic_answer (for side_topics)."""
    stmt = (
        select(SellerDialogTopic.topic_key, DialogTopic.title)
        .join(DialogTopic, DialogTopic.key == SellerDialogTopic.topic_key)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status.in_(("pending", "asked")),
        )
    )
    return [{"key": k, "title": t} for k, t in (await session.execute(stmt)).all()]


async def answered_topics(
    session: AsyncSession, dialog_id: uuid.UUID,
) -> list[tuple]:
    """Return list of (DialogTopic, answer_text) for all answered topics in priority order.
    Used by formulate_recap."""
    stmt = (
        select(DialogTopic, SellerDialogTopic.answer_text)
        .join(SellerDialogTopic, SellerDialogTopic.topic_key == DialogTopic.key)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status == "answered",
        )
        .order_by(SellerDialogTopic.priority)
    )
    return [(t, a) for t, a in (await session.execute(stmt)).all()]


async def count_open(session: AsyncSession, dialog_id: uuid.UUID) -> int:
    """Count topics still pending or asked (i.e. not done)."""
    stmt = select(SellerDialogTopic).where(
        SellerDialogTopic.dialog_id == dialog_id,
        SellerDialogTopic.status.in_(("pending", "asked")),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return len(rows)
```

- [ ] **Step 5: Run tests, pass**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/dialog_topics/ -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/services/dialog_topics/ avito-monitor/tests/dialog_topics/
git commit -m "feat(dialog-topics): service (quick_add + slugify) + per-dialog state helpers"
```

---

### Task 9: Worker `dialog_tick_questions`

**Files:**
- Modify: `avito-monitor/app/tasks/seller_dialog_tasks.py`
- Test: `avito-monitor/tests/seller_dialog/test_dialog_tick_questions.py`

- [ ] **Step 1: Write failing tests**

File `avito-monitor/tests/seller_dialog/test_dialog_tick_questions.py`:

```python
"""Tests for dialog_tick_questions state machine."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_first_tick_sends_opening_line_then_picks_first_pending():
    """First tick (no topics asked yet) sends opening line, then first question."""
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    session = AsyncMock()
    xapi = AsyncMock()
    xapi.send_text = AsyncMock(side_effect=[{"id": "m_open"}, {"id": "m_q1"}])

    topic = MagicMock()
    topic.id = uuid.uuid4()
    topic.title = "АКБ %"
    topic.default_phrasing = "x"
    topic.expected_format = "percent"
    topic.topic_key = "battery_health"

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.count_open",
               new=AsyncMock(return_value=1)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.pick_next_pending",
               new=AsyncMock(return_value=topic)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.mark_asked",
               new=AsyncMock()) as m_mark, \
         patch("app.tasks.seller_dialog_tasks.formulate_question",
               new=AsyncMock(return_value="Какой % АКБ?")), \
         patch("app.tasks.seller_dialog_tasks.has_started_questions",
               new=AsyncMock(return_value=False)), \
         patch("app.tasks.seller_dialog_tasks.asyncio.sleep",
               new=AsyncMock()):
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    # Two sends: opening + first question
    assert xapi.send_text.await_count == 2
    first_call = xapi.send_text.call_args_list[0]
    assert "вопросов по Вашему аппарату" in first_call.args[1]
    second_call = xapi.send_text.call_args_list[1]
    assert second_call.args[1] == "Какой % АКБ?"
    m_mark.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_waits_when_topic_already_asked():
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    asked_topic = MagicMock()
    asked_topic.id = uuid.uuid4()

    session = AsyncMock()
    xapi = AsyncMock()

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=asked_topic)):
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    xapi.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_tick_sends_recap_when_all_topics_done():
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    session = AsyncMock()
    xapi = AsyncMock()
    xapi.send_text = AsyncMock(return_value={"id": "m_recap"})

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.count_open",
               new=AsyncMock(return_value=0)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.pick_next_pending",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.answered_topics",
               new=AsyncMock(return_value=[(MagicMock(title="АКБ %"), "87%")])), \
         patch("app.tasks.seller_dialog_tasks.formulate_recap",
               new=AsyncMock(return_value="Итак: АКБ 87%. Всё верно?")), \
         patch("app.tasks.seller_dialog_tasks.has_started_questions",
               new=AsyncMock(return_value=True)), \
         patch("app.tasks.seller_dialog_tasks.sd_service.set_recap",
               new=AsyncMock()) as m_set:
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    xapi.send_text.assert_awaited_once()
    assert "Итак" in xapi.send_text.call_args.args[1]
    m_set.assert_awaited_once()
```

- [ ] **Step 2: Run, fail**

Expected: `ImportError: cannot import name '_dialog_tick_questions_impl'`.

- [ ] **Step 3: Add support helpers + task in `seller_dialog_tasks.py`**

Append at the bottom of `avito-monitor/app/tasks/seller_dialog_tasks.py`:

```python
# ---------------------------- Phase B ---------------------------------------
import asyncio
from app.services.dialog_topics import state as topic_state
from app.services.seller_dialog.constants import OPENING_LINE, RECAP_PENDING_ANSWER
from app.services.llm_analyzer import formulate_question, formulate_recap


async def has_started_questions(session, dialog_id) -> bool:
    """True if at least one topic was already asked/answered/skipped."""
    from sqlalchemy import select, func
    from app.db.models import SellerDialogTopic
    res = await session.execute(
        select(func.count())
        .select_from(SellerDialogTopic)
        .where(
            SellerDialogTopic.dialog_id == dialog_id,
            SellerDialogTopic.status.in_(("asked", "answered", "skipped")),
        )
    )
    return (res.scalar() or 0) > 0


async def _dialog_tick_questions_impl(session, xapi, dialog_id):
    """Pure-logic implementation, separated for testability."""
    dialog = await sd_service.get_dialog(session, dialog_id)
    if dialog is None or dialog.stage != "questions" or dialog.operator_mode:
        return

    # 1. If a topic is currently awaiting an answer — wait.
    asked = await topic_state.get_asked_topic(session, dialog_id)
    if asked is not None:
        return

    # 2. If first tick — send opening line first.
    if not await has_started_questions(session, dialog_id):
        opening_resp = await xapi.send_text(dialog.channel_id, OPENING_LINE)
        # Optional persist into messenger_messages happens via send wrapper if used;
        # else skip — opening is a courtesy, not part of state.
        await asyncio.sleep(3)

    # 3. Pick next pending topic.
    next_topic = await topic_state.pick_next_pending(session, dialog_id)
    if next_topic is not None:
        # Load full topic metadata for the LLM
        from sqlalchemy import select
        from app.db.models import DialogTopic
        topic_meta = (await session.execute(
            select(DialogTopic).where(DialogTopic.key == next_topic.topic_key)
        )).scalar_one()
        history_tail = []  # could be filled from messenger_messages — keep MVP simple
        question = await formulate_question(topic_meta, history_tail)
        send_resp = await xapi.send_text(dialog.channel_id, question)
        await topic_state.mark_asked(
            session, next_topic.id,
            question_text=question,
            question_msg_id=send_resp.get("id") if isinstance(send_resp, dict) else None,
        )
        await session.commit()
        return

    # 4. All topics done — formulate recap if not yet sent.
    if dialog.recap_status is None:
        answered = await topic_state.answered_topics(session, dialog_id)
        recap = await formulate_recap(answered)
        send_resp = await xapi.send_text(dialog.channel_id, recap)
        await sd_service.set_recap(
            session, dialog_id,
            text=recap,
            msg_id=send_resp.get("id") if isinstance(send_resp, dict) else None,
            status=RECAP_PENDING_ANSWER,
        )
        await session.commit()
        return

    # 5. recap is sent — waiting for seller's reply, nothing to do.


@broker.task(task_name="app.tasks.seller_dialog_tasks.dialog_tick_questions")
async def dialog_tick_questions(dialog_id: str) -> dict:
    """TaskIQ entrypoint for the questions stage state machine tick."""
    from app.db.base import get_sessionmaker
    from app.services.messenger_bot.runner import make_xapi_client

    sessionmaker = get_sessionmaker()
    xapi_raw = make_xapi_client()
    xapi = _XapiMessengerAdapter(xapi_raw)
    async with sessionmaker() as session:
        try:
            await _dialog_tick_questions_impl(session, xapi, uuid.UUID(dialog_id))
        except Exception:
            log.exception("dialog_tick_questions failed dialog=%s — operator_mode", dialog_id)
            try:
                await sd_service.set_operator_mode(session, uuid.UUID(dialog_id), True)
                await session.commit()
            except Exception:
                log.exception("operator_mode cleanup also failed")
            raise
    return {"dialog_id": dialog_id, "ok": True}
```

- [ ] **Step 4: Add `get_dialog` and `set_recap` helpers in `service.py`**

In `avito-monitor/app/services/seller_dialog/service.py`, append:

```python
async def get_dialog(session: AsyncSession, dialog_id: uuid.UUID) -> SellerDialog | None:
    return await session.get(SellerDialog, dialog_id)


async def set_recap(
    session: AsyncSession, dialog_id: uuid.UUID, *,
    text: str, msg_id: str | None, status: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(
            recap_text=text,
            recap_msg_id=msg_id,
            recap_status=status,
            last_event_at=datetime.now(tz=timezone.utc),
        )
    )


async def set_recap_status(
    session: AsyncSession, dialog_id: uuid.UUID, status: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(recap_status=status,
                last_event_at=datetime.now(tz=timezone.utc))
    )
```

- [ ] **Step 5: Run worker tests, pass**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_dialog_tick_questions.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/tasks/seller_dialog_tasks.py avito-monitor/app/services/seller_dialog/service.py avito-monitor/tests/seller_dialog/test_dialog_tick_questions.py
git commit -m "feat(worker): dialog_tick_questions state machine + service helpers"
```

---

### Task 10: SSE handler extension for stage='questions'

**Files:**
- Modify: `avito-monitor/app/services/seller_dialog/handler.py`
- Test: `avito-monitor/tests/seller_dialog/test_handler_phase_b.py`

- [ ] **Step 1: Write failing tests**

File `avito-monitor/tests/seller_dialog/test_handler_phase_b.py`:

```python
"""Handler tests for stage='questions' branch."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_inbound_in_questions_stage_parses_and_marks_answered():
    from app.services.seller_dialog.handler import handle_seller_inbound

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None

    asked_topic = MagicMock()
    asked_topic.id = uuid.uuid4()
    asked_topic.retry_count = 0
    asked_topic.topic_key = "battery_health"
    asked_topic.title = "АКБ %"
    asked_topic.default_phrasing = ""
    asked_topic.expected_format = "percent"

    session = AsyncMock()
    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.ensure_chat_row",
               new=AsyncMock()), \
         patch("app.services.seller_dialog.handler.topic_state.get_asked_topic",
               new=AsyncMock(return_value=asked_topic)), \
         patch("app.services.seller_dialog.handler.topic_state.all_open_topics",
               new=AsyncMock(return_value=[])), \
         patch("app.services.seller_dialog.handler.parse_topic_answer",
               new=AsyncMock(return_value={
                   "status": "answered", "extracted": "87%", "side_topics": [],
               })), \
         patch("app.services.seller_dialog.handler.topic_state.mark_answered",
               new=AsyncMock()) as m_mark, \
         patch("app.services.seller_dialog.handler.dialog_tick_questions") as m_tick:
        m_tick.kiq = AsyncMock()
        await handle_seller_inbound(
            session=session, channel_id="ch_x", message_id="m1",
            author_id="seller", text="87 процентов",
        )

    m_mark.assert_awaited_once()
    m_tick.kiq.assert_awaited_once_with(str(dialog.id))


@pytest.mark.asyncio
async def test_inbound_recap_yes_confirms_and_pings_operator():
    from app.services.seller_dialog.handler import handle_seller_inbound

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = "pending_answer"

    session = AsyncMock()
    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.ensure_chat_row",
               new=AsyncMock()), \
         patch("app.services.seller_dialog.handler.parse_seller_agreement",
               new=AsyncMock(return_value={"agreement": "yes", "corrections": None})), \
         patch("app.services.seller_dialog.handler.sd_service.set_recap_status",
               new=AsyncMock()) as m_set, \
         patch("app.services.seller_dialog.handler.enqueue_tg_ping",
               new=AsyncMock()) as m_ping:
        await handle_seller_inbound(
            session=session, channel_id="ch_x", message_id="m1",
            author_id="seller", text="да всё верно",
        )

    m_set.assert_awaited_once()
    m_ping.assert_awaited_once()
    assert m_ping.call_args.args[1] == "seller_dialog_ready_to_negotiate"
```

- [ ] **Step 2: Run, fail.**

- [ ] **Step 3: Extend `handler.py`**

In `avito-monitor/app/services/seller_dialog/handler.py`, after existing imports add:

```python
from app.services.dialog_topics import state as topic_state
from app.services.llm_analyzer import parse_seller_agreement, parse_topic_answer
from app.services.seller_dialog.constants import (
    STAGE_QUESTIONS,
    RECAP_PENDING_ANSWER,
    RECAP_CONFIRMED,
)
from app.services.seller_dialog import service as sd_service
from app.tasks.seller_dialog_tasks import dialog_tick_questions
from app.services.notifications import enqueue_tg_ping
```

(If circular import — defer `dialog_tick_questions` import inside function body.)

In the existing `handle_seller_inbound`, after the recovery branch for contact stage (where stage transitions to questions_setup), add a new branch:

```python
    # ── Stage QUESTIONS branch ──────────────────────────────────────────
    if dialog.stage == STAGE_QUESTIONS:
        # If recap awaits answer — classify seller's reply
        if dialog.recap_status == RECAP_PENDING_ANSWER:
            ag = await parse_seller_agreement(text or "")
            if ag["agreement"] == "yes":
                await sd_service.set_recap_status(session, dialog.id, RECAP_CONFIRMED)
                await session.commit()
                await enqueue_tg_ping(session, "seller_dialog_ready_to_negotiate", dialog.id)
            elif ag["agreement"] == "no":
                # Disputed — operator takes over
                from app.services.seller_dialog.service import set_operator_mode
                await set_operator_mode(session, dialog.id, True)
                await session.commit()
            # unclear → silently store msg + wait; operator may step in
            return

        # Otherwise — match inbound to current asked topic
        asked = await topic_state.get_asked_topic(session, dialog.id)
        if asked is None:
            return  # spam / out-of-band
        open_topics = await topic_state.all_open_topics(session, dialog.id)
        parsed = await parse_topic_answer(asked, text or "", open_topics=open_topics)
        if parsed["status"] == "answered":
            await topic_state.mark_answered(
                session, asked.id,
                answer_text=parsed["extracted"] or text or "",
                answer_msg_id=message_id,
            )
            for st in parsed["side_topics"]:
                # Find target by topic_key + dialog
                from sqlalchemy import select
                from app.db.models import SellerDialogTopic as SDT
                target = (await session.execute(
                    select(SDT).where(
                        SDT.dialog_id == dialog.id,
                        SDT.topic_key == st["topic_key"],
                        SDT.status.in_(("pending", "asked")),
                    )
                )).scalar_one_or_none()
                if target:
                    await topic_state.mark_answered(
                        session, target.id,
                        answer_text=st.get("extracted") or "",
                        answer_msg_id=message_id,
                    )
        else:  # unclear or off_topic
            new_retry = await topic_state.increment_retry(session, asked.id)
            if new_retry >= 2:
                await topic_state.mark_skipped(session, asked.id)
        await session.commit()
        await dialog_tick_questions.kiq(str(dialog.id))
        return
```

- [ ] **Step 4: Run handler tests, pass**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/seller_dialog/test_handler_phase_b.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/seller_dialog/handler.py avito-monitor/tests/seller_dialog/test_handler_phase_b.py
git commit -m "feat(handler): stage=questions branch — topic answer + recap reply parsing"
```

---

## Wave 4 — UI + endpoints

### Task 11: View — 3rd column + profile filter exposed in template

**Files:**
- Modify: `avito-monitor/app/services/seller_dialog_view.py`
- Test: `avito-monitor/tests/seller_dialog/test_view_phase_b.py`

- [ ] **Step 1: Write failing tests**

File `avito-monitor/tests/seller_dialog/test_view_phase_b.py`:

```python
"""View tests for Phase B (3rd column + filter)."""
import uuid
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_query_returns_three_columns_including_questions():
    from app.services.seller_dialog_view import query_kanban_cards, PHASE_B_STAGES

    session = AsyncMock()
    rows = AsyncMock()
    rows.all = lambda: []
    session.execute = AsyncMock(return_value=rows)

    out = await query_kanban_cards(session, user_id=uuid.uuid4())
    assert set(out.keys()) >= {"contact", "questions_setup", "questions"}
    assert "questions" in PHASE_B_STAGES


@pytest.mark.asyncio
async def test_query_filters_by_profile_id():
    from app.services.seller_dialog_view import query_kanban_cards, KanbanFilters

    session = AsyncMock()
    rows = AsyncMock()
    rows.all = lambda: []
    session.execute = AsyncMock(return_value=rows)
    pid = uuid.uuid4()
    await query_kanban_cards(session, user_id=uuid.uuid4(),
                             filters=KanbanFilters(profile_ids=[pid]))
    # Just assert the query was built (compiled SQL contains profile_id)
    sql_text = str(session.execute.call_args.args[0])
    assert "profile_id" in sql_text.lower()
```

- [ ] **Step 2: Run, watch test 1 fail (PHASE_B_STAGES not exported).**

- [ ] **Step 3: Update view**

In `avito-monitor/app/services/seller_dialog_view.py`, replace:

```python
PHASE_A_STAGES = [STAGE_CONTACT, STAGE_QUESTIONS_SETUP]
```

with:

```python
from app.services.seller_dialog.constants import STAGE_QUESTIONS

PHASE_B_STAGES = [STAGE_CONTACT, STAGE_QUESTIONS_SETUP, STAGE_QUESTIONS]
# Backwards-compat alias (callers using the old name still work).
PHASE_A_STAGES = PHASE_B_STAGES
```

Also replace any inline reference to `PHASE_A_STAGES` in the function with `PHASE_B_STAGES`.

- [ ] **Step 4: Run, pass**

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/seller_dialog_view.py avito-monitor/tests/seller_dialog/test_view_phase_b.py
git commit -m "feat(view): kanban includes questions stage + profile filter coverage"
```

---

### Task 12: HTTP endpoints

**Files:**
- Modify: `avito-monitor/app/web/routers.py`

5 new endpoints (no separate tests — covered by smoke and existing patterns):

- [ ] **Step 1: Render setup-modal endpoint**

Append to `avito-monitor/app/web/routers.py`:

```python
@router.get("/dialogs/{dialog_id}/setup", response_class=HTMLResponse)
async def render_setup_modal(
    dialog_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
):
    """HTML fragment for the setup modal (loaded by HTMX/JS into <dialog>)."""
    from app.db.models import SellerDialog, Listing
    from app.services.dialog_topics.service import topics_for_profile
    from sqlalchemy import select

    dialog = (await session.execute(
        select(SellerDialog).where(SellerDialog.id == dialog_id)
    )).scalar_one_or_none()
    if dialog is None:
        raise HTTPException(404, "Dialog not found")
    listing = (await session.execute(
        select(Listing).where(Listing.id == dialog.listing_id)
    )).scalar_one()
    topics = await topics_for_profile(session, dialog.profile_id)
    return templates.TemplateResponse(
        "_partials/setup_modal.html",
        {"request": request, "dialog": dialog, "listing": listing, "topics": topics},
    )
```

- [ ] **Step 2: Start-questions endpoint**

Append:

```python
@router.post("/dialogs/{dialog_id}/start-questions", response_model=None)
async def start_questions(
    dialog_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    """Operator clicked Запустить опрос: persist checked topics + transition."""
    from app.db.models import SellerDialog
    from app.services.dialog_topics.state import init_dialog_topics
    from app.services.seller_dialog.service import set_stage
    from app.services.seller_dialog.constants import STAGE_QUESTIONS
    from app.tasks.seller_dialog_tasks import dialog_tick_questions
    from sqlalchemy import select

    form = await request.form()
    topic_keys = form.getlist("topics")
    if not topic_keys:
        raise HTTPException(400, "select at least one topic")

    dialog = (await session.execute(
        select(SellerDialog).where(SellerDialog.id == dialog_id)
    )).scalar_one_or_none()
    if dialog is None:
        raise HTTPException(404, "Dialog not found")

    await init_dialog_topics(session, dialog_id=dialog_id, topic_keys=topic_keys)
    await set_stage(session, dialog_id, STAGE_QUESTIONS)
    await session.commit()
    await dialog_tick_questions.kiq(str(dialog_id))

    return RedirectResponse("/listings?tab=in_progress",
                            status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 3: Quick-add ad-hoc topic endpoint**

Append:

```python
@router.post("/dialog-topics/quick-add", response_class=HTMLResponse)
async def quick_add_topic_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
):
    """Ad-hoc topic creation from the setup modal. Returns the updated topic list fragment."""
    from app.services.dialog_topics.service import quick_add_topic, topics_for_profile
    form = await request.form()
    question_text = (form.get("question_text") or "").strip()
    profile_id_str = form.get("profile_id")
    if not question_text or not profile_id_str:
        raise HTTPException(400, "question_text + profile_id required")
    pid = uuid.UUID(profile_id_str)
    await quick_add_topic(session, profile_id=pid, question_text=question_text)
    topics = await topics_for_profile(session, pid)
    return templates.TemplateResponse(
        "_partials/setup_modal.html",
        {"request": request, "topics": topics, "_topics_only": True,
         "dialog": None, "listing": None},
    )
```

- [ ] **Step 4: Topic library list + add endpoints**

Append:

```python
@router.get("/dialog-topics", response_class=HTMLResponse)
async def topic_library_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
):
    from app.services.dialog_topics.service import list_topics
    topics = await list_topics(session)
    return templates.TemplateResponse(
        "dialog_topics.html",
        {"request": request, "topics": topics},
    )


@router.post("/dialog-topics/add", response_model=None)
async def topic_library_add(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> RedirectResponse:
    from app.services.dialog_topics.service import quick_add_topic
    form = await request.form()
    question_text = (form.get("question_text") or "").strip()
    profile_id_str = form.get("profile_id")
    if not question_text or not profile_id_str:
        raise HTTPException(400, "question_text + profile_id required")
    await quick_add_topic(
        session, profile_id=uuid.UUID(profile_id_str), question_text=question_text,
    )
    return RedirectResponse("/dialog-topics", status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/web/routers.py
git commit -m "feat(http): 5 endpoints — setup modal, start-questions, quick-add, topic library"
```

---

### Task 13: Templates — kanban + modal + library + 3rd column card

**Files:**
- Create: `avito-monitor/app/web/templates/_partials/kanban_card_questions.html`
- Create: `avito-monitor/app/web/templates/_partials/setup_modal.html`
- Create: `avito-monitor/app/web/templates/dialog_topics.html`
- Modify: `avito-monitor/app/web/templates/listings_kanban.html`
- Modify: `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html`

- [ ] **Step 1: Write `kanban_card_questions.html`**

File `avito-monitor/app/web/templates/_partials/kanban_card_questions.html`:

```html
{# Kanban card — Опрос stage. Shows progress + reject button. #}
<div class="bg-white rounded-lg shadow-sm hover:shadow-md transition p-3 mb-2 border-2 border-emerald-300">
  <a href="https://www.avito.ru/{{ card.avito_id }}" target="_blank" rel="noopener noreferrer" class="block">
    <div class="flex gap-3">
      {% if card.image_url %}
        <img src="{{ card.image_url }}" alt="" class="w-16 h-16 rounded object-cover flex-shrink-0" loading="lazy">
      {% else %}
        <div class="w-16 h-16 rounded bg-stone-200 flex-shrink-0"></div>
      {% endif %}
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium text-stone-800 truncate">{{ card.title }}</div>
        <div class="text-xs text-stone-500 mt-0.5">{{ card.profile_name }}</div>
        {% if card.price %}
          <div class="text-sm font-semibold text-emerald-700 mt-1">
            {{ "{:,}".format(card.price).replace(",", " ") }} ₽
          </div>
        {% endif %}
      </div>
    </div>
  </a>
  <div class="mt-2 pt-2 border-t border-stone-100 flex items-center justify-between gap-2 text-xs">
    <span class="px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-medium">
      идёт опрос
    </span>
    <form method="post" action="/listings/{{ card.profile_id }}/{{ card.listing_id }}/action" class="flex-shrink-0">
      <input type="hidden" name="action" value="reject">
      <input type="hidden" name="return_to" value="/listings?tab=in_progress">
      <input type="hidden" name="from_tab" value="in_progress">
      <button type="submit" aria-label="Отклонить лот"
              onclick="return confirm('Отклонить лот?')"
              class="text-stone-500 hover:text-rose-700 transition px-1.5 py-0.5 rounded hover:bg-rose-50">
        × Отклонить
      </button>
    </form>
  </div>
</div>
```

- [ ] **Step 2: Write `setup_modal.html`**

File `avito-monitor/app/web/templates/_partials/setup_modal.html`:

```html
{% if _topics_only %}
<ul id="topic-list" class="space-y-1">
{% for t in topics %}
  <li>
    <label class="flex items-start gap-2 cursor-pointer">
      <input type="checkbox" name="topics" value="{{ t.key }}" class="mt-1">
      <span class="text-sm">
        <span class="text-stone-800">{{ t.title }}</span>
        {% if t.category %}<span class="text-xs text-stone-400 ml-1">[{{ t.category }}]</span>{% endif %}
      </span>
    </label>
  </li>
{% endfor %}
</ul>
{% else %}
<div class="bg-white rounded-lg p-6 max-w-lg w-full">
  <h2 class="text-lg font-semibold mb-3">
    Настройка опроса — {{ listing.title }}
  </h2>
  <form method="post" action="/dialogs/{{ dialog.id }}/start-questions" class="space-y-4">
    <div>
      <p class="text-sm text-stone-600 mb-2">Выберите темы для опроса:</p>
      <ul id="topic-list" class="space-y-1 max-h-72 overflow-y-auto">
        {% for t in topics %}
        <li>
          <label class="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" name="topics" value="{{ t.key }}" class="mt-1">
            <span class="text-sm">
              <span class="text-stone-800">{{ t.title }}</span>
              {% if t.category %}<span class="text-xs text-stone-400 ml-1">[{{ t.category }}]</span>{% endif %}
            </span>
          </label>
        </li>
        {% endfor %}
      </ul>
    </div>
    <div class="border-t border-stone-200 pt-3">
      <label class="block text-sm text-stone-600 mb-1">Добавить свой вопрос:</label>
      <div class="flex gap-2">
        <input type="text" id="adhoc-text" placeholder="Например: сколько раз падал?"
               class="flex-1 border border-stone-300 rounded px-2 py-1 text-sm">
        <button type="button" id="adhoc-btn"
                data-profile="{{ dialog.profile_id }}"
                class="px-3 py-1 text-sm bg-stone-100 hover:bg-stone-200 rounded">+ добавить</button>
      </div>
    </div>
    <div class="flex justify-end gap-2 border-t border-stone-200 pt-3">
      <button type="button" id="cancel-btn"
              class="px-3 py-1 text-sm text-stone-600 hover:text-stone-900">Отмена</button>
      <button type="submit"
              class="px-4 py-1 text-sm bg-emerald-600 hover:bg-emerald-700 text-white rounded">
        Запустить опрос
      </button>
    </div>
  </form>
</div>
<script>
(function(){
  const adhocBtn = document.getElementById('adhoc-btn');
  const adhocTxt = document.getElementById('adhoc-text');
  const cancelBtn = document.getElementById('cancel-btn');
  const dialogEl = document.querySelector('dialog#setup-dialog');
  adhocBtn.addEventListener('click', async () => {
    const text = adhocTxt.value.trim();
    if (!text) return;
    const fd = new FormData();
    fd.append('question_text', text);
    fd.append('profile_id', adhocBtn.dataset.profile);
    const resp = await fetch('/dialog-topics/quick-add', {method:'POST', body: fd});
    if (resp.ok) {
      const html = await resp.text();
      document.getElementById('topic-list').outerHTML = html;
      adhocTxt.value = '';
    }
  });
  cancelBtn.addEventListener('click', () => dialogEl.close());
})();
</script>
{% endif %}
```

- [ ] **Step 3: Write `dialog_topics.html`**

File `avito-monitor/app/web/templates/dialog_topics.html`:

```html
{% extends "_layout.html" %}
{% block content %}
<div class="max-w-3xl mx-auto py-6">
  <h1 class="text-xl font-semibold mb-4">Библиотека тем для опроса</h1>
  <table class="w-full text-sm">
    <thead class="text-left text-xs text-stone-500 border-b">
      <tr>
        <th class="pb-2">Ключ</th>
        <th class="pb-2">Название</th>
        <th class="pb-2">Категория</th>
        <th class="pb-2">Формат</th>
        <th class="pb-2">Источник</th>
      </tr>
    </thead>
    <tbody>
    {% for t in topics %}
      <tr class="border-b border-stone-100">
        <td class="py-1.5 font-mono text-xs">{{ t.key }}</td>
        <td class="py-1.5">{{ t.title }}</td>
        <td class="py-1.5">{{ t.category }}</td>
        <td class="py-1.5">{{ t.expected_format }}</td>
        <td class="py-1.5 text-xs text-stone-400">{{ t.created_by }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <form method="post" action="/dialog-topics/add" class="mt-6 flex gap-2">
    <input type="text" name="question_text" placeholder="Новая тема (формулировка вопроса)"
           class="flex-1 border border-stone-300 rounded px-2 py-1 text-sm" required>
    <input type="hidden" name="profile_id" value="{{ profile_id_first }}">
    <button type="submit" class="px-4 py-1 text-sm bg-emerald-600 hover:bg-emerald-700 text-white rounded">
      Добавить
    </button>
  </form>
</div>
{% endblock %}
```

(Note: `profile_id_first` must be passed by route — extend `topic_library_page` to pull the user's first profile id and pass it.)

Update endpoint in `routers.py`:

```python
@router.get("/dialog-topics", response_class=HTMLResponse)
async def topic_library_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
):
    from app.db.models import SearchProfile
    from sqlalchemy import select
    from app.services.dialog_topics.service import list_topics

    topics = await list_topics(session)
    pid_row = (await session.execute(
        select(SearchProfile.id).where(SearchProfile.user_id == user.id).limit(1)
    )).scalar_one_or_none()
    return templates.TemplateResponse(
        "dialog_topics.html",
        {"request": request, "topics": topics, "profile_id_first": pid_row},
    )
```

- [ ] **Step 4: Update `listings_kanban.html`** — 3rd column + filter

In `avito-monitor/app/web/templates/listings_kanban.html`, just before the column container, add filter dropdown:

```html
<form method="get" class="mb-4 flex items-center gap-2">
  <input type="hidden" name="tab" value="in_progress">
  <label class="text-sm text-stone-600">Профиль:</label>
  <select name="profile_id" onchange="this.form.submit()"
          class="border border-stone-300 rounded px-2 py-1 text-sm">
    <option value="">Все профили</option>
    {% for p in profiles %}
    <option value="{{ p.id }}" {% if selected_profile_id == p.id|string %}selected{% endif %}>
      {{ p.name }}
    </option>
    {% endfor %}
  </select>
</form>
```

After the existing 2 columns, add the third column block:

```html
<div class="kanban-column">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-sm font-semibold text-stone-700">Опрос</h3>
    <span class="text-xs text-stone-500">{{ cards.questions|length }}</span>
  </div>
  {% for card in cards.questions %}
    {% include "_partials/kanban_card_questions.html" %}
  {% endfor %}
</div>

<dialog id="setup-dialog" class="rounded-lg shadow-xl backdrop:bg-black/40 backdrop:backdrop-blur-sm">
</dialog>
<script>
document.body.addEventListener('click', async (e) => {
  const t = e.target.closest('.setup-modal-trigger');
  if (!t) return;
  e.preventDefault();
  const id = t.dataset.dialogId;
  const r = await fetch(`/dialogs/${id}/setup`);
  if (!r.ok) { alert('Ошибка загрузки настройки'); return; }
  const html = await r.text();
  const dlg = document.getElementById('setup-dialog');
  dlg.innerHTML = html;
  dlg.showModal();
});
</script>
```

(The view endpoint that renders this template must also pass `profiles` and `selected_profile_id`. Update it in the listings route — see Task 14.)

- [ ] **Step 5: Wire modal trigger in `kanban_card_questions_setup.html`**

In `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html`, replace the `➜ настрой опрос` badge with a clickable trigger:

```html
<a href="#" class="setup-modal-trigger px-2 py-0.5 bg-amber-200 text-amber-900 rounded font-medium hover:bg-amber-300"
   data-dialog-id="{{ card.dialog_id }}">
  ➜ настрой опрос
</a>
```

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/web/templates/
git commit -m "feat(ui): 3rd column 'Опрос' + setup modal + topic library page + profile filter"
```

---

### Task 14: Wire filter + profiles list into the listings route

**Files:**
- Modify: `avito-monitor/app/web/routers.py`

- [ ] **Step 1: Find the in_progress kanban route handler**

Run: `grep -nE "tab=='in_progress'|tab_in_progress|cards =|query_kanban_cards" avito-monitor/app/web/routers.py | head -20`

- [ ] **Step 2: Extend it to pass profiles + selected_profile_id + apply filter**

In the relevant route (locate by `tab == "in_progress"` branch), modify to:

```python
# (where the in-progress kanban is rendered)
from app.db.models import SearchProfile
from app.services.seller_dialog_view import KanbanFilters

selected_pid_raw = request.query_params.get("profile_id") or ""
filters = KanbanFilters(profile_ids=[uuid.UUID(selected_pid_raw)] if selected_pid_raw else [])

profiles_rows = (await session.execute(
    select(SearchProfile.id, SearchProfile.name).where(SearchProfile.user_id == user.id)
)).all()
profiles = [{"id": str(r[0]), "name": r[1]} for r in profiles_rows]

cards = await query_kanban_cards(session, user_id=user.id, filters=filters)
# ... existing template render — add: profiles=profiles, selected_profile_id=selected_pid_raw
```

- [ ] **Step 3: Visual sanity check**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "http://localhost:8000/listings?tab=in_progress" -H "Cookie: ..."
```

Expected: 200 or 303 (auth).

- [ ] **Step 4: Commit**

```bash
git add avito-monitor/app/web/routers.py
git commit -m "feat(http): pass profiles + selected_profile_id to kanban view + apply filter"
```

---

## Wave 5 — TG pings + broker registration + smoke

### Task 15: TG pings integration

**Files:**
- Modify: `avito-monitor/app/tasks/notifications.py`
- Create new function: `enqueue_tg_ping` in `avito-monitor/app/services/notifications.py` (or matching existing path)

- [ ] **Step 1: Locate notifications type enum**

Run: `grep -nE "NotificationType|class Notification|seller_dialog_" avito-monitor/app/tasks/notifications.py avito-monitor/app/db/models/notification.py 2>/dev/null | head -20`

- [ ] **Step 2: Add 2 new types**

In the notifications enum/constants, add:

```python
NOTIFICATION_TYPE_SELLER_DIALOG_READY_TO_SETUP = "seller_dialog_ready_to_setup"
NOTIFICATION_TYPE_SELLER_DIALOG_READY_TO_NEGOTIATE = "seller_dialog_ready_to_negotiate"
```

- [ ] **Step 3: Add `enqueue_tg_ping` helper**

Create `avito-monitor/app/services/notifications.py` (if not already present) OR append in the existing notifications service module:

```python
async def enqueue_tg_ping(session, notif_type: str, dialog_id) -> None:
    """Persist a TG-ping notification row tied to a seller dialog.
    The dispatch_pending worker picks it up and sends through aiogram."""
    from sqlalchemy import text
    await session.execute(text(
        "INSERT INTO notifications (type, target_kind, target_id, payload, created_at) "
        "VALUES (:t, 'seller_dialog', :did, :p::jsonb, now())"
    ), {"t": notif_type, "did": str(dialog_id),
        "p": '{"dialog_id":"%s"}' % str(dialog_id)})
    await session.commit()
```

(Adjust SQL to match existing `notifications` schema — check `app/db/models/notification.py`.)

- [ ] **Step 4: Wire ping #1 into Phase A contact → questions_setup transition**

In `avito-monitor/app/services/seller_dialog/handler.py`, find where `next_stage_on_seller_reply` returns `STAGE_QUESTIONS_SETUP` and the transition is applied; right after `await session.commit()` add:

```python
        await enqueue_tg_ping(session, "seller_dialog_ready_to_setup", dialog.id)
```

- [ ] **Step 5: Implement TG dispatcher for the new notification types**

In the existing `notifications.dispatch_pending` task body, add branches for the 2 new types that render the template:

```python
elif notif.type == "seller_dialog_ready_to_setup":
    text = f"🟢 Лот {listing.avito_id} ({listing.title}, {listing.price}₽)\n" \
           f"Продавец откликнулся. Настрой темы для опроса\n" \
           f"→ {settings.app_base_url}/listings?tab=in_progress"
    await tg_send(text)
elif notif.type == "seller_dialog_ready_to_negotiate":
    text = f"🟢 Лот {listing.avito_id} ({listing.title}, {listing.price}₽)\n" \
           f"Продавец подтвердил темы. Готов к торгу\n" \
           f"→ {settings.app_base_url}/listings?tab=in_progress"
    await tg_send(text)
```

(Adapt to whatever exact API `notifications.dispatch_pending` uses — pull listing + dialog from DB by `target_id`.)

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/tasks/notifications.py avito-monitor/app/services/notifications.py avito-monitor/app/services/seller_dialog/handler.py
git commit -m "feat(notifications): 2 transition TG pings — ready_to_setup, ready_to_negotiate"
```

---

### Task 16: Broker registration + container deploy

**Files:**
- Modify: `avito-monitor/app/tasks/broker.py`

- [ ] **Step 1: Register the new task**

In `avito-monitor/app/tasks/broker.py::_register_tasks`, add:

```python
import app.tasks.seller_dialog_tasks  # noqa: F401  -- registers dialog_tick_questions
```

(If file already imports `seller_dialog_tasks`, this is a no-op — confirm the registration covers `dialog_tick_questions`.)

- [ ] **Step 2: Deploy**

```bash
scp ... (sync entire avito-monitor/ repo subtree, or git push + pull on VPS)
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose build && docker compose up -d --force-recreate avito-monitor worker messenger-bot scheduler"
```

- [ ] **Step 3: Run migration on VPS**

```bash
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose run --rm avito-monitor alembic upgrade head"
```

Expected: alembic reports `0014_phase_b_topics` applied.

- [ ] **Step 4: Verify worker registered the task**

```bash
ssh root@81.200.119.132 "docker exec avito-system-worker-8 grep -r 'dialog_tick_questions' /app/app/tasks/ | head -5"
```

Expected: matches in `seller_dialog_tasks.py` and `broker.py`.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/tasks/broker.py
git commit -m "feat(broker): register dialog_tick_questions task"
```

---

### Task 17: Smoke + final commit

- [ ] **Step 1: Run full test suite**

```bash
docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor pytest tests/ -v 2>&1 | tail -40
```

Expected: all passed.

- [ ] **Step 2: Live smoke**

Open `https://avitosystem.duckdns.org/listings?tab=in_progress` — verify:
- 3 columns (Контакт / Настройка опроса / Опрос)
- Profile dropdown in header
- Click on a `questions_setup` card's "➜ настрой опрос" → modal opens with 11 topic checkboxes
- Tick 2 topics, click "Запустить опрос" → card moves to "Опрос" column
- Worker logs (`docker compose logs --since 2m worker`) show:
  - `dialog_tick_questions` task executed
  - 2 send_text calls (opening + first question)
- Seller eventually replies → handler logs:
  - `parse_topic_answer` result
  - next tick fires → next question
- After all topics — recap message sent
- Seller "да всё верно" → TG-ping #2 received in @zipmobile_bot

- [ ] **Step 3: Update CONTINUE.md**

In `CONTINUE.md`, add §3.6:

```markdown
### §3.6 Phase B — Опрос autopilot shipped 2026-05-11

11 baseline topics for iPhone 12 Pro Max + ad-hoc support. 4 new LLM dispatchers, worker `dialog_tick_questions`, setup modal, 3rd kanban column "Опрос", profile filter, 2 transition TG pings. Migration 0014_phase_b_topics. End-to-end validated on production.

Next phases: C (drawer + better UI), D (price negotiation stage 4-6), E (silence-timeout worker + 4 remaining TG pings).
```

- [ ] **Step 4: Final commit**

```bash
git add CONTINUE.md
git commit -m "docs(continue): Phase B shipped — Опрос autopilot end-to-end on prod"
```

---

## Self-review

**Spec coverage:**
- §3 Q1 (scope bundle stages 2+3) → Tasks 1-17 cover both stages.
- §3 Q1 (profile filter) → Tasks 11, 13, 14.
- §3 Q2 (11 topics) → Task 1.
- §3 Q3 (default-unchecked) → Task 13 setup_modal.html has bare `<input type="checkbox">` (no `checked`).
- §3 Q4 (one-at-a-time) → Task 9 worker picks one pending topic per tick.
- §3 Q5 (recap human tone) → Task 6 prompt + Task 8 deterministic fallback.
- §3 Q6 (ad-hoc persists in dialog_topics) → Task 8 `quick_add_topic`.
- §3 Q7 (TG pings 1+2) → Task 15.
- §3 Q8 (modal UI) → Tasks 12, 13.
- §3 Q9 (opening line) → Task 3 constant + Task 9 worker step 2.

All spec sections (§4.1 state machine, §4.2 schema, §4.3 seed, §4.4 LLM dispatchers, §4.5 worker, §4.6 handler, §4.7 UI, §4.8 TG pings) → covered.

**Placeholder scan:** no TBD/TODO. Every step has either concrete code or an exact command.

**Type consistency:**
- `topic.title`, `topic.default_phrasing`, `topic.expected_format` — uniform across Tasks 4-9, 13.
- `parse_topic_answer` return shape `{status, extracted, side_topics}` — uniform Tasks 5, 10.
- `formulate_recap` accepts `list[tuple[DialogTopic, str]]` — uniform Tasks 6, 9.
- `parse_seller_agreement` returns `{agreement, corrections}` — uniform Tasks 7, 10.
- `dialog_tick_questions.kiq(str(dialog_id))` — uniform Tasks 9, 10, 12.
- `set_recap`, `set_recap_status` signatures consistent across Tasks 9, 10.
- `seller_dialog_topics.status` enum `pending/asked/answered/skipped` — uniform Tasks 1 (CHECK constraint), 8, 9, 10.
- `seller_dialogs.recap_status` enum `pending_answer/confirmed/disputed` — uniform Tasks 3 (constants), 9, 10.
- `enqueue_tg_ping(session, type_str, dialog_id)` signature — uniform Tasks 10, 15.

**Test counts:**
- Task 4: 2
- Task 5: 2
- Task 6: 2
- Task 7: 2
- Task 8: 2
- Task 9: 3
- Task 10: 2
- Task 11: 2
- **Total new unit tests: 17**

Plus existing Phase A: 21. Combined target after Phase B: 38 unit tests + smoke.
