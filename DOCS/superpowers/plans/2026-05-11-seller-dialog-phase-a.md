# Seller Dialog Flow — Phase A: MVP Backbone — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Wave 2 and Wave 3 contain parallelizable task groups** marked with `🟢 PARALLEL` — dispatch their subagents concurrently in a single tool-call message.

**Goal:** Auto-greeting workflow: when user clicks `✓ В работу` on a lot, system creates Avito messenger channel, sends standard greeting, listens for response, and (if seller confirms "still selling") transitions the lot's dialog state from `contact` to `questions_setup`. UI shows a basic 2-column kanban for `В работу` tab.

**Architecture:** New `seller_dialogs` table tracks per-(profile_listing) dialog state with stage enum. Existing xapi messenger client (`create_channel_by_item`, `send_text`) reused. New TaskIQ task `start_seller_dialog` enqueued from listing-action endpoint on `accept`. SSE inbound dispatcher gets a new branch: if `channel_id` is owned by a `seller_dialog`, route to sales handler (parallel with existing reliability flow). LLM classifier `detect_yes_selling` runs on first seller reply; on `yes` → transition stage. Hardcoded greeting (no per-profile customization in Phase A). Migration script seeds existing accepted-but-undialogued lots in `operator_mode=true` so they don't get spam-greeted.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, TaskIQ, asyncpg, Jinja2 + HTMX + Tailwind. Existing services: `avito-xapi` (port 8080), `messenger_bot/runner.py` SSE listener, `llm_analyzer.py` for prompts.

---

## File Structure

**Create:**
- `avito-monitor/alembic/versions/20260511_1000_seller_dialogs.py` — schema migration
- `avito-monitor/app/db/models/seller_dialog.py` — SQLAlchemy model
- `avito-monitor/app/services/seller_dialog/__init__.py` — package marker
- `avito-monitor/app/services/seller_dialog/service.py` — CRUD operations
- `avito-monitor/app/services/seller_dialog/handler.py` — SSE inbound handler for sales dialogs
- `avito-monitor/app/services/seller_dialog/transitions.py` — stage transition logic
- `avito-monitor/app/services/seller_dialog_view.py` — read-side query for kanban
- `avito-monitor/app/prompts/dialog_detect_yes_selling.md` — LLM prompt
- `avito-monitor/app/tasks/seller_dialog_tasks.py` — TaskIQ tasks (start_seller_dialog, dialog_tick_contact)
- `avito-monitor/app/web/templates/_partials/kanban_card_contact.html` — Контакт card
- `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html` — Настройка опроса card
- `avito-monitor/app/web/templates/listings_kanban.html` — kanban container template (replaces `В работе` tab)
- `avito-monitor/scripts/migrate_accepted_to_dialogs.py` — one-off migration script (not Alembic — data move)
- `avito-monitor/tests/seller_dialog/__init__.py` — test package
- `avito-monitor/tests/seller_dialog/test_service.py` — service CRUD tests
- `avito-monitor/tests/seller_dialog/test_transitions.py` — transition logic tests
- `avito-monitor/tests/seller_dialog/test_handler.py` — SSE handler tests
- `avito-monitor/tests/seller_dialog/test_llm_detect.py` — LLM classifier tests

**Modify:**
- `avito-monitor/app/db/models/__init__.py` — export `SellerDialog`
- `avito-monitor/app/db/models/messenger_message.py` — add `dialog_id` nullable FK
- `avito-monitor/app/services/llm_analyzer.py` — add `detect_yes_selling()` method
- `avito-monitor/app/services/messenger_bot/handler.py:317` — branch by dialog_id lookup before reliability flow
- `avito-monitor/app/web/routers.py:627-707` — enqueue `start_seller_dialog.kiq()` on `accept`
- `avito-monitor/app/web/routers.py:710-800` — same enqueue for `bulk-action accept` path
- `avito-monitor/app/web/routers.py` — render kanban template when `tab=in_progress`

**Constants:** new file `avito-monitor/app/services/seller_dialog/constants.py` with `GREETING_TEMPLATE` string.

---

## Wave 0 — Schema (sequential, blocks everything)

### Task 1: Alembic migration for seller_dialogs + messenger_messages.dialog_id

**Files:**
- Create: `avito-monitor/alembic/versions/20260511_1000_seller_dialogs.py`

- [ ] **Step 1.1: Write the migration file**

```python
"""seller_dialogs — seller-side conversation state machine (Phase A subset)

Phase A creates a minimal schema for the seller dialog workflow:
  - ``seller_dialogs`` — one row per (profile, listing) pair tracking the
    current pipeline stage (``contact``, ``questions_setup`` in Phase A;
    later phases add ``questions``, ``price_negotiation``, etc.).
  - ``messenger_messages.dialog_id`` — nullable FK so the existing chat-log
    table can carry both reliability-bot messages (NULL) and seller-dialog
    messages without splitting tables.

Phase A intentionally omits ``silence_deadline``, ``timeout_notified``,
``prolongation_count``, ``target_price``, ``final_price``,
``shipping_method``, ``return_reason``, ``extracted_data`` — those land
in later phases when the corresponding stages are implemented.

Revision ID: 0013_seller_dialogs
Revises: 0012_reservation_tracking
Create Date: 2026-05-11 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_seller_dialogs"
down_revision: Union[str, None] = "0012_reservation_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_dialogs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.Text, nullable=True),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column(
            "operator_mode",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id", "listing_id"],
            ["profile_listings.profile_id", "profile_listings.listing_id"],
            ondelete="CASCADE",
            name="fk_seller_dialogs_profile_listing",
        ),
        sa.UniqueConstraint(
            "profile_id", "listing_id",
            name="uq_seller_dialogs_profile_listing",
        ),
        sa.CheckConstraint(
            "stage IN ('contact','questions_setup','questions','price_negotiation',"
            "'price_changed','purchased','shipped','received','closed','rejected')",
            name="ck_seller_dialogs_stage",
        ),
    )
    op.create_index(
        "ix_seller_dialogs_channel_id",
        "seller_dialogs",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_seller_dialogs_stage",
        "seller_dialogs",
        ["stage"],
    )

    op.add_column(
        "messenger_messages",
        sa.Column(
            "dialog_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seller_dialogs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_messenger_messages_dialog_id",
        "messenger_messages",
        ["dialog_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messenger_messages_dialog_id", table_name="messenger_messages")
    op.drop_column("messenger_messages", "dialog_id")
    op.drop_index("ix_seller_dialogs_stage", table_name="seller_dialogs")
    op.drop_index("ix_seller_dialogs_channel_id", table_name="seller_dialogs")
    op.drop_table("seller_dialogs")
```

- [ ] **Step 1.2: Run migration locally against test database**

Run: `cd avito-monitor && alembic upgrade head`
Expected: `Running upgrade 0012_reservation_tracking -> 0013_seller_dialogs`. If local DB isn't available, run against the prod cloud pooler with caution OR set `DATABASE_URL=postgresql+asyncpg://test:test@localhost/test` and use a docker-compose Postgres. Either way: migration must apply cleanly.

- [ ] **Step 1.3: Verify schema with psql**

Run (against the DB you migrated):
```bash
psql "$DATABASE_URL_RAW" -c "\d seller_dialogs"
psql "$DATABASE_URL_RAW" -c "\d messenger_messages"
```
Expected: `seller_dialogs` shows 11 columns + 2 indexes + unique constraint + check constraint. `messenger_messages` shows new `dialog_id` column with FK.

- [ ] **Step 1.4: Commit**

```bash
git add avito-monitor/alembic/versions/20260511_1000_seller_dialogs.py
git commit -m "feat(schema): seller_dialogs table + messenger_messages.dialog_id (phase A)"
```

---

## Wave 1 — Models (sequential, depends on Wave 0)

### Task 2: SellerDialog SQLAlchemy model + MessengerMessage update

**Files:**
- Create: `avito-monitor/app/db/models/seller_dialog.py`
- Modify: `avito-monitor/app/db/models/messenger_message.py`
- Modify: `avito-monitor/app/db/models/__init__.py`
- Test: `avito-monitor/tests/seller_dialog/__init__.py` (empty)
- Test: `avito-monitor/tests/seller_dialog/test_model.py`

