# Defect Catalog (Project A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new admin tool at `/defects` for managing a global defect catalog with device hierarchy + bindings — config-only, no pipeline integration.

**Architecture:** Three new tables (`feature_nodes`, `device_nodes`, `device_feature_bindings`) — independent trees connected by bindings. Pure-Python resolver walks device tree to compute applicable defects with inheritance. Admin UI in FastAPI + Jinja + HTMX with two tabs (Устройства / Признаки). No changes to current `compute_bucket` / `ProfileFeatureRule` / kanban — those continue running on the flat 31-feature catalog.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Jinja2, HTMX, Tailwind (Avito-Cosplay tokens), pytest with SQLite in-memory.

**Spec:** [`DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md`](../specs/2026-05-13-defect-catalog-design.md)

---

## File map

**Models (3 new files, 1 modified):**
- Create: `avito-monitor/app/db/models/feature_node.py` — FeatureNode SQLAlchemy model
- Create: `avito-monitor/app/db/models/device_node.py` — DeviceNode model
- Create: `avito-monitor/app/db/models/device_feature_binding.py` — DeviceFeatureBinding model
- Modify: `avito-monitor/app/db/models/__init__.py` — re-export 3 new models

**Migration (1 new file):**
- Create: `avito-monitor/alembic/versions/20260514_1000_defect_catalog.py`

**Service layer (3 new files):**
- Create: `avito-monitor/app/services/defect_catalog/__init__.py`
- Create: `avito-monitor/app/services/defect_catalog/repository.py` — CRUD + cycle detection + slug validation
- Create: `avito-monitor/app/services/defect_catalog/resolver.py` — resolve_applicable_defects

**Web routes (1 new file, 1 modified):**
- Create: `avito-monitor/app/web/routers/defects.py` — all `/defects/*` endpoints
- Modify: `avito-monitor/app/main.py:54` — `app.include_router(defects_router)` after web_router

**Templates (8 new files, 1 modified):**
- Create: `avito-monitor/app/web/templates/defects/_layout.html` — wrapper with tabs
- Create: `avito-monitor/app/web/templates/defects/devices.html` — split-pane
- Create: `avito-monitor/app/web/templates/defects/catalog.html` — tree editor
- Create: `avito-monitor/app/web/templates/defects/_partials/device_tree.html`
- Create: `avito-monitor/app/web/templates/defects/_partials/device_detail.html`
- Create: `avito-monitor/app/web/templates/defects/_partials/binding_row.html`
- Create: `avito-monitor/app/web/templates/defects/_partials/feature_tree.html`
- Create: `avito-monitor/app/web/templates/defects/_partials/edit_modal.html`
- Modify: `avito-monitor/app/web/templates/_layout.html` — add «Дефекты» sidebar entry

**Seed (1 new file):**
- Create: `avito-monitor/scripts/seed_defect_catalog.py` — idempotent MVP seed

**Tests (6 new files):**
- Create: `avito-monitor/tests/defect_catalog/__init__.py` — empty
- Create: `avito-monitor/tests/defect_catalog/conftest.py` — SQLite DDL + fixtures
- Create: `avito-monitor/tests/defect_catalog/test_repository.py` — CRUD, cycles, slug validation
- Create: `avito-monitor/tests/defect_catalog/test_resolver.py` — inheritance, override, disabled
- Create: `avito-monitor/tests/defect_catalog/test_seed.py` — seed idempotency
- Create: `avito-monitor/tests/web/test_defects_routes.py` — endpoints + HTMX swaps

---

## Phase 1 — Models + Migration

### Task 1: SQLAlchemy model for FeatureNode

**Files:**
- Create: `avito-monitor/app/db/models/feature_node.py`

- [ ] **Step 1: Write the model file**

```python
"""FeatureNode — entry in the global defect catalog tree.

kind='node' = structural grouping (e.g., «Корпус»). Cannot be bound.
kind='defect' = leaf (e.g., «Стекло разбито»). Can be bound to device nodes.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeatureNode(Base):
    __tablename__ = "feature_nodes"
    __table_args__ = (
        UniqueConstraint("parent_id", "slug", name="uq_feature_nodes_parent_slug"),
        CheckConstraint("kind IN ('node', 'defect')", name="ck_feature_nodes_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("feature_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    prompt_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
```

- [ ] **Step 2: Commit**

```bash
git add avito-monitor/app/db/models/feature_node.py
git commit -m "feat(defect-catalog): FeatureNode model"
```

---

### Task 2: SQLAlchemy model for DeviceNode

**Files:**
- Create: `avito-monitor/app/db/models/device_node.py`

- [ ] **Step 1: Write the model file**

```python
"""DeviceNode — entry in the device hierarchy (Phone → Apple → iPhone 12 PM)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceNode(Base):
    __tablename__ = "device_nodes"
    __table_args__ = (
        UniqueConstraint("parent_id", "slug", name="uq_device_nodes_parent_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("device_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
```

- [ ] **Step 2: Commit**

```bash
git add avito-monitor/app/db/models/device_node.py
git commit -m "feat(defect-catalog): DeviceNode model"
```

---

### Task 3: SQLAlchemy model for DeviceFeatureBinding

**Files:**
- Create: `avito-monitor/app/db/models/device_feature_binding.py`

- [ ] **Step 1: Write the model file**

```python
"""DeviceFeatureBinding — links a device_node to a feature_node with severity."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, String,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceFeatureBinding(Base):
    __tablename__ = "device_feature_bindings"
    __table_args__ = (
        UniqueConstraint(
            "device_node_id", "feature_node_id",
            name="uq_dfb_device_feature",
        ),
        CheckConstraint(
            "defect_action IN ('block', 'info')",
            name="ck_dfb_defect_action",
        ),
        CheckConstraint(
            "unknown_action IN ('ask', 'skip')",
            name="ck_dfb_unknown_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    device_node_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("device_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_node_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("feature_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    defect_action: Mapped[str] = mapped_column(String(16), nullable=False)
    unknown_action: Mapped[str] = mapped_column(String(16), nullable=False)
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
```

- [ ] **Step 2: Commit**

```bash
git add avito-monitor/app/db/models/device_feature_binding.py
git commit -m "feat(defect-catalog): DeviceFeatureBinding model"
```

---

### Task 4: Re-export models from package

**Files:**
- Modify: `avito-monitor/app/db/models/__init__.py`

- [ ] **Step 1: Add three imports + __all__ entries (alphabetical order)**

Add after `from app.db.models.chat_dialog_state import ChatDialogState`:

```python
from app.db.models.device_feature_binding import DeviceFeatureBinding
from app.db.models.device_node import DeviceNode
```

Add after `from app.db.models.dialog_topic import DialogTopic`:

```python
from app.db.models.feature_node import FeatureNode
```

In `__all__` list, insert alphabetically:
```python
    "DeviceFeatureBinding",
    "DeviceNode",
    "FeatureNode",
```

- [ ] **Step 2: Verify imports work**

```bash
cd avito-monitor && python -c "from app.db.models import FeatureNode, DeviceNode, DeviceFeatureBinding; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add avito-monitor/app/db/models/__init__.py
git commit -m "feat(defect-catalog): re-export models from package"
```

---

### Task 5: Alembic migration 0017_defect_catalog

**Files:**
- Create: `avito-monitor/alembic/versions/20260514_1000_defect_catalog.py`

- [ ] **Step 1: Get current head revision**

```bash
cd avito-monitor && grep -h "^revision " alembic/versions/20260513_1000_unified_criteria.py
```

Note the revision string (e.g., `"0016_unified_criteria"`).

- [ ] **Step 2: Write the migration**

```python
"""defect_catalog — feature_nodes + device_nodes + device_feature_bindings

Revision ID: 0017_defect_catalog
Revises: 0016_unified_criteria
Create Date: 2026-05-14 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0017_defect_catalog"
down_revision = "0016_unified_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("feature_nodes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_hint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("parent_id", "slug", name="uq_feature_nodes_parent_slug"),
        sa.CheckConstraint("kind IN ('node', 'defect')", name="ck_feature_nodes_kind"),
    )
    op.create_index("idx_feature_nodes_parent", "feature_nodes", ["parent_id"])

    op.create_table(
        "device_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("device_nodes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("parent_id", "slug", name="uq_device_nodes_parent_slug"),
    )
    op.create_index("idx_device_nodes_parent", "device_nodes", ["parent_id"])

    op.create_table(
        "device_feature_bindings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("device_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("feature_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("feature_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("defect_action", sa.String(16), nullable=False),
        sa.Column("unknown_action", sa.String(16), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("device_node_id", "feature_node_id", name="uq_dfb_device_feature"),
        sa.CheckConstraint("defect_action IN ('block', 'info')", name="ck_dfb_defect_action"),
        sa.CheckConstraint("unknown_action IN ('ask', 'skip')", name="ck_dfb_unknown_action"),
    )
    op.create_index("idx_dfb_device", "device_feature_bindings", ["device_node_id"])
    op.create_index("idx_dfb_feature", "device_feature_bindings", ["feature_node_id"])


def downgrade() -> None:
    op.drop_index("idx_dfb_feature", table_name="device_feature_bindings")
    op.drop_index("idx_dfb_device", table_name="device_feature_bindings")
    op.drop_table("device_feature_bindings")
    op.drop_index("idx_device_nodes_parent", table_name="device_nodes")
    op.drop_table("device_nodes")
    op.drop_index("idx_feature_nodes_parent", table_name="feature_nodes")
    op.drop_table("feature_nodes")
```

- [ ] **Step 3: Verify alembic can parse it**

```bash
cd avito-monitor && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; sd = ScriptDirectory.from_config(Config('alembic.ini')); print(sd.get_revision('head').revision)"
```

Expected: `0017_defect_catalog`

- [ ] **Step 4: Commit**

