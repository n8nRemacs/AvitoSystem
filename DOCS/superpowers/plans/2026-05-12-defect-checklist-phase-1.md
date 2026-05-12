# Defect Checklist — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship deterministic feature×rules bucketing — replace confidence-based bucketing with a 22-feature taxonomy that the LLM extracts from listings (Avito-parameters prioritized), and let the operator configure per-profile rules (🟢 green-flag / 🔴 red-flag / ⊘ ignore) through a new model-settings page. Read-only feature checklist appears on every kanban card.

**Architecture:** Two new tables (`listing_features`, `profile_feature_rules`). New service package `app/services/defect_features/` with: yaml taxonomy loader, Avito-parameter matcher, 6 per-section LLM dispatchers (parallel via `asyncio.gather`), pure `compute_bucket(features, rules)` function, pipeline glue. The parser runs after `classify_condition` in `analyze_listing` and writes to `listing_features` (UPSERT) + `profile_listings.bucket`. UI adds a Признаки block in expanded card bodies and a `/profiles/{id}/feature-rules` editor page with 3-state segment toggles. Sidebar gets a collapse toggle + new nav item.

**Tech Stack:** FastAPI + Jinja + Tailwind + SQLAlchemy 2.0 async + Alembic + Pydantic v2 + asyncio + pytest-asyncio. LLM through existing OpenRouter integration (Gemini 2.5 Flash Lite).

**Spec:** [`docs/superpowers/specs/2026-05-12-defect-checklist-design.md`](../specs/2026-05-12-defect-checklist-design.md). Phase 2 (category-batched survey + opener + double-LLM-per-inbound) has a separate plan, written after Phase 1 soak.

---

## File Structure

**Created:**
- `avito-monitor/alembic/versions/20260512_1500_defect_checklist.py` — migration `0015_defect_checklist`
- `avito-monitor/app/db/models/listing_feature.py` — `ListingFeature` model
- `avito-monitor/app/db/models/profile_feature_rule.py` — `ProfileFeatureRule` model
- `avito-monitor/app/services/defect_features/__init__.py` — public exports
- `avito-monitor/app/services/defect_features/taxonomy.py` — yaml loader, `FeatureSpec` dataclass
- `avito-monitor/app/services/defect_features/avito_params.py` — `match_avito_parameters`
- `avito-monitor/app/services/defect_features/llm_parser.py` — `parse_section_defects` + `parse_defect_features`
- `avito-monitor/app/services/defect_features/bucket.py` — pure `compute_bucket`
- `avito-monitor/app/services/defect_features/pipeline.py` — `analyze_listing_features` (the orchestrator called from analysis.py)
- `avito-monitor/app/services/defect_features/repository.py` — DB helpers (upsert features, list active features for profile, persist rule, recompute_buckets_for_profile)
- `avito-monitor/app/prompts/parse_section_display.md`
- `avito-monitor/app/prompts/parse_section_case.md`
- `avito-monitor/app/prompts/parse_section_locks.md`
- `avito-monitor/app/prompts/parse_section_sensors.md`
- `avito-monitor/app/prompts/parse_section_charging.md`
- `avito-monitor/app/prompts/parse_section_operability.md`
- `avito-monitor/app/web/templates/_partials/_features_block.html`
- `avito-monitor/app/web/templates/profiles/feature_rules.html`
- `avito-monitor/scripts/backfill_features.py`
- `avito-monitor/tests/defect_features/__init__.py`
- `avito-monitor/tests/defect_features/test_taxonomy.py`
- `avito-monitor/tests/defect_features/test_avito_params.py`
- `avito-monitor/tests/defect_features/test_llm_parser.py`
- `avito-monitor/tests/defect_features/test_bucket.py`
- `avito-monitor/tests/defect_features/test_pipeline.py`
- `avito-monitor/tests/defect_features/test_repository.py`

**Modified:**
- `avito-monitor/app/data/dialog_topics.yaml` — replace 11 flat topics with 22 categorized features
- `avito-monitor/app/db/models/__init__.py` — export the 2 new models
- `avito-monitor/app/tasks/analysis.py` — call `analyze_listing_features`, drive bucket from `compute_bucket`, drop confidence-based bucketing
- `avito-monitor/app/services/seller_dialog_view.py` — load `features` into `KanbanCard`
- `avito-monitor/app/services/listings_view.py` — load `features` into `ListingRow`
- `avito-monitor/app/web/routers.py` — `/profiles/{id}/feature-rules` GET + PATCH + POST recompute
- `avito-monitor/app/web/templates/_partials/_kanban_card_body.html` — include `_features_block.html`
- `avito-monitor/app/web/templates/listings.html` — include `_features_block.html` in expanded body
- `avito-monitor/app/web/templates/_layout.html` — sidebar id + collapse toggle + new nav item

**Notes:**
- All paths assume working dir is repo root (`c:/Projects/Sync/AvitoSystem` locally, `/opt/avito-system/repo` on VPS).
- `pytest` is run from `avito-monitor/` subdir (its `pyproject.toml` is the project root for tests).
- Commits use the project's conventional-commits style (`feat:`, `fix:`, `chore:` etc.).

---

## Task 1: Taxonomy yaml + loader

**Files:**
- Create: `avito-monitor/tests/defect_features/__init__.py` (empty)
- Create: `avito-monitor/tests/defect_features/test_taxonomy.py`
- Create: `avito-monitor/app/services/defect_features/__init__.py`
- Create: `avito-monitor/app/services/defect_features/taxonomy.py`
- Modify: `avito-monitor/app/data/dialog_topics.yaml`

- [ ] **Step 1: Write the failing test**

Create `avito-monitor/tests/defect_features/__init__.py` empty, then `avito-monitor/tests/defect_features/test_taxonomy.py`:

```python
"""Tests for the defect-feature taxonomy loader."""
from app.services.defect_features.taxonomy import (
    load_taxonomy,
    SECTIONS,
    FeatureSpec,
)


def test_load_taxonomy_returns_all_22_features():
    """The yaml must define exactly 22 defect features in 6 categories."""
    features = load_taxonomy()
    assert len(features) == 22
    assert all(isinstance(f, FeatureSpec) for f in features)


def test_taxonomy_covers_all_sections():
    """Every section in SECTIONS must have at least one feature."""
    features = load_taxonomy()
    by_section = {s: 0 for s in SECTIONS}
    for f in features:
        assert f.section in SECTIONS, f"unknown section: {f.section}"
        by_section[f.section] += 1
    assert all(c >= 1 for c in by_section.values()), by_section


def test_keys_are_dotted_section_first():
    features = load_taxonomy()
    for f in features:
        assert f.key.startswith(f"{f.section}."), f.key


def test_icloud_is_red_flag_hint():
    """icloud_linked should default to red-flag (auto-reject hint)."""
    feats = {f.key: f for f in load_taxonomy()}
    assert "locks.icloud_linked" in feats
    assert feats["locks.icloud_linked"].severity_hint == "red"


def test_each_feature_has_required_fields():
    for f in load_taxonomy():
        assert f.key and f.title and f.section
        assert f.severity_hint in {"red", "green", "info"}
        assert f.expected_format in {"yesno", "text"}
        assert f.opener_phrasing  # short defect-tone phrasing for Phase 2 opener
```

- [ ] **Step 2: Run test to verify it fails**

Run from `avito-monitor/`:
```
python -m pytest tests/defect_features/test_taxonomy.py -v
```
Expected: `ImportError` — module `app.services.defect_features.taxonomy` does not exist.

- [ ] **Step 3: Write the yaml**

Replace `avito-monitor/app/data/dialog_topics.yaml` with the 22-feature taxonomy. Use **section.key** format. Old flat keys (`battery_health`, `face_id_works`, …) are dropped — Task 2 migration handles renames in DB.

```yaml
# Defect taxonomy — see DOCS/superpowers/specs/2026-05-12-defect-checklist-design.md §5
- key: display.replaced
  section: display
  title: Дисплей менялся
  default_phrasing: "Уточни — менялся ли дисплей"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "дисплей менялся"
- key: display.glass_broken
  section: display
  title: Стекло дисплея разбито
  default_phrasing: "Стекло дисплея целое или есть трещины/сколы?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "разбито стекло дисплея"
- key: display.touchscreen_glitch
  section: display
  title: Тачскрин глючит
  default_phrasing: "Тачскрин работает корректно?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "глючит тачскрин"
- key: display.stains_stripes
  section: display
  title: Пятна / полосы на дисплее
  default_phrasing: "Есть ли полосы или пятна на дисплее, битые пиксели?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "есть полосы/пятна на дисплее"
- key: case.back_broken
  section: case
  title: Задняя крышка разбита
  default_phrasing: "Задняя крышка целая?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "разбита задняя крышка"
- key: case.midframe_bent
  section: case
  title: Средняя часть корпуса погнута
  default_phrasing: "Средняя часть корпуса ровная, без замятий?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "погнута средняя часть корпуса"
- key: case.midframe_cracked
  section: case
  title: Средняя часть корпуса сломана
  default_phrasing: "На корпусе нет трещин или сломов?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "сломана средняя часть корпуса"
- key: locks.icloud_linked
  section: locks
  title: iCloud привязан к чужому аккаунту
  default_phrasing: "iCloud отвязан от прошлого аккаунта?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "iCloud привязан"
- key: locks.passcode_forgotten
  section: locks
  title: Пароль на экран забыт
  default_phrasing: "Пароль на разблокировку известен / снят?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "пароль на экран забыт"
- key: sensors.face_id
  section: sensors
  title: Face ID не работает
  default_phrasing: "Face ID работает без сбоев?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "не работает Face ID"
- key: sensors.truetone
  section: sensors
  title: TrueTone не работает
  default_phrasing: "TrueTone в настройках включается?"
  expected_format: yesno
  severity_hint: info
  opener_phrasing: "не работает TrueTone"
- key: sensors.wifi
  section: sensors
  title: WiFi не работает
  default_phrasing: "WiFi ловит сети, подключается стабильно?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "не работает WiFi"
- key: sensors.sim
  section: sensors
  title: SIM не работает
  default_phrasing: "SIM-карта определяется, сеть ловит?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "не работает SIM"
- key: sensors.bluetooth
  section: sensors
  title: Bluetooth не работает
  default_phrasing: "Bluetooth подключается к устройствам?"
  expected_format: yesno
  severity_hint: info
  opener_phrasing: "не работает Bluetooth"
- key: sensors.other
  section: sensors
  title: Другие датчики не работают
  default_phrasing: "Какие-нибудь другие датчики не работают (proximity, гироскоп)?"
  expected_format: text
  severity_hint: info
  opener_phrasing: "есть проблемы с другими датчиками"
- key: charging.not_charging
  section: charging
  title: Не заряжается
  default_phrasing: "Аппарат заряжается от кабеля?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "не заряжается"
- key: charging.wireless_only
  section: charging
  title: Заряжается только беспроводной
  default_phrasing: "Аппарат заряжается от обычного кабеля Lightning?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "заряжается только беспроводной зарядкой"
- key: charging.unstable
  section: charging
  title: Зарядка нестабильна
  default_phrasing: "Зарядка стабильная или нужно двигать кабель?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "зарядка нестабильна (нужно двигать кабель)"
- key: operability.boot_loop
  section: operability
  title: Висит на прошивке
  default_phrasing: "Аппарат прошивается / включается без зависания?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "висит на прошивке"
- key: operability.reboots
  section: operability
  title: Периодически перезагружается
  default_phrasing: "Бывает ли что аппарат сам перезагружается?"
  expected_format: yesno
  severity_hint: green
  opener_phrasing: "периодически перезагружается"
- key: operability.no_boot
  section: operability
  title: Не загружается
  default_phrasing: "После включения экран загрузки доходит до рабочего стола?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "стартует и не загружается"
- key: operability.apple_loop
  section: operability
  title: Циклится на яблоке
  default_phrasing: "Аппарат загружается до яблока и идёт дальше?"
  expected_format: yesno
  severity_hint: red
  opener_phrasing: "циклится на яблоке"
```

