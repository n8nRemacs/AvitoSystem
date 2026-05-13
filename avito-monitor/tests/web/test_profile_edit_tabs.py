"""Tests for Phase 2.0: feature-rules partial extraction + form tabs."""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import SearchProfile, User
from app.deps import db_session, require_user
from app.main import create_app


PROFILE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _ScalarOne:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value if self._value is not None else 0

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    """Async session double — returns counts=0 for sidebar context."""

    async def execute(self, stmt: Any) -> _ScalarOne:
        return _ScalarOne(value=0)

    async def get(self, model: Any, ident: Any) -> Any:
        if model is SearchProfile and ident == PROFILE_ID:
            p = SearchProfile()
            p.id = PROFILE_ID
            p.user_id = USER_ID
            p.name = "iPhone 12 PM"
            p.avito_search_url = "https://www.avito.ru/test"
            p.is_active = True
            return p
        return None

    async def commit(self) -> None:
        return None


def _fake_user() -> User:
    user = User()
    user.id = USER_ID
    user.username = "owner"
    user.password_hash = "x"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def client(monkeypatch):
    # Mock service-layer + repo so we don't hit the DB
    from app.web import routers
    from app.services import search_profiles as svc

    async def _fake_get_profile(session, user_id, profile_id):
        if profile_id == PROFILE_ID:
            p = SearchProfile()
            p.id = PROFILE_ID
            p.user_id = USER_ID
            p.name = "iPhone 12 PM"
            p.avito_search_url = "https://www.avito.ru/test"
            p.import_source = None
            p.is_active = True
            return p
        return None

    async def _fake_load_rules(session, profile_id):
        return {}  # no rules set

    monkeypatch.setattr(svc, "get_profile", _fake_get_profile)
    monkeypatch.setattr(routers.feat_repo, "load_profile_rules", _fake_load_rules)
    monkeypatch.setattr(routers, "_load_regions", lambda: [])

    app = create_app()
    fake_session = FakeSession()

    async def _fake_db():
        yield fake_session

    async def _fake_user_dep():
        return _fake_user()

    app.dependency_overrides[db_session] = _fake_db
    app.dependency_overrides[require_user] = _fake_user_dep
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_standalone_feature_rules_page_renders_partial(client):
    """Phase 2.0 Task 1: feature_rules.html includes _partials/feature_rules_section.html"""
    resp = client.get(f"/profiles/{PROFILE_ID}/feature-rules")
    assert resp.status_code == 200
    body = resp.text
    # Markup из partial (был в feature_rules.html, теперь в partial). Используем
    # data-rules-root как стабильный hook — id="rules-form" мы убираем, т.к.
    # partial может теоретически попасть на страницу дважды → дубликаты ID.
    assert 'data-rules-root' in body
    assert 'data-profile-id="' in body
    assert 'rule-seg' in body  # 3-state segment class
    # Section legends ОБЯЗАТЕЛЬНО есть
    assert 'Дисплей' in body
    assert 'Работоспособность' in body


