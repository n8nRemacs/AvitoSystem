"""Phase 2.1 Task 4: V2 code rip verification."""
from __future__ import annotations

import os


def test_no_v2_model_files():
    """V2 model files removed from app.db.models."""
    models_dir = os.path.join(
        os.path.dirname(__file__), "..", "app", "db", "models"
    )
    files = set(os.listdir(models_dir))
    assert "criteria_template.py" not in files
    assert "profile_criteria.py" not in files
    assert "profile_listing_evaluation.py" not in files
    assert "llm_analysis.py" not in files


def test_no_v2_model_imports():
    """Importing app.db.models does not expose V2 names."""
    import app.db.models as m
    for forbidden in (
        "CriteriaTemplate",
        "ProfileCriterion",
        "LLMAnalysis",
        "ProfileListingEvaluation",
    ):
        assert not hasattr(m, forbidden), f"V2 model {forbidden} still exposed"


def test_no_v2_prompts():
    """V2 prompt files removed."""
    prompts_dir = os.path.join(
        os.path.dirname(__file__), "..", "app", "prompts"
    )
    files = set(os.listdir(prompts_dir))
    assert "evaluate_criterion.md" not in files
    assert "evaluate_listing_batch.md" not in files
    assert "extract_info.md" not in files


def test_no_v2_yaml():
    """V2 criteria_templates.yaml removed."""
    data_dir = os.path.join(
        os.path.dirname(__file__), "..", "app", "data"
    )
    assert "criteria_templates.yaml" not in os.listdir(data_dir)


def test_no_v2_llm_methods_on_analyzer():
    """LLMAnalyzer class no longer has V2 evaluate methods."""
    from app.services.llm_analyzer import LLMAnalyzer
    for forbidden in (
        "evaluate_listing",
        "_eval_batch",
        "_eval_one_criterion",
        "_eval_info_batch",
        "_cache_key_for_criterion",
        "_cache_key_for_info_llm",
        "_fallback_unknown_for_specs",
    ):
        assert not hasattr(LLMAnalyzer, forbidden), \
            f"V2 method {forbidden} still on LLMAnalyzer"


def test_compare_to_reference_preserved():
    """Price Intelligence kept."""
    from app.services.llm_analyzer import LLMAnalyzer
    assert hasattr(LLMAnalyzer, "compare_to_reference")
    assert hasattr(LLMAnalyzer, "_cache_key_for_compare")


def test_seller_dialog_functions_preserved():
    """seller_dialog LLM dispatchers kept."""
    from app.services import llm_analyzer
    for name in (
        "detect_yes_selling",
        "formulate_question",
        "parse_topic_answer",
        "formulate_recap",
        "parse_seller_agreement",
    ):
        assert hasattr(llm_analyzer, name), f"seller_dialog {name} missing"
