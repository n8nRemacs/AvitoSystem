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


# Old flat key → (new_dotted_key, invert_state). Inversions (e.g. icloud_unlinked
# ='no defect when ok' → icloud_linked='ok when not linked') change semantic;
# state values are reset to 'pending' to force re-ask.
RENAME_MAP = {
    "replaced_display":       ("display.replaced",         False),
    "broken_glass":           ("display.glass_broken",     False),
    "display_stains_stripes": ("display.stains_stripes",   False),
    "broken_back":            ("case.back_broken",         False),
    "face_id_works":          ("sensors.face_id",          True),
    "icloud_unlinked":        ("locks.icloud_linked",      True),
    "charging_stability":     ("charging.unstable",        True),
}

# Keys removed entirely in the new taxonomy.
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
        sa.UniqueConstraint("listing_id", "feature_key",
                            name="uq_listing_features_listing_key"),
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

    # 3. profile_listings.rejected_reason (idempotent — column may already exist).
    bind = op.get_bind()
    col_exists = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='profile_listings' AND column_name='rejected_reason'"
    )).first()
    if not col_exists:
        op.add_column("profile_listings",
                      sa.Column("rejected_reason", sa.Text, nullable=True))

    # 4. Rename existing dialog_topics keys + cascade.
    for old, (new, _invert) in RENAME_MAP.items():
        op.execute(sa.text(
            "UPDATE dialog_topics SET key = :new WHERE key = :old"
        ).bindparams(new=new, old=old))
        op.execute(sa.text(
            "UPDATE seller_dialog_topics SET topic_key = :new WHERE topic_key = :old"
        ).bindparams(new=new, old=old))
        op.execute(sa.text(
            "UPDATE profile_dialog_topics SET topic_key = :new WHERE topic_key = :old"
        ).bindparams(new=new, old=old))

    # 5. Invert state for keys whose semantic flipped — reset to 'pending'.
    invert_keys = [v[0] for v in RENAME_MAP.values() if v[1]]
    if invert_keys:
        op.execute(sa.text(
            "UPDATE seller_dialog_topics SET status = 'pending', answer_text = NULL, "
            "answer_msg_id = NULL, answered_at = NULL "
            "WHERE topic_key = ANY(:keys) AND status = 'answered'"
        ).bindparams(keys=invert_keys))

    # 6. Drop removed keys from library + links + per-dialog rows.
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
    # NOTE: We intentionally do NOT auto-link new feature keys into
    # profile_dialog_topics. In Phase 1 onwards, feature gating per profile
    # is driven by the new profile_feature_rules table (rule != 'ignore').
    # profile_dialog_topics remains for the legacy Phase B dialog-topic flow,
    # and the operator opts each feature into a survey explicitly via the
    # setup-drawer (Phase 2). See spec §6 + §10.1 for rationale.
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
    # rejected_reason + renamed dialog_topics left as-is (downgrade is dev-only)