```bash
git add avito-monitor/alembic/versions/20260514_1000_defect_catalog.py
git commit -m "feat(defect-catalog): migration 0017 — 3 new tables"
```

---

## Phase 2 — Test infrastructure

### Task 6: Test conftest with SQLite DDL

**Files:**
- Create: `avito-monitor/tests/defect_catalog/__init__.py`
- Create: `avito-monitor/tests/defect_catalog/conftest.py`

- [ ] **Step 1: Empty package init**

```bash
mkdir -p avito-monitor/tests/defect_catalog
touch avito-monitor/tests/defect_catalog/__init__.py
```

- [ ] **Step 2: Write conftest with SQLite DDL fixture**

```python
"""Fixtures for defect_catalog tests — in-memory async SQLite session
with raw DDL (UUID→TEXT, no Postgres-specific defaults)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS feature_nodes (
        id          TEXT PRIMARY KEY,
        parent_id   TEXT REFERENCES feature_nodes(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL,
        slug        TEXT NOT NULL,
        title       TEXT NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        prompt_hint TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (parent_id, slug),
        CHECK (kind IN ('node', 'defect'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_nodes (
        id          TEXT PRIMARY KEY,
        parent_id   TEXT REFERENCES device_nodes(id) ON DELETE CASCADE,
        slug        TEXT NOT NULL,
        title       TEXT NOT NULL,
        kind        TEXT,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (parent_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_feature_bindings (
        id              TEXT PRIMARY KEY,
        device_node_id  TEXT NOT NULL REFERENCES device_nodes(id) ON DELETE CASCADE,
        feature_node_id TEXT NOT NULL REFERENCES feature_nodes(id) ON DELETE CASCADE,
        defect_action   TEXT NOT NULL,
        unknown_action  TEXT NOT NULL,
        disabled        INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (device_node_id, feature_node_id),
        CHECK (defect_action IN ('block', 'info')),
        CHECK (unknown_action IN ('ask', 'skip'))
    )
    """,
]


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        for stmt in _DDL:
            await conn.execute(text(stmt))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        # Re-enable FK in session-level connection too
        await s.execute(text("PRAGMA foreign_keys = ON"))
        yield s
    await engine.dispose()
```

- [ ] **Step 3: Verify fixture works**

```bash
cd avito-monitor && python -c "
import asyncio
import pytest
from tests.defect_catalog.conftest import db_session
print('fixture imported OK')
"
```

Expected: `fixture imported OK`

- [ ] **Step 4: Commit**

```bash
git add avito-monitor/tests/defect_catalog/__init__.py avito-monitor/tests/defect_catalog/conftest.py
git commit -m "test(defect-catalog): conftest with SQLite DDL fixture"
```

---

## Phase 3 — Repository (CRUD + cycle detection)

### Task 7: Service package + slug validator

**Files:**
- Create: `avito-monitor/app/services/defect_catalog/__init__.py`
- Create: `avito-monitor/app/services/defect_catalog/repository.py` (skeleton + slug validator only)
- Test: `avito-monitor/tests/defect_catalog/test_repository.py` (slug tests)

- [ ] **Step 1: Write failing slug tests first**

```python
# tests/defect_catalog/test_repository.py
import pytest
from app.services.defect_catalog.repository import validate_slug


@pytest.mark.parametrize("good", ["icloud_linked", "iphone_12_pro_max", "x", "abc_123"])
def test_validate_slug_accepts_snake_case(good):
    validate_slug(good)  # no exception


@pytest.mark.parametrize("bad", ["", "WithCaps", "with space", "with-dash", "лат", "_leading"])
def test_validate_slug_rejects_invalid(bad):
    with pytest.raises(ValueError, match="slug"):
        validate_slug(bad)
```

- [ ] **Step 2: Run test, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: ImportError or AttributeError on `validate_slug`.

- [ ] **Step 3: Write the validator**

```python
# app/services/defect_catalog/__init__.py
```
(empty file)

```python
# app/services/defect_catalog/repository.py
"""CRUD + invariants for feature_nodes / device_nodes / device_feature_bindings."""
from __future__ import annotations

import re


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_slug(slug: str) -> None:
    """Slug must be ^[a-z][a-z0-9_]*$ (snake-case, starting with a letter)."""
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must match ^[a-z][a-z0-9_]*$"
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/defect_catalog/ avito-monitor/tests/defect_catalog/test_repository.py
git commit -m "feat(defect-catalog): slug validator"
```

---

### Task 8: Feature-node create + read

**Files:**
- Modify: `avito-monitor/app/services/defect_catalog/repository.py`
- Modify: `avito-monitor/tests/defect_catalog/test_repository.py`

- [ ] **Step 1: Add failing tests for create_feature_node**

Append to `test_repository.py`:

```python
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text
from app.services.defect_catalog.repository import (
    create_feature_node, get_feature_node, list_feature_children,
)


@pytest.mark.asyncio
async def test_create_root_feature_node(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    assert isinstance(nid, uuid.UUID)
    fn = await get_feature_node(db_session, nid)
    assert fn.title == "Корпус"
    assert fn.parent_id is None


@pytest.mark.asyncio
async def test_create_child_defect(db_session):
    case_id = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    leaf_id = await create_feature_node(
        db_session, parent_id=case_id, kind="defect",
        slug="back_broken", title="Задняя крышка разбита",
    )
    children = await list_feature_children(db_session, case_id)
    assert len(children) == 1
    assert children[0].id == leaf_id


@pytest.mark.asyncio
async def test_create_rejects_invalid_slug(db_session):
    with pytest.raises(ValueError, match="slug"):
        await create_feature_node(
            db_session, parent_id=None, kind="node", slug="Bad Slug", title="x",
        )
```

- [ ] **Step 2: Run tests, confirm fail (ImportError)**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v -k "create or list"
```

- [ ] **Step 3: Implement the 3 functions**

Append to `repository.py`:

```python
import uuid
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FeatureNodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: str
    slug: str
    title: str
    sort_order: int
    prompt_hint: str | None


def _row_to_fn(row) -> FeatureNodeRow:
    return FeatureNodeRow(
        id=uuid.UUID(str(row.id)),
        parent_id=uuid.UUID(str(row.parent_id)) if row.parent_id else None,
        kind=row.kind, slug=row.slug, title=row.title,
        sort_order=row.sort_order, prompt_hint=row.prompt_hint,
    )


