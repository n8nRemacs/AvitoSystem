"""Avito-parameters matcher — short-circuits the LLM when Avito tells us explicitly."""
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