- [ ] **Step 4: Write the loader module**

Create `avito-monitor/app/services/defect_features/__init__.py`:

```python
"""Defect-feature analyzer package — taxonomy, parser, bucketing."""
from app.services.defect_features.taxonomy import (
    FeatureSpec,
    SECTIONS,
    load_taxonomy,
)

__all__ = ["FeatureSpec", "SECTIONS", "load_taxonomy"]
```

Create `avito-monitor/app/services/defect_features/taxonomy.py`:

```python
"""Defect-feature taxonomy: load 22 features from yaml into FeatureSpec dataclasses.

The taxonomy is shared by parser, bucketer and UI — single source of truth.
Loader is cached in process (taxonomy doesn't change at runtime).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml


SECTIONS = ("display", "case", "locks", "sensors", "charging", "operability")

SeverityHint = Literal["red", "green", "info"]
FeatureFormat = Literal["yesno", "text"]


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    section: str
    title: str
    default_phrasing: str
    expected_format: FeatureFormat
    severity_hint: SeverityHint
    opener_phrasing: str


_YAML_PATH = Path(__file__).parent.parent.parent / "data" / "dialog_topics.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> tuple[FeatureSpec, ...]:
    """Read app/data/dialog_topics.yaml and return tuple of FeatureSpec."""
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    return tuple(
        FeatureSpec(
            key=item["key"],
            section=item["section"],
            title=item["title"],
            default_phrasing=item["default_phrasing"],
            expected_format=item["expected_format"],
            severity_hint=item["severity_hint"],
            opener_phrasing=item["opener_phrasing"],
        )
        for item in raw
    )
```

- [ ] **Step 5: Run test to verify it passes**

```
python -m pytest tests/defect_features/test_taxonomy.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add avito-monitor/app/data/dialog_topics.yaml \
        avito-monitor/app/services/defect_features/__init__.py \
        avito-monitor/app/services/defect_features/taxonomy.py \
        avito-monitor/tests/defect_features/__init__.py \
        avito-monitor/tests/defect_features/test_taxonomy.py
git commit -m "feat(defect-features): add 22-feature taxonomy + yaml loader"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `avito-monitor/alembic/versions/20260512_1500_defect_checklist.py`

- [ ] **Step 1: Write migration with schema + data-migration**

Create `avito-monitor/alembic/versions/20260512_1500_defect_checklist.py`:

```python
"""defect_checklist — listing_features + profile_feature_rules + rename old topic keys.

Revision ID: 0015_defect_checklist
Revises: 0014_phase_b_topics
Create Date: 2026-05-12 15:00:00
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0015_defect_checklist"
down_revision: Union[str, None] = "0014_phase_b_topics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Old flat key → new dotted key. Inversions (e.g. icloud_unlinked='no defect when ok'
# → icloud_linked='ok when not linked') change semantic, but state values flip
# below so existing 'ok' rows remain meaningful.
RENAME_MAP = {
    # old_key: (new_key, invert_state)
    "replaced_display":       ("display.replaced",         False),
    "broken_glass":           ("display.glass_broken",     False),
    "display_stains_stripes": ("display.stains_stripes",   False),
    "broken_back":            ("case.back_broken",         False),
    "face_id_works":          ("sensors.face_id",          True),   # works=ok → not_works=defect
    "icloud_unlinked":        ("locks.icloud_linked",      True),   # unlinked=ok → linked=defect
    "charging_stability":     ("charging.unstable",        True),
}

# Keys removed in new taxonomy (no rename target) — drop their library + per-dialog/profile rows.
DROPPED_KEYS = ("battery_health", "cameras_work", "replaced_parts", "complectness")


def upgrade() -> None:
    # 1. listing_features
    op.create_table(
        "listing_features",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("listing_id", "feature_key", name="uq_listing_features_listing_key"),
    )
    op.create_index("ix_listing_features_listing_id",
                    "listing_features", ["listing_id"])
    op.create_index("ix_listing_features_feature_state",
                    "listing_features", ["feature_key", "state"])

    # 2. profile_feature_rules
    op.create_table(
        "profile_feature_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("search_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(64), nullable=False),
        sa.Column("rule", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("profile_id", "feature_key",
                            name="uq_profile_feature_rules_profile_key"),
    )
    op.create_index("ix_profile_feature_rules_profile_id",
                    "profile_feature_rules", ["profile_id"])

    # 3. profile_listings.rejected_reason (idempotent — column may already exist)
    bind = op.get_bind()
    col_exists = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='profile_listings' AND column_name='rejected_reason'"
    )).first()
    if not col_exists:
        op.add_column("profile_listings",
                      sa.Column("rejected_reason", sa.Text, nullable=True))

    # 4. Rename existing dialog_topics keys + cascade to seller_dialog_topics +
    #    profile_dialog_topics. Use raw SQL since we need ordering.
    for old, (new, _invert) in RENAME_MAP.items():
        op.execute(sa.text(
            "UPDATE dialog_topics SET key = :new WHERE key = :old"
        ).bindparams(new=new, old=old))
        # Foreign-key cascade rewrites seller_dialog_topics.topic_key and
        # profile_dialog_topics.topic_key automatically? — NO, ON UPDATE
        # default is NO ACTION. Update manually.
        op.execute(sa.text(
            "UPDATE seller_dialog_topics SET topic_key = :new WHERE topic_key = :old"
        ).bindparams(new=new, old=old))
        op.execute(sa.text(
            "UPDATE profile_dialog_topics SET topic_key = :new WHERE topic_key = :old"
        ).bindparams(new=new, old=old))

    # 5. Invert state for keys whose semantic flipped (face_id_works→sensors.face_id, etc.)
    #    Only on seller_dialog_topics — profile_dialog_topics has no state column.
    invert_keys = [v[0] for v in RENAME_MAP.values() if v[1]]
    if invert_keys:
        op.execute(sa.text(
            # If answer_text indicates "yes works" → flip to defect-state semantic? Too
            # data-specific to flip server-side. Instead we set status=pending so the
            # bot re-asks for unambiguous answers. Real dialogs are few (Phase B was
            # just shipped) — operator can re-trigger by accept→reject→accept dance.
            "UPDATE seller_dialog_topics SET status = 'pending', answer_text = NULL, "
            "answer_msg_id = NULL, answered_at = NULL "
            "WHERE topic_key = ANY(:keys) AND status IN ('answered','unclear')"
        ).bindparams(keys=invert_keys))

    # 6. Drop dropped keys from library + links + per-dialog rows.
    if DROPPED_KEYS:
        keys_arr = list(DROPPED_KEYS)
        op.execute(sa.text(
            "DELETE FROM seller_dialog_topics WHERE topic_key = ANY(:k)"
        ).bindparams(k=keys_arr))
        op.execute(sa.text(
            "DELETE FROM profile_dialog_topics WHERE topic_key = ANY(:k)"
        ).bindparams(k=keys_arr))
        op.execute(sa.text(
            "DELETE FROM dialog_topics WHERE key = ANY(:k)"
        ).bindparams(k=keys_arr))

    # 7. Upsert the 22-feature taxonomy into dialog_topics (idempotent).
    yaml_path = (Path(__file__).resolve().parent.parent.parent
                 / "app" / "data" / "dialog_topics.yaml")
    features = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    for f in features:
        op.execute(sa.text(
            "INSERT INTO dialog_topics (key, title, category, default_phrasing, "
            "expected_format, created_by, is_active) "
            "VALUES (:key, :title, :category, :phrasing, :fmt, 'system_seed', true) "
            "ON CONFLICT (key) DO UPDATE SET "
            "  title = EXCLUDED.title, "
            "  category = EXCLUDED.category, "
            "  default_phrasing = EXCLUDED.default_phrasing, "
            "  expected_format = EXCLUDED.expected_format"
        ).bindparams(
            key=f["key"], title=f["title"], category=f["section"],
            phrasing=f["default_phrasing"], fmt=f["expected_format"],
        ))


def downgrade() -> None:
    op.drop_index("ix_profile_feature_rules_profile_id",
                  table_name="profile_feature_rules")
    op.drop_table("profile_feature_rules")
    op.drop_index("ix_listing_features_feature_state",
                  table_name="listing_features")
    op.drop_index("ix_listing_features_listing_id",
                  table_name="listing_features")
    op.drop_table("listing_features")
    # leave rejected_reason + renamed dialog_topics as-is on downgrade
    # (reverse rename is fragile; downgrade is for dev only)
```

- [ ] **Step 2: Validate migration syntax**

```
cd avito-monitor && python -c "import alembic.script; \
  s = alembic.script.ScriptDirectory('alembic'); \
  print(s.get_revision('0015_defect_checklist').doc)"
```
Expected: docstring printed without error.

- [ ] **Step 3: Apply migration locally (dev DB)**

```
cd avito-monitor && DATABASE_URL=$DEV_DB alembic upgrade head
```
Expected: ends with `Running upgrade 0014_phase_b_topics -> 0015_defect_checklist`.

- [ ] **Step 4: Sanity-check schema**

```
psql $DEV_DB -c "\d listing_features" -c "\d profile_feature_rules" \
              -c "SELECT key FROM dialog_topics ORDER BY key" | head -40
```
Expected: 2 new tables visible, 22 dotted keys in dialog_topics, no old flat keys among them.

- [ ] **Step 5: Commit**

```
git add avito-monitor/alembic/versions/20260512_1500_defect_checklist.py
git commit -m "feat(db): migration 0015 — listing_features + profile_feature_rules + topic key rename"
```

---

## Task 3: SQLAlchemy models

**Files:**
- Create: `avito-monitor/app/db/models/listing_feature.py`
- Create: `avito-monitor/app/db/models/profile_feature_rule.py`
- Modify: `avito-monitor/app/db/models/__init__.py`
- Create: `avito-monitor/tests/defect_features/test_repository.py`

- [ ] **Step 1: Write the failing test for the models being importable**

Create `avito-monitor/tests/defect_features/test_repository.py`:

```python
"""Smoke tests for SQLAlchemy models + repository helpers."""
import uuid

from app.db.models import ListingFeature, ProfileFeatureRule


def test_listing_feature_table_name():
    assert ListingFeature.__tablename__ == "listing_features"


def test_listing_feature_required_columns():
    cols = {c.name for c in ListingFeature.__table__.columns}
    assert {"id", "listing_id", "feature_key", "state",
            "confidence", "source", "evidence", "parsed_at"} <= cols


def test_listing_feature_unique_constraint():
    constraints = ListingFeature.__table__.constraints
    uniq = [c for c in constraints if getattr(c, "name", "") ==
            "uq_listing_features_listing_key"]
    assert len(uniq) == 1


def test_profile_feature_rule_table_name():
    assert ProfileFeatureRule.__tablename__ == "profile_feature_rules"


def test_profile_feature_rule_required_columns():
    cols = {c.name for c in ProfileFeatureRule.__table__.columns}
    assert {"id", "profile_id", "feature_key", "rule", "updated_at"} <= cols
```

- [ ] **Step 2: Run test, expect ImportError**

```
python -m pytest tests/defect_features/test_repository.py -v
```
Expected: `ImportError: cannot import name 'ListingFeature' from 'app.db.models'`.

- [ ] **Step 3: Write the models**

Inspect a sibling model first (`avito-monitor/app/db/models/listing.py`) to mirror the SQLAlchemy 2 style — `Mapped[...]`, `mapped_column`, `__tablename__`, naming conventions for FK columns.

Create `avito-monitor/app/db/models/listing_feature.py`:

```python
"""SQLAlchemy model for the listing_features table.

