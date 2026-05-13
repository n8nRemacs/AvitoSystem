"""Tests for compute_bucket — pure deterministic function."""
from app.services.defect_features.bucket import compute_bucket


def test_red_flag_confirmed_defect_short_circuits():
    bucket, reason = compute_bucket(
        features={"locks.icloud_linked": "defect", "display.glass_broken": "ok"},
        rules={"locks.icloud_linked": "red", "display.glass_broken": "green"},
    )
    assert bucket == "red"
    assert reason == "locks.icloud_linked"


def test_green_flag_unknown_yields_green():
    """Post-F2: parser-emitted 'unknown' counts as not-a-defect, not blocker."""
    bucket, reason = compute_bucket(
        features={"display.glass_broken": "unknown"},
        rules={"display.glass_broken": "green"},
    )
    assert bucket == "green"
    assert reason is None


def test_red_flag_unknown_yields_green_not_red():
    """Post-F2: explicit 'unknown' on red-rule does NOT block green.
    Only confirmed defects can move bucket; absence-of-positive is acceptable."""
    bucket, _ = compute_bucket(
        features={"locks.icloud_linked": "unknown"},
        rules={"locks.icloud_linked": "red"},
    )
    assert bucket == "green"


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


def test_missing_feature_yields_grey():
    """Parser hasn't filled this rule's feature at all (None default).
    Distinct from explicit state='unknown' — this signals «never analyzed»."""
    bucket, reason = compute_bucket(
        features={},
        rules={"display.glass_broken": "green"},
    )
    assert bucket == "grey"
    assert reason == "display.glass_broken"


def test_partial_features_with_one_missing_yields_grey():
    """All other rules covered, but one rule has no feature row → grey."""
    bucket, _ = compute_bucket(
        features={"display.glass_broken": "ok"},
        rules={"display.glass_broken": "green", "locks.icloud_linked": "red"},
    )
    assert bucket == "grey"


def test_all_unknown_yields_green():
    """Fully populated by parser but every state is 'unknown' → green.
    This is the post-F2 fix: LLM saw the listing and reported no defects."""
    bucket, _ = compute_bucket(
        features={
            "locks.icloud_linked": "unknown",
            "display.glass_broken": "unknown",
            "operability.no_boot": "unknown",
        },
        rules={
            "locks.icloud_linked": "red",
            "display.glass_broken": "green",
            "operability.no_boot": "red",
        },
    )
    assert bucket == "green"


def test_unknown_with_one_red_defect_still_red():
    """Confirmed defect on red rule wins even if rest are unknown."""
    bucket, reason = compute_bucket(
        features={
            "locks.icloud_linked": "defect",
            "display.glass_broken": "unknown",
        },
        rules={"locks.icloud_linked": "red", "display.glass_broken": "green"},
    )
    assert bucket == "red"
    assert reason == "locks.icloud_linked"


def test_no_rules_at_all_yields_green():
    bucket, _ = compute_bucket(features={"display.glass_broken": "defect"}, rules={})
    assert bucket == "green"
