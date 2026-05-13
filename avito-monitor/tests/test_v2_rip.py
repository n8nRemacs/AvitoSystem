"""Phase 2.1 Task 4 — V2 rip verification.

Ensures V2-only symbols are gone AND shared resources still importable.
"""
import pytest


def test_v2_only_models_gone():
    """V2-only model classes no longer importable from app.db.models."""
    from app.db import models

    assert not hasattr(models, "CriteriaTemplate")
    assert not hasattr(models, "ProfileCriterion")
    assert not hasattr(models, "ProfileListingEvaluation")


def test_shared_llm_analysis_kept():
    """LLMAnalysis remains — used by /llm-budget + Price Intelligence cache."""
    from app.db.models import LLMAnalysis  # noqa: F401


def test_v2_evaluate_listing_method_gone():
    """LLMAnalyzer.evaluate_listing was V2-only; removed in Phase 2.1."""
    from app.services.llm_analyzer import LLMAnalyzer

    assert not hasattr(LLMAnalyzer, "evaluate_listing")
    assert not hasattr(LLMAnalyzer, "_eval_batch")
    assert not hasattr(LLMAnalyzer, "_eval_one_criterion")


def test_compare_to_reference_kept():
    """Price Intelligence (Block 7) — KEEP."""
    from app.services.llm_analyzer import LLMAnalyzer

    assert hasattr(LLMAnalyzer, "compare_to_reference")


def test_seller_dialog_functions_kept():
    """seller_dialog module-level functions — KEEP."""
    from app.services.llm_analyzer import (
        detect_yes_selling,
        formulate_question,
        parse_topic_answer,
        formulate_recap,
        parse_seller_agreement,
    )
    # Just import — actual behavior tested elsewhere


def test_llm_cache_still_active():
    """DBLLMCache uses llm_analyses table — KEEP active."""
    from app.services.llm_cache import DBLLMCache
    # Confirm it's not a stub — should have async get/put methods
    assert callable(getattr(DBLLMCache, "get", None))
    assert callable(getattr(DBLLMCache, "put", None))


def test_llm_budget_still_active():
    """llm_budget.assert_budget uses llm_analyses — KEEP active."""
    from app.services.llm_budget import assert_budget, LLMBudgetExceeded
    # Just confirm import works


def test_evaluate_listing_task_survives():
    """Task wrapper kept (polling.py imports it); body refactored to Phase 1."""
    from app.tasks.analysis import evaluate_listing
    # It's a TaskIQ task — should have .kiq attribute
    assert hasattr(evaluate_listing, "kiq")


def test_profile_listing_bucket_kept():
    """profile_listings.bucket — KEEP (Phase 1 writes/reads)."""
    from app.db.models import ProfileListing

    assert hasattr(ProfileListing, "bucket")


def test_v2_columns_removed_from_search_profile():
    """search_profiles V2-only columns gone from model."""
    from app.db.models import SearchProfile

    for col in ("evaluate_strategy", "confidence_threshold", "criteria_set_hash", "bucket_routing"):
        assert not hasattr(SearchProfile, col), f"{col} should be removed"