async def create_feature_node(
    session: AsyncSession, *, parent_id: uuid.UUID | None,
    kind: str, slug: str, title: str, prompt_hint: str | None = None,
    sort_order: int = 0,
) -> uuid.UUID:
    validate_slug(slug)
    if kind not in ("node", "defect"):
        raise ValueError(f"Invalid kind {kind!r}")
    nid = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO feature_nodes
            (id, parent_id, kind, slug, title, sort_order, prompt_hint)
        VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
    """), {
        "id": str(nid), "pid": str(parent_id) if parent_id else None,
        "kind": kind, "slug": slug, "title": title,
        "sort": sort_order, "hint": prompt_hint,
    })
    await session.commit()
    return nid


async def get_feature_node(session: AsyncSession, nid: uuid.UUID) -> FeatureNodeRow | None:
    row = (await session.execute(
        text("SELECT * FROM feature_nodes WHERE id = :id"),
        {"id": str(nid)},
    )).first()
    return _row_to_fn(row) if row else None


async def list_feature_children(
    session: AsyncSession, parent_id: uuid.UUID | None,
) -> list[FeatureNodeRow]:
    if parent_id is None:
        rows = (await session.execute(
            text("SELECT * FROM feature_nodes WHERE parent_id IS NULL ORDER BY sort_order, slug")
        )).all()
    else:
        rows = (await session.execute(
            text("SELECT * FROM feature_nodes WHERE parent_id = :pid ORDER BY sort_order, slug"),
            {"pid": str(parent_id)},
        )).all()
    return [_row_to_fn(r) for r in rows]
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/defect_catalog/repository.py avito-monitor/tests/defect_catalog/test_repository.py
git commit -m "feat(defect-catalog): feature_node create / get / list_children"
```

---

### Task 9: Feature-node update / delete + duplicate-slug error

**Files:**
- Modify: `avito-monitor/app/services/defect_catalog/repository.py`
- Modify: `avito-monitor/tests/defect_catalog/test_repository.py`

- [ ] **Step 1: Add failing tests**

```python
from app.services.defect_catalog.repository import (
    update_feature_node, delete_feature_node,
)


@pytest.mark.asyncio
async def test_update_feature_node_title(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    await update_feature_node(db_session, nid, title="Корпус (обновлено)")
    fn = await get_feature_node(db_session, nid)
    assert fn.title == "Корпус (обновлено)"


@pytest.mark.asyncio
async def test_delete_cascade(db_session):
    case_id = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    leaf_id = await create_feature_node(
        db_session, parent_id=case_id, kind="defect",
        slug="back_broken", title="x",
    )
    await delete_feature_node(db_session, case_id)
    assert await get_feature_node(db_session, leaf_id) is None


@pytest.mark.asyncio
async def test_duplicate_slug_in_parent_rejected(db_session):
    pid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    await create_feature_node(
        db_session, parent_id=pid, kind="defect", slug="back_broken", title="A",
    )
    with pytest.raises(Exception):  # IntegrityError
        await create_feature_node(
            db_session, parent_id=pid, kind="defect", slug="back_broken", title="B",
        )
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v -k "update or delete or duplicate"
```

- [ ] **Step 3: Implement update/delete**

Append:

```python
async def update_feature_node(
    session: AsyncSession, nid: uuid.UUID, *,
    title: str | None = None, slug: str | None = None,
    parent_id: uuid.UUID | None = ..., sort_order: int | None = None,
    prompt_hint: str | None = ..., kind: str | None = None,
) -> None:
    sets, params = [], {"id": str(nid)}
    if title is not None:
        sets.append("title = :title"); params["title"] = title
    if slug is not None:
        validate_slug(slug); sets.append("slug = :slug"); params["slug"] = slug
    if parent_id is not ...:
        sets.append("parent_id = :pid"); params["pid"] = str(parent_id) if parent_id else None
    if sort_order is not None:
        sets.append("sort_order = :sort"); params["sort"] = sort_order
    if prompt_hint is not ...:
        sets.append("prompt_hint = :hint"); params["hint"] = prompt_hint
    if kind is not None:
        if kind not in ("node", "defect"):
            raise ValueError(f"Invalid kind {kind!r}")
        sets.append("kind = :kind"); params["kind"] = kind
    if not sets:
        return
    sets.append("updated_at = datetime('now')")  # SQLite-friendly; on PG NOW() preferred
    await session.execute(
        text(f"UPDATE feature_nodes SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_feature_node(session: AsyncSession, nid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM feature_nodes WHERE id = :id"), {"id": str(nid)},
    )
    await session.commit()
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat(defect-catalog): feature_node update / delete + duplicate-slug guard"
```

---

### Task 10: Cycle detection for feature_node parent change

**Files:**
- Modify: `avito-monitor/app/services/defect_catalog/repository.py`
- Modify: `avito-monitor/tests/defect_catalog/test_repository.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_update_parent_to_self_rejected(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="x",
    )
    with pytest.raises(ValueError, match="cycle"):
        await update_feature_node(db_session, nid, parent_id=nid)


@pytest.mark.asyncio
async def test_update_parent_to_descendant_rejected(db_session):
    root = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="root", title="r",
    )
    mid = await create_feature_node(
        db_session, parent_id=root, kind="node", slug="mid", title="m",
    )
    leaf = await create_feature_node(
        db_session, parent_id=mid, kind="defect", slug="leaf", title="l",
    )
    with pytest.raises(ValueError, match="cycle"):
        await update_feature_node(db_session, root, parent_id=leaf)
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v -k "cycle or descendant"
```

- [ ] **Step 3: Add cycle check inside update_feature_node**

In `update_feature_node`, AFTER processing args but BEFORE running the UPDATE, add:

```python
    if parent_id is not ... and parent_id is not None:
        if str(parent_id) == str(nid):
            raise ValueError("cycle: node cannot be its own parent")
        # Walk up from proposed new parent; if we hit nid, there's a cycle
        cursor = parent_id
        while cursor is not None:
            row = (await session.execute(
                text("SELECT parent_id FROM feature_nodes WHERE id = :id"),
                {"id": str(cursor)},
            )).first()
            if row is None:
                break
            if str(row.parent_id) == str(nid):
                raise ValueError("cycle: parent would create a loop")
            cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat(defect-catalog): cycle detection on feature_node parent change"
```

---

### Task 11: Device-node CRUD (mirror of feature-node)

**Files:**
- Modify: `avito-monitor/app/services/defect_catalog/repository.py`
- Modify: `avito-monitor/tests/defect_catalog/test_repository.py`

- [ ] **Step 1: Add failing tests**

```python
from app.services.defect_catalog.repository import (
    create_device_node, get_device_node, list_device_children,
    update_device_node, delete_device_node,
)


@pytest.mark.asyncio
async def test_device_node_crud(db_session):
    root = await create_device_node(
        db_session, parent_id=None, slug="phone", title="Phone", kind="type",
    )
    brand = await create_device_node(
        db_session, parent_id=root, slug="apple", title="Apple", kind="brand",
    )
    model = await create_device_node(
        db_session, parent_id=brand, slug="iphone_12_pm",
        title="iPhone 12 Pro Max", kind="model",
    )
    assert (await get_device_node(db_session, model)).title == "iPhone 12 Pro Max"
    assert len(await list_device_children(db_session, root)) == 1
    await delete_device_node(db_session, brand)
    assert await get_device_node(db_session, model) is None


@pytest.mark.asyncio
async def test_device_node_cycle_detection(db_session):
    a = await create_device_node(db_session, parent_id=None, slug="a", title="A")
    b = await create_device_node(db_session, parent_id=a, slug="b", title="B")
    with pytest.raises(ValueError, match="cycle"):
        await update_device_node(db_session, a, parent_id=b)
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v -k "device"
```

- [ ] **Step 3: Implement (mirror feature_node — same logic, table name swap)**

Append to `repository.py`:

```python
@dataclass
class DeviceNodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    slug: str
    title: str
    kind: str | None
    sort_order: int


def _row_to_dn(row) -> DeviceNodeRow:
    return DeviceNodeRow(
        id=uuid.UUID(str(row.id)),
        parent_id=uuid.UUID(str(row.parent_id)) if row.parent_id else None,
        slug=row.slug, title=row.title, kind=row.kind,
        sort_order=row.sort_order,
    )


async def create_device_node(
    session: AsyncSession, *, parent_id: uuid.UUID | None,
    slug: str, title: str, kind: str | None = None, sort_order: int = 0,
) -> uuid.UUID:
    validate_slug(slug)
    nid = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO device_nodes (id, parent_id, slug, title, kind, sort_order)
        VALUES (:id, :pid, :slug, :title, :kind, :sort)
    """), {
        "id": str(nid), "pid": str(parent_id) if parent_id else None,
        "slug": slug, "title": title, "kind": kind, "sort": sort_order,
    })
    await session.commit()
    return nid


async def get_device_node(session: AsyncSession, nid: uuid.UUID) -> DeviceNodeRow | None:
    row = (await session.execute(
        text("SELECT * FROM device_nodes WHERE id = :id"), {"id": str(nid)},
    )).first()
    return _row_to_dn(row) if row else None


async def list_device_children(
    session: AsyncSession, parent_id: uuid.UUID | None,
) -> list[DeviceNodeRow]:
    if parent_id is None:
        rows = (await session.execute(
            text("SELECT * FROM device_nodes WHERE parent_id IS NULL ORDER BY sort_order, slug")
        )).all()
    else:
        rows = (await session.execute(
            text("SELECT * FROM device_nodes WHERE parent_id = :pid ORDER BY sort_order, slug"),
            {"pid": str(parent_id)},
        )).all()
    return [_row_to_dn(r) for r in rows]


async def update_device_node(
    session: AsyncSession, nid: uuid.UUID, *,
    title: str | None = None, slug: str | None = None,
    parent_id: uuid.UUID | None = ..., kind: str | None = ...,
    sort_order: int | None = None,
) -> None:
    if parent_id is not ... and parent_id is not None:
        if str(parent_id) == str(nid):
            raise ValueError("cycle: device cannot be its own parent")
        cursor = parent_id
        while cursor is not None:
            row = (await session.execute(
                text("SELECT parent_id FROM device_nodes WHERE id = :id"),
                {"id": str(cursor)},
            )).first()
            if row is None:
                break
            if str(row.parent_id) == str(nid):
                raise ValueError("cycle: parent would create a loop")
            cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None

    sets, params = [], {"id": str(nid)}
    if title is not None:
        sets.append("title = :title"); params["title"] = title
    if slug is not None:
        validate_slug(slug); sets.append("slug = :slug"); params["slug"] = slug
    if parent_id is not ...:
        sets.append("parent_id = :pid"); params["pid"] = str(parent_id) if parent_id else None
    if kind is not ...:
        sets.append("kind = :kind"); params["kind"] = kind
    if sort_order is not None:
        sets.append("sort_order = :sort"); params["sort"] = sort_order
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    await session.execute(
        text(f"UPDATE device_nodes SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_device_node(session: AsyncSession, nid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM device_nodes WHERE id = :id"), {"id": str(nid)},
    )
    await session.commit()
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat(defect-catalog): device_node CRUD with cycle detection"
```

---

### Task 12: Binding CRUD + kind=defect validation

**Files:**
- Modify: `avito-monitor/app/services/defect_catalog/repository.py`
- Modify: `avito-monitor/tests/defect_catalog/test_repository.py`

- [ ] **Step 1: Add failing tests**

```python
from app.services.defect_catalog.repository import (
    create_binding, get_binding, list_bindings_at_device,
    update_binding, delete_binding,
)