def test_patch_feature_rule_still_works(client, monkeypatch):
    """Phase 2.0 Task 1: PATCH endpoint /profiles/{id}/feature-rules/{key} unchanged."""
    from app.web import routers

    upserts = []

    async def _fake_upsert(session, *, profile_id, feature_key, rule):
        upserts.append((str(profile_id), feature_key, rule))

    async def _fake_recompute(session, profile_id):
        return {"green": 0, "grey": 0, "red": 0}

    monkeypatch.setattr(routers.feat_repo, "upsert_profile_rule", _fake_upsert)
    monkeypatch.setattr(routers, "recompute_buckets_for_profile", _fake_recompute)

    resp = client.patch(
        f"/profiles/{PROFILE_ID}/feature-rules/display.glass_broken",
        json={"rule": "red"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "recompute": {"green": 0, "grey": 0, "red": 0}}
    assert upserts == [(str(PROFILE_ID), "display.glass_broken", "red")]


def test_sidebar_no_longer_has_model_settings_nav(client):
    """Phase 2.0 Task 2: sidebar nav removes «Настройки модели» link (moved into profile form tab).

    Тестируем на edit-form, а НЕ на dashboard ("/"). Причины:
    - `_layout.html` отрисовывается на каждой странице с _layout extends, поведение
      одинаковое. Edit-form уже полностью замокана в фикстуре.
    - Dashboard ("/") может делать сложные DB-агрегаты, которые FakeSession не
      поддерживает (`.scalars().all()` и т.п.) — упадёт раньше assertion'ов.

    Проверяем точечно: текст "Настройки модели" не появляется в `<a>` тэгах sidebar.
    НЕ проверяем substring `/feature-rules` — он легитимно есть в JS partial'а
    (PATCH endpoint URL литерально присутствует в template-string `${pid}` после
    включения partial в tab «Признаки» через Task 3).
    """
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    assert resp.status_code == 200
    body = resp.text
    assert 'Настройки модели' not in body, \
        "sidebar nav still contains 'Настройки модели' — should be removed in Phase 2.0"
    # Дополнительная проверка: убедиться что нет sidebar-link именно с feature-rules href.
    # Партиал содержит `/profiles/${pid}/feature-rules/` в JS-литерале — это
    # PATCH endpoint, не href, не link в sidebar. Ищем точнее: href в nav.
    # Допустимо иметь упоминание `/feature-rules` где угодно в теле, но НЕ
    # внутри тэга <a href="..."> в sidebar nav block.
    # Чтобы не цепляться за hand-crafted parsing — проверяем что нигде в body
    # нет точной строки `href="/profiles/` + ... + `/feature-rules"`:
    import re
    assert not re.search(r'href="/profiles/[^"]*/feature-rules"', body), \
        "sidebar still has hardcoded /profiles/<id>/feature-rules href — should be removed"


def test_form_edit_renders_three_tabs(client):
    """Phase 2.0 Task 3: profiles/form.html has 3 tabs nav: Поиск / Признаки / Уведомления."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    assert resp.status_code == 200
    body = resp.text
    assert 'role="tablist"' in body
    assert 'data-tab="search"' in body
    assert 'data-tab="features"' in body
    assert 'data-tab="notifications"' in body
    assert 'Поиск' in body
    assert 'Признаки' in body
    assert 'Уведомления' in body


def test_form_edit_includes_feature_rules_partial(client):
    """Phase 2.0 Task 3: tab «Признаки» content includes _partials/feature_rules_section.html markup."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    assert resp.status_code == 200
    body = resp.text
    assert 'data-rules-root' in body
    assert f'data-profile-id="{PROFILE_ID}"' in body
    assert 'rule-seg' in body


def test_form_edit_has_three_tabpanels(client):
    """Phase 2.0 Task 3: form has 3 <section role='tabpanel'> with right data-panel attrs."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert 'data-panel="search"' in body
    assert 'data-panel="features"' in body
    assert 'data-panel="notifications"' in body


def test_notifications_tab_moved_existing_fields(client):
    """Phase 2.0 spec §7.1: Step 7 Notifications fields move INTO tab «Уведомления»."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    panel_start = body.index('data-panel="notifications"')
    panel_chunk = body[panel_start:panel_start + 2000]
    assert 'name="notification_channels"' in panel_chunk
    assert 'value="telegram"' in panel_chunk
    assert 'value="max"' in panel_chunk
    assert 'переедут сюда в следующих итерациях' not in body
    search_start = body.index('data-panel="search"')
    search_end = body.index('data-panel="features"')
    search_chunk = body[search_start:search_end]
    assert 'name="notification_channels"' not in search_chunk


def test_form_edit_search_form_action_and_key_fields_preserved(client):
    """Phase 2.0 Task 3: outer <form> action/method/avito_search_url не теряются после restructure."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    assert f'action="/search-profiles/{PROFILE_ID}"' in body
    assert 'method="post"' in body
    assert 'name="avito_search_url"' in body
    assert 'name="name"' in body
    assert 'type="submit"' in body


def test_form_edit_tab_query_param_marks_features_active(client):
    """Phase 2.0 Task 4: ?tab=features renders features tab with aria-selected='true'."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}?tab=features")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="tab-features"' in body
    features_btn_idx = body.index('id="tab-features"')
    snippet = body[max(0, features_btn_idx - 200):features_btn_idx + 200]
    assert 'aria-selected="true"' in snippet, "features tab must be aria-selected when ?tab=features"


def test_form_edit_default_tab_is_search(client):
    """Phase 2.0 Task 4: no ?tab= → search tab is default active."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    search_btn_idx = body.index('id="tab-search"')
    snippet = body[max(0, search_btn_idx - 200):search_btn_idx + 200]
    assert 'aria-selected="true"' in snippet


def test_form_edit_invalid_tab_falls_back_to_search(client):
    """Phase 2.0 Task 4: ?tab=invalid → search tab still default."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}?tab=garbage")
    body = resp.text
    search_btn_idx = body.index('id="tab-search"')
    snippet = body[max(0, search_btn_idx - 200):search_btn_idx + 200]
    assert 'aria-selected="true"' in snippet


def test_form_edit_features_panel_visible_when_tab_features(client):
    """Phase 2.0 Task 4: ?tab=features → features panel НЕ имеет hidden, search ИМЕЕТ."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}?tab=features")
    body = resp.text
    features_idx = body.index('id="tabpanel-features"')
    features_snippet = body[features_idx:features_idx + 300]
    assert 'hidden' not in features_snippet, "features panel must NOT be hidden when ?tab=features"
    search_idx = body.index('id="tabpanel-search"')
    search_snippet = body[search_idx:search_idx + 300]
    assert 'hidden' in search_snippet, "search panel must be hidden when ?tab=features"


def test_create_form_renders_without_partial(client):
    """Phase 2.0 Task 3: GET /search-profiles/new (profile=None) рендерится без TemplateError.

    Tab «Признаки» показывает placeholder вместо partial (нет profile.id для PATCH).
    """
    resp = client.get("/search-profiles/new")
    assert resp.status_code == 200
    body = resp.text
    assert 'data-tab="search"' in body
    assert 'data-tab="features"' in body
    assert 'data-tab="notifications"' in body
    search_btn_idx = body.index('id="tab-search"')
    snippet = body[max(0, search_btn_idx - 200):search_btn_idx + 200]
    assert 'aria-selected="true"' in snippet
    features_idx = body.index('data-panel="features"')
    features_chunk = body[features_idx:features_idx + 1500]
    assert 'data-rules-root' not in features_chunk
    assert 'rule-seg' not in features_chunk
    assert 'Сначала создайте профиль' in features_chunk or 'после создания профиля' in features_chunk