One row per (listing, feature_key). Written by the defect-feature parser
(Avito-parameter matcher / LLM section parser / seller-dialog inbound
broad-scan in Phase 2). UPSERT on (listing_id, feature_key) — last
write wins so a freshly re-parsed listing supersedes stale rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingFeature(Base):
    __tablename__ = "listing_features"
    __table_args__ = (
        UniqueConstraint("listing_id", "feature_key",
                         name="uq_listing_features_listing_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)  # 'ok'|'defect'|'unknown'
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'avito_parameters' | 'llm' | 'description_kw' | 'seller_dialog'
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
```

Create `avito-monitor/app/db/models/profile_feature_rule.py`:

```python
"""SQLAlchemy model for the profile_feature_rules table.

One row per (profile, feature_key). Operator-edited through the
/profiles/{id}/feature-rules page. Drives the per-profile bucketing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfileFeatureRule(Base):
    __tablename__ = "profile_feature_rules"
    __table_args__ = (
        UniqueConstraint("profile_id", "feature_key",
                         name="uq_profile_feature_rules_profile_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rule: Mapped[str] = mapped_column(String(16), nullable=False)  # 'green'|'red'|'ignore'
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
```

- [ ] **Step 4: Re-export from db.models package**

Read `avito-monitor/app/db/models/__init__.py` to see the existing pattern, then append:

```python
from app.db.models.listing_feature import ListingFeature
from app.db.models.profile_feature_rule import ProfileFeatureRule
```

Update `__all__` (if present) to include `"ListingFeature"`, `"ProfileFeatureRule"`.

- [ ] **Step 5: Run test, expect PASS**

```
python -m pytest tests/defect_features/test_repository.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add avito-monitor/app/db/models/listing_feature.py \
        avito-monitor/app/db/models/profile_feature_rule.py \
        avito-monitor/app/db/models/__init__.py \
        avito-monitor/tests/defect_features/test_repository.py
git commit -m "feat(db): ListingFeature + ProfileFeatureRule models"
```

---

## Task 4: `match_avito_parameters`

**Files:**
- Create: `avito-monitor/app/services/defect_features/avito_params.py`
- Create: `avito-monitor/tests/defect_features/test_avito_params.py`

The function maps Avito's `parameters` jsonb to feature states. Avito's actual parameter keys are determined by category — for iPhones the relevant ones live under fields like `"Состояние"`, `"Привязан к iCloud"` etc. The matcher is a dict-driven heuristic, generous on false-negatives (return `unknown` when not sure — LLM picks up the slack).

- [ ] **Step 1: Write failing test**

Create `avito-monitor/tests/defect_features/test_avito_params.py`:

```python
"""Avito-parameters matcher — short-circuits the LLM when Avito tells us
explicitly."""
from app.services.defect_features.avito_params import match_avito_parameters
from app.services.defect_features.taxonomy import load_taxonomy


ALL_KEYS = {f.key for f in load_taxonomy()}


def test_no_parameters_yields_no_matches():
    assert match_avito_parameters({}, ALL_KEYS) == {}
    assert match_avito_parameters(None, ALL_KEYS) == {}


def test_icloud_locked_is_picked_up():
    params = {"Состояние": "Б/у", "Привязка к iCloud": "Привязан"}
    out = match_avito_parameters(params, ALL_KEYS)
    assert out.get("locks.icloud_linked") is not None
    assert out["locks.icloud_linked"]["state"] == "defect"
    assert out["locks.icloud_linked"]["evidence"]
    assert out["locks.icloud_linked"]["source"] == "avito_parameters"


def test_icloud_unlinked_is_ok():
    params = {"Привязка к iCloud": "Отвязан"}
    out = match_avito_parameters(params, ALL_KEYS)
    assert out["locks.icloud_linked"]["state"] == "ok"


def test_ignored_feature_keys_skipped():
    """Caller may pass a subset of active keys — matcher ignores all others."""
    params = {"Привязка к iCloud": "Привязан"}
    out = match_avito_parameters(params, set())  # nothing active
    assert out == {}


def test_unknown_value_yields_unknown():
    params = {"Привязка к iCloud": "Не указано"}
    out = match_avito_parameters(params, ALL_KEYS)
    # either skipped entirely or explicit unknown — both OK
    assert out.get("locks.icloud_linked", {}).get("state") in (None, "unknown")
```

- [ ] **Step 2: Run, expect ImportError**

```
python -m pytest tests/defect_features/test_avito_params.py -v
```
Expected: ImportError.

- [ ] **Step 3: Write the matcher**

Create `avito-monitor/app/services/defect_features/avito_params.py`:

```python
"""Avito-parameters → feature state matcher.

For features that Avito itself encodes structurally (mostly locks +
display 'condition' fields), prefer the structured value over LLM
parsing of the free-text description. Returns a partial dict; features
not covered here are left for the LLM section parser.

Generous on negative — when in doubt return nothing and let the LLM
decide. Never raise.
"""
from __future__ import annotations

from typing import Any, Iterable


# value normalization helper
def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


# (feature_key, avito_param_name) → ((ok_values, defect_values))
# Values matched substring-wise after _norm.
RULES: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("locks.icloud_linked", "привязка к icloud"): (
        ("отвязан", "не привязан", "снят", "чист"),
        ("привязан", "залочен", "icloud locked"),
    ),
    ("locks.passcode_forgotten", "пароль"): (
        ("известен", "снят", "сброшен"),
        ("забыт", "не помню",),
    ),
}


def match_avito_parameters(
    parameters: dict[str, Any] | None,
    active_keys: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Map raw Avito parameters dict to {feature_key: {state, source, evidence}}.

    Returns only entries that were resolved (ok or defect). Unknown is
    represented by absence — caller's LLM dispatch fills the rest.
    """
    if not parameters:
        return {}
    active = set(active_keys)
    # Lower-cased copy keyed by canonical param name for case-insensitive lookup
    norm_params = {_norm(k): (k, v) for k, v in parameters.items() if v is not None}

    out: dict[str, dict[str, Any]] = {}
    for (fkey, param_name), (ok_vals, def_vals) in RULES.items():
        if fkey not in active:
            continue
        if param_name not in norm_params:
            continue
        orig_key, raw_val = norm_params[param_name]
        v = _norm(raw_val)
        state: str | None = None
        if any(token in v for token in def_vals):
            state = "defect"
        elif any(token in v for token in ok_vals):
            state = "ok"
        if state is None:
            continue
        out[fkey] = {
            "state": state,
            "source": "avito_parameters",
            "evidence": f"{orig_key}: {raw_val}",
            "confidence": None,
        }
    return out
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest tests/defect_features/test_avito_params.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add avito-monitor/app/services/defect_features/avito_params.py \
        avito-monitor/tests/defect_features/test_avito_params.py
git commit -m "feat(defect-features): match_avito_parameters — structured-field short-circuit"
```

---

## Task 5: Per-section LLM parser dispatcher

**Files:**
- Create: `avito-monitor/app/services/defect_features/llm_parser.py`
- Create: `avito-monitor/app/prompts/parse_section_display.md`
- Create: `avito-monitor/app/prompts/parse_section_case.md`
- Create: `avito-monitor/app/prompts/parse_section_locks.md`
- Create: `avito-monitor/app/prompts/parse_section_sensors.md`
- Create: `avito-monitor/app/prompts/parse_section_charging.md`
- Create: `avito-monitor/app/prompts/parse_section_operability.md`
- Create: `avito-monitor/tests/defect_features/test_llm_parser.py`

- [ ] **Step 1: Write failing test**

Create `avito-monitor/tests/defect_features/test_llm_parser.py`:

```python
"""Per-section LLM parser tests — mock the LLM, verify parsing + safe fallback."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.defect_features.llm_parser import parse_section_defects
from app.services.defect_features.taxonomy import FeatureSpec


# A minimal list of FeatureSpec to drive the dispatcher
DISPLAY = [
    FeatureSpec(
        key="display.replaced", section="display",
        title="Дисплей менялся", default_phrasing="Менялся?",
        expected_format="yesno", severity_hint="green",
        opener_phrasing="дисплей менялся",
    ),
    FeatureSpec(
        key="display.glass_broken", section="display",
        title="Стекло разбито", default_phrasing="Стекло целое?",
        expected_format="yesno", severity_hint="green",
        opener_phrasing="разбито стекло",
    ),
]


@pytest.mark.asyncio
async def test_parses_valid_llm_response():
    fake_llm_resp = {
        "display.replaced": {"state": "ok", "confidence": 0.9, "evidence": "Оригинальный экран"},
        "display.glass_broken": {"state": "defect", "confidence": 0.85, "evidence": "есть трещина"},
    }
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(return_value=fake_llm_resp),
    ):
        out = await parse_section_defects(
            section="display",
            features=DISPLAY,
            title="iPhone 12 Pro Max 256gb",
            description="Оригинальный экран, есть небольшая трещина на стекле",
            parameters={},
        )
    assert out["display.replaced"]["state"] == "ok"
    assert out["display.replaced"]["source"] == "llm"
    assert out["display.glass_broken"]["state"] == "defect"


@pytest.mark.asyncio
async def test_llm_failure_returns_unknown_for_all():
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("network error")),
    ):
        out = await parse_section_defects(
            section="display", features=DISPLAY,
            title="x", description="y", parameters={},
        )
    assert out["display.replaced"]["state"] == "unknown"
    assert out["display.glass_broken"]["state"] == "unknown"


@pytest.mark.asyncio
async def test_invalid_state_value_is_clamped_to_unknown():
    bad_resp = {"display.replaced": {"state": "yes", "confidence": 0.9}}
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(return_value=bad_resp),
    ):
        out = await parse_section_defects(
            section="display", features=DISPLAY,
            title="x", description="y", parameters={},
        )
    assert out["display.replaced"]["state"] == "unknown"
    assert out["display.glass_broken"]["state"] == "unknown"  # not in response


@pytest.mark.asyncio
async def test_empty_features_returns_empty_no_llm_call():
    """If caller passed no features for this section, dispatcher must NOT call LLM."""
    mock_llm = AsyncMock(return_value={})
    with patch("app.services.defect_features.llm_parser._llm_call_json", new=mock_llm):
        out = await parse_section_defects(
            section="display", features=[],
            title="x", description="y", parameters={},
        )
    assert out == {}
    mock_llm.assert_not_called()
```

- [ ] **Step 2: Run, expect ImportError**

```
python -m pytest tests/defect_features/test_llm_parser.py -v
```
Expected: ImportError.

- [ ] **Step 3: Write the six prompt files**

All six follow the same template; create `avito-monitor/app/prompts/parse_section_display.md` first:

```markdown
Ты анализируешь объявление о продаже {{model}}. Извлеки состояние следующих признаков ДИСПЛЕЯ из текста объявления и полей Avito.

Признаки:
{{features_listing}}

ВАЖНО:
- Ставь "ok" ТОЛЬКО если продавец ЯВНО сказал, что признак в порядке.
- Ставь "defect" если продавец явно описал проблему.
- Если признак вообще не упомянут или сомнительно — "unknown".
- evidence = короткая цитата из объявления или null.

Заголовок: {{title}}

Описание:
"""
{{description}}
"""

Avito-параметры:
{{parameters_yaml}}

Ответь ОДНИМ JSON-объектом по схеме (без markdown, без пояснений):
{
  "<feature_key>": {"state": "ok|defect|unknown", "confidence": 0.0-1.0, "evidence": "цитата или null"},
  ...
}
```

Duplicate the file under each of `parse_section_case.md`, `parse_section_locks.md`, `parse_section_sensors.md`, `parse_section_charging.md`, `parse_section_operability.md` — replace `ДИСПЛЕЯ` with the right section name:
- case → `КОРПУСА`
- locks → `БЛОКИРОВОК И ПО`
- sensors → `ДАТЧИКОВ`
- charging → `ЗАРЯДКИ`
- operability → `РАБОТОСПОСОБНОСТИ`

- [ ] **Step 4: Write the parser module**

Create `avito-monitor/app/services/defect_features/llm_parser.py`:

```python
"""Per-section LLM-based defect parser.

For each section (display / case / ...), one LLM call extracts the
state of all the requested features in a single response. Six sections
run in parallel via parse_defect_features (Task 6).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.services.defect_features.taxonomy import FeatureSpec
from app.services.llm_analyzer import _llm_call_json


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_VALID_STATES = {"ok", "defect", "unknown"}


def _build_features_listing(features: Iterable[FeatureSpec]) -> str:
    return "\n".join(
        f"- {f.key}: {f.title} ({f.expected_format})" for f in features
    )


def _render_prompt(section: str, features: Iterable[FeatureSpec],
                   title: str, description: str,
                   parameters: dict[str, Any]) -> str:
    path = _PROMPTS_DIR / f"parse_section_{section}.md"
    template = path.read_text(encoding="utf-8")
    return (
        template
        .replace("{{model}}", "iPhone")  # generic — Avito's category gives model anyway
        .replace("{{features_listing}}", _build_features_listing(features))
        .replace("{{title}}", title or "")
        .replace("{{description}}", description or "")
        .replace("{{parameters_yaml}}",
                 yaml.safe_dump(parameters or {}, allow_unicode=True))
    )


def _coerce_one(raw: Any) -> dict[str, Any]:
    """Validate one feature's LLM block, returning a normalized dict."""
    if not isinstance(raw, dict):
        return {"state": "unknown", "confidence": None, "evidence": None}
    state = raw.get("state")
    if state not in _VALID_STATES:
        state = "unknown"
    confidence = raw.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    evidence = raw.get("evidence")
    if not isinstance(evidence, str):
        evidence = None
    return {"state": state, "confidence": confidence, "evidence": evidence}


async def parse_section_defects(
    *,
    section: str,
    features: list[FeatureSpec],
    title: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return {feature_key: {state, confidence, evidence, source='llm'}}.

    If `features` is empty, returns {} immediately without calling LLM.
    On LLM failure: all requested features → state='unknown', source='llm'.
    """
    if not features:
        return {}

    prompt = _render_prompt(section, features, title, description, parameters)
    try:
        result = await _llm_call_json(prompt, max_tokens=600)
    except Exception:
        return {
            f.key: {"state": "unknown", "confidence": None,
                    "evidence": None, "source": "llm"}
            for f in features
        }
    if not isinstance(result, dict):
        result = {}
    out: dict[str, dict[str, Any]] = {}
    for f in features:
        block = _coerce_one(result.get(f.key))
        block["source"] = "llm"
        out[f.key] = block
    return out
```

- [ ] **Step 5: Run, expect PASS**

```
python -m pytest tests/defect_features/test_llm_parser.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```
git add avito-monitor/app/services/defect_features/llm_parser.py \
        avito-monitor/app/prompts/parse_section_*.md \
        avito-monitor/tests/defect_features/test_llm_parser.py
git commit -m "feat(defect-features): per-section LLM parser + 6 prompt templates"
```

---

## Task 6: Orchestrator `parse_defect_features`

**Files:**
- Modify: `avito-monitor/app/services/defect_features/llm_parser.py` — add `parse_defect_features`
- Modify: `avito-monitor/tests/defect_features/test_llm_parser.py` — add tests for orchestrator

- [ ] **Step 1: Write failing test (append to test file)**

Append to `avito-monitor/tests/defect_features/test_llm_parser.py`:

```python
from app.services.defect_features.llm_parser import parse_defect_features


@pytest.mark.asyncio
async def test_orchestrator_skips_features_already_resolved_by_avito_params():
    """Avito-param matcher resolved locks.icloud_linked → LLM should NOT
    be asked about it; LLM still asked about everything else."""
    captured_features = []

    async def _fake_section(*, section, features, **kw):
        captured_features.append((section, [f.key for f in features]))
        return {
            f.key: {"state": "unknown", "confidence": None,
                    "evidence": None, "source": "llm"}
            for f in features
        }

    with patch(
        "app.services.defect_features.llm_parser.parse_section_defects",
        new=_fake_section,
    ):
        out = await parse_defect_features(
            title="iPhone 12 PM",
            description="...",
            parameters={"Привязка к iCloud": "Привязан"},
            active_keys={
                "locks.icloud_linked", "display.glass_broken",
                "case.back_broken", "sensors.face_id",
            },
        )
    # Avito-resolved
    assert out["locks.icloud_linked"]["source"] == "avito_parameters"
    assert out["locks.icloud_linked"]["state"] == "defect"
    # LLM-resolved (unknown in fake)
    assert out["display.glass_broken"]["source"] == "llm"
    # LLM was NOT asked about locks.icloud_linked (already resolved by Avito)
    locks_sections = [feats for sect, feats in captured_features if sect == "locks"]
    assert all("locks.icloud_linked" not in feats for feats in locks_sections)


@pytest.mark.asyncio
async def test_orchestrator_skips_sections_with_no_active_keys():
    """If active_keys doesn't include any operability features, that
    section's LLM call must be skipped."""
    called_sections = []

    async def _fake_section(*, section, features, **kw):
        called_sections.append(section)
        return {f.key: {"state": "unknown", "confidence": None,
                        "evidence": None, "source": "llm"}
                for f in features}

    with patch(
        "app.services.defect_features.llm_parser.parse_section_defects",
        new=_fake_section,
    ):
        await parse_defect_features(
            title="x", description="y", parameters={},
            active_keys={"display.glass_broken"},
        )
    assert called_sections == ["display"]
```

- [ ] **Step 2: Run, expect failures**

```
python -m pytest tests/defect_features/test_llm_parser.py -v
```
Expected: 2 new tests fail with `ImportError: cannot import name 'parse_defect_features'`.

- [ ] **Step 3: Add `parse_defect_features` to `llm_parser.py`**

Append to `avito-monitor/app/services/defect_features/llm_parser.py`:

```python
import asyncio
from app.services.defect_features.avito_params import match_avito_parameters
from app.services.defect_features.taxonomy import load_taxonomy, SECTIONS


async def parse_defect_features(
    *,
    title: str,
    description: str,
    parameters: dict[str, Any] | None,
    active_keys: set[str],
) -> dict[str, dict[str, Any]]:
    """Full pipeline: Avito-params first, then LLM for the rest, parallel by section.

    `active_keys` = the subset of features the caller is interested in
    (typically `{k for k, r in profile_rules.items() if r != 'ignore'}`).
    Returns {feature_key: {state, confidence, evidence, source}} for every key
    in active_keys (state='unknown' if neither layer resolved it).
    """
    if not active_keys:
        return {}

    taxonomy_by_key = {f.key: f for f in load_taxonomy()}
    requested = {k: taxonomy_by_key[k] for k in active_keys if k in taxonomy_by_key}

    # Layer 1 — Avito structured parameters
    avito_resolved = match_avito_parameters(parameters, set(requested.keys()))

    # Layer 2 — LLM by section, for keys NOT yet resolved
    pending = {k: spec for k, spec in requested.items() if k not in avito_resolved}
    by_section: dict[str, list[FeatureSpec]] = {s: [] for s in SECTIONS}
    for spec in pending.values():
        by_section[spec.section].append(spec)

    tasks = [
        parse_section_defects(
            section=section, features=feats,
            title=title, description=description, parameters=parameters or {},
        )
        for section, feats in by_section.items() if feats
    ]
    llm_results = await asyncio.gather(*tasks) if tasks else []

    out = dict(avito_resolved)
    for partial in llm_results:
        out.update(partial)

    # Anything still missing → explicit unknown (defensive)
    for k in active_keys:
        out.setdefault(k, {"state": "unknown", "confidence": None,
                           "evidence": None, "source": "llm"})
    return out
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest tests/defect_features/test_llm_parser.py -v
```
Expected: 6 passed total.

- [ ] **Step 5: Commit**

```
git add avito-monitor/app/services/defect_features/llm_parser.py \
        avito-monitor/tests/defect_features/test_llm_parser.py
git commit -m "feat(defect-features): parse_defect_features orchestrator (Avito-params + parallel LLM)"
```

---

## Task 7: `compute_bucket` pure function

**Files:**
- Create: `avito-monitor/app/services/defect_features/bucket.py`
- Create: `avito-monitor/tests/defect_features/test_bucket.py`

- [ ] **Step 1: Write failing test**

Create `avito-monitor/tests/defect_features/test_bucket.py`:

```python
"""Tests for compute_bucket — pure deterministic function."""
from app.services.defect_features.bucket import compute_bucket


def test_red_flag_confirmed_defect_short_circuits():
    bucket, reason = compute_bucket(
        features={"locks.icloud_linked": "defect", "display.glass_broken": "ok"},
        rules={"locks.icloud_linked": "red", "display.glass_broken": "green"},
    )
    assert bucket == "red"
    assert reason == "locks.icloud_linked"


def test_green_flag_unknown_yields_grey():
    bucket, reason = compute_bucket(
        features={"display.glass_broken": "unknown"},
        rules={"display.glass_broken": "green"},
    )
    assert bucket == "grey"
    assert reason == "display.glass_broken"


def test_red_flag_unknown_yields_grey_not_red():
    """Critical: unknown on red-flag must NOT auto-reject. Verified in spec Q4."""
    bucket, reason = compute_bucket(
        features={"locks.icloud_linked": "unknown"},
        rules={"locks.icloud_linked": "red"},
    )
    assert bucket == "grey"


def test_green_flag_defect_yields_grey():
    bucket, reason = compute_bucket(
        features={"display.glass_broken": "defect"},
        rules={"display.glass_broken": "green"},
    )
    assert bucket == "grey"


def test_all_green_rules_ok_yields_green():
    bucket, reason = compute_bucket(
        features={"display.glass_broken": "ok", "locks.icloud_linked": "ok"},
        rules={"display.glass_broken": "green", "locks.icloud_linked": "red"},
    )
    assert bucket == "green"
    assert reason is None


def test_ignored_features_do_not_affect_bucket():
    bucket, _ = compute_bucket(
        features={"sensors.truetone": "defect", "display.glass_broken": "ok"},
        rules={"sensors.truetone": "ignore", "display.glass_broken": "green"},
    )
    assert bucket == "green"


def test_missing_feature_state_treated_as_unknown():
    """A profile may have rules for features the parser hasn't filled in yet —
    treat as unknown."""
    bucket, _ = compute_bucket(
        features={},  # parser hasn't run yet
        rules={"display.glass_broken": "green"},
    )
    assert bucket == "grey"


def test_no_rules_at_all_yields_green():
    bucket, _ = compute_bucket(features={"display.glass_broken": "defect"}, rules={})
    assert bucket == "green"
```

- [ ] **Step 2: Run, expect ImportError**

```
python -m pytest tests/defect_features/test_bucket.py -v
```
Expected: ImportError.

- [ ] **Step 3: Write the bucket function**

Create `avito-monitor/app/services/defect_features/bucket.py`:

```python
"""Deterministic bucketing: (features, profile_rules) → ('green'|'grey'|'red', reason)."""
from __future__ import annotations

from typing import Literal


Bucket = Literal["green", "grey", "red"]


def compute_bucket(
    features: dict[str, str],   # {feature_key: 'ok'|'defect'|'unknown'}
    rules: dict[str, str],      # {feature_key: 'green'|'red'|'ignore'}
) -> tuple[Bucket, str | None]:
    """Pure: same inputs → same outputs. See spec §8 for the truth table.

    Returns (bucket, reason_feature_key). reason is None when bucket == 'green'.
    """
    # Step 1: red-flag CONFIRMED defect → red, short-circuit
    for fkey, rule in rules.items():
        if rule == "red" and features.get(fkey) == "defect":
            return ("red", fkey)

    # Step 2: any non-ignored unknown → grey (must clarify)
    for fkey, rule in rules.items():
        if rule in ("green", "red") and features.get(fkey, "unknown") == "unknown":
            return ("grey", fkey)

    # Step 3: green-flag defect → grey (operator decides)
    for fkey, rule in rules.items():
        if rule == "green" and features.get(fkey) == "defect":
            return ("grey", fkey)

    # Step 4: clean sweep
    return ("green", None)
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest tests/defect_features/test_bucket.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```
git add avito-monitor/app/services/defect_features/bucket.py \
        avito-monitor/tests/defect_features/test_bucket.py
git commit -m "feat(defect-features): compute_bucket pure function with 8 unit tests"
```

---

## Task 8: Repository helpers (DB read/write)

**Files:**
- Create: `avito-monitor/app/services/defect_features/repository.py`
- Modify: `avito-monitor/tests/defect_features/test_repository.py`

The repository module encapsulates SQL: UPSERT feature rows, load features for a listing, load rules for a profile, persist rule edits, list all (profile_id, listing_id) pairs that need bucket recompute.

- [ ] **Step 1: Add failing repository tests**

Append to `avito-monitor/tests/defect_features/test_repository.py`:

```python
"""Repository helpers — exercised against an in-memory SQLite via the
conftest fixture `db_session`. If conftest doesn't provide one yet,
skip these tests and run them once Task 8.5 wires it in."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ListingFeature, ProfileFeatureRule
from app.services.defect_features import repository


pytestmark = pytest.mark.asyncio


async def test_upsert_listing_features_inserts_new(db_session: AsyncSession,
                                                   sample_listing_id):
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={
            "locks.icloud_linked": {"state": "defect", "source": "avito_parameters",
                                     "evidence": "Привязка: Привязан", "confidence": None},
        },
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "avito_parameters"


async def test_upsert_listing_features_updates_existing(db_session, sample_listing_id):
    """Second upsert with same key overrides the row (last-write-wins)."""
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={"locks.icloud_linked": {"state": "ok", "source": "llm",
                                           "evidence": None, "confidence": 0.8}},
    )
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={"locks.icloud_linked": {"state": "defect", "source": "seller_dialog",
                                           "evidence": "Продавец сказал привязан",
                                           "confidence": 0.95}},
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "seller_dialog"


async def test_load_profile_rules(db_session, sample_profile_id):
    await repository.upsert_profile_rule(
        db_session, profile_id=sample_profile_id,
        feature_key="locks.icloud_linked", rule="red",
    )
    rules = await repository.load_profile_rules(db_session, sample_profile_id)
    assert rules["locks.icloud_linked"] == "red"


async def test_active_keys_excludes_ignore(db_session, sample_profile_id):
    await repository.upsert_profile_rule(db_session, profile_id=sample_profile_id,
                                          feature_key="locks.icloud_linked", rule="red")
    await repository.upsert_profile_rule(db_session, profile_id=sample_profile_id,
                                          feature_key="sensors.truetone", rule="ignore")
    active = await repository.load_active_feature_keys(db_session, sample_profile_id)
    assert "locks.icloud_linked" in active
    assert "sensors.truetone" not in active
```

Add a conftest fixture for `db_session`, `sample_listing_id`, `sample_profile_id` to `avito-monitor/tests/defect_features/conftest.py` (create new). Use the project's existing in-memory test DB pattern (look at `tests/conftest.py` for inspiration). If the project has no in-memory async fixture yet, create one:

```python
# avito-monitor/tests/defect_features/conftest.py
import uuid
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


@pytest_asyncio.fixture
async def db_session():
    """Each test gets a fresh in-memory async SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def sample_listing_id(db_session):
    """A minimal Listing row that the FK can hang on."""
    from app.db.models import Listing  # may need other required fields
    lst = Listing(avito_id=12345, title="iPhone 12 PM", url="https://x", images=[])
    db_session.add(lst)
    await db_session.commit()
    return lst.id


@pytest_asyncio.fixture
async def sample_profile_id(db_session):
    from app.db.models import SearchProfile
    sp = SearchProfile(name="iPhone 12 PM", user_id=uuid.uuid4())
    db_session.add(sp)
    await db_session.commit()
    return sp.id
```

If the Listing/SearchProfile fields above don't match the real models, peek at `app/db/models/listing.py` and `app/db/models/search_profile.py` and supply the actual NOT-NULL fields. Adjust until tests can at least import.

- [ ] **Step 2: Run, expect failures**

```
python -m pytest tests/defect_features/test_repository.py -v
```
Expected: ImportError on `from app.services.defect_features import repository`.

- [ ] **Step 3: Write the repository**

Create `avito-monitor/app/services/defect_features/repository.py`:

```python
"""DB helpers for listing_features + profile_feature_rules."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ListingFeature, ProfileFeatureRule


async def upsert_listing_features(
    session: AsyncSession,
    *,
    listing_id: uuid.UUID,
    features: dict[str, dict[str, Any]],
) -> None:
    """INSERT … ON CONFLICT UPDATE for each feature key.

    `features` values: {state, source, evidence, confidence}.
    """
    if not features:
        return
    for fkey, payload in features.items():
        stmt = pg_insert(ListingFeature).values(
            listing_id=listing_id,
            feature_key=fkey,
            state=payload["state"],
            source=payload["source"],
            evidence=payload.get("evidence"),
            confidence=payload.get("confidence"),
        ).on_conflict_do_update(
            index_elements=["listing_id", "feature_key"],
            set_={
                "state": payload["state"],
                "source": payload["source"],
                "evidence": payload.get("evidence"),
                "confidence": payload.get("confidence"),
                "parsed_at": pg_insert(ListingFeature).excluded.parsed_at,
            },
        )
        await session.execute(stmt)
    await session.flush()


async def load_listing_features(
    session: AsyncSession, listing_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    rows = (await session.execute(
        select(ListingFeature).where(ListingFeature.listing_id == listing_id)
    )).scalars().all()
    return {
        r.feature_key: {
            "state": r.state, "source": r.source,
            "evidence": r.evidence, "confidence": r.confidence,
        }
        for r in rows
    }


async def upsert_profile_rule(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    feature_key: str,
    rule: str,
) -> None:
    stmt = pg_insert(ProfileFeatureRule).values(
        profile_id=profile_id, feature_key=feature_key, rule=rule,
    ).on_conflict_do_update(
        index_elements=["profile_id", "feature_key"],
        set_={"rule": rule, "updated_at": pg_insert(ProfileFeatureRule).excluded.updated_at},
    )
    await session.execute(stmt)
    await session.flush()


async def load_profile_rules(
    session: AsyncSession, profile_id: uuid.UUID,
) -> dict[str, str]:
    rows = (await session.execute(
        select(ProfileFeatureRule.feature_key, ProfileFeatureRule.rule)
        .where(ProfileFeatureRule.profile_id == profile_id)
    )).all()
    return {r.feature_key: r.rule for r in rows}


async def load_active_feature_keys(
    session: AsyncSession, profile_id: uuid.UUID,
) -> set[str]:
    """All feature keys where rule != 'ignore'."""
    rules = await load_profile_rules(session, profile_id)
    return {k for k, r in rules.items() if r in ("green", "red")}
```

> **Note on UPSERT portability.** `pg_insert.on_conflict_do_update` is PostgreSQL-only. The SQLite-backed tests will fail on that. If conftest uses SQLite, factor out a dialect-aware UPSERT helper (try `pg_insert`, fallback to `select-then-insert/update`). The simplest: detect dialect once at module-load and pick implementation. Add it as a helper inside this file. The tests must pass against whichever DB conftest provides.

- [ ] **Step 4: Run, fix until PASS**

```
python -m pytest tests/defect_features/test_repository.py -v
```
Expected: 4 new tests pass. If SQLite barfs on `pg_insert`, add dialect-aware fallback and re-run.

- [ ] **Step 5: Commit**

```
git add avito-monitor/app/services/defect_features/repository.py \
        avito-monitor/tests/defect_features/test_repository.py \
        avito-monitor/tests/defect_features/conftest.py
git commit -m "feat(defect-features): repository — UPSERT/load for features + rules"
```

---

## Task 9: Pipeline integration in analyze_listing

**Files:**
- Create: `avito-monitor/app/services/defect_features/pipeline.py`
- Modify: `avito-monitor/app/tasks/analysis.py`
- Create: `avito-monitor/tests/defect_features/test_pipeline.py`

- [ ] **Step 1: Write failing test for pipeline orchestrator**

Create `avito-monitor/tests/defect_features/test_pipeline.py`:

```python
"""Integration-style tests for analyze_listing_features:
   features parser → DB upsert → compute_bucket → bucket written."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.defect_features.pipeline import analyze_listing_features


pytestmark = pytest.mark.asyncio


async def test_writes_features_and_returns_bucket(db_session,
                                                  sample_listing_id,
                                                  sample_profile_id):
    # Seed a red-flag rule on the profile
    from app.services.defect_features import repository
    await repository.upsert_profile_rule(
        db_session, profile_id=sample_profile_id,
        feature_key="locks.icloud_linked", rule="red",
    )

    fake_parsed = {
        "locks.icloud_linked": {"state": "defect", "source": "llm",
                                "evidence": "Привязан", "confidence": 0.9},
    }
    with patch(
        "app.services.defect_features.pipeline.parse_defect_features",
        new=AsyncMock(return_value=fake_parsed),
    ):
        bucket, reason = await analyze_listing_features(
            session=db_session,
            listing_id=sample_listing_id,
            profile_id=sample_profile_id,
            title="x", description="y", parameters={},
        )
    assert bucket == "red"
    assert reason == "locks.icloud_linked"
    # DB has the feature row written
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"


async def test_no_active_rules_yields_green(db_session,
                                            sample_listing_id, sample_profile_id):
    """Profile with no rules at all → bucket=green, no LLM call."""
    with patch(
        "app.services.defect_features.pipeline.parse_defect_features",
        new=AsyncMock(),
    ) as m_parse:
        bucket, reason = await analyze_listing_features(
            session=db_session,
            listing_id=sample_listing_id,
            profile_id=sample_profile_id,
            title="x", description="y", parameters={},
        )
    assert bucket == "green"
    assert reason is None
    m_parse.assert_not_called()
```

- [ ] **Step 2: Run, expect ImportError**

```
python -m pytest tests/defect_features/test_pipeline.py -v
```

- [ ] **Step 3: Write `pipeline.py`**

Create `avito-monitor/app/services/defect_features/pipeline.py`:

```python
"""Orchestrates the full defect-feature pipeline for one listing/profile pair.

  load_active_keys(profile)
    ↓
  parse_defect_features(active_keys)
    ↓
  upsert_listing_features
    ↓
  compute_bucket(features, rules)
    ↓
  return (bucket, reason)
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.defect_features import repository
from app.services.defect_features.bucket import Bucket, compute_bucket
from app.services.defect_features.llm_parser import parse_defect_features


async def analyze_listing_features(
    *,
    session: AsyncSession,
    listing_id: uuid.UUID,
    profile_id: uuid.UUID,
    title: str,
    description: str,
    parameters: dict[str, Any] | None,
) -> tuple[Bucket, str | None]:
    """Run the parser and bucketing for one (listing, profile) pair.

    No side-effect on user_action — caller decides whether to auto-reject.
    """
    rules = await repository.load_profile_rules(session, profile_id)
    active_keys = {k for k, r in rules.items() if r in ("green", "red")}
    if not active_keys:
        return ("green", None)

    parsed = await parse_defect_features(
        title=title, description=description,
        parameters=parameters or {}, active_keys=active_keys,
    )

    await repository.upsert_listing_features(
        session, listing_id=listing_id, features=parsed,
    )

    feature_states = {k: v["state"] for k, v in parsed.items()}
    return compute_bucket(feature_states, rules)
```

- [ ] **Step 4: Run, expect 2 passed**

```
python -m pytest tests/defect_features/test_pipeline.py -v
```

- [ ] **Step 5: Wire into `analyze_listing` in `app/tasks/analysis.py`**

Locate the spot in `app/tasks/analysis.py` where `classify_condition` is called and the bucket is written to `ProfileListing.bucket`. Insert `analyze_listing_features` call immediately after `classify_condition` and replace the V2 confidence-based bucket assignment with the function's return value. Also write `user_action='rejected'`, `rejected_reason=f'auto:{reason}'` when bucket=red AND current user_action ∈ (NULL, 'pending', 'viewed').

Pseudocode for the modification (apply with `Edit` tool — match existing variable names):

```python
# AFTER the existing classify_condition block:
from app.services.defect_features.pipeline import analyze_listing_features

new_bucket, reason = await analyze_listing_features(
    session=session,
    listing_id=listing.id,
    profile_id=profile.id,
    title=listing.title,
    description=listing.description or "",
    parameters=listing.parameters or {},
)
pl.bucket = new_bucket  # ProfileListing row in scope here
if new_bucket == "red" and pl.user_action in (None, "pending", "viewed"):
    pl.user_action = "rejected"
    pl.rejected_reason = f"auto:{reason}"
# REMOVE / COMMENT-OUT the old V2 confidence-based bucket assignment that
# preceded this block. Keep classify_condition itself (condition_class is
# still used by market-stats).
```

If you can't safely identify the old V2 lines, ship them disabled behind a `settings.v2_reliability_bucketing_enabled` feature flag set to `False` in env (add to `Settings` class with default `False`). Document the flag in the commit message.

- [ ] **Step 6: Integration smoke — manual**

Apply the migration locally if not yet (Task 2), seed one rule on the dev profile:
```
psql $DEV_DB -c "INSERT INTO profile_feature_rules (profile_id, feature_key, rule) \
    SELECT id, 'locks.icloud_linked', 'red' FROM search_profiles LIMIT 1;"
```
Run the worker manually on one listing:
```
cd avito-monitor && python -c "
import asyncio
from app.tasks.analysis import analyze_listing
# substitute a known listing UUID
asyncio.run(analyze_listing.kiq('<listing-uuid>').wait_result())
"
```
Inspect:
```
psql $DEV_DB -c "SELECT feature_key, state, source FROM listing_features \
  WHERE listing_id = '<listing-uuid>'"
psql $DEV_DB -c "SELECT bucket, user_action, rejected_reason FROM profile_listings \
  WHERE listing_id = '<listing-uuid>'"
```
Expected: feature rows present, bucket = one of the three.

- [ ] **Step 7: Commit**

```
git add avito-monitor/app/services/defect_features/pipeline.py \
        avito-monitor/app/tasks/analysis.py \
        avito-monitor/tests/defect_features/test_pipeline.py
git commit -m "feat(analysis): integrate defect-feature parser + bucket into analyze_listing"
```

---

## Task 10: View-layer — load features into KanbanCard / ListingRow

**Files:**
- Modify: `avito-monitor/app/services/seller_dialog_view.py`
- Modify: `avito-monitor/app/services/listings_view.py`
- Modify: `avito-monitor/tests/seller_dialog/test_view.py` — assert KanbanCard has features
- Modify: `avito-monitor/app/db/models/__init__.py` if needed

- [ ] **Step 1: Add failing assertion to KanbanCard test**

Append to `avito-monitor/tests/seller_dialog/test_view.py`:

```python
def test_kanban_card_has_features_field():
    """Phase 1: card carries pre-loaded {feature_key: state} dict for the
    Признаки block rendered in the expanded body."""
    fields = set(KanbanCard.__annotations__.keys())
    assert "features" in fields, fields
```

- [ ] **Step 2: Run, expect fail**

```
python -m pytest tests/seller_dialog/test_view.py::test_kanban_card_has_features_field -v
```

- [ ] **Step 3: Add features field + load in seller_dialog_view.py**

Modify `avito-monitor/app/services/seller_dialog_view.py`:

1. Add `features: dict[str, str]` (key → state) to the `KanbanCard` dataclass.
2. In `query_kanban_cards`: after rows are fetched, batch-load features for all listings in one query:

```python
from sqlalchemy import select
from app.db.models import ListingFeature

# ... in query_kanban_cards, after the main rows query:
listing_ids = [listing.id for _, listing, _ in rows]
features_rows = []
if listing_ids:
    features_rows = (await session.execute(
        select(ListingFeature.listing_id, ListingFeature.feature_key,
               ListingFeature.state)
        .where(ListingFeature.listing_id.in_(listing_ids))
    )).all()
features_by_listing: dict[uuid.UUID, dict[str, str]] = {}
for lid, fkey, state in features_rows:
    features_by_listing.setdefault(lid, {})[fkey] = state

# in the loop that builds KanbanCard, pass:
card = KanbanCard(..., features=features_by_listing.get(listing.id, {}))
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest tests/seller_dialog/test_view.py -v
```

- [ ] **Step 5: Do the same for `listings_view.py`**

Find `ListingRow` dataclass; add `features: dict[str, str]` field.
Find the main `query_listings` (already loads `_images_list`); add the same batch-load-features section and pass into ListingRow.

- [ ] **Step 6: Smoke test the listings view doesn't crash**

```
python -m pytest tests/services/test_listings_view.py -v 2>&1 | tail
```
(If no such test file exists, just run the broader `python -m pytest tests/ -q -k listings` and fix any breakage.)

- [ ] **Step 7: Commit**

```
git add avito-monitor/app/services/seller_dialog_view.py \
        avito-monitor/app/services/listings_view.py \
        avito-monitor/tests/seller_dialog/test_view.py
git commit -m "feat(views): load listing_features into KanbanCard + ListingRow"
```

---

## Task 11: UI — Признаки block partial

**Files:**
- Create: `avito-monitor/app/web/templates/_partials/_features_block.html`
- Modify: `avito-monitor/app/web/templates/_partials/_kanban_card_body.html`
- Modify: `avito-monitor/app/web/templates/listings.html`

The block iterates the 22-feature taxonomy grouped by section. For each feature it shows an icon based on `card.features[feature.key]` (or `r.features` in listings.html context). Features the operator marked `ignore` are skipped (we need rules for that — for now show ALL features parsed; suppression by rule comes in Task 13 when rules endpoint exists. In Phase 1 first deploy: show all that have a state row).

- [ ] **Step 1: Create the partial**

Create `avito-monitor/app/web/templates/_partials/_features_block.html`:

```html
{# Признаки — defect-feature checklist for one listing.
   Required context vars:
     features: {feature_key: state} where state ∈ ok | defect | unknown
     features_evidence: optional {feature_key: evidence text}  (None ⇒ no tooltip)
   The taxonomy is loaded via the `defect_taxonomy` global injected by
   the layout context processor (see Task 14). Sections in fixed order. #}

{% if features %}
{% set _STATE_ICON = {'ok': '✓', 'defect': '⊘', 'unknown': '⚪'} %}
{% set _STATE_CLS = {
    'ok':      'text-emerald-600',
    'defect':  'text-rose-600',
    'unknown': 'text-stone-400',
} %}
{% set _SECTION_LABELS = {
    'display':     'Дисплей',
    'case':        'Корпус',
    'locks':       'Блокировки',
    'sensors':     'Датчики',
    'charging':    'Зарядка',
    'operability': 'Работоспособность',
} %}

<div class="bg-white rounded-md border border-stone-200 p-3 mb-3">
  <div class="text-[11px] uppercase text-stone-500 mb-2">Признаки</div>
  <div class="grid grid-cols-1 gap-y-2 text-xs">
    {% for section in ('display','case','locks','sensors','charging','operability') %}
      {% set section_features = defect_taxonomy | selectattr('section','equalto',section) | list %}
      {% set visible = section_features | selectattr('key','in',features) | list %}
      {% if visible %}
        <div class="flex gap-2">
          <div class="w-20 text-stone-500 flex-shrink-0">{{ _SECTION_LABELS[section] }}</div>
          <div class="flex-1 space-y-0.5">
            {% for f in visible %}
              {% set st = features[f.key] %}
              <div class="flex items-center gap-1.5" title="{{ (features_evidence or {}).get(f.key, '') }}">
                <span class="{{ _STATE_CLS[st] }} text-base leading-none w-3">{{ _STATE_ICON[st] }}</span>
                <span class="text-stone-800">{{ f.title }}</span>
              </div>
            {% endfor %}
          </div>
        </div>
      {% endif %}
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: Include in kanban card body**

In `avito-monitor/app/web/templates/_partials/_kanban_card_body.html`, find the start of the expanded body and add the partial BEFORE the description:

```html
{# ... existing 'description' block area ... #}
{% with features=card.features, features_evidence=None %}
  {% include "_partials/_features_block.html" %}
{% endwith %}
```

(Tip: pass via `{% with %}` so the partial works for both kanban-card and listings.html contexts where the variable name differs.)

- [ ] **Step 3: Include in listings.html**

In `avito-monitor/app/web/templates/listings.html`, in the expanded-body area for each card (likely inside the `<details>` body or row-expanded section), add:

```html
{% with features=r.features, features_evidence=None %}
  {% include "_partials/_features_block.html" %}
{% endwith %}
```

- [ ] **Step 4: Inject `defect_taxonomy` into template context**

Find the FastAPI/Jinja context provider used by the kanban + listings routes. Add a global:

```python
# in app/web/templates.py or wherever Jinja `templates` is configured
from app.services.defect_features.taxonomy import load_taxonomy
templates.env.globals["defect_taxonomy"] = list(load_taxonomy())
```

(Hardcoded global is fine since taxonomy is process-static.)

- [ ] **Step 5: Render-test**

Start the dev server:
```
cd avito-monitor && uvicorn app.main:app --reload --port 8001
```
Open `http://localhost:8001/listings?tab=in_progress` — expand a card. You should see the Признаки block above the description. Features without a row remain hidden (which is most of them on first run before backfill, see Task 17).

Stop server.

- [ ] **Step 6: Commit**

```
git add avito-monitor/app/web/templates/_partials/_features_block.html \
        avito-monitor/app/web/templates/_partials/_kanban_card_body.html \
        avito-monitor/app/web/templates/listings.html \
        avito-monitor/app/web/templates.py  # or wherever you injected the global
git commit -m "feat(ui): Признаки block (defect checklist) in kanban + listings cards"
```

---

## Task 12: Sidebar collapse + persistent state

**Files:**
- Modify: `avito-monitor/app/web/templates/_layout.html`

- [ ] **Step 1: Add the hamburger button + collapsed state**

Edit `_layout.html`:

1. Wrap the `<aside>` so it carries `id="sidebar"` and `data-collapsed="false"`:
```html
<aside id="sidebar" data-collapsed="false"
       class="bg-avito-bg border-r border-avito-border flex-shrink-0
              w-60 data-[collapsed=true]:w-14 transition-[width] duration-200">
```

2. Add a hamburger button at the very start of the `<header>` topbar:
```html
<button id="sidebar-toggle" type="button" aria-label="Свернуть меню"
        class="mr-3 w-9 h-9 rounded-md hover:bg-avito-elev text-avito-text-soft hover:text-avito-text">
  ☰
</button>
```

3. Make the labels (the `flex-1` spans inside each nav link) and the bottom info block hide when collapsed:
```html
<span class="flex-1 data-[collapsed=true]:hidden">{{ label }}</span>
...
<div class="px-5 pt-4 pb-6 mt-2 text-[11px] ... data-[collapsed=true]:hidden ...">
```

   The `data-[collapsed=true]:hidden` arbitrary-variant references the closest parent with `data-collapsed="true"`. Tailwind doesn't traverse — apply the attribute on `<body>` or replicate the variant by reading `sidebar.dataset.collapsed` in JS. The simpler approach: have the JS toggle a single class on each label span. Use whichever works in your Tailwind config; both compile.

4. Append the JS at the end of `<body>`:
```html
<script>
(function () {
  const KEY = 'kpis_sidebar_collapsed';
  const sb = document.getElementById('sidebar');
  const btn = document.getElementById('sidebar-toggle');
  if (!sb || !btn) return;
  const apply = (collapsed) => {
    sb.dataset.collapsed = collapsed ? 'true' : 'false';
    // Toggle visibility of labels + bottom block
    sb.querySelectorAll('[data-sidebar-label]').forEach(el => {
      el.classList.toggle('hidden', collapsed);
    });
    btn.setAttribute('aria-label', collapsed ? 'Развернуть меню' : 'Свернуть меню');
  };
  apply(localStorage.getItem(KEY) === '1');
  btn.addEventListener('click', () => {
    const next = sb.dataset.collapsed !== 'true';
    apply(next);
    localStorage.setItem(KEY, next ? '1' : '0');
  });
})();
</script>
```

   And on every `<span class="flex-1">` and the bottom info `<div>` add `data-sidebar-label`.

- [ ] **Step 2: Smoke test in browser**

Dev server + open the kanban page. Click hamburger — sidebar should shrink to icon-only column ~56px; click again to expand back. Reload — state persists.

- [ ] **Step 3: Commit**

```
git add avito-monitor/app/web/templates/_layout.html
git commit -m "feat(ui): collapsible sidebar with persistent state"
```

---

## Task 13: /profiles/{id}/feature-rules page + endpoints

**Files:**
- Create: `avito-monitor/app/web/templates/profiles/feature_rules.html`
- Modify: `avito-monitor/app/web/routers.py`
- Modify: `avito-monitor/app/web/templates/_layout.html` — add sidebar nav item

- [ ] **Step 1: Write failing tests for endpoints**

Add to `avito-monitor/tests/defect_features/test_repository.py` (or a new `test_routes.py`):

```python
# (in a routes-style test that drives FastAPI with TestClient)
# If the project doesn't have a TestClient fixture yet, skip this and
# rely on the manual smoke in Step 5 — Task 13 is mostly UI-glue and the
# repository-level logic is already covered by Task 8.
```

(Phase 1 plan only requires manual smoke for HTTP routes — the data-layer is covered. Skip the failing-test cycle here.)

- [ ] **Step 2: Write the page template**

Create `avito-monitor/app/web/templates/profiles/feature_rules.html`:

```html
{% extends "_layout.html" %}
{% block page_content %}
<div class="max-w-[1024px]">
  <h1 class="text-2xl font-semibold mb-1 text-avito-text">Настройки модели — {{ profile.name }}</h1>
  <p class="text-sm text-avito-text-soft mb-6">
    Per-feature правила определяют как лоты бакетятся: 🟢 — желателен ok,
    🔴 — критичный дефект (auto-reject), ⊘ — не учитываем.
  </p>

  {% set _SECTION_LABELS = {
      'display':'Дисплей','case':'Корпус','locks':'Блокировки и ПО',
      'sensors':'Датчики','charging':'Зарядка','operability':'Работоспособность',
  } %}

  <form id="rules-form" data-profile-id="{{ profile.id }}">
    {% for section in ('display','case','locks','sensors','charging','operability') %}
      <fieldset class="bg-avito-surface border border-avito-border rounded-md mb-4">
        <legend class="px-3 py-2 text-sm font-semibold text-avito-text">{{ _SECTION_LABELS[section] }}</legend>
        <div class="divide-y divide-avito-border-soft">
          {% for f in defect_taxonomy if f.section == section %}
            {% set current = rules.get(f.key, 'ignore') %}
            <div class="flex items-center justify-between px-3 py-2">
              <div class="text-sm text-avito-text">{{ f.title }}</div>
              <div class="inline-flex rounded-md border border-avito-border bg-avito-elev overflow-hidden text-xs">
                {% for value, label, cls in [
                    ('green', '🟢', 'hover:bg-emerald-100'),
                    ('red',   '🔴', 'hover:bg-rose-100'),
                    ('ignore','⊘',  'hover:bg-stone-200'),
                  ] %}
                  <button type="button" data-rule-key="{{ f.key }}" data-rule-value="{{ value }}"
                          aria-pressed="{{ 'true' if current == value else 'false' }}"
                          class="rule-seg px-3 py-1 {{ cls }}
                                 {% if current == value %}bg-avito-brand-soft font-medium{% endif %}">
                    {{ label }}
                  </button>
                {% endfor %}
              </div>
            </div>
          {% endfor %}
        </div>
      </fieldset>
    {% endfor %}
  </form>

  <div id="rules-toast" class="fixed bottom-4 right-4 bg-avito-text text-white px-4 py-2 rounded-md text-sm hidden"></div>
</div>

<script>
(function () {
  const form = document.getElementById('rules-form');
  const toast = document.getElementById('rules-toast');
  if (!form) return;
  const pid = form.dataset.profileId;

  const showToast = (msg) => {
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2500);
  };

  form.addEventListener('click', async (e) => {
    const btn = e.target.closest('.rule-seg');
    if (!btn) return;
    const key = btn.dataset.ruleKey;
    const value = btn.dataset.ruleValue;
    const resp = await fetch(`/profiles/${pid}/feature-rules/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({rule: value}),
    });
    if (!resp.ok) { showToast('Не удалось сохранить'); return; }
    // Repaint segment group
    btn.parentElement.querySelectorAll('.rule-seg').forEach(b => {
      const active = b === btn;
      b.setAttribute('aria-pressed', active ? 'true' : 'false');
      b.classList.toggle('bg-avito-brand-soft', active);
      b.classList.toggle('font-medium', active);
    });
    const data = await resp.json();
    if (data.recompute) {
      showToast(`Бакеты: ${data.recompute.green} зелёных / ${data.recompute.grey} серых / ${data.recompute.red} отклонено`);
    } else {
      showToast('Сохранено');
    }
  });
})();
</script>
{% endblock %}
```

- [ ] **Step 3: Add routes**

In `avito-monitor/app/web/routers.py`:

```python
@router.get("/profiles/{profile_id}/feature-rules", response_class=HTMLResponse)
async def feature_rules_page(profile_id: uuid.UUID,
                             request: Request,
                             session: AsyncSession = Depends(get_session),
                             user=Depends(current_user)):
    profile = await session.get(SearchProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(404)
    rules = await repository.load_profile_rules(session, profile_id)
    ctx = await _base_context(request, user, session, active="model-settings",
                              profile=profile, rules=rules)
    return templates.TemplateResponse(request, "profiles/feature_rules.html", ctx)


@router.patch("/profiles/{profile_id}/feature-rules/{feature_key}")
async def set_feature_rule(profile_id: uuid.UUID, feature_key: str,
                           body: dict = Body(...),
                           session: AsyncSession = Depends(get_session),
                           user=Depends(current_user)):
    profile = await session.get(SearchProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(404)
    rule = body.get("rule")
    if rule not in ("green", "red", "ignore"):
        raise HTTPException(422, "rule must be green|red|ignore")
    await repository.upsert_profile_rule(
        session, profile_id=profile_id, feature_key=feature_key, rule=rule,
    )
    await session.commit()
    # Recompute buckets synchronously (small N — see spec §9.4)
    summary = await recompute_buckets_for_profile(session, profile_id)
    await session.commit()
    return {"ok": True, "recompute": summary}
```

Add the `recompute_buckets_for_profile` function (inline in `routers.py` is OK for Phase 1, can move to `defect_features/recompute.py` later):

```python
async def recompute_buckets_for_profile(session: AsyncSession, profile_id: uuid.UUID):
    """Recompute bucket for every profile_listings row of this profile.
    Returns {'green': N, 'grey': N, 'red': N} summary.

    Does NOT call LLM — only re-reads listing_features. For accepted lots
    user_action is preserved; for pending/viewed/null with new bucket=red
    we auto-reject (spec §8)."""
    from app.services.defect_features.bucket import compute_bucket

    rules = await repository.load_profile_rules(session, profile_id)
    pls = (await session.execute(
        select(ProfileListing).where(ProfileListing.profile_id == profile_id)
    )).scalars().all()

    counters = {"green": 0, "grey": 0, "red": 0}
    for pl in pls:
        features = await repository.load_listing_features(session, pl.listing_id)
        states = {k: v["state"] for k, v in features.items()}
        new_bucket, reason = compute_bucket(states, rules)
        pl.bucket = new_bucket
        counters[new_bucket] += 1
        if new_bucket == "red" and pl.user_action in (None, "pending", "viewed"):
            pl.user_action = "rejected"
            pl.rejected_reason = f"auto:{reason}"
    return counters
```

- [ ] **Step 4: Add new sidebar nav item**

In `_layout.html`, in the `_items` list:

```python
('model-settings', '/profiles/' ~ (sidebar_active_profile_id or '') ~ '/feature-rules',
 '🛠', 'Настройки модели', None),
```

Add `sidebar_active_profile_id` to `_base_context` — for Phase 1 hardcode to the first profile of the user:

```python
# In app/web/routers.py:_base_context
sidebar_active_profile_id = (
    await session.execute(
        select(SearchProfile.id).where(SearchProfile.user_id == user.id)
        .order_by(SearchProfile.created_at).limit(1)
    )
).scalar_one_or_none()
```

If no profile exists, leave the link href as `#`.

- [ ] **Step 5: Manual smoke**

Dev server up. Open `/profiles/{your_profile_id}/feature-rules`. Click each segment toggle — toast appears with bucket counts. Refresh the page — selections persist. Visit `/listings?tab=in_progress` — bucket badges reflect new state.

- [ ] **Step 6: Commit**

```
git add avito-monitor/app/web/templates/profiles/feature_rules.html \
        avito-monitor/app/web/routers.py \
        avito-monitor/app/web/templates/_layout.html
git commit -m "feat(ui): /profiles/{id}/feature-rules page + sidebar nav + sync bucket recompute"
```

---

## Task 14: Backfill script

**Files:**
- Create: `avito-monitor/scripts/backfill_features.py`

- [ ] **Step 1: Write the script**

```python
"""Backfill defect-feature rows for all active listings.

For each (profile, listing) pair currently in user_action IN
(NULL, 'pending', 'viewed', 'accepted'), run analyze_listing_features
exactly once. Reports progress every 25 listings.

Usage:
    python -m scripts.backfill_features
    python -m scripts.backfill_features --profile <profile_id>
    python -m scripts.backfill_features --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from sqlalchemy import select

from app.db.models import Listing, ProfileListing, SearchProfile
from app.db.session import async_session_maker
from app.services.defect_features.pipeline import analyze_listing_features


logger = logging.getLogger("backfill_features")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


async def run(profile_filter: uuid.UUID | None, dry_run: bool):
    async with async_session_maker() as session:
        q = (select(ProfileListing.profile_id, ProfileListing.listing_id, Listing)
             .join(Listing, Listing.id == ProfileListing.listing_id)
             .where(ProfileListing.user_action.in_(
                 (None, "pending", "viewed", "accepted")
             )))
        if profile_filter:
            q = q.where(ProfileListing.profile_id == profile_filter)
        rows = (await session.execute(q)).all()
        logger.info("found %d pairs to backfill", len(rows))

        for i, (pid, lid, listing) in enumerate(rows, 1):
            if dry_run:
                logger.info("[dry] %s — %s", lid, listing.title[:60])
                continue
            try:
                bucket, reason = await analyze_listing_features(
                    session=session,
                    listing_id=lid, profile_id=pid,
                    title=listing.title or "",
                    description=listing.description or "",
                    parameters=listing.parameters or {},
                )
                await session.commit()
                if i % 25 == 0:
                    logger.info("[%d/%d] bucket=%s reason=%s", i, len(rows), bucket, reason)
            except Exception:
                logger.exception("listing %s failed, skipping", lid)
                await session.rollback()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", type=uuid.UUID, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    asyncio.run(run(a.profile, a.dry_run))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run smoke**

```
cd avito-monitor && python -m scripts.backfill_features --dry-run | head -5
```
Expected: prints "found N pairs to backfill" + a few `[dry] <uuid> — <title>` lines.

- [ ] **Step 3: Commit**

```
git add avito-monitor/scripts/backfill_features.py
git commit -m "feat(scripts): backfill defect-features for active listings"
```

---

## Task 15: Acceptance smoke — full pipeline on prod-like data

**Files:** none (purely operational)

- [ ] **Step 1: Apply migration on dev DB**

```
cd avito-monitor && alembic upgrade head
```

- [ ] **Step 2: Seed rules for one profile**

```
psql $DEV_DB <<SQL
INSERT INTO profile_feature_rules (profile_id, feature_key, rule)
SELECT id, 'locks.icloud_linked',     'red'   FROM search_profiles LIMIT 1;
INSERT INTO profile_feature_rules (profile_id, feature_key, rule)
SELECT id, 'display.glass_broken',    'green' FROM search_profiles LIMIT 1;
INSERT INTO profile_feature_rules (profile_id, feature_key, rule)
SELECT id, 'sensors.face_id',         'green' FROM search_profiles LIMIT 1;
SQL
```

- [ ] **Step 3: Backfill**

```
python -m scripts.backfill_features
```
Tail logs — watch for LLM-cost spike. Expected: 6 parallel LLM per listing, takes ~3-5 seconds per lot.

- [ ] **Step 4: Visual smoke**

Open kanban → expanded card body should show Признаки block populated.
Open `/profiles/{id}/feature-rules` → toggle locks.icloud_linked to 🔴 if not already → toast shows counter.

- [ ] **Step 5: Auto-reject sanity**

Find one listing where LLM marked `locks.icloud_linked = defect`:
```
psql $DEV_DB -c "SELECT lf.listing_id FROM listing_features lf \
  WHERE feature_key='locks.icloud_linked' AND state='defect' LIMIT 5;"
```
For at least one of these, check `profile_listings.user_action`:
```
psql $DEV_DB -c "SELECT user_action, rejected_reason, bucket FROM profile_listings \
  WHERE listing_id='<uuid>';"
```
Expected: `user_action='rejected'`, `rejected_reason='auto:locks.icloud_linked'`, `bucket='red'`.

- [ ] **Step 6: NO commit needed** — operational task only.

---

## Final Self-Review (executed by writing-plans skill)

(See "Self-Review" section in the writing-plans skill — placeholder scan, spec coverage, type consistency.)

After all 15 tasks: spec §1-§13 has a corresponding task. Phase 2 (sections 10.2-10.4 of spec) is **out of scope** for this plan — separate plan after soak.