@pytest_asyncio.fixture
async def seeded(db_session):
    """Seed a minimal tree: Phone device, Корпус node, Стекло defect."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    case = await create_feature_node(db_session, parent_id=None, kind="node", slug="case", title="Корпус")
    leaf = await create_feature_node(
        db_session, parent_id=case, kind="defect", slug="back_broken", title="Задняя крышка",
    )
    return {"phone": phone, "case": case, "leaf": leaf}


@pytest.mark.asyncio
async def test_create_binding_on_defect(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    b = await get_binding(db_session, bid)
    assert b.defect_action == "block"
    assert b.disabled is False


@pytest.mark.asyncio
async def test_binding_on_node_kind_rejected(db_session, seeded):
    """Cannot bind a non-leaf feature_node (kind='node')."""
    with pytest.raises(ValueError, match="defect"):
        await create_binding(
            db_session, device_node_id=seeded["phone"],
            feature_node_id=seeded["case"],  # this is kind='node', not 'defect'
            defect_action="block", unknown_action="ask",
        )


@pytest.mark.asyncio
async def test_binding_update_severity(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    await update_binding(db_session, bid, defect_action="info", unknown_action="skip")
    b = await get_binding(db_session, bid)
    assert b.defect_action == "info"
    assert b.unknown_action == "skip"


@pytest.mark.asyncio
async def test_binding_toggle_disabled(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    await update_binding(db_session, bid, disabled=True)
    assert (await get_binding(db_session, bid)).disabled is True


@pytest.mark.asyncio
async def test_binding_unique_per_device_feature(db_session, seeded):
    await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    with pytest.raises(Exception):  # IntegrityError
        await create_binding(
            db_session, device_node_id=seeded["phone"],
            feature_node_id=seeded["leaf"],
            defect_action="info", unknown_action="skip",
        )
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v -k binding
```

- [ ] **Step 3: Implement**

```python
@dataclass
class BindingRow:
    id: uuid.UUID
    device_node_id: uuid.UUID
    feature_node_id: uuid.UUID
    defect_action: str
    unknown_action: str
    disabled: bool


def _row_to_b(row) -> BindingRow:
    return BindingRow(
        id=uuid.UUID(str(row.id)),
        device_node_id=uuid.UUID(str(row.device_node_id)),
        feature_node_id=uuid.UUID(str(row.feature_node_id)),
        defect_action=row.defect_action,
        unknown_action=row.unknown_action,
        disabled=bool(row.disabled),
    )


async def create_binding(
    session: AsyncSession, *,
    device_node_id: uuid.UUID, feature_node_id: uuid.UUID,
    defect_action: str, unknown_action: str, disabled: bool = False,
) -> uuid.UUID:
    if defect_action not in ("block", "info"):
        raise ValueError(f"Invalid defect_action {defect_action!r}")
    if unknown_action not in ("ask", "skip"):
        raise ValueError(f"Invalid unknown_action {unknown_action!r}")
    # Enforce: feature must be a defect leaf
    row = (await session.execute(
        text("SELECT kind FROM feature_nodes WHERE id = :id"),
        {"id": str(feature_node_id)},
    )).first()
    if row is None:
        raise ValueError(f"feature_node {feature_node_id} not found")
    if row.kind != "defect":
        raise ValueError(
            f"feature_node {feature_node_id} is kind={row.kind!r}; "
            "bindings can only point to kind='defect' leaves"
        )

    bid = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO device_feature_bindings
            (id, device_node_id, feature_node_id, defect_action, unknown_action, disabled)
        VALUES (:id, :dn, :fn, :da, :ua, :dis)
    """), {
        "id": str(bid),
        "dn": str(device_node_id), "fn": str(feature_node_id),
        "da": defect_action, "ua": unknown_action,
        "dis": 1 if disabled else 0,
    })
    await session.commit()
    return bid


async def get_binding(session: AsyncSession, bid: uuid.UUID) -> BindingRow | None:
    row = (await session.execute(
        text("SELECT * FROM device_feature_bindings WHERE id = :id"),
        {"id": str(bid)},
    )).first()
    return _row_to_b(row) if row else None


async def list_bindings_at_device(
    session: AsyncSession, device_node_id: uuid.UUID,
) -> list[BindingRow]:
    rows = (await session.execute(
        text("SELECT * FROM device_feature_bindings WHERE device_node_id = :dn"),
        {"dn": str(device_node_id)},
    )).all()
    return [_row_to_b(r) for r in rows]


async def update_binding(
    session: AsyncSession, bid: uuid.UUID, *,
    defect_action: str | None = None, unknown_action: str | None = None,
    disabled: bool | None = None,
) -> None:
    sets, params = [], {"id": str(bid)}
    if defect_action is not None:
        if defect_action not in ("block", "info"):
            raise ValueError(f"Invalid defect_action {defect_action!r}")
        sets.append("defect_action = :da"); params["da"] = defect_action
    if unknown_action is not None:
        if unknown_action not in ("ask", "skip"):
            raise ValueError(f"Invalid unknown_action {unknown_action!r}")
        sets.append("unknown_action = :ua"); params["ua"] = unknown_action
    if disabled is not None:
        sets.append("disabled = :dis"); params["dis"] = 1 if disabled else 0
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    await session.execute(
        text(f"UPDATE device_feature_bindings SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_binding(session: AsyncSession, bid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM device_feature_bindings WHERE id = :id"), {"id": str(bid)},
    )
    await session.commit()
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_repository.py -v
```

Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat(defect-catalog): binding CRUD + kind='defect' constraint"
```

---

## Phase 4 — Resolver (inheritance algorithm)

### Task 13: Resolver — single device, own bindings

**Files:**
- Create: `avito-monitor/app/services/defect_catalog/resolver.py`
- Create: `avito-monitor/tests/defect_catalog/test_resolver.py`

- [ ] **Step 1: Write failing test**

```python
# tests/defect_catalog/test_resolver.py
import pytest
import pytest_asyncio
from app.services.defect_catalog.repository import (
    create_device_node, create_feature_node, create_binding,
)
from app.services.defect_catalog.resolver import resolve_applicable_defects


@pytest_asyncio.fixture
async def basic_tree(db_session):
    """Phone → Apple → iPhone 12 PM; one defect Стекло разбито bound at Phone."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    apple = await create_device_node(db_session, parent_id=phone, slug="apple", title="Apple")
    ipm = await create_device_node(
        db_session, parent_id=apple, slug="ipm", title="iPhone 12 PM",
    )
    display = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="display", title="Дисплей",
    )
    glass = await create_feature_node(
        db_session, parent_id=display, kind="defect",
        slug="glass_broken", title="Стекло разбито",
    )
    bid = await create_binding(
        db_session, device_node_id=phone, feature_node_id=glass,
        defect_action="info", unknown_action="ask",
    )
    return {"phone": phone, "apple": apple, "ipm": ipm,
            "display": display, "glass": glass, "binding": bid}


@pytest.mark.asyncio
async def test_resolver_returns_own_binding(db_session, basic_tree):
    """Bindings on the target device itself are returned."""
    resolved = await resolve_applicable_defects(db_session, basic_tree["phone"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.feature_node_id == basic_tree["glass"]
    assert r.defect_action == "info"
    assert r.unknown_action == "ask"
    assert r.inherited_from is None
    assert r.feature_path == ["Дисплей", "Стекло разбито"]
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

- [ ] **Step 3: Implement skeleton**

```python
# app/services/defect_catalog/resolver.py
"""Resolve applicable defects for a target device via inheritance walk-up."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ResolvedBinding:
    binding_id: uuid.UUID
    feature_node_id: uuid.UUID
    feature_path: list[str]   # ["Дисплей", "Стекло разбито"]
    defect_action: Literal["block", "info"]
    unknown_action: Literal["ask", "skip"]
    inherited_from: uuid.UUID | None  # device_node where binding was defined; None if on target


async def _walk_up_device(session: AsyncSession, start_id: uuid.UUID) -> list[uuid.UUID]:
    """Return [target, parent, ..., root]."""
    out: list[uuid.UUID] = []
    cursor: uuid.UUID | None = start_id
    while cursor is not None:
        out.append(cursor)
        row = (await session.execute(
            text("SELECT parent_id FROM device_nodes WHERE id = :id"),
            {"id": str(cursor)},
        )).first()
        if row is None or row.parent_id is None:
            break
        cursor = uuid.UUID(str(row.parent_id))
    return out


async def _feature_path(session: AsyncSession, leaf_id: uuid.UUID) -> list[str]:
    """Walk feature tree up; return titles ordered root → leaf."""
    titles: list[str] = []
    cursor: uuid.UUID | None = leaf_id
    while cursor is not None:
        row = (await session.execute(
            text("SELECT title, parent_id FROM feature_nodes WHERE id = :id"),
            {"id": str(cursor)},
        )).first()
        if row is None:
            break
        titles.append(row.title)
        cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None
    return list(reversed(titles))


async def resolve_applicable_defects(
    session: AsyncSession, target_device_node_id: uuid.UUID,
) -> list[ResolvedBinding]:
    """Walk device tree up from target; for each feature take nearest-ancestor binding.
    Drop disabled. Sort by feature_path."""
    ancestors = await _walk_up_device(session, target_device_node_id)
    resolved: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID, str, str, bool]] = {}
    # (binding_id, source_device, da, ua, disabled), keyed by feature_node_id
    for anc in ancestors:
        rows = (await session.execute(
            text("""
                SELECT id, feature_node_id, defect_action, unknown_action, disabled
                FROM device_feature_bindings WHERE device_node_id = :dn
            """),
            {"dn": str(anc)},
        )).all()
        for r in rows:
            fnid = uuid.UUID(str(r.feature_node_id))
            if fnid in resolved:
                continue  # nearer ancestor already won
            resolved[fnid] = (
                uuid.UUID(str(r.id)), anc,
                r.defect_action, r.unknown_action, bool(r.disabled),
            )

    out: list[ResolvedBinding] = []
    for fnid, (bid, source, da, ua, dis) in resolved.items():
        if dis:
            continue
        path = await _feature_path(session, fnid)
        out.append(ResolvedBinding(
            binding_id=bid, feature_node_id=fnid, feature_path=path,
            defect_action=da, unknown_action=ua,
            inherited_from=(None if source == target_device_node_id else source),
        ))
    out.sort(key=lambda r: r.feature_path)
    return out
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/services/defect_catalog/resolver.py avito-monitor/tests/defect_catalog/test_resolver.py
git commit -m "feat(defect-catalog): resolver skeleton + own-binding test"
```

---

### Task 14: Resolver — inheritance from ancestor

**Files:**
- Modify: `avito-monitor/tests/defect_catalog/test_resolver.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_resolver_inherits_from_ancestor(db_session, basic_tree):
    """Binding on Phone is visible from iPhone 12 PM, marked as inherited."""
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.feature_node_id == basic_tree["glass"]
    assert r.defect_action == "info"
    assert r.inherited_from == basic_tree["phone"]
```

- [ ] **Step 2: Run, confirm pass (already works thanks to Task 13 implementation)**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "test(defect-catalog): resolver inherits ancestor binding"
```

---

### Task 15: Resolver — override (child wins)

**Files:**
- Modify: `avito-monitor/tests/defect_catalog/test_resolver.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_resolver_child_overrides_ancestor(db_session, basic_tree):
    """Phone-level (info, ask). iPhone 12 PM overrides to (block, skip).
    Resolution returns iPhone-level binding."""
    await create_binding(
        db_session, device_node_id=basic_tree["ipm"],
        feature_node_id=basic_tree["glass"],
        defect_action="block", unknown_action="skip",
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.defect_action == "block"
    assert r.unknown_action == "skip"
    assert r.inherited_from is None  # set on target
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "test(defect-catalog): resolver respects child override"
```

---

### Task 16: Resolver — disabled flag drops binding

**Files:**
- Modify: `avito-monitor/tests/defect_catalog/test_resolver.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_resolver_disabled_drops_inherited(db_session, basic_tree):
    """iPhone 12 PM marks the inherited binding as disabled — resolver drops it."""
    from app.services.defect_catalog.repository import create_binding as _cb
    await _cb(
        db_session, device_node_id=basic_tree["ipm"],
        feature_node_id=basic_tree["glass"],
        defect_action="info", unknown_action="ask",
        disabled=True,
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert resolved == []
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "test(defect-catalog): resolver drops disabled bindings"
```

---

### Task 17: Resolver — multiple features sorted by path

**Files:**
- Modify: `avito-monitor/tests/defect_catalog/test_resolver.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_resolver_sorts_by_feature_path(db_session, basic_tree):
    """Multiple defects across two узлы — output sorted by [section, title]."""
    case = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    back = await create_feature_node(
        db_session, parent_id=case, kind="defect",
        slug="back_broken", title="Задняя крышка разбита",
    )
    await create_binding(
        db_session, device_node_id=basic_tree["phone"], feature_node_id=back,
        defect_action="info", unknown_action="skip",
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert [r.feature_path for r in resolved] == [
        ["Дисплей", "Стекло разбито"],
        ["Корпус", "Задняя крышка разбита"],
    ]
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_resolver.py -v
```

Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "test(defect-catalog): resolver output sorted by feature_path"
```

---

## Phase 5 — Web routes + templates

### Task 18: Defects router skeleton + redirect

**Files:**
- Create: `avito-monitor/app/web/routers/defects.py`
- Modify: `avito-monitor/app/main.py`

- [ ] **Step 1: Check existing router registration**

```bash
cd avito-monitor && grep -n "web_router\|include_router" app/main.py | head -10
```

Note the line where `web_router` is included. We'll add `defects_router` right after.

- [ ] **Step 2: Skeleton router**

```python
# app/web/routers/defects.py
"""Admin UI for defect catalog (Project A)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import db_session
from app.web.auth import require_user
from app.web.templating import templates  # adjust import to match codebase
from app.db.models import User


