"""v2_seed_criteria_library — populate criteria_templates from YAML
                              + auto-migrate 7 legacy profiles.

Reads ``app/data/criteria_templates.yaml`` and upserts rows into
``criteria_templates`` (idempotent on ``key``). Then for every
SearchProfile whose ``profile_criteria`` is empty, derives:

* one ``profile_criteria`` row per condition that is NOT in the
  legacy ``allowed_conditions`` list (mapping enum → library key);
* one custom ``profile_criteria`` row carrying the legacy
  ``custom_criteria`` free text, if non-empty.

Data migration only — schema unchanged. Idempotent: re-running has
no effect on profiles that already have rows.

Revision ID: 0007_v2_seed_criteria_library
Revises: 0006_v2_llm_pipeline
Create Date: 2026-05-05 10:10:00
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
import yaml
from alembic import op

revision: str = "0007_v2_seed_criteria_library"
down_revision: Union[str, None] = "0006_v2_llm_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Maps a legacy ConditionClass enum value to the library criterion key
# whose presence-as-red would mean the listing is in that bad-condition
# class. If allowed_conditions does NOT include the enum, the user
# wants those listings filtered out — which means we must add the
# corresponding criterion as red-trigger.
CONDITION_TO_CRITERION_KEY = {
    "blocked_icloud": "icloud_locked",
    "blocked_account": "account_blocked",
    "not_starting": "not_starting",
    "broken_screen": "screen_broken",
    "parts_only": "parts_only",
    # broken_other has no direct library mapping — skipped on purpose.
}


def _yaml_path() -> Path:
    # alembic runs from the repo root; the file lives under app/data.
    here = Path(__file__).resolve()
    # avito-monitor/alembic/versions/<file>.py → up to avito-monitor/
    repo = here.parents[2]
    return repo / "app" / "data" / "criteria_templates.yaml"


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Upsert library rows from YAML ---------------------------
    rows = yaml.safe_load(_yaml_path().read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError(
            "criteria_templates.yaml must be a list of templates"
        )

    upsert_sql = sa.text(
        """
        INSERT INTO criteria_templates
            (id, key, title_ru, description_ru, kind, prompt_fragment,
             api_path, params_schema, output_schema, version, is_active,
             created_at, updated_at)
        VALUES
            (:id, :key, :title_ru, :description_ru, :kind, :prompt_fragment,
             :api_path, CAST(:params_schema AS JSONB),
             CAST(:output_schema AS JSONB), :version, TRUE,
             NOW(), NOW())
        ON CONFLICT (key) DO UPDATE SET
            title_ru = EXCLUDED.title_ru,
            description_ru = EXCLUDED.description_ru,
            kind = EXCLUDED.kind,
            prompt_fragment = EXCLUDED.prompt_fragment,
            api_path = EXCLUDED.api_path,
            params_schema = EXCLUDED.params_schema,
            output_schema = EXCLUDED.output_schema,
            version = EXCLUDED.version,
            is_active = TRUE,
            updated_at = NOW()
        """
    )

    for row in rows:
        bind.execute(
            upsert_sql,
            {
                "id": str(uuid.uuid4()),
                "key": row["key"],
                "title_ru": row["title_ru"],
                "description_ru": row.get("description_ru"),
                "kind": row["kind"],
                "prompt_fragment": row.get("prompt_fragment"),
                "api_path": row.get("api_path"),
                "params_schema": (
                    json.dumps(row["params_schema"])
                    if row.get("params_schema") is not None
                    else None
                ),
                "output_schema": (
                    json.dumps(row["output_schema"])
                    if row.get("output_schema") is not None
                    else None
                ),
                "version": int(row.get("version", 1)),
            },
        )

    # --- 2. Auto-migrate existing profiles --------------------------
    # Only profiles with no profile_criteria rows yet.
    profiles = bind.execute(
        sa.text(
            """
            SELECT sp.id, sp.allowed_conditions, sp.custom_criteria
            FROM search_profiles sp
            WHERE NOT EXISTS (
                SELECT 1 FROM profile_criteria pc
                WHERE pc.profile_id = sp.id
            )
            """
        )
    ).fetchall()

    if not profiles:
        return

    # Resolve template ids by key
    tpl_rows = bind.execute(
        sa.text("SELECT id, key FROM criteria_templates")
    ).fetchall()
    key_to_tpl_id = {r.key: r.id for r in tpl_rows}

    insert_pc = sa.text(
        """
        INSERT INTO profile_criteria
            (id, profile_id, template_id, custom_key, custom_title_ru,
             custom_kind, custom_prompt_fragment, params, is_hard,
             sort_order, created_at, updated_at)
        VALUES
            (:id, :profile_id, :template_id, :custom_key,
             :custom_title_ru, :custom_kind, :custom_prompt_fragment,
             CAST(:params AS JSONB), :is_hard, :sort_order,
             NOW(), NOW())
        """
    )

    for prof in profiles:
        allowed = set(prof.allowed_conditions or ["working"])
        sort_order = 0

        # Each condition NOT in allowed becomes a hard criterion
        # (red on that flag → drop the listing).
        for cond, key in CONDITION_TO_CRITERION_KEY.items():
            if cond in allowed:
                continue
            tpl_id = key_to_tpl_id.get(key)
            if tpl_id is None:
                continue
            bind.execute(
                insert_pc,
                {
                    "id": str(uuid.uuid4()),
                    "profile_id": prof.id,
                    "template_id": tpl_id,
                    "custom_key": None,
                    "custom_title_ru": None,
                    "custom_kind": None,
                    "custom_prompt_fragment": None,
                    "params": None,
                    "is_hard": True,
                    "sort_order": sort_order,
                },
            )
            sort_order += 10

        # Legacy free-text custom_criteria → one custom criterion row.
        custom_text = (prof.custom_criteria or "").strip()
        if custom_text:
            bind.execute(
                insert_pc,
                {
                    "id": str(uuid.uuid4()),
                    "profile_id": prof.id,
                    "template_id": None,
                    "custom_key": "legacy_custom",
                    "custom_title_ru": "Произвольные критерии (legacy)",
                    "custom_kind": "criterion",
                    "custom_prompt_fragment": custom_text,
                    "params": None,
                    "is_hard": True,
                    "sort_order": sort_order,
                },
            )


def downgrade() -> None:
    # Best-effort: remove legacy_custom rows + auto-derived rows. Since
    # we cannot precisely identify which rows came from this migration,
    # we wipe profile_criteria for profiles that have no
    # profile_listing_evaluations yet — anything older is preserved.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM profile_criteria pc
            WHERE NOT EXISTS (
                SELECT 1 FROM profile_listing_evaluations e
                WHERE e.profile_id = pc.profile_id
            )
            """
        )
    )
    bind.execute(sa.text("DELETE FROM criteria_templates"))
