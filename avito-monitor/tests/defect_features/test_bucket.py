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