router = APIRouter(prefix="/defects", tags=["defects"])


@router.get("", include_in_schema=False)
async def defects_root() -> RedirectResponse:
    return RedirectResponse(url="/defects/devices", status_code=303)


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/devices.html",
        {"active_tab": "devices", "user": user},
    )


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/catalog.html",
        {"active_tab": "catalog", "user": user},
    )
```

**Note:** Adjust `from app.web.templating import templates` and `from app.web.auth import require_user` and `from app.db.deps import db_session` to match existing module paths in the codebase. Check `app/web/routers.py` for the existing imports.

- [ ] **Step 3: Register router in main.py**

In `app/main.py` after `app.include_router(web_router)`:

```python
    from app.web.routers.defects import router as defects_router
    app.include_router(defects_router)
```

- [ ] **Step 4: Verify import works**

```bash
cd avito-monitor && python -c "from app.web.routers.defects import router; print(router.prefix)"
```

Expected: `/defects`

- [ ] **Step 5: Commit**

```bash
git add avito-monitor/app/web/routers/defects.py avito-monitor/app/main.py
git commit -m "feat(defect-catalog): router skeleton + registration"
```

---

### Task 19: Templates — minimal layout + tabs

**Files:**
- Create: `avito-monitor/app/web/templates/defects/_layout.html`
- Create: `avito-monitor/app/web/templates/defects/devices.html`
- Create: `avito-monitor/app/web/templates/defects/catalog.html`

- [ ] **Step 1: Inspect existing template extension pattern**

```bash
cd avito-monitor && head -15 app/web/templates/profiles/feature_rules.html
```

Note `{% extends %}` line. New templates should use the same parent.

- [ ] **Step 2: Write _layout.html (defects-specific tabs wrapper)**

```html
{# app/web/templates/defects/_layout.html #}
{% extends "_layout.html" %}
{% block title %}Дефекты — Настройки{% endblock %}
{% block content %}
<div class="max-w-6xl mx-auto px-4 py-4">
  <h1 class="text-xl font-medium text-avito-text mb-4">Настройки дефектов</h1>
  <nav class="flex border-b border-avito-border-soft mb-4 text-sm">
    <a href="/defects/devices"
       class="px-4 py-2 -mb-px border-b-2 {% if active_tab == 'devices' %}border-avito-green text-avito-green{% else %}border-transparent text-avito-text-soft hover:text-avito-text{% endif %}">
      Устройства
    </a>
    <a href="/defects/catalog"
       class="px-4 py-2 -mb-px border-b-2 {% if active_tab == 'catalog' %}border-avito-green text-avito-green{% else %}border-transparent text-avito-text-soft hover:text-avito-text{% endif %}">
      Признаки
    </a>
  </nav>
  {% block defects_content %}{% endblock %}
</div>
{% endblock %}
```

- [ ] **Step 3: Write devices.html stub**

```html
{# app/web/templates/defects/devices.html #}
{% extends "defects/_layout.html" %}
{% block defects_content %}
<div class="grid grid-cols-4 gap-4">
  <aside class="col-span-1 bg-white rounded border border-avito-border-soft p-3">
    <div class="text-xs uppercase text-avito-text-soft mb-2">Устройства</div>
    <div id="device-tree" hx-get="/defects/devices/tree" hx-trigger="load" hx-swap="innerHTML">
      <div class="text-avito-text-soft">Loading…</div>
    </div>
  </aside>
  <section class="col-span-3 bg-white rounded border border-avito-border-soft p-3 min-h-[40vh]">
    <div class="text-avito-text-soft">Выберите устройство в дереве слева.</div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 4: Write catalog.html stub**

```html
{# app/web/templates/defects/catalog.html #}
{% extends "defects/_layout.html" %}
{% block defects_content %}
<div class="bg-white rounded border border-avito-border-soft p-3">
  <div class="text-xs uppercase text-avito-text-soft mb-2">Каталог признаков</div>
  <div id="feature-tree" hx-get="/defects/catalog/tree" hx-trigger="load" hx-swap="innerHTML">
    <div class="text-avito-text-soft">Loading…</div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Manual local check (no test yet — needs DB)**

Start dev server (skip if not available; the rest of testing is integration):
```bash
# Optional — if local FastAPI runs without DB this'd fail. Skip and rely on test in Task 24.
```

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/web/templates/defects/
git commit -m "feat(defect-catalog): minimal templates — layout + 2 tab stubs"
```

---

### Task 20: Device tree partial endpoint + template

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`
- Create: `avito-monitor/app/web/templates/defects/_partials/device_tree.html`

- [ ] **Step 1: Add endpoint**

Append to `defects.py`:

```python
from app.services.defect_catalog.repository import list_device_children


@router.get("/devices/tree", response_class=HTMLResponse)
async def devices_tree(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    """Return the full device tree as nested <details> partial."""
    roots = await list_device_children(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html",
        {"roots": roots, "session": session, "list_device_children": list_device_children},
    )
```

- [ ] **Step 2: Write recursive partial**

```html
{# app/web/templates/defects/_partials/device_tree.html #}
{% macro render(node, session, lister) %}
  {% set children = lister(session, parent_id=node.id) | await %}
  {% if children %}
    <details class="ml-2" open>
      <summary class="cursor-pointer text-sm py-1 hover:text-avito-green">
        <a href="/defects/devices/{{ node.id }}" hx-boost="false">{{ node.title }}</a>
      </summary>
      {% for child in children %}
        {{ render(child, session, lister) }}
      {% endfor %}
    </details>
  {% else %}
    <div class="ml-4 text-sm py-1">
      <a href="/defects/devices/{{ node.id }}" hx-boost="false"
         class="hover:text-avito-green">{{ node.title }}</a>
    </div>
  {% endif %}
{% endmacro %}

{% for root in roots %}
  {{ render(root, session, list_device_children) }}
{% endfor %}
```

**Note on `| await`:** Jinja's async support requires the template environment to be configured with `enable_async=True`. Verify this in existing template config (`app/web/templating.py` or wherever). If not enabled, the partial should call a precomputed nested dict from the endpoint instead — see fallback in Step 3.

- [ ] **Step 3: Fallback if templates aren't async — precompute tree in endpoint**

If `templates.TemplateResponse` doesn't support `await` inside templates, replace the endpoint:

```python
async def _build_device_tree(session: AsyncSession, parent_id):
    nodes = await list_device_children(session, parent_id=parent_id)
    return [{"node": n, "children": await _build_device_tree(session, n.id)} for n in nodes]


@router.get("/devices/tree", response_class=HTMLResponse)
async def devices_tree(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )
```

And the partial becomes:

```html
{% macro render(entry) %}
  {% if entry.children %}
    <details class="ml-2" open>
      <summary class="cursor-pointer text-sm py-1 hover:text-avito-green">
        <a href="/defects/devices/{{ entry.node.id }}" hx-boost="false">{{ entry.node.title }}</a>
      </summary>
      {% for child in entry.children %}{{ render(child) }}{% endfor %}
    </details>
  {% else %}
    <div class="ml-4 text-sm py-1">
      <a href="/defects/devices/{{ entry.node.id }}" hx-boost="false"
         class="hover:text-avito-green">{{ entry.node.title }}</a>
    </div>
  {% endif %}
{% endmacro %}
{% for entry in tree %}{{ render(entry) }}{% endfor %}
```

Use this fallback unless you've confirmed Jinja async is enabled.

- [ ] **Step 4: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py avito-monitor/app/web/templates/defects/_partials/
git commit -m "feat(defect-catalog): /defects/devices/tree partial endpoint"
```

---

### Task 21: Device detail endpoint + bindings partial

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`
- Create: `avito-monitor/app/web/templates/defects/_partials/device_detail.html`
- Create: `avito-monitor/app/web/templates/defects/_partials/binding_row.html`

- [ ] **Step 1: Add endpoint**

```python
import uuid
from app.services.defect_catalog.repository import get_device_node
from app.services.defect_catalog.resolver import resolve_applicable_defects


@router.get("/devices/{device_id}", response_class=HTMLResponse)
async def device_detail(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    device = await get_device_node(session, device_id)
    if device is None:
        return HTMLResponse("Device not found", status_code=404)
    resolved = await resolve_applicable_defects(session, device_id)
    return templates.TemplateResponse(
        request, "defects/_partials/device_detail.html",
        {"active_tab": "devices", "device": device, "bindings": resolved},
    )
```

- [ ] **Step 2: Detail template**

```html
{# app/web/templates/defects/_partials/device_detail.html #}
{% extends "defects/_layout.html" %}
{% block defects_content %}
<div class="grid grid-cols-4 gap-4">
  <aside class="col-span-1 bg-white rounded border border-avito-border-soft p-3">
    <div class="text-xs uppercase text-avito-text-soft mb-2">Устройства</div>
    <div id="device-tree" hx-get="/defects/devices/tree" hx-trigger="load" hx-swap="innerHTML">
      <div class="text-avito-text-soft">Loading…</div>
    </div>
  </aside>
  <section class="col-span-3 bg-white rounded border border-avito-border-soft p-3">
    <h2 class="text-lg font-medium mb-1">{{ device.title }}</h2>
    <div class="text-xs text-avito-text-soft mb-3">
      Применимые дефекты ({{ bindings | length }})
    </div>
    <div id="bindings-list" class="space-y-3">
      {% for b in bindings %}
        {% include "defects/_partials/binding_row.html" %}
      {% endfor %}
      {% if not bindings %}
        <div class="text-avito-text-soft text-sm">Нет привязанных дефектов.</div>
      {% endif %}
    </div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 3: Binding row partial**

UX distinction: inherited rows are **read-only** with an «Override» button (which POSTs a new binding on the target device); set-here rows have editable dropdowns. The endpoint context must pass `target_device_id` so inherited-row Override knows where to create.

```html
{# app/web/templates/defects/_partials/binding_row.html
   Context: b (ResolvedBinding-shaped), target_device_id (uuid str). #}
<div class="flex items-start gap-3 py-2 border-b border-avito-border-soft text-sm"
     id="binding-{{ b.binding_id }}">
  <div class="flex-1">
    <div class="font-medium">{{ b.feature_path | join(' / ') }}</div>

    {% if b.inherited_from %}
      {# Inherited — read-only labels + Override button #}
      <div class="mt-1 text-xs">
        При находке: <strong>{{ b.defect_action }}</strong>
        · Если неясно: <strong>{{ b.unknown_action }}</strong>
      </div>
      <div class="mt-1 text-xs text-avito-text-soft">← inherited from ancestor</div>
    {% else %}
      {# Set here — editable dropdowns #}
      <div class="mt-1 flex gap-3 items-center text-xs">
        <label>При находке:
          <select hx-patch="/defects/bindings/{{ b.binding_id }}"
                  hx-target="#binding-{{ b.binding_id }}"
                  hx-swap="outerHTML"
                  hx-vals='{"target_device_id": "{{ target_device_id }}"}'
                  name="defect_action"
                  class="border rounded px-1">
            <option value="block" {% if b.defect_action == 'block' %}selected{% endif %}>block</option>
            <option value="info"  {% if b.defect_action == 'info'  %}selected{% endif %}>info</option>
          </select>
        </label>
        <label>Если неясно:
          <select hx-patch="/defects/bindings/{{ b.binding_id }}"
                  hx-target="#binding-{{ b.binding_id }}"
                  hx-swap="outerHTML"
                  hx-vals='{"target_device_id": "{{ target_device_id }}"}'
                  name="unknown_action"
                  class="border rounded px-1">
            <option value="ask"  {% if b.unknown_action == 'ask'  %}selected{% endif %}>ask</option>
            <option value="skip" {% if b.unknown_action == 'skip' %}selected{% endif %}>skip</option>
          </select>
        </label>
      </div>
      <div class="mt-1 text-xs text-avito-text-soft">← set here</div>
    {% endif %}
  </div>

  {% if b.inherited_from %}
    <form hx-post="/defects/bindings" hx-target="#binding-{{ b.binding_id }}" hx-swap="outerHTML">
      <input type="hidden" name="device_node_id"  value="{{ target_device_id }}">
      <input type="hidden" name="feature_node_id" value="{{ b.feature_node_id }}">
      <input type="hidden" name="defect_action"   value="{{ b.defect_action }}">
      <input type="hidden" name="unknown_action"  value="{{ b.unknown_action }}">
      <button type="submit"
              class="text-xs text-avito-text-soft hover:text-avito-green">Override</button>
    </form>
  {% else %}
    <button hx-delete="/defects/bindings/{{ b.binding_id }}"
            hx-target="#binding-{{ b.binding_id }}"
            hx-swap="delete"
            class="text-xs text-avito-text-soft hover:text-red-600">Удалить</button>
  {% endif %}
</div>
```

**Implication for endpoints:**
- Task 21 (`device_detail`) — pass `target_device_id` (str) into the template context for `device_detail.html` and via `{% include %}` `binding_row.html`.
- Task 22 (`patch_binding`) — read the new `target_device_id` form field; after PATCH, re-render binding_row with `target_device_id` so the `set here` button stays correct.
- Task 25 (`create_binding_endpoint`) — same; the new binding is set-here on `target_device_id`, render it that way.

Update Task 21's `device_detail.html` include to pass `target_device_id`:

```html
{% set target_device_id = device.id | string %}
{% for b in bindings %}
  {% include "defects/_partials/binding_row.html" %}
{% endfor %}
```

- [ ] **Step 4: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py avito-monitor/app/web/templates/defects/_partials/
git commit -m "feat(defect-catalog): device detail page with applicable bindings"
```

---

### Task 22: Binding PATCH / DELETE endpoints (HTMX swap)

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`

- [ ] **Step 1: Add endpoints**

```python
from fastapi import Form
from app.services.defect_catalog.repository import (
    get_binding, update_binding, delete_binding,
)


@router.patch("/bindings/{binding_id}", response_class=HTMLResponse)
async def patch_binding(
    binding_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    defect_action: Annotated[str | None, Form()] = None,
    unknown_action: Annotated[str | None, Form()] = None,
    disabled: Annotated[bool | None, Form()] = None,
    target_device_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    await update_binding(
        session, binding_id,
        defect_action=defect_action,
        unknown_action=unknown_action,
        disabled=disabled,
    )
    b = await get_binding(session, binding_id)
    if b is None:
        return HTMLResponse("", status_code=200)
    from app.services.defect_catalog.resolver import _feature_path
    fp = await _feature_path(session, b.feature_node_id)
    view = {
        "binding_id": b.id,
        "feature_node_id": b.feature_node_id,
        "feature_path": fp,
        "defect_action": b.defect_action,
        "unknown_action": b.unknown_action,
        "inherited_from": None,  # PATCH was on this device's set-here row
    }
    return templates.TemplateResponse(
        request, "defects/_partials/binding_row.html",
        {"b": view, "target_device_id": target_device_id or str(b.device_node_id)},
    )


@router.delete("/bindings/{binding_id}", response_class=HTMLResponse)
async def delete_binding_endpoint(
    binding_id: uuid.UUID,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_binding(session, binding_id)
    return HTMLResponse("", status_code=200)
```

- [ ] **Step 2: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py
git commit -m "feat(defect-catalog): binding PATCH/DELETE endpoints (HTMX swap)"
```

---

### Task 23: Catalog tree partial endpoint

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`
- Create: `avito-monitor/app/web/templates/defects/_partials/feature_tree.html`

- [ ] **Step 1: Add endpoint (mirror of device tree)**

```python
from app.services.defect_catalog.repository import list_feature_children


async def _build_feature_tree(session: AsyncSession, parent_id):
    nodes = await list_feature_children(session, parent_id=parent_id)
    return [{"node": n, "children": await _build_feature_tree(session, n.id)} for n in nodes]


@router.get("/catalog/tree", response_class=HTMLResponse)
async def catalog_tree(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )
```

- [ ] **Step 2: Partial template**

```html
{# app/web/templates/defects/_partials/feature_tree.html #}
{% macro render(entry) %}
  {% if entry.node.kind == 'node' %}
    <details class="ml-2" open>
      <summary class="cursor-pointer text-sm py-1 font-medium">
        ▼ {{ entry.node.title }}
      </summary>
      {% for child in entry.children %}{{ render(child) }}{% endfor %}
    </details>
  {% else %}
    <div class="ml-4 text-sm py-1">• {{ entry.node.title }}</div>
  {% endif %}
{% endmacro %}
{% for entry in tree %}{{ render(entry) }}{% endfor %}
```

- [ ] **Step 3: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py avito-monitor/app/web/templates/defects/_partials/
git commit -m "feat(defect-catalog): /defects/catalog/tree partial endpoint"
```

---

### Task 24: Integration test — route smoke

**Files:**
- Create: `avito-monitor/tests/web/test_defects_routes.py`

- [ ] **Step 1: Write smoke tests**

Check existing `tests/web/conftest.py` for `client` fixture pattern (TestClient or AsyncClient + auth).

```python
"""Smoke tests for /defects/* routes."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_defects_root_redirects(client):
    resp = await client.get("/defects", follow_redirects=False)
    assert resp.status_code in (303, 307)
    assert resp.headers["location"] == "/defects/devices"


@pytest.mark.asyncio
async def test_defects_devices_page_200(client):
    resp = await client.get("/defects/devices")
    assert resp.status_code == 200
    assert "Дефекты" in resp.text or "Настройки дефектов" in resp.text


@pytest.mark.asyncio
async def test_defects_catalog_page_200(client):
    resp = await client.get("/defects/catalog")
    assert resp.status_code == 200
    assert "Каталог признаков" in resp.text


@pytest.mark.asyncio
async def test_defects_devices_tree_empty_200(client):
    resp = await client.get("/defects/devices/tree")
    assert resp.status_code == 200
    # Empty tree — body is just empty macro output, may be a few whitespace chars
    assert "<details" not in resp.text
```

- [ ] **Step 2: Run**

```bash
cd avito-monitor && python -m pytest tests/web/test_defects_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add avito-monitor/tests/web/test_defects_routes.py
git commit -m "test(defect-catalog): smoke tests for /defects routes"
```

---

## Phase 6 — CRUD endpoints (feature_node, device_node, binding create)

### Task 25: POST /defects/devices + POST /defects/catalog + POST /defects/bindings

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`

- [ ] **Step 1: Add endpoints**

```python
from app.services.defect_catalog.repository import (
    create_device_node, create_feature_node, create_binding,
)


@router.post("/devices", response_class=HTMLResponse)
async def create_device_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    parent_id: Annotated[str | None, Form()] = None,
    slug: Annotated[str, Form()] = ...,
    title: Annotated[str, Form()] = ...,
    kind: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else None
    try:
        await create_device_node(session, parent_id=pid, slug=slug, title=title, kind=kind)
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    # Re-render device tree partial
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.post("/catalog", response_class=HTMLResponse)
async def create_feature_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    parent_id: Annotated[str | None, Form()] = None,
    kind: Annotated[str, Form()] = ...,
    slug: Annotated[str, Form()] = ...,
    title: Annotated[str, Form()] = ...,
    prompt_hint: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else None
    try:
        await create_feature_node(
            session, parent_id=pid, kind=kind, slug=slug, title=title,
            prompt_hint=prompt_hint,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )


@router.post("/bindings", response_class=HTMLResponse)
async def create_binding_endpoint(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    device_node_id: Annotated[str, Form()] = ...,
    feature_node_id: Annotated[str, Form()] = ...,
    defect_action: Annotated[str, Form()] = "info",
    unknown_action: Annotated[str, Form()] = "skip",
) -> HTMLResponse:
    try:
        await create_binding(
            session,
            device_node_id=uuid.UUID(device_node_id),
            feature_node_id=uuid.UUID(feature_node_id),
            defect_action=defect_action,
            unknown_action=unknown_action,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    # Re-render bindings list for the device
    from app.services.defect_catalog.resolver import resolve_applicable_defects
    bindings = await resolve_applicable_defects(session, uuid.UUID(device_node_id))
    return templates.TemplateResponse(
        request, "defects/_partials/bindings_list_fragment.html",
        {"bindings": bindings, "target_device_id": device_node_id},
    )
```

- [ ] **Step 2: Add bindings_list_fragment.html for re-render**

```html
{# app/web/templates/defects/_partials/bindings_list_fragment.html #}
{% for b in bindings %}
  {% include "defects/_partials/binding_row.html" %}
{% endfor %}
{% if not bindings %}
  <div class="text-avito-text-soft text-sm">Нет привязанных дефектов.</div>
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py avito-monitor/app/web/templates/defects/_partials/
git commit -m "feat(defect-catalog): POST endpoints for device / feature / binding"
```

---

### Task 26: DELETE + PATCH endpoints for nodes

**Files:**
- Modify: `avito-monitor/app/web/routers/defects.py`

- [ ] **Step 1: Add endpoints**

```python
from app.services.defect_catalog.repository import (
    update_feature_node, delete_feature_node,
    update_device_node, delete_device_node,
)


@router.patch("/devices/{device_id}/edit", response_class=HTMLResponse)
async def patch_device_endpoint(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    title: Annotated[str | None, Form()] = None,
    slug: Annotated[str | None, Form()] = None,
    parent_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = uuid.UUID(parent_id) if parent_id else ...  # ... means no change
    try:
        await update_device_node(session, device_id, title=title, slug=slug, parent_id=pid)
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.delete("/devices/{device_id}", response_class=HTMLResponse)
async def delete_device_endpoint(
    device_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_device_node(session, device_id)
    tree = await _build_device_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/device_tree.html", {"tree": tree},
    )


@router.patch("/catalog/{feature_id}/edit", response_class=HTMLResponse)
async def patch_feature_endpoint(
    feature_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    title: Annotated[str | None, Form()] = None,
    slug: Annotated[str | None, Form()] = None,
    prompt_hint: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    try:
        await update_feature_node(
            session, feature_id, title=title, slug=slug, prompt_hint=prompt_hint,
        )
    except ValueError as e:
        return HTMLResponse(f'<div class="text-red-600 text-xs">{e}</div>', status_code=400)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )


@router.delete("/catalog/{feature_id}", response_class=HTMLResponse)
async def delete_feature_endpoint(
    feature_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    await delete_feature_node(session, feature_id)
    tree = await _build_feature_tree(session, parent_id=None)
    return templates.TemplateResponse(
        request, "defects/_partials/feature_tree.html", {"tree": tree},
    )
```

- [ ] **Step 2: Commit**

```bash
git add -u avito-monitor/app/web/routers/defects.py
git commit -m "feat(defect-catalog): PATCH/DELETE endpoints for nodes"
```

---

### Task 27: Sidebar nav entry «Дефекты»

**Files:**
- Modify: `avito-monitor/app/web/templates/_layout.html`

- [ ] **Step 1: Locate sidebar nav block**

```bash
cd avito-monitor && grep -n "sidebar\|nav-item\|/profiles\|/listings" app/web/templates/_layout.html | head -15
```

Find where existing nav items like "Профили" / "Объявления" are rendered.

- [ ] **Step 2: Add «Дефекты» entry after «Объявления»**

Add a new `<a>` element matching the existing style:

```html
<a href="/defects"
   class="block px-3 py-2 text-sm hover:bg-avito-surface-soft {% if request.url.path.startswith('/defects') %}text-avito-green font-medium{% else %}text-avito-text{% endif %}">
  🛠 Дефекты
</a>
```

- [ ] **Step 3: Verify by curl on dev server (optional — covered by Task 30 final smoke)**

- [ ] **Step 4: Commit**

```bash
git add avito-monitor/app/web/templates/_layout.html
git commit -m "feat(defect-catalog): sidebar nav entry"
```

---

## Phase 7 — Seed + final integration

### Task 28: Seed script with idempotency

**Files:**
- Create: `avito-monitor/scripts/seed_defect_catalog.py`

- [ ] **Step 1: Write seed script**

```python
"""Idempotent MVP seed for defect catalog.

Run: python -m scripts.seed_defect_catalog
Re-runs are safe — uses INSERT ... ON CONFLICT DO NOTHING semantics.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import text

from app.db.base import dispose_engine, get_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_defect_catalog")


# Stable UUIDs for idempotency (so re-run finds same rows).
# Use uuid5 with a fixed namespace + slug-path.
NS = uuid.UUID("11111111-2222-3333-4444-555555555555")

def fid(path: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"feature:{path}")

def did(path: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"device:{path}")


# Feature catalog: 2 nodes + 6 defects
FEATURES = [
    {"id": fid("case"), "parent": None, "kind": "node",
     "slug": "case", "title": "Корпус", "sort": 1},
    {"id": fid("case/back_broken"), "parent": fid("case"), "kind": "defect",
     "slug": "back_broken", "title": "Задняя крышка разбита", "sort": 1,
     "hint": "defect — продавец явно упоминает разбитую заднюю крышку. ok — упомянуто что задняя целая."},
    {"id": fid("case/midframe_bent"), "parent": fid("case"), "kind": "defect",
     "slug": "midframe_bent", "title": "Midframe погнут", "sort": 2,
     "hint": "defect — корпус погнут / замят. ok — корпус ровный."},
    {"id": fid("case/midframe_cracked"), "parent": fid("case"), "kind": "defect",
     "slug": "midframe_cracked", "title": "Midframe сломан", "sort": 3,
     "hint": "defect — трещина на корпусе / сломан midframe. ok — без трещин."},

    {"id": fid("display"), "parent": None, "kind": "node",
     "slug": "display", "title": "Дисплей", "sort": 2},
    {"id": fid("display/glass_broken"), "parent": fid("display"), "kind": "defect",
     "slug": "glass_broken", "title": "Стекло разбито", "sort": 1,
     "hint": "defect — трещины/сколы на стекле. ok — стекло целое."},
    {"id": fid("display/stains_stripes"), "parent": fid("display"), "kind": "defect",
     "slug": "stains_stripes", "title": "Полосы / пятна", "sort": 2,
     "hint": "defect — пятна / полосы / битые пиксели. ok — изображение чистое."},
    {"id": fid("display/replaced"), "parent": fid("display"), "kind": "defect",
     "slug": "replaced", "title": "Дисплей менялся", "sort": 3,
     "hint": "defect — дисплей менялся. unknown — нет упоминания."},
]

# Device tree: Phone → Apple → iPhone 12 PM
DEVICES = [
    {"id": did("phone"), "parent": None, "slug": "phone", "title": "Phone",
     "kind": "type", "sort": 1},
    {"id": did("phone/apple"), "parent": did("phone"), "slug": "apple",
     "title": "Apple", "kind": "brand", "sort": 1},
    {"id": did("phone/apple/ipm"), "parent": did("phone/apple"), "slug": "ipm",
     "title": "iPhone 12 Pro Max", "kind": "model", "sort": 1},
]

# Bindings: all at Phone level — inherited by Apple + iPhone 12 PM
BINDINGS = [
    (did("phone"), fid("case/back_broken"),       "info",  "skip"),
    (did("phone"), fid("case/midframe_bent"),     "info",  "ask"),
    (did("phone"), fid("case/midframe_cracked"),  "block", "ask"),
    (did("phone"), fid("display/glass_broken"),   "info",  "skip"),
    (did("phone"), fid("display/stains_stripes"), "info",  "ask"),
    (did("phone"), fid("display/replaced"),       "info",  "ask"),
]


async def main() -> None:
    Session = get_sessionmaker()
    async with Session() as session:
        for f in FEATURES:
            await session.execute(text("""
                INSERT INTO feature_nodes
                    (id, parent_id, kind, slug, title, sort_order, prompt_hint)
                VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(f["id"]),
                "pid": str(f["parent"]) if f["parent"] else None,
                "kind": f["kind"], "slug": f["slug"], "title": f["title"],
                "sort": f["sort"], "hint": f.get("hint"),
            })
        for d in DEVICES:
            await session.execute(text("""
                INSERT INTO device_nodes
                    (id, parent_id, slug, title, kind, sort_order)
                VALUES (:id, :pid, :slug, :title, :kind, :sort)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(d["id"]),
                "pid": str(d["parent"]) if d["parent"] else None,
                "slug": d["slug"], "title": d["title"],
                "kind": d["kind"], "sort": d["sort"],
            })
        # Bindings — use stable id from (device, feature) so re-runs idempotent
        for dn, fn, da, ua in BINDINGS:
            bid = uuid.uuid5(NS, f"binding:{dn}:{fn}")
            await session.execute(text("""
                INSERT INTO device_feature_bindings
                    (id, device_node_id, feature_node_id, defect_action, unknown_action)
                VALUES (:id, :dn, :fn, :da, :ua)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(bid), "dn": str(dn), "fn": str(fn),
                "da": da, "ua": ua,
            })
        await session.commit()
    log.info(
        "seeded: %d features, %d devices, %d bindings",
        len(FEATURES), len(DEVICES), len(BINDINGS),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(dispose_engine())
```

- [ ] **Step 2: Smoke local-import**

```bash
cd avito-monitor && python -c "from scripts.seed_defect_catalog import FEATURES, DEVICES, BINDINGS; print(len(FEATURES), len(DEVICES), len(BINDINGS))"
```

Expected: `8 3 6`

- [ ] **Step 3: Commit**

```bash
git add avito-monitor/scripts/seed_defect_catalog.py
git commit -m "feat(defect-catalog): MVP seed script with stable UUIDs"
```

---

### Task 29: Seed idempotency test

**Files:**
- Create: `avito-monitor/tests/defect_catalog/test_seed.py`

- [ ] **Step 1: Write test**

```python
"""Seed idempotency — running twice yields same row counts."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from scripts.seed_defect_catalog import FEATURES, DEVICES, BINDINGS


@pytest.mark.asyncio
async def test_seed_data_lists_consistent():
    """FEATURES, DEVICES, BINDINGS have expected sizes (sanity)."""
    assert len(FEATURES) == 8
    assert len(DEVICES) == 3
    assert len(BINDINGS) == 6


@pytest.mark.asyncio
async def test_seed_runs_twice_no_duplicates(db_session):
    """Simulate seed by inlining inserts; second run should not duplicate."""
    # ON CONFLICT not supported by SQLite the same way — use INSERT OR IGNORE
    for f in FEATURES:
        for _ in range(2):  # twice
            await db_session.execute(text("""
                INSERT OR IGNORE INTO feature_nodes
                    (id, parent_id, kind, slug, title, sort_order, prompt_hint)
                VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
            """), {
                "id": str(f["id"]),
                "pid": str(f["parent"]) if f["parent"] else None,
                "kind": f["kind"], "slug": f["slug"], "title": f["title"],
                "sort": f["sort"], "hint": f.get("hint"),
            })
    await db_session.commit()
    count = (await db_session.execute(
        text("SELECT COUNT(*) FROM feature_nodes")
    )).scalar()
    assert count == len(FEATURES)
```

- [ ] **Step 2: Run**

```bash
cd avito-monitor && python -m pytest tests/defect_catalog/test_seed.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add avito-monitor/tests/defect_catalog/test_seed.py
git commit -m "test(defect-catalog): seed idempotency"
```

---

### Task 30: Full local test suite green

**Files:**
- (no changes)

- [ ] **Step 1: Run full test suite**

```bash
cd avito-monitor && python -m pytest -q --tb=short 2>&1 | tail -20
```

Expected: all Phase 2.1 tests still pass + new ~21 defect_catalog tests + ~4 web/test_defects_routes tests pass. No regressions.

If failures appear:
- Verify migrations don't run during pytest (existing pytest uses SQLite DDL, not Alembic)
- Verify new tests use the conftest's `db_session` fixture
- Verify router registration didn't break existing routes

- [ ] **Step 2: Commit (no changes — just lock-in checkpoint)**

```bash
git log --oneline -5  # sanity
```

No commit needed if no changes. Move to deploy phase.

---

## Phase 8 — Deploy + manual smoke

### Task 31: Deploy to VPS

- [ ] **Step 1: Sync source to VPS**

```bash
cd avito-monitor && tar -czf - --exclude __pycache__ --exclude .git --exclude .pytest_cache --exclude '*.pyc' . | ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'
```

- [ ] **Step 2: Rebuild all 7 Python service images**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose build avito-monitor worker scheduler avito-mcp messenger-bot telegram-bot health-checker'
```

Expected: all images build OK (exit 0).

- [ ] **Step 3: Apply migration**

```bash
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 alembic upgrade head'
```

Expected: `Running upgrade 0016_unified_criteria -> 0017_defect_catalog`.

- [ ] **Step 4: Recreate containers**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose up -d --force-recreate avito-monitor worker scheduler avito-mcp messenger-bot telegram-bot health-checker'
```

- [ ] **Step 5: Wait for startup + smoke /login**

```bash
ssh root@81.200.119.132 'sleep 15 && curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "HTTP %{http_code}\n" https://avitosystem.duckdns.org/login'
```

Expected: `HTTP 200`.

---

### Task 32: Seed data + smoke /defects

- [ ] **Step 1: Run seed**

```bash
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 python -m scripts.seed_defect_catalog'
```

Expected: `seeded: 8 features, 3 devices, 6 bindings`.

- [ ] **Step 2: Smoke /defects redirect**

```bash
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "%{http_code} %{redirect_url}\n" https://avitosystem.duckdns.org/defects'
```

Expected: `303 https://avitosystem.duckdns.org/defects/devices` (or 200 after follow).

- [ ] **Step 3: Manual UI check (user)**

User opens `https://avitosystem.duckdns.org/defects/devices`:
- Sidebar shows «Дефекты»
- Tabs «Устройства» / «Признаки» visible
- Device tree loads with Phone → Apple → iPhone 12 PM
- Clicking iPhone 12 PM shows 6 bindings (all inherited from Phone)
- Tab «Признаки» shows feature tree with Корпус + Дисплей expanded

---

### Task 33: Verify on-VPS migration was applied

- [ ] **Step 1: Confirm head revision**

```bash
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 alembic current'
```

Expected: `0017_defect_catalog (head)`.

- [ ] **Step 2: Confirm tables exist**

```bash
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 python -c "
import asyncio, os, re, asyncpg
def strip(u):
    u = u.replace(\"postgresql+asyncpg://\", \"postgresql://\")
    u = re.sub(r\"[?&]prepared_statement_cache_size=\d+\", \"\", u)
    return u.replace(\"?ssl=require\", \"?sslmode=require\")
async def go():
    c = await asyncpg.connect(strip(os.environ[\"DATABASE_URL\"]), statement_cache_size=0)
    for t in (\"feature_nodes\", \"device_nodes\", \"device_feature_bindings\"):
        n = await c.fetchval(f\"SELECT COUNT(*) FROM {t}\")
        print(t, n)
    await c.close()
asyncio.run(go())
"'
```

Expected:
```
feature_nodes 8
device_nodes 3
device_feature_bindings 6
```

---

### Task 34: Final push + done

- [ ] **Step 1: Push branch**

```bash
git push origin <branch-name>
```

(If working on `main`, push `main`; if on a feature branch, push that.)

- [ ] **Step 2: Quick PR-ready summary in commit log**

```bash
git log --oneline main..HEAD | head -30
```

Verify all task commits are visible.

- [ ] **Step 3: Done**

Project A shipped. Next: Project B (Признаки UI on profile/cards reading from catalog) — separate spec + plan.

---

## Self-review checklist (run before handoff)

- [ ] **Spec coverage:**
  - §5 Architecture → Tasks 1-3 (models) ✓
  - §6 Data model → Task 5 (migration) ✓
  - §7 Resolution algorithm → Tasks 13-17 ✓
  - §8 Admin UI → Tasks 18-23 ✓
  - §9 API routes → Tasks 18, 21, 22, 25, 26 (all 12 endpoints) ✓
  - §10 MVP seed → Tasks 28-29 ✓
  - §11 Error handling → Tasks 25-26 return 400 on ValueError ✓
  - §12 Testing → Tasks 7-12 (repo), 13-17 (resolver), 24 (routes), 29 (seed) ✓
  - §13 Path forward — informational, no tasks needed ✓
  - §14 Open questions — deferred per spec ✓

- [ ] **Placeholder scan:** no TBD/TODO/«TODO later»/«similar to» — all steps have full code.

- [ ] **Type consistency:** `defect_action` / `unknown_action` / `disabled` / `inherited_from` named identically across resolver / repository / templates. `ResolvedBinding` dataclass matches binding_row.html context.

- [ ] **File-path consistency:** all `app/web/templates/defects/` paths match across tasks; partial imports use `defects/_partials/...`.

---

## Total: 34 tasks, ~2-3 hours of focused work