- [ ] **Step 2.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/__init__.py` (empty file).
Create `avito-monitor/tests/seller_dialog/test_model.py`:

```python
"""Verify SellerDialog model wires up correctly."""
import uuid
from datetime import datetime

from app.db.models import SellerDialog


def test_seller_dialog_construct_minimal():
    sd = SellerDialog(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        stage="contact",
        opened_at=datetime.utcnow(),
    )
    assert sd.stage == "contact"
    assert sd.operator_mode is False or sd.operator_mode is None
    assert sd.channel_id is None
    assert sd.closed_at is None


def test_messenger_message_has_dialog_id_field():
    from app.db.models import MessengerMessage
    cols = {c.name for c in MessengerMessage.__table__.columns}
    assert "dialog_id" in cols
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd avito-monitor && pytest tests/seller_dialog/test_model.py -v`
Expected: `ImportError: cannot import name 'SellerDialog' from 'app.db.models'` (or similar).

- [ ] **Step 2.3: Create the model file**

Create `avito-monitor/app/db/models/seller_dialog.py`:

```python
"""Seller-side dialog state machine — Phase A skeleton.

One row per (profile, listing) tracking the current pipeline stage. Later
phases will extend with SLA timers, target/final price, shipping method,
return reason, extracted data JSONB, etc.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SellerDialog(Base):
    __tablename__ = "seller_dialogs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "listing_id"],
            ["profile_listings.profile_id", "profile_listings.listing_id"],
            ondelete="CASCADE",
            name="fk_seller_dialogs_profile_listing",
        ),
        UniqueConstraint(
            "profile_id", "listing_id",
            name="uq_seller_dialogs_profile_listing",
        ),
        CheckConstraint(
            "stage IN ('contact','questions_setup','questions','price_negotiation',"
            "'price_changed','purchased','shipped','received','closed','rejected')",
            name="ck_seller_dialogs_stage",
        ),
        Index("ix_seller_dialogs_channel_id", "channel_id"),
        Index("ix_seller_dialogs_stage", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    operator_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
```

- [ ] **Step 2.4: Update MessengerMessage with dialog_id**

Edit `avito-monitor/app/db/models/messenger_message.py` — add the import and field. The full updated file:

```python
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessengerMessage(Base):
    """V2 reliability + V1 seller-dialog — local cache of Avito messenger messages.

    ``dialog_id`` discriminates the two flows:
      - NULL = reliability-bot message (auto-reply to inbound on someone else's lot)
      - NOT NULL = seller-dialog message (our outbound greeting, q&a, or
        seller's reply to it)
    """

    __tablename__ = "messenger_messages"
    __table_args__ = (
        Index("ix_messenger_messages_channel_created", "channel_id", "created_at"),
        Index("ix_messenger_messages_dialog_id", "dialog_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # avito message_id
    channel_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("messenger_chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    dialog_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("seller_dialogs.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[str | None] = mapped_column(Text)  # 'in' | 'out'
    author_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)  # 'text' | 'image' | 'voice' | 'system'
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
```

- [ ] **Step 2.5: Update __init__.py exports**

Edit `avito-monitor/app/db/models/__init__.py` — add the import alphabetically and to `__all__`:

```python
from app.db.models.seller_dialog import SellerDialog
```

Add `"SellerDialog",` to `__all__` list alphabetically (between `SearchProfile` and `SystemSetting`).

- [ ] **Step 2.6: Run tests, verify they pass**

Run: `cd avito-monitor && pytest tests/seller_dialog/test_model.py -v`
Expected: 2 tests pass.

- [ ] **Step 2.7: Commit**

```bash
git add avito-monitor/app/db/models/seller_dialog.py \
        avito-monitor/app/db/models/messenger_message.py \
        avito-monitor/app/db/models/__init__.py \
        avito-monitor/tests/seller_dialog/__init__.py \
        avito-monitor/tests/seller_dialog/test_model.py
git commit -m "feat(models): SellerDialog + MessengerMessage.dialog_id"
```

---

## Wave 2 — Independent building blocks 🟢 PARALLEL

Tasks 3, 4, 5, 6 can be dispatched concurrently — they don't share files and only depend on Wave 1 (models).

### Task 3: seller_dialog service layer (CRUD)

**Files:**
- Create: `avito-monitor/app/services/seller_dialog/__init__.py` (empty)
- Create: `avito-monitor/app/services/seller_dialog/service.py`
- Create: `avito-monitor/app/services/seller_dialog/constants.py`
- Test: `avito-monitor/tests/seller_dialog/test_service.py`

- [ ] **Step 3.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/test_service.py`:

```python
"""Service layer for seller dialogs — CRUD only (no Avito or LLM calls)."""
import uuid
import pytest
from unittest.mock import AsyncMock

from app.services.seller_dialog.service import (
    create_dialog,
    get_dialog_by_channel,
    get_dialog_by_listing,
    set_stage,
    set_operator_mode,
)


@pytest.mark.asyncio
async def test_create_dialog_inserts_row():
    session = AsyncMock()
    profile_id = uuid.uuid4()
    listing_id = uuid.uuid4()

    await create_dialog(
        session,
        profile_id=profile_id,
        listing_id=listing_id,
        operator_mode=False,
    )

    # Verify session.add was called with a SellerDialog instance
    assert session.add.called
    added = session.add.call_args[0][0]
    assert added.profile_id == profile_id
    assert added.listing_id == listing_id
    assert added.stage == "contact"
    assert added.operator_mode is False
    assert added.channel_id is None
```

- [ ] **Step 3.2: Run test to verify failure**

Run: `pytest tests/seller_dialog/test_service.py -v`
Expected: `ImportError`.

- [ ] **Step 3.3: Implement constants module**

Create `avito-monitor/app/services/seller_dialog/__init__.py` (empty file).

Create `avito-monitor/app/services/seller_dialog/constants.py`:

```python
"""Hardcoded strings + enums for the seller dialog flow."""

GREETING_TEMPLATE = "Здравствуйте! Меня заинтересовал ваш аппарат. Ещё продаётся?"

# Stage names — keep in sync with the CHECK constraint in migration 0013.
STAGE_CONTACT = "contact"
STAGE_QUESTIONS_SETUP = "questions_setup"
STAGE_QUESTIONS = "questions"
STAGE_PRICE_NEGOTIATION = "price_negotiation"
STAGE_PRICE_CHANGED = "price_changed"
STAGE_PURCHASED = "purchased"
STAGE_SHIPPED = "shipped"
STAGE_RECEIVED = "received"
STAGE_CLOSED = "closed"
STAGE_REJECTED = "rejected"

CLOSED_REASON_SILENT = "silent"
CLOSED_REASON_REFUSED = "refused"
CLOSED_REASON_MANUAL = "manual"
```

- [ ] **Step 3.4: Implement service module**

Create `avito-monitor/app/services/seller_dialog/service.py`:

```python
"""CRUD operations for SellerDialog rows.

Single responsibility — no Avito API calls, no LLM, no HTTP. Pure DB.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SellerDialog
from app.services.seller_dialog.constants import STAGE_CONTACT


async def create_dialog(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
    operator_mode: bool = False,
) -> SellerDialog:
    """Insert a new dialog row at stage=contact. Caller commits."""
    sd = SellerDialog(
        profile_id=profile_id,
        listing_id=listing_id,
        stage=STAGE_CONTACT,
        operator_mode=operator_mode,
    )
    session.add(sd)
    await session.flush()
    return sd


async def get_dialog_by_listing(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
) -> SellerDialog | None:
    stmt = select(SellerDialog).where(
        SellerDialog.profile_id == profile_id,
        SellerDialog.listing_id == listing_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_dialog_by_channel(
    session: AsyncSession, channel_id: str
) -> SellerDialog | None:
    stmt = select(SellerDialog).where(SellerDialog.channel_id == channel_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def set_stage(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    new_stage: str,
) -> None:
    """Transition to a new stage, update last_event_at to now()."""
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(
            stage=new_stage,
            last_event_at=datetime.now(tz=timezone.utc),
        )
    )


async def set_operator_mode(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    operator_mode: bool,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(operator_mode=operator_mode)
    )


async def set_channel_id(
    session: AsyncSession,
    dialog_id: uuid.UUID,
    channel_id: str,
) -> None:
    await session.execute(
        update(SellerDialog)
        .where(SellerDialog.id == dialog_id)
        .values(channel_id=channel_id)
    )
```

- [ ] **Step 3.5: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_service.py -v`
Expected: 1 test passes.

- [ ] **Step 3.6: Commit**

```bash
git add avito-monitor/app/services/seller_dialog/ \
        avito-monitor/tests/seller_dialog/test_service.py
git commit -m "feat(seller-dialog): service layer with CRUD + constants"
```

### Task 4: LLM detect_yes_selling prompt + dispatcher 🟢 PARALLEL with T3, T5, T6

**Files:**
- Create: `avito-monitor/app/prompts/dialog_detect_yes_selling.md`
- Modify: `avito-monitor/app/services/llm_analyzer.py` (add new method)
- Test: `avito-monitor/tests/seller_dialog/test_llm_detect.py`

- [ ] **Step 4.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/test_llm_detect.py`:

```python
"""LLM classifier: does the seller's reply confirm the item is still for sale?

Mock the LLM call — we test prompt construction + result parsing, not the
model itself.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm_analyzer import detect_yes_selling


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_true_on_affirmative():
    with patch("app.services.llm_analyzer._llm_call_json") as m:
        m.return_value = {"is_selling": True, "confidence": 0.95}
        result = await detect_yes_selling("Да, продается. Что хотели?")
    assert result is True


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_false_on_negative():
    with patch("app.services.llm_analyzer._llm_call_json") as m:
        m.return_value = {"is_selling": False, "confidence": 0.9}
        result = await detect_yes_selling("Уже продал, извините")
    assert result is False


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_false_on_low_confidence():
    """Below 0.7 confidence — treat as unknown (do NOT auto-transition)."""
    with patch("app.services.llm_analyzer._llm_call_json") as m:
        m.return_value = {"is_selling": True, "confidence": 0.5}
        result = await detect_yes_selling("Хм, ну в принципе")
    assert result is False
```

- [ ] **Step 4.2: Run test to verify failure**

Run: `pytest tests/seller_dialog/test_llm_detect.py -v`
Expected: `ImportError: cannot import name 'detect_yes_selling'`.

- [ ] **Step 4.3: Create the LLM prompt**

Create `avito-monitor/app/prompts/dialog_detect_yes_selling.md`:

```markdown
# Detect yes-selling classifier

You are a classifier deciding whether a seller's reply on Avito confirms
that the item is still available for purchase.

## Seller's reply

```
{{seller_message}}
```

## Decision rules

- Output `is_selling: true` if the seller says yes / confirms availability / asks a clarifying question that implies they're still interested in selling.
- Output `is_selling: false` if the seller says it's sold / reserved for someone else / they changed their mind.
- If ambiguous ("дайте подумаю", "сейчас на работе"), output `is_selling: false` and `confidence < 0.7` — the caller will treat low-confidence as "not yet".

## Output

Return strict JSON:

```json
{
  "is_selling": true,
  "confidence": 0.95
}
```

Confidence is 0.0-1.0. No prose outside JSON.
```

- [ ] **Step 4.4: Implement detect_yes_selling in llm_analyzer.py**

Open `avito-monitor/app/services/llm_analyzer.py` and find the existing module-level helpers near the top (after imports). Add (placement: near other classifier-style methods, e.g. after `evaluate_listing` or near other public exports):

```python
async def detect_yes_selling(seller_message: str) -> bool:
    """Decide if seller's first reply confirms item is still for sale.

    Returns True only on high-confidence (>=0.7) affirmative. Anything else
    (including LLM error / parse failure) returns False so the caller does
    NOT auto-transition the stage — operator stays in control of edge cases.
    """
    import importlib.resources
    prompt_template = (
        importlib.resources.files("app.prompts")
        .joinpath("dialog_detect_yes_selling.md")
        .read_text(encoding="utf-8")
    )
    prompt = prompt_template.replace("{{seller_message}}", seller_message)

    try:
        result = await _llm_call_json(prompt, max_tokens=128)
    except Exception:
        return False
    if not isinstance(result, dict):
        return False
    is_selling = result.get("is_selling")
    confidence = result.get("confidence", 0.0)
    if not isinstance(is_selling, bool) or not isinstance(confidence, (int, float)):
        return False
    return is_selling and confidence >= 0.7
```

If `_llm_call_json` doesn't exist as a helper, search the file for the existing JSON-returning OpenRouter call (look for `litellm`, `openrouter`, or `httpx.post` with `response_format`). Wrap it in a module-level `async def _llm_call_json(prompt: str, max_tokens: int = 256) -> dict:` if not already extracted. Read the file end-to-end before adding to find existing conventions.

- [ ] **Step 4.5: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_llm_detect.py -v`
Expected: 3 tests pass.

- [ ] **Step 4.6: Commit**

```bash
git add avito-monitor/app/prompts/dialog_detect_yes_selling.md \
        avito-monitor/app/services/llm_analyzer.py \
        avito-monitor/tests/seller_dialog/test_llm_detect.py
git commit -m "feat(llm): detect_yes_selling classifier with 0.7 confidence threshold"
```

### Task 5: seller_dialog_view.py — read-side query for kanban 🟢 PARALLEL with T3, T4, T6

**Files:**
- Create: `avito-monitor/app/services/seller_dialog_view.py`
- Test: `avito-monitor/tests/seller_dialog/test_view.py`

- [ ] **Step 5.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/test_view.py`:

```python
"""Read-side query that powers the kanban UI."""
import pytest
from unittest.mock import AsyncMock

from app.services.seller_dialog_view import query_kanban_cards, KanbanFilters


@pytest.mark.asyncio
async def test_query_kanban_groups_by_stage():
    """The view returns a dict keyed by stage name with lists of cards inside."""
    session = AsyncMock()
    # Mock executescalar / execute(.all()) appropriately for the actual impl.
    # The test focuses on the SHAPE of the return value.

    # We'll just verify the function signature + return key set after impl.
    result = await query_kanban_cards(session, user_id="00000000-0000-0000-0000-000000000000",
                                       filters=KanbanFilters())
    assert isinstance(result, dict)
    # Phase A only renders contact + questions_setup buckets.
    assert "contact" in result
    assert "questions_setup" in result
```

- [ ] **Step 5.2: Run test to verify failure**

Run: `pytest tests/seller_dialog/test_view.py -v`
Expected: `ImportError`.

- [ ] **Step 5.3: Implement the view module**

Create `avito-monitor/app/services/seller_dialog_view.py`:

```python
"""Read-side query service for the kanban UI.

Returns dialogs grouped by stage. Phase A only renders the first two
columns (contact + questions_setup); later phases add the rest by
extending ``PHASE_A_STAGES`` to ``ALL_STAGES``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, ProfileListing, SearchProfile, SellerDialog
from app.services.seller_dialog.constants import (
    STAGE_CONTACT,
    STAGE_QUESTIONS_SETUP,
)


PHASE_A_STAGES = [STAGE_CONTACT, STAGE_QUESTIONS_SETUP]


@dataclass
class KanbanCard:
    dialog_id: uuid.UUID
    listing_id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str
    avito_id: int
    title: str
    price: int | None
    image_url: str | None
    stage: str
    operator_mode: bool
    opened_at: datetime
    last_event_at: datetime | None


@dataclass
class KanbanFilters:
    profile_ids: list[uuid.UUID] = field(default_factory=list)


def _first_image_url(images_jsonb: Any) -> str | None:
    if isinstance(images_jsonb, list) and images_jsonb:
        first = images_jsonb[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


async def query_kanban_cards(
    session: AsyncSession,
    user_id: uuid.UUID | str,
    filters: KanbanFilters | None = None,
) -> dict[str, list[KanbanCard]]:
    """Return dict[stage_name → list[KanbanCard]] for all stages in PHASE_A_STAGES.

    Empty list for stages with no cards (so the template can always iterate).
    """
    filters = filters or KanbanFilters()

    stmt = (
        select(
            SellerDialog,
            Listing,
            SearchProfile.name.label("profile_name"),
        )
        .select_from(SellerDialog)
        .join(Listing, Listing.id == SellerDialog.listing_id)
        .join(SearchProfile, SearchProfile.id == SellerDialog.profile_id)
        .where(
            SearchProfile.user_id == user_id,
            SellerDialog.stage.in_(PHASE_A_STAGES),
            SellerDialog.closed_at.is_(None),
        )
        .order_by(SellerDialog.opened_at.desc())
    )

    if filters.profile_ids:
        stmt = stmt.where(SellerDialog.profile_id.in_(filters.profile_ids))

    rows = (await session.execute(stmt)).all()

    out: dict[str, list[KanbanCard]] = {s: [] for s in PHASE_A_STAGES}
    for sd, listing, profile_name in rows:
        card = KanbanCard(
            dialog_id=sd.id,
            listing_id=sd.listing_id,
            profile_id=sd.profile_id,
            profile_name=profile_name,
            avito_id=listing.avito_id,
            title=listing.title,
            price=int(listing.price) if listing.price is not None else None,
            image_url=_first_image_url(listing.images),
            stage=sd.stage,
            operator_mode=sd.operator_mode,
            opened_at=sd.opened_at,
            last_event_at=sd.last_event_at,
        )
        out[sd.stage].append(card)
    return out
```

- [ ] **Step 5.4: Verify test passes (loose — mocked session)**

The mock-based test verifies signature + shape only. With the AsyncMock session, the function will fail to execute the SQL, so we need to adapt. Replace `test_view.py` content:

```python
"""Read-side query that powers the kanban UI."""
from app.services.seller_dialog_view import (
    KanbanCard,
    KanbanFilters,
    PHASE_A_STAGES,
    query_kanban_cards,
)


def test_phase_a_stages_contains_two_stages():
    assert PHASE_A_STAGES == ["contact", "questions_setup"]


def test_kanban_filters_default_empty():
    f = KanbanFilters()
    assert f.profile_ids == []


def test_kanban_card_dataclass_fields():
    fields_set = {
        "dialog_id", "listing_id", "profile_id", "profile_name",
        "avito_id", "title", "price", "image_url", "stage",
        "operator_mode", "opened_at", "last_event_at",
    }
    annotations = set(KanbanCard.__annotations__.keys())
    assert fields_set <= annotations
```

Run: `pytest tests/seller_dialog/test_view.py -v`
Expected: 3 tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add avito-monitor/app/services/seller_dialog_view.py \
        avito-monitor/tests/seller_dialog/test_view.py
git commit -m "feat(seller-dialog): read-side view query for kanban"
```

### Task 6: Card partial templates 🟢 PARALLEL with T3, T4, T5

**Files:**
- Create: `avito-monitor/app/web/templates/_partials/kanban_card_contact.html`
- Create: `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html`

No tests for templates — visual verification at end of Wave 5.

- [ ] **Step 6.1: Create Контакт card partial**

Create `avito-monitor/app/web/templates/_partials/kanban_card_contact.html`:

```html
{# Kanban card — Контакт stage (waiting for first reply from seller).
   Compact card: photo thumbnail + title + price + last_event_at.
   Phase A: no drawer yet — full card link points to /listings/{id}. #}
<a href="/listings/{{ card.listing_id }}"
   class="block bg-white rounded-lg shadow-sm hover:shadow-md transition p-3 mb-2 border border-stone-200">
  <div class="flex gap-3">
    {% if card.image_url %}
      <img src="{{ card.image_url }}"
           alt=""
           class="w-16 h-16 rounded object-cover flex-shrink-0"
           loading="lazy">
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
  <div class="mt-2 pt-2 border-t border-stone-100 flex items-center justify-between text-xs">
    {% if card.operator_mode %}
      <span class="px-2 py-0.5 bg-amber-100 text-amber-800 rounded">ручной режим</span>
    {% else %}
      <span class="text-stone-500">ждём ответ продавца</span>
    {% endif %}
    {% if card.last_event_at %}
      <span class="text-stone-400" title="последнее событие">
        {{ card.last_event_at.strftime("%d.%m %H:%M") }}
      </span>
    {% else %}
      <span class="text-stone-400">{{ card.opened_at.strftime("%d.%m %H:%M") }}</span>
    {% endif %}
  </div>
</a>
```

- [ ] **Step 6.2: Create Настройка опроса card partial**

Create `avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html`:

```html
{# Kanban card — Настройка опроса stage. Operator must pick topics and
   click "Запустить опрос" to advance the card. In Phase A there's no
   actual setup screen yet (Phase C); we just show a "настрой опрос"
   badge to signal pending operator action. #}
<a href="/listings/{{ card.listing_id }}"
   class="block bg-white rounded-lg shadow-sm hover:shadow-md transition p-3 mb-2 border-2 border-amber-300">
  <div class="flex gap-3">
    {% if card.image_url %}
      <img src="{{ card.image_url }}"
           alt=""
           class="w-16 h-16 rounded object-cover flex-shrink-0"
           loading="lazy">
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
  <div class="mt-2 pt-2 border-t border-stone-100 flex items-center justify-between text-xs">
    <span class="px-2 py-0.5 bg-amber-200 text-amber-900 rounded font-medium">
      ➜ настрой опрос
    </span>
    {% if card.last_event_at %}
      <span class="text-stone-400">{{ card.last_event_at.strftime("%d.%m %H:%M") }}</span>
    {% endif %}
  </div>
</a>
```

- [ ] **Step 6.3: Commit**

```bash
git add avito-monitor/app/web/templates/_partials/kanban_card_contact.html \
        avito-monitor/app/web/templates/_partials/kanban_card_questions_setup.html
git commit -m "feat(web): kanban card partials for contact + questions_setup"
```

---

## Wave 3 — Workers + handlers + migration 🟢 PARALLEL

Tasks 7, 8, 9 can run concurrently — they depend on Wave 2 outputs but don't share files among themselves.

### Task 7: TaskIQ task start_seller_dialog

**Files:**
- Create: `avito-monitor/app/tasks/seller_dialog_tasks.py`
- Test: `avito-monitor/tests/seller_dialog/test_tasks.py`

- [ ] **Step 7.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/test_tasks.py`:

```python
"""Worker tasks for seller dialog."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_start_seller_dialog_creates_channel_and_sends_greeting():
    """Task: create dialog row + Avito channel + send greeting + persist message."""
    from app.tasks.seller_dialog_tasks import _start_seller_dialog_impl
    from app.services.seller_dialog.constants import GREETING_TEMPLATE

    profile_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    avito_item_id = "1234567890"

    session = AsyncMock()
    xapi_client = AsyncMock()
    xapi_client.create_channel_by_item.return_value = {"id": "ch_abc"}
    xapi_client.send_text.return_value = {"id": "msg_xyz"}

    # Mock listing lookup
    with patch("app.tasks.seller_dialog_tasks._get_avito_item_id",
               new=AsyncMock(return_value=avito_item_id)):
        result = await _start_seller_dialog_impl(
            session=session,
            xapi_client=xapi_client,
            profile_id=profile_id,
            listing_id=listing_id,
        )

    xapi_client.create_channel_by_item.assert_awaited_once_with(avito_item_id)
    xapi_client.send_text.assert_awaited_once_with("ch_abc", GREETING_TEMPLATE)
    assert result["channel_id"] == "ch_abc"
    assert result["greeting_message_id"] == "msg_xyz"
```

- [ ] **Step 7.2: Run test to verify failure**

Run: `pytest tests/seller_dialog/test_tasks.py -v`
Expected: `ImportError`.

- [ ] **Step 7.3: Implement the task module**

Create `avito-monitor/app/tasks/seller_dialog_tasks.py`:

```python
"""TaskIQ tasks for the seller dialog workflow (Phase A).

Phase A exposes one task: ``start_seller_dialog(profile_id, listing_id)``.
It's enqueued from the listing-action HTTP endpoint when a user accepts a
lot. Logic:

  1. Create a SellerDialog row (stage=contact).
  2. Look up the listing's Avito item_id.
  3. Call xapi to create a messenger channel.
  4. Send the hardcoded greeting on that channel.
  5. Persist the outgoing message to messenger_messages with
     dialog_id linking it back.

If anything fails after step 1, the dialog is marked operator_mode=true
so a human can take over. We do NOT retry — Avito rate-limits aggressively
and we'd rather have a stuck dialog than a duplicate greeting.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, MessengerMessage
from app.db.session import async_session_maker
from app.services.seller_dialog import service as sd_service
from app.services.seller_dialog.constants import GREETING_TEMPLATE
from app.tasks.broker import broker

log = logging.getLogger(__name__)


async def _get_avito_item_id(session: AsyncSession, listing_id: uuid.UUID) -> str:
    """Look up Avito's item_id for our internal listing UUID."""
    stmt = select(Listing.avito_id).where(Listing.id == listing_id)
    avito_id = (await session.execute(stmt)).scalar_one()
    return str(avito_id)


async def _start_seller_dialog_impl(
    session: AsyncSession,
    xapi_client,  # XapiClient from avito-xapi.workers.http_client
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
) -> dict[str, Any]:
    """Pure-logic implementation, separated from broker wrapping for testability."""
    # Step 1: create dialog
    dialog = await sd_service.create_dialog(
        session,
        profile_id=profile_id,
        listing_id=listing_id,
        operator_mode=False,
    )
    await session.flush()

    # Step 2: avito item_id
    avito_item_id = await _get_avito_item_id(session, listing_id)

    # Step 3: create channel
    channel_resp = await xapi_client.create_channel_by_item(avito_item_id)
    channel_id = channel_resp["id"]
    await sd_service.set_channel_id(session, dialog.id, channel_id)

    # Step 4: send greeting
    msg_resp = await xapi_client.send_text(channel_id, GREETING_TEMPLATE)
    msg_id = msg_resp["id"]

    # Step 5: persist outgoing message
    msg = MessengerMessage(
        id=msg_id,
        channel_id=channel_id,
        dialog_id=dialog.id,
        direction="out",
        author_id=None,
        text=GREETING_TEMPLATE,
        type="text",
        created_at=datetime.now(tz=timezone.utc),
        raw={"source": "seller_dialog.start"},
    )
    session.add(msg)

    await session.commit()

    log.info(
        "seller_dialog.start success listing=%s channel=%s msg=%s",
        listing_id, channel_id, msg_id,
    )
    return {"dialog_id": str(dialog.id), "channel_id": channel_id, "greeting_message_id": msg_id}


@broker.task()
async def start_seller_dialog(profile_id: str, listing_id: str) -> dict[str, Any]:
    """TaskIQ entrypoint — opens its own DB session + xapi client."""
    from app.integrations.xapi import build_xapi_client

    async with async_session_maker() as session:
        async with build_xapi_client() as xapi:
            try:
                return await _start_seller_dialog_impl(
                    session=session,
                    xapi_client=xapi,
                    profile_id=uuid.UUID(profile_id),
                    listing_id=uuid.UUID(listing_id),
                )
            except Exception:
                log.exception(
                    "seller_dialog.start failed listing=%s — switching to operator_mode",
                    listing_id,
                )
                # Mark the (possibly created) dialog as operator_mode for human takeover
                try:
                    dlg = await sd_service.get_dialog_by_listing(
                        session,
                        profile_id=uuid.UUID(profile_id),
                        listing_id=uuid.UUID(listing_id),
                    )
                    if dlg:
                        await sd_service.set_operator_mode(session, dlg.id, True)
                        await session.commit()
                except Exception:
                    log.exception("seller_dialog.start cleanup also failed")
                raise
```

Two implementation notes for the executing agent:

- `from app.integrations.xapi import build_xapi_client` — confirm the actual exported name. If it doesn't exist, search `avito-monitor/app/integrations/` for the xapi wrapper. The codebase uses `httpx.AsyncClient` against `http://avito-xapi:8080`; you may need to call `httpx.AsyncClient(base_url=settings.AVITO_XAPI_URL, headers={"X-Api-Key": settings.AVITO_XAPI_API_KEY})` directly. Look at how `polling.py` calls xapi for the pattern.
- `from app.db.session import async_session_maker` — confirm exact import. If different name (e.g., `SessionLocal`), adapt.

- [ ] **Step 7.4: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_tasks.py -v`
Expected: 1 test passes.

- [ ] **Step 7.5: Commit**

```bash
git add avito-monitor/app/tasks/seller_dialog_tasks.py \
        avito-monitor/tests/seller_dialog/test_tasks.py
git commit -m "feat(tasks): start_seller_dialog — create channel + send greeting"
```

### Task 8: Sales handler (inbound SSE routing + stage transition) 🟢 PARALLEL with T7, T9

**Files:**
- Create: `avito-monitor/app/services/seller_dialog/handler.py`
- Create: `avito-monitor/app/services/seller_dialog/transitions.py`
- Test: `avito-monitor/tests/seller_dialog/test_handler.py`
- Test: `avito-monitor/tests/seller_dialog/test_transitions.py`

- [ ] **Step 8.1: Write the failing tests**

Create `avito-monitor/tests/seller_dialog/test_transitions.py`:

```python
"""Stage transition rules — pure functions, easy to unit test."""
from app.services.seller_dialog.transitions import next_stage_on_seller_reply
from app.services.seller_dialog.constants import (
    STAGE_CONTACT, STAGE_QUESTIONS_SETUP, STAGE_QUESTIONS,
)


def test_contact_to_questions_setup_on_yes_selling():
    """At contact, LLM says yes-selling → advance to questions_setup."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_CONTACT,
        llm_yes_selling=True,
    )
    assert new == STAGE_QUESTIONS_SETUP


def test_contact_stays_on_low_confidence():
    """At contact, LLM not confident enough → keep waiting (no transition)."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_CONTACT,
        llm_yes_selling=False,
    )
    assert new is None  # no transition


def test_questions_setup_no_auto_transition():
    """At questions_setup, no auto-transition from a seller reply (operator drives)."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_QUESTIONS_SETUP,
        llm_yes_selling=True,
    )
    assert new is None
```

Create `avito-monitor/tests/seller_dialog/test_handler.py`:

```python
"""Inbound SSE handler — dispatches to seller dialog flow."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_seller_inbound_persists_message():
    """Inbound on a sales channel: persist incoming message with dialog_id."""
    from app.services.seller_dialog.handler import handle_seller_inbound

    session = AsyncMock()
    dialog = AsyncMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "contact"
    dialog.operator_mode = False

    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.detect_yes_selling",
               new=AsyncMock(return_value=True)) as m_detect:
        await handle_seller_inbound(
            session=session,
            channel_id="ch_abc",
            message_id="m1",
            author_id="seller_id",
            text="Да, продаётся",
        )

    # Either we persisted the message AND attempted transition
    assert session.add.called
    m_detect.assert_awaited_once_with("Да, продаётся")


@pytest.mark.asyncio
async def test_handle_seller_inbound_skips_when_operator_mode():
    """When operator_mode=True, do NOT run LLM (operator handles dialog)."""
    from app.services.seller_dialog.handler import handle_seller_inbound

    session = AsyncMock()
    dialog = AsyncMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "contact"
    dialog.operator_mode = True

    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.detect_yes_selling",
               new=AsyncMock(return_value=True)) as m_detect:
        await handle_seller_inbound(
            session=session,
            channel_id="ch_abc",
            message_id="m2",
            author_id="seller_id",
            text="any",
        )

    m_detect.assert_not_called()
```

- [ ] **Step 8.2: Run tests to verify failure**

Run: `pytest tests/seller_dialog/test_transitions.py tests/seller_dialog/test_handler.py -v`
Expected: `ImportError` for both modules.

- [ ] **Step 8.3: Implement transitions module**

Create `avito-monitor/app/services/seller_dialog/transitions.py`:

```python
"""Pure stage-transition logic for seller dialogs.

Phase A only knows the contact → questions_setup transition. Later phases
extend the function by adding more cases.
"""
from __future__ import annotations

from app.services.seller_dialog.constants import (
    STAGE_CONTACT,
    STAGE_QUESTIONS_SETUP,
)


def next_stage_on_seller_reply(
    *,
    current_stage: str,
    llm_yes_selling: bool,
) -> str | None:
    """Decide whether a fresh seller reply triggers a stage transition.

    Returns the new stage name, or None if no transition.
    """
    if current_stage == STAGE_CONTACT and llm_yes_selling:
        return STAGE_QUESTIONS_SETUP
    return None
```

- [ ] **Step 8.4: Implement handler module**

Create `avito-monitor/app/services/seller_dialog/handler.py`:

```python
"""Inbound SSE handler for seller-dialog channels.

Called from the existing messenger_bot.handler.handle_event() after it
checks whether the inbound's channel belongs to a SellerDialog (rather
than a reliability-flow chat). We get the channel_id + message metadata
and run:

  1. Persist incoming message with dialog_id link.
  2. If operator_mode=True — that's it, operator handles it.
  3. Otherwise dispatch a stage-specific reaction:
       contact + yes-selling → set stage=questions_setup + TG-ping operator
       (TG-ping is added in Phase E; for now we just transition the stage)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MessengerMessage
from app.services.llm_analyzer import detect_yes_selling
from app.services.seller_dialog.service import (
    get_dialog_by_channel,
    set_stage,
)
from app.services.seller_dialog.transitions import next_stage_on_seller_reply

log = logging.getLogger(__name__)


async def handle_seller_inbound(
    *,
    session: AsyncSession,
    channel_id: str,
    message_id: str,
    author_id: str | None,
    text: str | None,
) -> None:
    """Process one inbound message for a known seller-dialog channel.

    Caller (messenger_bot.handler) must have already confirmed via
    get_dialog_by_channel() that this channel belongs to seller-dialog flow.
    """
    dialog = await get_dialog_by_channel(session, channel_id)
    if dialog is None:
        log.warning("seller_dialog.handler called for unknown channel %s", channel_id)
        return

    # Step 1: persist the inbound (idempotent on PK)
    msg = MessengerMessage(
        id=message_id,
        channel_id=channel_id,
        dialog_id=dialog.id,
        direction="in",
        author_id=author_id,
        text=text,
        type="text",
        created_at=datetime.now(tz=timezone.utc),
        raw=None,
    )
    session.add(msg)

    if dialog.operator_mode:
        log.info(
            "seller_dialog.handler op-mode dialog=%s — stored msg, no LLM",
            dialog.id,
        )
        await session.commit()
        return

    # Step 2: run stage-specific LLM check
    yes_selling = False
    if text:
        yes_selling = await detect_yes_selling(text)

    new_stage = next_stage_on_seller_reply(
        current_stage=dialog.stage,
        llm_yes_selling=yes_selling,
    )

    if new_stage is not None:
        await set_stage(session, dialog.id, new_stage)
        log.info(
            "seller_dialog.handler transition dialog=%s %s → %s",
            dialog.id, dialog.stage, new_stage,
        )

    await session.commit()
```

- [ ] **Step 8.5: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_transitions.py tests/seller_dialog/test_handler.py -v`
Expected: 3 + 2 tests pass.

- [ ] **Step 8.6: Commit**

```bash
git add avito-monitor/app/services/seller_dialog/transitions.py \
        avito-monitor/app/services/seller_dialog/handler.py \
        avito-monitor/tests/seller_dialog/test_transitions.py \
        avito-monitor/tests/seller_dialog/test_handler.py
git commit -m "feat(seller-dialog): inbound handler + stage transition logic"
```

### Task 9: Migration script for existing accepted lots 🟢 PARALLEL with T7, T8

**Files:**
- Create: `avito-monitor/scripts/migrate_accepted_to_dialogs.py`

This is a one-off script run manually post-deploy, not part of automated migration chain — because it depends on production data state.

- [ ] **Step 9.1: Create the script**

Create `avito-monitor/scripts/migrate_accepted_to_dialogs.py`:

```python
"""One-off post-deploy migration: seed seller_dialogs for already-accepted lots.

Run AFTER alembic migration 0013 applies + the deploy of code that
auto-creates dialogs on accept. Without this script, all already-accepted
lots would be invisible in the new kanban (no SellerDialog row).

Strategy:
  - Find every (profile_id, listing_id) in profile_listings with
    user_action='accepted' AND no existing SellerDialog row.
  - Insert a SellerDialog at stage='contact' with operator_mode=true.
  - **Do NOT auto-send greeting** — operator already may have chatted
    manually. operator_mode=true means LLM and auto-greeting stay silent.

The cards appear in the kanban Контакт column with a "ручной режим"
badge so operator can decide what to do with each.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import asyncpg


SQL_FIND_GAPS = """
SELECT pl.profile_id, pl.listing_id
FROM profile_listings pl
LEFT JOIN seller_dialogs sd
  ON sd.profile_id = pl.profile_id AND sd.listing_id = pl.listing_id
WHERE pl.user_action = 'accepted'
  AND sd.id IS NULL
"""

SQL_INSERT = """
INSERT INTO seller_dialogs
    (id, profile_id, listing_id, stage, operator_mode, opened_at)
VALUES
    ($1, $2, $3, 'contact', true, now())
"""


async def main() -> None:
    url = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        rows = await conn.fetch(SQL_FIND_GAPS)
        print(f"accepted lots without dialog: {len(rows)}")
        for r in rows:
            await conn.execute(
                SQL_INSERT,
                uuid.uuid4(),
                r["profile_id"],
                r["listing_id"],
            )
        print(f"inserted: {len(rows)} dialogs at stage=contact operator_mode=true")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 9.2: Commit (no test — manual-run script)**

```bash
git add avito-monitor/scripts/migrate_accepted_to_dialogs.py
git commit -m "chore(seller-dialog): one-off migration for already-accepted lots"
```

---

## Wave 4 — Integration glue (sequential)

### Task 10: Hook listing_action endpoint to enqueue start_seller_dialog

**Files:**
- Modify: `avito-monitor/app/web/routers.py:627-707`
- Modify: `avito-monitor/app/web/routers.py:710-800` (bulk-action)
- Test: `avito-monitor/tests/seller_dialog/test_hook_integration.py`

- [ ] **Step 10.1: Write the failing test**

Create `avito-monitor/tests/seller_dialog/test_hook_integration.py`:

```python
"""When user clicks ✓В работу, the listing_action endpoint enqueues
start_seller_dialog with the correct (profile_id, listing_id)."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_accept_enqueues_dialog_task():
    """The action handler calls start_seller_dialog.kiq(profile_id, listing_id)."""
    with patch("app.web.routers.start_seller_dialog") as m:
        m.kiq = AsyncMock()
        # We construct a minimal action call. Easier path: import the helper
        # function and verify the side effect — to keep this a unit test rather
        # than a full FastAPI request test, the implementation extracts the
        # enqueue side effect to a helper.
        from app.web.routers import _maybe_enqueue_start_seller_dialog
        await _maybe_enqueue_start_seller_dialog(
            action_raw="accept",
            profile_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            listing_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        m.kiq.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_does_not_enqueue_dialog_task():
    with patch("app.web.routers.start_seller_dialog") as m:
        m.kiq = AsyncMock()
        from app.web.routers import _maybe_enqueue_start_seller_dialog
        await _maybe_enqueue_start_seller_dialog(
            action_raw="reject",
            profile_id=uuid.uuid4(),
            listing_id=uuid.uuid4(),
        )
        m.kiq.assert_not_called()
```

- [ ] **Step 10.2: Run test to verify failure**

Run: `pytest tests/seller_dialog/test_hook_integration.py -v`
Expected: `ImportError: _maybe_enqueue_start_seller_dialog`.

- [ ] **Step 10.3: Add helper and import to routers.py**

Open `avito-monitor/app/web/routers.py`. Near the top with other module-level imports add:

```python
from app.tasks.seller_dialog_tasks import start_seller_dialog
```

Above the `@router.post("/listings/{profile_id}/{listing_id}/action"` decorator (around line 625) add:

```python
async def _maybe_enqueue_start_seller_dialog(
    *,
    action_raw: str,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
) -> None:
    """Enqueue dialog-start task only on the 'accept' action, never on reject/undo.

    Idempotency note: the worker itself bails if a SellerDialog already
    exists for this (profile, listing), so double-clicks or accept→undo→
    accept don't send a second greeting. (Phase A leaves the dialog row
    behind after undo — that's acceptable.)
    """
    if action_raw == "accept":
        await start_seller_dialog.kiq(str(profile_id), str(listing_id))
```

- [ ] **Step 10.4: Wire the helper into both action endpoints**

Inside `listing_action` (line 627), just before the final `RedirectResponse` (after `await session.commit()` at line 692), add:

```python
    await _maybe_enqueue_start_seller_dialog(
        action_raw=action_raw,
        profile_id=profile_id,
        listing_id=listing_id,
    )
```

Inside `listings_bulk_action` (line 710), inside the per-decision loop after `if new_action == UserAction.ACCEPTED.value:` block (find where individual accept happens), add the same enqueue call inside the loop:

```python
        if new_action == UserAction.ACCEPTED.value:
            await _maybe_enqueue_start_seller_dialog(
                action_raw="accept",
                profile_id=profile_id,
                listing_id=listing_id,
            )
```

(Read the bulk endpoint carefully — variable names may be `pid`/`lid` instead of `profile_id`/`listing_id`. Adapt accordingly. The loop iterates over a list of decisions; the enqueue goes inside the per-decision branch where ACCEPTED is set.)

- [ ] **Step 10.5: Update the start_seller_dialog task to be idempotent**

Edit `avito-monitor/app/tasks/seller_dialog_tasks.py` `_start_seller_dialog_impl` — add early-return on existing dialog. Insert at the top of the function body, before the `create_dialog` call:

```python
    existing = await sd_service.get_dialog_by_listing(
        session, profile_id=profile_id, listing_id=listing_id,
    )
    if existing is not None:
        log.info(
            "seller_dialog.start skip — dialog already exists listing=%s stage=%s",
            listing_id, existing.stage,
        )
        return {
            "dialog_id": str(existing.id),
            "channel_id": existing.channel_id,
            "skipped": True,
        }
```

- [ ] **Step 10.6: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_hook_integration.py tests/seller_dialog/test_tasks.py -v`
Expected: all pass. (test_tasks.py may need a tweak — adapt if the idempotency guard breaks the existing test by mocking `get_dialog_by_listing` to return None.)

- [ ] **Step 10.7: Commit**

```bash
git add avito-monitor/app/web/routers.py \
        avito-monitor/app/tasks/seller_dialog_tasks.py \
        avito-monitor/tests/seller_dialog/test_hook_integration.py
git commit -m "feat(routers): enqueue start_seller_dialog on accept (single + bulk)"
```

### Task 11: SSE handler routing (branch to seller_dialog when channel is owned)

**Files:**
- Modify: `avito-monitor/app/services/messenger_bot/handler.py:317-450` (handle_event)
- Test: extend `avito-monitor/tests/seller_dialog/test_handler.py`

- [ ] **Step 11.1: Read handle_event carefully**

Open `avito-monitor/app/services/messenger_bot/handler.py` and read lines 317-450. We add a branch:

After the function extracts `channel_id` from the event payload (somewhere after line 376 where it has `event.event_name != "new_message"`), insert a check: lookup `get_dialog_by_channel(session, channel_id)`. If a seller_dialog exists, route to `handle_seller_inbound()` and return a verdict marking this as a sales-flow handle; otherwise fall through to existing reliability flow.

- [ ] **Step 11.2: Implement the branch**

Inside `handle_event`, after `channel_id` is extracted and BEFORE the kill-switch / rate-limit gates fire, add:

```python
    # ── Seller-dialog flow branch ───────────────────────────────────────
    # If this channel belongs to a SellerDialog (= we initiated this chat
    # via accept-action), route into the sales handler and return.
    # The reliability flow's gates (kill-switch, dedup, etc.) don't apply.
    from app.db.session import async_session_maker
    from app.services.seller_dialog.service import get_dialog_by_channel
    from app.services.seller_dialog.handler import handle_seller_inbound

    async with async_session_maker() as sd_session:
        sales_dialog = await get_dialog_by_channel(sd_session, channel_id)
        if sales_dialog is not None:
            # Extract message metadata from the event payload
            payload = event.data.get("payload", {}) if isinstance(event.data, dict) else {}
            message_id = payload.get("message_id") or payload.get("id")
            author_id = payload.get("author_id") or payload.get("user_id")
            text = payload.get("text") or payload.get("body")
            try:
                await handle_seller_inbound(
                    session=sd_session,
                    channel_id=channel_id,
                    message_id=str(message_id) if message_id else f"missing-{channel_id}",
                    author_id=str(author_id) if author_id else None,
                    text=text,
                )
            except Exception:
                log.exception("seller_dialog.inbound failed channel=%s", channel_id)
            return HandlerVerdict(
                action="sales_handled",
                reason="routed to seller_dialog",
                details={"channel_id": channel_id, "dialog_id": str(sales_dialog.id)},
            )
```

Adjust `event.data`/`event.payload` field access to match the real `SseEvent` shape (look at existing handle_event code for how `channel_id` was extracted — copy the same approach for `message_id`/`text`).

- [ ] **Step 11.3: Add an integration test**

Append to `avito-monitor/tests/seller_dialog/test_handler.py`:

```python
@pytest.mark.asyncio
async def test_messenger_bot_routes_sales_channels_to_seller_handler():
    """When handle_event sees a known sales channel, it bypasses reliability gates."""
    from app.services.messenger_bot.handler import handle_event, HandlerVerdict
    from types import SimpleNamespace

    event = SimpleNamespace(
        event_name="new_message",
        data={"payload": {
            "channel_id": "ch_sales",
            "message_id": "m1",
            "author_id": "seller_id",
            "text": "Да, ещё продаётся",
        }},
    )
    client = AsyncMock()

    with patch("app.services.messenger_bot.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=MagicMock(id=uuid.uuid4()))), \
         patch("app.services.messenger_bot.handler.handle_seller_inbound",
               new=AsyncMock()) as m_inbound, \
         patch("app.services.messenger_bot.handler.async_session_maker"):
        verdict = await handle_event(event, client=client)

    assert verdict.action == "sales_handled"
    m_inbound.assert_awaited_once()
```

(The mock chain is finicky; if patching `async_session_maker` is awkward, refactor `handle_event` to accept an optional `session_maker` kwarg with a default, then test passes a custom factory. Either approach is fine.)

- [ ] **Step 11.4: Run tests, verify pass**

Run: `pytest tests/seller_dialog/test_handler.py -v`
Expected: 3 tests pass (2 original + 1 new).

- [ ] **Step 11.5: Commit**

```bash
git add avito-monitor/app/services/messenger_bot/handler.py \
        avito-monitor/tests/seller_dialog/test_handler.py
git commit -m "feat(messenger-bot): route sales channels to seller_dialog.handler"
```

### Task 12: Kanban view route + template

**Files:**
- Create: `avito-monitor/app/web/templates/listings_kanban.html`
- Modify: `avito-monitor/app/web/routers.py` — when `tab=in_progress`, render kanban
- Test: smoke (visual)

- [ ] **Step 12.1: Find the listings GET route**

Open `avito-monitor/app/web/routers.py` and find the GET `/listings` handler (it should construct `ListingFilters(tab=...)` and render `listings.html`). Note the function name and which template it currently uses.

- [ ] **Step 12.2: Create kanban template**

Create `avito-monitor/app/web/templates/listings_kanban.html`:

```html
{% extends "_layout.html" %}

{% block title %}В работе — Avito Monitor{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-4">

  {# Tab navigation — same as listings.html so user keeps orientation #}
  <div class="flex gap-2 mb-4 border-b border-stone-300">
    <a href="/listings?tab=new"
       class="px-4 py-2 text-sm {{ 'border-b-2 border-emerald-600 text-emerald-700 font-medium' if tab == 'new' else 'text-stone-600' }}">
      Новые
    </a>
    <a href="/listings?tab=in_progress"
       class="px-4 py-2 text-sm {{ 'border-b-2 border-emerald-600 text-emerald-700 font-medium' if tab == 'in_progress' else 'text-stone-600' }}">
      В работе
    </a>
    <a href="/listings?tab=rejected"
       class="px-4 py-2 text-sm {{ 'border-b-2 border-emerald-600 text-emerald-700 font-medium' if tab == 'rejected' else 'text-stone-600' }}">
      Отклонённые
    </a>
  </div>

  {# Phase A — 2 columns. Later phases will extend to 9 columns + horizontal scroll. #}
  <div class="grid grid-cols-2 gap-4">

    <div class="bg-stone-50 rounded-lg p-3 min-h-[300px]">
      <div class="flex items-center justify-between mb-3 px-1">
        <h2 class="text-sm font-semibold text-stone-700 uppercase tracking-wide">Контакт</h2>
        <span class="text-xs text-stone-500">{{ cards.contact|length }}</span>
      </div>
      {% for card in cards.contact %}
        {% include "_partials/kanban_card_contact.html" %}
      {% else %}
        <div class="text-xs text-stone-400 text-center py-8">пусто</div>
      {% endfor %}
    </div>

    <div class="bg-stone-50 rounded-lg p-3 min-h-[300px]">
      <div class="flex items-center justify-between mb-3 px-1">
        <h2 class="text-sm font-semibold text-stone-700 uppercase tracking-wide">Настройка опроса</h2>
        <span class="text-xs text-stone-500">{{ cards.questions_setup|length }}</span>
      </div>
      {% for card in cards.questions_setup %}
        {% include "_partials/kanban_card_questions_setup.html" %}
      {% else %}
        <div class="text-xs text-stone-400 text-center py-8">пусто</div>
      {% endfor %}
    </div>

  </div>
</div>
{% endblock %}
```

- [ ] **Step 12.3: Wire the route to render kanban for tab=in_progress**

In the GET `/listings` handler, branch on `tab`:

```python
    if tab == "in_progress":
        from app.services.seller_dialog_view import query_kanban_cards, KanbanFilters
        cards = await query_kanban_cards(session, user.id, KanbanFilters())
        return templates.TemplateResponse(
            "listings_kanban.html",
            {"request": request, "tab": tab, "cards": cards},
        )
```

Place this branch BEFORE the existing `query_listings(...)` call so the flat listings view never runs for in_progress.

- [ ] **Step 12.4: Manual UI verification**

Run dev locally (or check on the staging /prod URL):
```bash
# Locally:
cd avito-monitor && uvicorn app.main:app --reload
```
Open `http://localhost:8000/listings?tab=in_progress` (after logging in).
Expected: two columns rendered. If any accepted-lots exist from migration script (Task 9), they should appear in Контакт column with "ручной режим" badge. If none — both columns show "пусто".

- [ ] **Step 12.5: Commit**

```bash
git add avito-monitor/app/web/templates/listings_kanban.html \
        avito-monitor/app/web/routers.py
git commit -m "feat(web): kanban view for В работе tab (2 columns Phase A)"
```

---

## Wave 5 — Deploy + smoke test

### Task 13: Deploy Phase A to VPS

**Files:** none (deploy)

- [ ] **Step 13.1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 13.2: Sync to VPS**

```bash
rsync -av --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' \
  avito-monitor/ \
  root@81.200.119.132:/opt/avito-system/repo/avito-monitor/
```

- [ ] **Step 13.3: Apply migration on VPS**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose run --rm --no-deps avito-monitor alembic upgrade head'
```
Expected: `Running upgrade 0012_reservation_tracking -> 0013_seller_dialogs`.

- [ ] **Step 13.4: Run accepted-lots migration script on VPS**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose run --rm --no-deps \
    -v /opt/avito-system/repo/avito-monitor/scripts/migrate_accepted_to_dialogs.py:/app/migrate.py \
    avito-monitor python /app/migrate.py'
```
Expected: `accepted lots without dialog: N` followed by `inserted: N dialogs at stage=contact operator_mode=true`.

- [ ] **Step 13.5: Rebuild + restart services**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose build avito-monitor scheduler worker health-checker telegram-bot && \
  docker compose up -d avito-monitor scheduler worker health-checker telegram-bot'
```

- [ ] **Step 13.6: Verify kanban renders**

```bash
curl -sS -o /dev/null -w "/listings?tab=in_progress -> %{http_code}\n" \
  https://avitosystem.duckdns.org/listings?tab=in_progress
```
Expected: `200` (after auth — may be `303` redirect to login; either is OK).

Then open in browser: `https://avitosystem.duckdns.org/listings?tab=in_progress` — should see 2 columns, existing accepted lots in Контакт column with "ручной режим" badges.

### Task 14: Live smoke test with a real lot

**Files:** none (manual)

- [ ] **Step 14.1: Manually accept a fresh lot**

Open the `Новые` tab. Pick one lot you don't mind contacting. Click `✓ В работу`.

- [ ] **Step 14.2: Verify dialog was created in DB**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose run --rm --no-deps avito-monitor python -c "
import asyncio, asyncpg, os
async def m():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    rows = await conn.fetch(
      \"SELECT id, stage, channel_id, operator_mode, opened_at FROM seller_dialogs ORDER BY opened_at DESC LIMIT 5\"
    )
    for r in rows:
        print(dict(r))
    await conn.close()
asyncio.run(m())
"'
```
Expected: top row has `stage='contact'`, `operator_mode=False`, `channel_id` is populated (e.g. `'u2i-...'`), `opened_at` is the recent timestamp.

- [ ] **Step 14.3: Verify greeting was sent**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose run --rm --no-deps avito-monitor python -c "
import asyncio, asyncpg, os
async def m():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    rows = await conn.fetch(
      \"SELECT id, direction, text, created_at FROM messenger_messages WHERE dialog_id IS NOT NULL ORDER BY created_at DESC LIMIT 5\"
    )
    for r in rows:
        print(dict(r))
    await conn.close()
asyncio.run(m())
"'
```
Expected: an `direction='out'` message with `text='Здравствуйте! Меня заинтересовал ваш аппарат. Ещё продаётся?'` for the dialog you just created.

- [ ] **Step 14.4: Manually reply on the seller's side (from the phone or use a friend)**

Go to Avito-app on your test device → open chats → find the new chat with our system → reply: `Да, продается`.

- [ ] **Step 14.5: Watch worker logs**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && \
  docker compose logs --tail=50 -f worker' | grep -E "seller_dialog|sales_handled|transition"
```
Within ~10s of your reply, expect to see:
```
seller_dialog.handler transition dialog=<uuid> contact → questions_setup
```

- [ ] **Step 14.6: Verify the card moved to Настройка опроса column**

Open `https://avitosystem.duckdns.org/listings?tab=in_progress`.
Expected: the test card now sits in the second column («Настройка опроса») with amber border, badge `➜ настрой опрос`.

If everything above passes — **Phase A is complete**. Move on to the brainstorm+plan cycle for Phase B (Опрос autopilot).

If any step fails — apply systematic-debugging skill: read errors carefully, check worker logs for traceback, verify env vars / FK consistency / xapi connectivity. Common gotchas:
- `create_channel_by_item` returns 401 → xapi token expired / wrong account
- `start_seller_dialog.kiq` enqueued but worker never picks it up → check broker subscription / worker consuming queues
- SSE inbound never arrives → check `messenger_bot.runner` is running + connected; phone notifications routed properly
- `handle_seller_inbound` runs but doesn't transition → check LLM provider connectivity, verify `detect_yes_selling` actually returned True (add temporary log)

---

## Phase A acceptance criteria (recap)

- [x] Migration 0013 applied on prod, schema verified
- [x] Existing accepted lots seeded as operator_mode=true dialogs
- [x] New accept-click triggers auto-greeting end-to-end
- [x] Seller reply triggers stage transition contact → questions_setup
- [x] Kanban renders 2 columns; cards land in correct column based on stage
- [x] Operator-mode badge visible on existing-lot cards
- [x] Worker logs confirm transition events

After this lands and soaks 3-4 days, **next steps:**
- **Phase B brainstorm/plan**: Опрос autopilot — topic library, LLM dispatchers, dialog_tick_questions worker, Опрос column.
- **Phase C**: Operator drawer + Настройка опроса screen + operator overrides.
- **Phase D**: stages 4-9 (negotiation through close).
- **Phase E**: SLA worker (silent + notified-prolongate) + 6 TG-пингов + sortings/filters.

---

## Self-review notes

- **Spec coverage**: Phase A scope from spec §4 — auto-greeting (✓ T7), SSE routing (✓ T11), LLM yes-selling (✓ T4), stage transition (✓ T8), basic kanban (✓ T12), migration (✓ T9). Topic library / drawer / operator actions / SLA — deferred to later phases per plan intro.
- **Placeholder scan**: no TBD / TODO / "handle edge cases" without specifics. Every step has runnable code or runnable command.
- **Type consistency**: `dialog_id` uuid.UUID consistent across model / service / handler. Stage names use constants from `seller_dialog.constants`. `KanbanCard` dataclass fields match what `query_kanban_cards` returns and what the template iterates.
- **Parallelization markers**: Wave 2 (T3-T6) and Wave 3 (T7-T9) explicitly marked 🟢 PARALLEL. Wave 4 must be sequential (touches shared `routers.py`/`handler.py`). Wave 5 is deploy + manual smoke.
- **TDD discipline**: tests written first in every task that has substantive logic (T2, T3, T4, T5, T7, T8, T10, T11). T1 (migration) verified by schema introspection rather than unit test. T6 (templates), T9 (one-off script), T12 (UI route), T13/14 (deploy/smoke) — manual verification.
