"""Phase 2.1 Task 5: V2 UI sections removed from profile form."""
from __future__ import annotations

import re

import pytest

# client fixture provided via tests/web/conftest.py


def test_form_edit_no_v2_llm_criteria_section(client):
    """Phase 2.1 Task 5: «LLM-критерии и фильтр состояния» section removed."""
    from tests.web.test_profile_edit_tabs import PROFILE_ID
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert "LLM-критерии и фильтр состояния" not in body
    assert "Допустимые состояния" not in body
    assert "Произвольные критерии (естественный язык)" not in body
    assert 'name="custom_criteria"' not in body
    assert 'name="allowed_conditions"' not in body
    assert 'name="analyze_photos"' not in body


def test_form_edit_no_v2_pipeline_section(client):
    """Phase 2.1 Task 5: «V2 пайплайн (флаг-based, экспериментальный)» section removed."""
    from tests.web.test_profile_edit_tabs import PROFILE_ID
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert "V2 пайплайн" not in body
    assert "Использовать V2 пайплайн вместо ADR-010" not in body
    assert "Стратегия LLM-вызовов" not in body
    assert "Порог уверенности" not in body
    assert 'name="enable_v2"' not in body
    assert 'name="evaluate_strategy"' not in body
    assert 'name="confidence_threshold"' not in body


def test_form_edit_no_v2_library_criteria(client):
    """Phase 2.1 Task 5: V2 library section (Жёсткие критерии / Info-поля) removed."""
    from tests.web.test_profile_edit_tabs import PROFILE_ID
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert "Жёсткие критерии" not in body
    assert "Info-поля (LLM-извлечение)" not in body
    assert "Info-поля (из параметров объявления)" not in body
    assert 'name="criteria_template_keys"' not in body


def test_form_edit_search_tab_remains_intact(client):
    """Phase 2.1 Task 5: Поиск tab still has core fields after V2 rip."""
    from tests.web.test_profile_edit_tabs import PROFILE_ID
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert 'name="avito_search_url"' in body
    assert 'name="name"' in body
    assert 'name="alert_min_price"' in body
    assert 'name="poll_interval_minutes"' in body
    assert 'data-tab="search"' in body
    assert 'data-tab="features"' in body
    assert 'data-tab="notifications"' in body
    assert 'name="notification_channels"' in body
