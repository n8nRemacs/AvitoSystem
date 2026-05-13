# Phase 2.0 — Unified Criteria UI Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переместить редактор feature-rules из глобального sidebar в форму редактирования профиля как таб «Признаки» (3 tabs: Поиск / Признаки / Уведомления), чтобы каждый профиль (включая iPhone 13 без UI-trigger'а) имел доступную настройку правил.

**Architecture:** Чистая UI-перестановка без изменения серверной логики. Существующий HTML/markup `feature_rules.html` выделяется в partial `_partials/feature_rules_section.html` и включается inline в `profiles/form.html`. Sidebar-nav пункт «🛠 Настройки модели» удаляется вместе с уже не нужным запросом `sidebar_active_profile_id`. Tabs реализованы vanilla JS (без новых зависимостей) с поддержкой `localStorage.profile_edit_active_tab` и URL `?tab=...` deep-link. Standalone route `/profiles/{id}/feature-rules` сохраняется для backwards-compat (любые внешние ссылки продолжают работать).

**Tech Stack:** FastAPI + Jinja2 templates, Tailwind 4 (CDN) + DaisyUI 4, vanilla JS, pytest + FastAPI TestClient.

**Spec:** [`docs/superpowers/specs/2026-05-12-unified-criteria-design.md`](../specs/2026-05-12-unified-criteria-design.md) — §7.1 Phase 2.0.

---

## File Structure

| Файл | Тип | Ответственность |
|---|---|---|
| `avito-monitor/app/web/templates/_partials/feature_rules_section.html` | **Create** | Выделенный partial: fieldsets per-section + 3-state переключатели + PATCH JS. Источник истины для markup правил. Используется как standalone-страницей, так и tab «Признаки» формы профиля. |
| `avito-monitor/app/web/templates/profiles/feature_rules.html` | **Modify** | Тонкая обёртка: `extends _layout.html` + `include _partials/feature_rules_section.html`. Для backwards-compat URL. |
| `avito-monitor/app/web/templates/profiles/form.html` | **Modify** | Обёртка существующего markup в tabs (3 секции: Поиск / Признаки / Уведомления). Добавление tab-nav + tab-JS. Передача `rules` контекста для partial. |
| `avito-monitor/app/web/templates/_layout.html` | **Modify** | Удалить пункт `('model-settings', '/profiles/' ~ ... ~ '/feature-rules', '🛠', 'Настройки модели', None)` из `_items` (line 43). |
| `avito-monitor/app/web/routers.py` | **Modify** | (a) `_layout_context` (line 44-65): удалить `sidebar_active_profile_id` query + ключ (мёртвый код после убирания nav). (b) `profile_edit_form` (line 355-375): добавить `rules` + `active_tab` (?tab=-based) в контекст. (c) `profile_new` (line 170-186): добавить `rules={}` + `active_tab='search'` (тот же шаблон). (d) `profile_create` error-rerender (line 314-329): то же что и (c). (e) `feature_rules_page` (line 491-505): `active="model-settings"` → `active="profiles"` (orphan после удаления nav item). |
| `avito-monitor/tests/web/test_profile_edit_tabs.py` | **Create** | Integration-тесты: форма содержит tabs nav, panels со всеми 3 секциями, partial-markup рендерится; standalone `/profiles/{id}/feature-rules` всё ещё работает; sidebar nav больше не содержит «Настройки модели». |

---

## Task 1: Extract feature-rules markup into partial

**Цель:** Чистый refactor — вытащить markup из `feature_rules.html` в partial, чтобы тот же markup переиспользовался из двух точек (standalone и tab формы). Поведение standalone-страницы не меняется.

**Files:**
- Create: `avito-monitor/app/web/templates/_partials/feature_rules_section.html`
- Modify: `avito-monitor/app/web/templates/profiles/feature_rules.html`
- Test: `avito-monitor/tests/web/test_profile_edit_tabs.py` (создаём в этом же task — стартовый failing-test для всего плана)

- [ ] **Step 1: Write baseline characterization test for standalone feature_rules page**

Это не TDD-failing-test, а **baseline characterization** — фиксирует текущее поведение, чтобы refactor не сломал стандартный URL. Step 2 ожидает PASS на текущем коде (до refactor'а).

Создать тестовый файл `avito-monitor/tests/web/test_profile_edit_tabs.py`:

```python
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

    async def _fake_load_lib(session):
        return []  # empty V2 library

    async def _fake_load_state(session, profile_id):
        return {}

    monkeypatch.setattr(svc, "get_profile", _fake_get_profile)
    monkeypatch.setattr(routers.feat_repo, "load_profile_rules", _fake_load_rules)
    monkeypatch.setattr(routers, "_load_criteria_library", _fake_load_lib)
    monkeypatch.setattr(routers, "_load_profile_criteria_state", _fake_load_state)
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
```

- [ ] **Step 2: Run test to verify it passes against current code (baseline)**

Команда:
```bash
cd c:/Projects/Sync/AvitoSystem/avito-monitor
python -m pytest tests/web/test_profile_edit_tabs.py::test_standalone_feature_rules_page_renders_partial -v
```

Expected: PASS — текущий `feature_rules.html` уже содержит все эти маркеры. Это baseline, чтобы убедиться что refactor его не сломает.

Если FAIL — баг в test setup (fake session/user-deps), исправь до перехода к шагу 3.

- [ ] **Step 3: Create partial `_partials/feature_rules_section.html`**

Файл `avito-monitor/app/web/templates/_partials/feature_rules_section.html` — копия body из `feature_rules.html` без `{% extends %}` / `{% block %}`. Конвертируем outer `<form>` в `<div>` чтобы не было nested-form проблем при включении в `profiles/form.html` (где уже есть outer `<form method="post">`):

```html
{# Partial: feature-rules editor section.
   Expects context: profile (SearchProfile), rules (dict[feature_key -> rule_value]),
   defect_taxonomy (global, from templates.env.globals).

   PATCH endpoint: /profiles/{profile_id}/feature-rules/{feature_key}
   JS handles 3-state segmented control with optimistic UI + toast. #}

{% set _SECTION_LABELS = {
    'display':'Дисплей','case':'Корпус','locks':'Блокировки и ПО',
    'sensors':'Датчики','charging':'Зарядка','operability':'Работоспособность',
} %}

<div class="max-w-[1024px]">
  <p class="text-sm text-avito-text-soft mb-6">
    Per-feature правила определяют как лоты бакетятся: 🟢 — желателен ok,
    🔴 — критичный дефект (auto-reject), ⊘ — не учитываем.
  </p>

  <div data-rules-root data-profile-id="{{ profile.id }}">
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
  </div>

  <div data-rules-toast class="fixed bottom-4 right-4 bg-avito-text text-white px-4 py-2 rounded-md text-sm hidden"></div>
</div>

<script>
(function () {
  // Per-root init — каждый data-rules-root получает свой listener.
  // Безопасно если partial окажется на странице дважды (multi-profile или HTMX swap).
  document.querySelectorAll('[data-rules-root]').forEach((root) => {
    if (root.dataset.rulesInitialized === 'true') return;
    root.dataset.rulesInitialized = 'true';

    const pid = root.dataset.profileId;
    // Toast — ближайший data-rules-toast в DOM (sibling от root), fallback на любой на странице.
    const toast =
      root.parentElement && root.parentElement.querySelector('[data-rules-toast]')
      || document.querySelector('[data-rules-toast]');

    const showToast = (msg) => {
      if (!toast) return;
      toast.textContent = msg;
      toast.classList.remove('hidden');
      setTimeout(() => toast.classList.add('hidden'), 2500);
    };

    root.addEventListener('click', async (e) => {
      const btn = e.target.closest('.rule-seg');
      if (!btn || btn.disabled) return;
      const segGroup = btn.parentElement;
      segGroup.querySelectorAll('.rule-seg').forEach(b => { b.disabled = true; });
      try {
        const key = btn.dataset.ruleKey;
        const value = btn.dataset.ruleValue;
        const resp = await fetch(`/profiles/${pid}/feature-rules/${encodeURIComponent(key)}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({rule: value}),
        });
        if (!resp.ok) { showToast('Не удалось сохранить'); return; }
        segGroup.querySelectorAll('.rule-seg').forEach(b => {
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
      } finally {
        segGroup.querySelectorAll('.rule-seg').forEach(b => { b.disabled = false; });
      }
    });
  });
})();
</script>
```

**Что изменилось vs оригинала:**
- `<form id="rules-form">` → `<div data-rules-root>` (нет nested-form, нет дублирующегося ID если partial попадёт дважды).
- `id="rules-toast"` → `data-rules-toast` (тот же риск дубликатов ID).
- Удалён header `<h1>Настройки модели — {{ profile.name }}</h1>` — он остаётся в обёртке `feature_rules.html` (см. шаг 4) и в tab-panel формы.
- JS переписан на **per-root init** через `querySelectorAll('[data-rules-root]').forEach` с пер-элементным флагом `root.dataset.rulesInitialized`. Глобальный `window.__rulesSegInitialized` убран — он бы блокировал инициализацию второго root'а.
- Toast lookup — `root.parentElement.querySelector('[data-rules-toast]')` с fallback'ом на любой `[data-rules-toast]` в документе. Снимает зависимость от глобального ID.

- [ ] **Step 4: Replace `feature_rules.html` with thin wrapper**

Файл `avito-monitor/app/web/templates/profiles/feature_rules.html` — полная замена:

```html
{% extends "_layout.html" %}
{% block page_content %}
<div class="max-w-[1024px]">
  <h1 class="text-2xl font-semibold mb-1 text-avito-text">Настройки модели — {{ profile.name }}</h1>
</div>
{% include "_partials/feature_rules_section.html" %}
{% endblock %}
```

Это сохраняет URL `/profiles/{id}/feature-rules` для backwards-compat.

- [ ] **Step 5: Run baseline test — partial extraction should not break standalone page**

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_standalone_feature_rules_page_renders_partial -v
```

Expected: PASS — все маркеры (`rules-form`, `data-profile-id`, `rule-seg`, `Дисплей`, `Работоспособность`) есть в partial → есть в include → есть в standalone page. Если FAIL — diff проверь, добавил ли ты `data-rules-root` правильно.

- [ ] **Step 6: Add second test — PATCH endpoint still works**

Добавить в `test_profile_edit_tabs.py`:

```python
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
```

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_patch_feature_rule_still_works -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add avito-monitor/app/web/templates/_partials/feature_rules_section.html \
        avito-monitor/app/web/templates/profiles/feature_rules.html \
        avito-monitor/tests/web/test_profile_edit_tabs.py
git commit -m "refactor(feature-rules): extract editor markup into reusable partial

Pure refactor — feature_rules.html content moves to _partials/feature_rules_section.html,
the standalone route /profiles/{id}/feature-rules now thin-wraps the partial. Drops
nested <form> in favor of <div data-rules-root> so the partial is safe to include
inside profiles/form.html (next task wraps the form in tabs).

Tests verify both render-shape and PATCH endpoint behavior unchanged."
```

---

## Task 2: Remove sidebar nav «🛠 Настройки модели» + dead-code cleanup

**Цель:** Sidebar-nav пункт «Настройки модели» больше не нужен — feature-rules переедут в форму профиля (task 3+). Заодно убираем `sidebar_active_profile_id` query из `_layout_context` — он использовался только для этого hardcoded link'а.

**Files:**
- Modify: `avito-monitor/app/web/templates/_layout.html:43`
- Modify: `avito-monitor/app/web/routers.py:54-57, 64`
- Test: `avito-monitor/tests/web/test_profile_edit_tabs.py`

- [ ] **Step 1: Write failing test — sidebar should NOT contain «Настройки модели» link**

Добавить в `test_profile_edit_tabs.py`:

```python
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
```

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_sidebar_no_longer_has_model_settings_nav -v
```

Expected: FAIL — current `_layout.html:43` строит href `/profiles/<id>/feature-rules` и текст «Настройки модели» в nav.

- [ ] **Step 2: Remove `('model-settings', ...)` row from `_items`**

В `avito-monitor/app/web/templates/_layout.html:43` — удалить строку:

```
('model-settings', '/profiles/' ~ (sidebar_active_profile_id or '') ~ '/feature-rules', '🛠', 'Настройки модели', None),
```

После правки строки 36-45 должны быть:

```jinja
        {% set _items = [
            ('dashboard',   '/',                  '📊', 'Дашборд',           None),
            ('profiles',    '/search-profiles',   '🎯', 'Профили поиска',    sidebar_profiles_count),
            ('listings',    '/listings',          '📦', 'Лоты',              sidebar_listings_count),
            ('prices',      '/price-intelligence','💰', 'Ценовая разведка',  None),
            ('reliability', '/reliability',       '🩺', 'Reliability',       None),
            ('logs',        '/logs',              '📜', 'Логи',              None),
            ('settings',    '/settings',          '⚙️',  'Настройки',         None),
        ] %}
```

- [ ] **Step 3: Run test — sidebar removal verified**

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_sidebar_no_longer_has_model_settings_nav -v
```

Expected: PASS.

- [ ] **Step 4: Remove dead `sidebar_active_profile_id` query + fix `active="model-settings"` orphan**

Две связанных правки в `avito-monitor/app/web/routers.py`:

**4a.** В `_layout_context` (line 44-65) — удалить строки 54-57 (запрос на первый profile.id) и строку 64 (передача ключа в context).

**4b.** В `feature_rules_page` (line 491-505, route `/profiles/{id}/feature-rules`) — заменить `active="model-settings"` (строка 502) на `active="profiles"`. Sidebar nav «model-settings» больше нет (4a), поэтому никакая подсветка не сработает. Логически standalone-страница относится к редактированию профиля → подсвечиваем «Профили поиска».

После правки 4a функция выглядит так:

```python
async def _layout_context(
    user: User, session: AsyncSession, active: str
) -> dict[str, Any]:
    """Common variables every _layout-extending page needs."""
    profiles_count_stmt = select(func.count(SearchProfile.id)).where(
        SearchProfile.user_id == user.id
    )
    active_count_stmt = profiles_count_stmt.where(SearchProfile.is_active.is_(True))
    total = (await session.execute(profiles_count_stmt)).scalar_one()
    active_total = (await session.execute(active_count_stmt)).scalar_one()
    return {
        "current_user": user,
        "active": active,
        "sidebar_profiles_count": total,
        "sidebar_active_profiles": active_total,
        "sidebar_listings_count": 0,  # filled by Block 4
    }
```

И правка 4b (`feature_rules_page`):

```python
@router.get("/profiles/{profile_id}/feature-rules", response_class=HTMLResponse)
async def feature_rules_page(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await session.get(SearchProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(404)
    rules = await feat_repo.load_profile_rules(session, profile_id)
    ctx = await _layout_context(user, session, active="profiles")  # was "model-settings"
    ctx["profile"] = profile
    ctx["rules"] = rules
    return templates.TemplateResponse(request, "profiles/feature_rules.html", ctx)
```

- [ ] **Step 5: Verify no other code references `sidebar_active_profile_id`**

```bash
cd c:/Projects/Sync/AvitoSystem/avito-monitor
grep -rn "sidebar_active_profile_id" app/ tests/ 2>/dev/null
```

Expected: пусто (или только matches в spec/plan markdown). Если что-то нашлось в `app/` или `tests/` — добавь правку в этот же task.

- [ ] **Step 6: Run all web tests to verify nothing broke**

```bash
python -m pytest tests/web/ -v
```

Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add avito-monitor/app/web/templates/_layout.html \
        avito-monitor/app/web/routers.py \
        avito-monitor/tests/web/test_profile_edit_tabs.py
git commit -m "refactor(sidebar): drop hardcoded «Настройки модели» nav item

The link was wired to the earliest-created profile per user, leaving any
additional profile (e.g. iPhone 13) without a UI trigger for feature-rules.
Phase 2.0 moves rule editing into the profile edit form as a tab, so the
global nav item is no longer correct.

Also drops the now-dead sidebar_active_profile_id query from _layout_context."
```

---

## Task 3: Add tabs structure to `profiles/form.html`

**Цель:** Обернуть всю форму редактирования профиля в 3-tabs layout:
- **«Поиск»** — все текущие секции formа КРОМЕ Step 7 Notifications (URL, имя, вилки, overlay, LLM-criteria, расписание).
- **«Признаки»** — `{% include _partials/feature_rules_section.html %}` (partial делает свои PATCH-запросы независимо от outer `<form>`).
- **«Уведомления»** — **перемещённый Step 7 markup** (Telegram + Max checkboxes). Per spec §7.1 line 244: «если поля в форме — они переезжают; иначе placeholder». У нас есть → переезжают.

**Архитектура `<form>`:** outer `<form method="post" action="{{ form_action }}">` оборачивает **все 3 panels + submit button** (не один panel). Submit applies изменения из обеих form-наполненных tabs (Поиск + Уведомления) одним POST. Partial в «Признаки» не submit'ит — он PATCH'ит через fetch, конфликта с outer form нет.

**«Опасная зона»** (delete profile, текущие form.html:454-473) — выносится **вне** `<form>` и вне всех `<section data-panel>`, на верхнем уровне `block page_content`. Inline `<form action="/delete">` внутри danger-zone остаётся как сейчас.

**Files:**
- Modify: `avito-monitor/app/web/templates/profiles/form.html`
- Modify: `avito-monitor/app/web/routers.py` — **три** места:
  - `profile_edit_form` (line 355-375) — добавить `rules` + `active_tab` в context.
  - `profile_new` (line 170-186) — добавить `rules={}` + `active_tab='search'` в context (этот же шаблон используется для create).
  - `profile_create` error-rerender (line 314-329) — то же самое (тот же шаблон при ошибке валидации).
- Test: `avito-monitor/tests/web/test_profile_edit_tabs.py`

**Why three routers?** Шаблон `profiles/form.html` рендерится из всех трёх точек. После Task 3 он обращается к `active_tab` (Jinja default'ит на pустую строку при отсутствии) и условно включает partial при `profile and profile.id`. Без правки create-routes — create-page либо упадёт на TemplateError, либо нарисует tabs с ни одним aria-selected='true'.

- [ ] **Step 1: Write failing tests for tabs presence**

Добавить в `test_profile_edit_tabs.py`:

```python
def test_form_edit_renders_three_tabs(client):
    """Phase 2.0 Task 3: profiles/form.html has 3 tabs nav: Поиск / Признаки / Уведомления."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    assert resp.status_code == 200
    body = resp.text
    # Tab navigation
    assert 'role="tablist"' in body
    assert 'data-tab="search"' in body
    assert 'data-tab="features"' in body
    assert 'data-tab="notifications"' in body
    # Tab labels (UI text)
    assert 'Поиск' in body
    assert 'Признаки' in body
    assert 'Уведомления' in body


def test_form_edit_includes_feature_rules_partial(client):
    """Phase 2.0 Task 3: tab «Признаки» content includes _partials/feature_rules_section.html markup."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    assert resp.status_code == 200
    body = resp.text
    # Markup из partial должен быть на странице (внутри tab-panel)
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
    """Phase 2.0 spec §7.1: Step 7 Notifications fields move INTO tab «Уведомления».

    Existing form.html:424-441 has real telegram/max checkboxes — they must be
    inside <section data-panel="notifications">, not the search panel, and the
    'переедут сюда в следующих итерациях' placeholder MUST NOT appear (we have
    real fields, so the placeholder branch from earlier plan revision doesn't
    apply per spec §7.1 line 244).
    """
    resp = client.get(f"/search-profiles/{PROFILE_ID}")
    body = resp.text
    # Locate the notifications panel boundaries
    panel_start = body.index('data-panel="notifications"')
    # Scope to ~2KB after the opening tag (panel content) — adjust if panels grow
    panel_chunk = body[panel_start:panel_start + 2000]
    # Real Step 7 markers must be inside the notifications panel:
    assert 'name="notification_channels"' in panel_chunk
    assert 'value="telegram"' in panel_chunk
    assert 'value="max"' in panel_chunk
    # Placeholder from earlier plan revision must NOT appear anywhere:
    assert 'переедут сюда в следующих итерациях' not in body
    # And these checkboxes must NOT also live inside the search panel
    # (i.e. they were truly MOVED, not duplicated):
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
    # Core field — URL поиска, должен быть в search-panel
    assert 'name="avito_search_url"' in body
    # Имя профиля — core field
    assert 'name="name"' in body
    # Submit button
    assert 'type="submit"' in body


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
    # Tabs nav присутствует
    assert 'data-tab="search"' in body
    assert 'data-tab="features"' in body
    assert 'data-tab="notifications"' in body
    # search tab активный по умолчанию (active_tab default = 'search')
    search_btn_idx = body.index('id="tab-search"')
    snippet = body[max(0, search_btn_idx - 200):search_btn_idx + 200]
    assert 'aria-selected="true"' in snippet
    # «Признаки» panel НЕ содержит partial markup (нет profile.id)
    features_idx = body.index('data-panel="features"')
    features_chunk = body[features_idx:features_idx + 1500]
    assert 'data-rules-root' not in features_chunk
    assert 'rule-seg' not in features_chunk
    # Placeholder-текст есть
    assert 'Сначала создайте профиль' in features_chunk or 'после создания профиля' in features_chunk
```

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_form_edit_renders_three_tabs tests/web/test_profile_edit_tabs.py::test_form_edit_includes_feature_rules_partial tests/web/test_profile_edit_tabs.py::test_form_edit_has_three_tabpanels tests/web/test_profile_edit_tabs.py::test_notifications_tab_moved_existing_fields tests/web/test_profile_edit_tabs.py::test_form_edit_search_form_action_and_key_fields_preserved tests/web/test_profile_edit_tabs.py::test_form_edit_features_panel_visible_when_tab_features tests/web/test_profile_edit_tabs.py::test_create_form_renders_without_partial -v
```

**Note для test_create_form_renders_without_partial:** требуется добавить в fixture `_fake_user_dep` уже мокнут, `_fake_db` — мокнут. Маршрут `/search-profiles/new` вызывает `_layout_context` + `_load_regions` + `_load_criteria_library` — всё уже замокано. Если упадёт — посмотреть на отсутствие нужного monkeypatch'а в fixture.

Expected: ALL FAIL — current form.html не имеет ни tabs ни partial-include. `test_notifications_tab_moved_existing_fields` упадёт на `body.index('data-panel="notifications"')` → ValueError, либо на assert что placeholder есть в текущем коде (он не есть, но и `data-panel` тоже нет — упадёт раньше).

- [ ] **Step 2: Pass `rules` + `active_tab` to all three routes that render `profiles/form.html`**

Шаблон `profiles/form.html` рендерится из трёх routes. Все три нужно обновить, иначе create-page упадёт.

**2a. `profile_edit_form` (line 355-375)** — добавить `rules` и `active_tab` (default из Task 4 Step 2 будет дальше — пока хардкодим `'search'`):

```python
@router.get("/search-profiles/{profile_id}", response_class=HTMLResponse)
async def profile_edit_form(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    ctx = await _layout_context(user, session, active="profiles")
    rules = await feat_repo.load_profile_rules(session, profile.id)
    ctx.update({
        "title": "Редактирование профиля",
        "form_action": f"/search-profiles/{profile.id}",
        "submit_label": "Сохранить изменения",
        "profile": profile,
        "regions": _load_regions(),
        "criteria_library": await _load_criteria_library(session),
        "criteria_state": await _load_profile_criteria_state(session, profile.id),
        "rules": rules,
        "active_tab": "search",  # Task 4 Step 2 заменит на ?tab=-based logic
    })
    return templates.TemplateResponse(request, "profiles/form.html", ctx)
```

**2b. `profile_new` (line 170-186)** — добавить `rules={}` и `active_tab='search'`. Profile=None → partial guard в шаблоне покажет placeholder, rules dict не используется на create-page но передаём для шаблона-безопасности:

```python
@router.get("/search-profiles/new", response_class=HTMLResponse)
async def profile_new(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    ctx = await _layout_context(user, session, active="profiles")
    ctx.update({
        "title": "Новый профиль",
        "form_action": "/search-profiles/new",
        "submit_label": "Создать профиль",
        "profile": None,
        "regions": _load_regions(),
        "criteria_library": await _load_criteria_library(session),
        "criteria_state": {"selected": {}, "custom": []},
        "rules": {},
        "active_tab": "search",
    })
    return templates.TemplateResponse(request, "profiles/form.html", ctx)
```

**2c. `profile_create` error-rerender (line 314-329)** — тот же набор полей, форма перерисовывается на ошибке валидации:

```python
        ctx = await _layout_context(user, session, active="profiles")
        ctx.update({
            "title": "Новый профиль",
            "form_action": "/search-profiles/new",
            "submit_label": "Создать профиль",
            "profile": None,
            "regions": _load_regions(),
            "criteria_library": await _load_criteria_library(session),
            "criteria_state": {"selected": {}, "custom": []},
            "rules": {},
            "active_tab": "search",
            "error": f"Не удалось сохранить профиль: {e}",
        })
        return templates.TemplateResponse(
            request, "profiles/form.html", ctx,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
```

- [ ] **Step 3: Restructure `form.html` into tabs layout**

В `avito-monitor/app/web/templates/profiles/form.html` — реструктурировать всё содержимое `block page_content` (строки 6-475 текущего файла). Изменения:

1. **Outer `<form>` теперь оборачивает все 3 panels + submit + tabs-nav**, а НЕ один panel.
2. **Step 7 Notifications** (текущие строки 424-441 — Telegram + Max checkboxes) **физически перемещается** из tab «Поиск» в tab «Уведомления».
3. **«Опасная зона»** (текущие строки 454-473) — выносится вне `<form>`, в самом конце `block page_content`.
4. **Submit-кнопка** (строки 443-451) остаётся внутри `<form>` но **вне** всех `<section data-panel>` — applies все поля из tabs Поиск + Уведомления.

Целевая структура (показан scaffold, сохраняя существующие fieldset'ы из form.html без изменений их внутренней разметки):

```jinja
{% extends "_layout.html" %}
{% from "_macros.html" import dual_price_range %}

{% block title %}{{ title }} — Avito Monitor{% endblock %}

{% block page_content %}
{# Defensive default: если какой-то route забыл передать active_tab — рисуем search. #}
{% set active_tab = active_tab|default('search') %}
{% set rules = rules|default({}) %}
<div class="max-w-3xl mx-auto">
  <div class="flex items-center gap-3 mb-6">
    <a href="/search-profiles" class="text-sm text-avito-text-soft hover:text-avito-text">← К списку</a>
    <h1 class="text-2xl font-semibold text-avito-text">{{ title }}</h1>
  </div>

  {% if error %}
  <div class="bg-red-50 border border-red-200 text-red-800 rounded-md px-4 py-3 mb-4 text-sm">
    {{ error }}
  </div>
  {% endif %}

  {# Outer form wraps tabs nav + all 3 panels + submit. Partial in tab «Признаки»
     uses PATCH via fetch, not form-submit — no conflict with outer form. #}
  <form method="post" action="{{ form_action }}" class="space-y-5">

    {# ---------- Tab navigation ---------- #}
    <nav role="tablist" aria-label="Разделы профиля"
         class="flex border-b border-avito-border -mx-0 gap-1">
      {% set _tabs = [
          ('search',        'Поиск',        '🔎'),
          ('features',      'Признаки',     '🧩'),
          ('notifications', 'Уведомления',  '🔔'),
      ] %}
      {% for slug, label, icon in _tabs %}
        <button type="button" role="tab"
                data-tab="{{ slug }}"
                aria-selected="{{ 'true' if slug == active_tab else 'false' }}"
                aria-controls="tabpanel-{{ slug }}"
                id="tab-{{ slug }}"
                class="profile-tab px-4 py-2 text-sm font-medium text-avito-text-soft
                       hover:text-avito-text border-b-2 border-transparent
                       aria-selected:text-avito-text aria-selected:border-avito-brand
                       transition-colors">
          <span class="mr-1">{{ icon }}</span>{{ label }}
        </button>
      {% endfor %}
    </nav>

    {# ---------- Tab panel: Поиск ---------- #}
    <section role="tabpanel" data-panel="search" id="tabpanel-search"
             aria-labelledby="tab-search"
             class="space-y-5"
             {% if active_tab != 'search' %}hidden{% endif %}>
      {# ВСЁ существующее содержимое формы КРОМЕ Step 7 Notifications:
         - Step 1: URL поиска / autosearch source (текущие form.html:21-74)
         - Step 2: имя профиля (76-85)
         - Step 3: двойная вилка цен (87-131)
         - Step 4: overlay details (133-169)
         - Step 5: LLM-критерии (171-211)
         - Step 5b: V2 pipeline toggle (213-400)
         - Step 6: расписание (402-422)
         Перенесено сюда без изменений внутренней вёрстки каждого fieldset'а. #}
      ...
    </section>

    {# ---------- Tab panel: Признаки ----------
       Partial требует profile.id (для PATCH endpoint). На create-page (profile=None)
       вместо partial рисуем placeholder — оператор сохранит профиль, потом вернётся. #}
    <section role="tabpanel" data-panel="features" id="tabpanel-features"
             aria-labelledby="tab-features"
             {% if active_tab != 'features' %}hidden{% endif %}>
      {% if profile and profile.id %}
        {% include "_partials/feature_rules_section.html" %}
      {% else %}
        <div class="bg-avito-surface rounded-lg border border-avito-border p-5 text-sm text-avito-text-soft">
          <p>
            Сначала создайте профиль (сохраните настройки в табе «Поиск»). После
            создания вернитесь сюда — здесь будет редактор per-feature правил.
          </p>
        </div>
      {% endif %}
    </section>

    {# ---------- Tab panel: Уведомления ----------
       Перенесённый Step 7 markup (был form.html:424-441). Per spec §7.1 line 244 —
       мы кладём существующие поля сюда, не placeholder. #}
    <section role="tabpanel" data-panel="notifications" id="tabpanel-notifications"
             aria-labelledby="tab-notifications"
             {% if active_tab != 'notifications' %}hidden{% endif %}>
      <section class="bg-avito-surface rounded-lg border border-avito-border p-5 space-y-3">
        <h2 class="text-sm font-semibold text-avito-text">Каналы уведомлений</h2>
        <div class="flex gap-4 text-sm">
          <label class="flex items-center gap-2">
            <input type="checkbox" name="notification_channels" value="telegram"
                   {% if not profile or 'telegram' in (profile.notification_channels or []) %}checked{% endif %}
                   class="rounded">
            <span>Telegram</span>
          </label>
          <label class="flex items-center gap-2 opacity-60">
            <input type="checkbox" name="notification_channels" value="max"
                   {% if profile and 'max' in (profile.notification_channels or []) %}checked{% endif %}
                   class="rounded">
            <span>Max <span class="text-xs text-avito-text-muted">(скоро)</span></span>
          </label>
        </div>
      </section>
    </section>

    {# ---------- Submit row (visible across all tabs) ---------- #}
    <div class="flex justify-between items-center pt-2">
      <a href="/search-profiles" class="px-4 py-2 rounded-md text-sm text-avito-text-soft hover:text-avito-text">
        Отмена
      </a>
      <button type="submit"
              class="px-5 py-2 rounded-md bg-avito-brand text-white text-sm font-medium hover:bg-avito-brand-hover">
        {{ submit_label | default('Сохранить') }}
      </button>
    </div>
  </form>

  {# ---------- Danger zone (OUTSIDE outer form) ---------- #}
  {% if profile %}
  <div class="mt-8 pt-6 border-t border-avito-border-soft">
    <h3 class="text-sm font-semibold text-avito-negative mb-2">Опасная зона</h3>
    <div class="flex items-center justify-between gap-4 bg-red-50 border border-red-200 rounded-md p-4">
      <div class="text-sm text-avito-text">
        <div class="font-medium">Удалить профиль «{{ profile.name }}»</div>
        <div class="text-xs text-avito-text-soft mt-1">
          Лоты и история останутся в БД, но привязка к профилю будет разорвана.
        </div>
      </div>
      <form method="post" action="/search-profiles/{{ profile.id }}/delete"
            onsubmit="return confirm('Удалить профиль «{{ profile.name }}» окончательно?')">
        <button type="submit"
                class="px-4 py-2 rounded-md bg-white border border-avito-negative text-avito-negative text-sm font-medium hover:bg-avito-negative hover:text-white">
          Удалить
        </button>
      </form>
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

**Важно:**
- **Step 7 Notifications физически удаляется из tab «Поиск»** — иначе `test_notifications_tab_moved_existing_fields` упадёт на проверке "не должно быть в search-panel".
- **Submit button общий** для всех tabs. Сейчас при submit формы посылаются все checked-чекboxes из любого panel (даже скрытые `hidden`-секции submit'ятся, hidden — это display:none, а не disabled). Это и есть нужное поведение: оператор может править Поиск и Уведомления в любом порядке, нажать «Сохранить» — POST принесёт все поля.
- `aria-selected="{{ 'true' if slug == active_tab else 'false' }}"` — этот вариант уже учитывает Task 4 server-side (default `active_tab='search'` придёт из routers.py — см. Task 4 Step 2).
- `aria-selected:text-avito-text aria-selected:border-avito-brand` — Tailwind 4 [aria-state variant](https://tailwindcss.com/docs/hover-focus-and-other-states#aria-states). Проверь `package.json` / CDN-URL в base.html на `tailwindcss@4.x` перед стартом. Если v3 — заменить на класс `.tab-active` + JS toggle.
- `hidden` атрибуты на panels — server-side initial state; JS task 4 переключает.

- [ ] **Step 4: Run tests — markup tests should pass**

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_form_edit_renders_three_tabs tests/web/test_profile_edit_tabs.py::test_form_edit_includes_feature_rules_partial tests/web/test_profile_edit_tabs.py::test_form_edit_has_three_tabpanels -v
```

Expected: ALL PASS.

- [ ] **Step 5: Run all web tests to verify nothing broke**

```bash
python -m pytest tests/web/ -v
```

Expected: ALL PASS. Если provider tests показали несовместимость (например, тест который ожидает что form.html НЕ содержит partial-маркеров) — посмотри, нужно ли обновить тест или это реальный regression.

- [ ] **Step 6: Commit**

```bash
git add avito-monitor/app/web/templates/profiles/form.html \
        avito-monitor/app/web/routers.py \
        avito-monitor/tests/web/test_profile_edit_tabs.py
git commit -m "feat(profile-form): restructure edit form into 3-tab layout

Outer <form> now wraps all 3 panels + submit. Tab «Поиск» holds URL,
price ranges, criteria, schedule. Tab «Признаки» includes the partial
on edit-page (PATCH via fetch, independent of outer form). Tab
«Уведомления» receives the MOVED Step 7 markup (Telegram/Max channels)
per spec §7.1 line 244.

Danger zone moves outside outer form. Submit applies fields from any
tab (hidden=display:none does NOT skip form submit). active_tab has
a |default('search') fallback so create-page renders search active.

Create-page (profile=None): tab «Признаки» falls back to a placeholder
'Сначала создайте профиль' message — partial is only included when
profile.id exists. iPhone 13 (and any future profile) gets UI-trigger
for feature-rules via tab «Признаки» on edit — closes the hardcoded
sidebar-nav gap from Phase 1.

profile_edit_form context loads rules via feat_repo.load_profile_rules;
profile_new / profile_create error-rerender pass rules={} and
active_tab='search'."
```

---

## Task 4: Add vanilla-JS tabs activation + localStorage + URL `?tab=` deep-link

**Цель:** Сделать tabs interactive — клик переключает активный panel, состояние сохраняется в `localStorage.profile_edit_active_tab`, URL `?tab=features` авто-активирует panel при загрузке (для deep-link из других страниц / уведомлений). Default — `search`.

**Files:**
- Modify: `avito-monitor/app/web/templates/profiles/form.html` (добавление `<script>`)
- Test: `avito-monitor/tests/web/test_profile_edit_tabs.py`

- [ ] **Step 1: Write failing test — server-side rendering supports `?tab=` parameter**

Логика: даже если основная активация в JS, имеет смысл рендерить `aria-selected="true"` на правильном табе на сервере (улучшает FOUC и SEO-семантику). Server-side читает `?tab=` query parameter.

Добавить в `test_profile_edit_tabs.py`:

```python
def test_form_edit_tab_query_param_marks_features_active(client):
    """Phase 2.0 Task 4: ?tab=features renders features tab with aria-selected='true'."""
    resp = client.get(f"/search-profiles/{PROFILE_ID}?tab=features")
    assert resp.status_code == 200
    body = resp.text
    # The features tab button must have aria-selected="true"
    # The search tab button must NOT be selected
    # Search for the button markup precisely:
    assert 'id="tab-features"' in body
    # We accept either explicit aria-selected="true" on the right tab,
    # or the panel being visible (no hidden attr). Pick one.
    # Server-side approach: aria-selected attribute.
    features_btn_idx = body.index('id="tab-features"')
    # Take the surrounding 200 chars of the button declaration
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
```

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_form_edit_tab_query_param_marks_features_active tests/web/test_profile_edit_tabs.py::test_form_edit_default_tab_is_search tests/web/test_profile_edit_tabs.py::test_form_edit_invalid_tab_falls_back_to_search -v
```

Expected: FAIL — first one fails (no server-side tab handling), второй PASS (default OK by accident — `loop.first` makes search default), третий PASS (same reason).

- [ ] **Step 2: Add server-side initial tab handling**

В `avito-monitor/app/web/routers.py` `profile_edit_form` — добавить чтение query param и валидацию. Найти функцию (~line 355):

```python
@router.get("/search-profiles/{profile_id}", response_class=HTMLResponse)
async def profile_edit_form(
    profile_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    profile = await svc.get_profile(session, user.id, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    ctx = await _layout_context(user, session, active="profiles")
    rules = await feat_repo.load_profile_rules(session, profile.id)
    # Server-side tab selection (?tab=features|notifications|search). Invalid → search.
    requested_tab = request.query_params.get("tab", "search")
    active_tab = requested_tab if requested_tab in ("search", "features", "notifications") else "search"
    ctx.update({
        "title": "Редактирование профиля",
        "form_action": f"/search-profiles/{profile.id}",
        "submit_label": "Сохранить изменения",
        "profile": profile,
        "regions": _load_regions(),
        "criteria_library": await _load_criteria_library(session),
        "criteria_state": await _load_profile_criteria_state(session, profile.id),
        "rules": rules,
        "active_tab": active_tab,
    })
    return templates.TemplateResponse(request, "profiles/form.html", ctx)
```

- [ ] **Step 3: Verify form.html уже использует `active_tab` (no-op после Task 3)**

После моих правок Task 3 Step 3 markup уже рендерит:
- `aria-selected="{{ 'true' if slug == active_tab else 'false' }}"` на каждой tab-кнопке
- `{% if active_tab != 'search' %}hidden{% endif %}` (и аналогично features, notifications) на каждой panel
- `{% set active_tab = active_tab|default('search') %}` в начале `block page_content`

И `profile_edit_form` после Task 3 Step 2 уже передаёт `active_tab: "search"` хардкодом. **Это Step делает только одну правку:** заменить хардкод `"search"` в `profile_edit_form` на ?tab=-парсинг (см. Step 2 ниже). `profile_new` и `profile_create` остаются с `'search'` — на create-page нет смысла deep-link'а к "Признаки" (placeholder), к "Уведомления" в принципе можно но over-engineering для Phase 2.0.

- [ ] **Step 4: Run server-side tab tests**

```bash
python -m pytest tests/web/test_profile_edit_tabs.py::test_form_edit_tab_query_param_marks_features_active tests/web/test_profile_edit_tabs.py::test_form_edit_default_tab_is_search tests/web/test_profile_edit_tabs.py::test_form_edit_invalid_tab_falls_back_to_search -v
```

Expected: ALL PASS.

- [ ] **Step 5: Add tabs JS — click activation, localStorage, URL update**

В `avito-monitor/app/web/templates/profiles/form.html` — добавить `<script>` в самом конце шаблона (перед `{% endblock %}`):

```html
<script>
(function () {
  // Phase 2.0 — profile edit form tabs.
  // Server already rendered correct initial state from ?tab= query param;
  // this script just wires click handlers, localStorage persistence,
  // and URL sync on tab change.
  const STORAGE_KEY = 'profile_edit_active_tab';
  const URL_PARAM = 'tab';
  const VALID = ['search', 'features', 'notifications'];

  const tabs = document.querySelectorAll('[role="tab"][data-tab]');
  const panels = document.querySelectorAll('[role="tabpanel"][data-panel]');
  if (tabs.length === 0 || panels.length === 0) return;

  function activate(name) {
    if (!VALID.includes(name)) return;
    tabs.forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
    panels.forEach(p => {
      if (p.dataset.panel === name) p.removeAttribute('hidden');
      else p.setAttribute('hidden', '');
    });
    try { localStorage.setItem(STORAGE_KEY, name); } catch (e) { /* private mode */ }
    try {
      const url = new URL(window.location.href);
      url.searchParams.set(URL_PARAM, name);
      window.history.replaceState(null, '', url.toString());
    } catch (e) { /* IE / file:// */ }
  }

  // If URL has no ?tab= but localStorage has a remembered tab — restore it on load.
  // (Server already picked 'search' as default in that case.)
  //
  // FOUC trade-off: при cold-load с stored != 'search' юзер увидит вспышку
  // search-panel'а перед переключением (typically < 50ms на initial paint, в
  // практике незаметно). Принимаем сознательно — spec §7.1 требует
  // localStorage-персистентность ("вернулся на форму — попадаешь на тот же tab"),
  // а server без cookie/session storage не знает remembered tab.
  // Альтернатива (cookie-based SSR pick) — over-engineering для Phase 2.0.
  const urlParams = new URLSearchParams(window.location.search);
  if (!urlParams.has(URL_PARAM)) {
    let stored = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) { /* ignore */ }
    if (stored && VALID.includes(stored) && stored !== 'search') {
      activate(stored);
    }
  }

  tabs.forEach(t => {
    t.addEventListener('click', () => activate(t.dataset.tab));
  });
})();
</script>
```

- [ ] **Step 6: Run all web tests**

```bash
python -m pytest tests/web/ -v
```

Expected: ALL PASS. JS не покрыт unit-тестами (нет JS test infra) — будет проверено в Task 6 smoke test.

- [ ] **Step 7: Commit**

```bash
git add avito-monitor/app/web/templates/profiles/form.html \
        avito-monitor/app/web/routers.py \
        avito-monitor/tests/web/test_profile_edit_tabs.py
git commit -m "feat(profile-form): wire tabs JS + ?tab= deep-link + localStorage persistence

Server reads ?tab=features|notifications|search query param (invalid →
search) and renders the right aria-selected + hidden attrs for FOUC-less
initial state.

Client-side JS handles tab clicks, persists active tab to
localStorage.profile_edit_active_tab, and syncs URL via
history.replaceState. On load with no ?tab= query, localStorage value
(if any) takes precedence over server-side default."
```

---

## Task 5: Verify standalone `/profiles/{id}/feature-rules` still works

**Цель:** Sanity check — standalone route не сломался во время refactor'а task 1-4. Не пишем новый тест, прогоняем существующий + проверяем тесты Phase 1 defect-features.

**Files:**
- (none — verification only)

- [ ] **Step 1: Run all web tests + defect_features tests**

```bash
cd c:/Projects/Sync/AvitoSystem/avito-monitor
python -m pytest tests/web/ tests/defect_features/ -v
```

Expected: ALL PASS. Особенно:
- `test_standalone_feature_rules_page_renders_partial` (task 1)
- `test_patch_feature_rule_still_works` (task 1)
- `test_form_edit_*` (tasks 3-4)
- Существующие Phase 1 тесты в `tests/defect_features/` (~37 штук, все должны проходить — мы не трогали parser/compute_bucket/repo).

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ -v --timeout=60
```

Expected: ALL PASS (или те же failures которые были до старта Phase 2.0 — `git stash` и проверь baseline если что-то падает).

- [ ] **Step 3: Manual git status check**

```bash
cd c:/Projects/Sync/AvitoSystem
git status
git log --oneline -5
```

Expected: 4 commits (tasks 1-4), worktree clean. Если есть uncommitted изменения — закоммить или stash.

---

## Task 6: Manual smoke test on local dev server

**Цель:** Phase 2.0 не имеет автоматизированных JS-тестов; reality-check через браузер обязателен. Smoke-сценарий — операторский use case: создать второй профиль (или открыть iPhone 13), настроить feature-rules через новый tab, убедиться что rule сохраняется + recompute toast приходит.

**Files:**
- (none — manual checklist)

- [ ] **Step 1: Start local dev server**

В отдельном терминале:

```bash
cd c:/Projects/Sync/AvitoSystem/avito-monitor
docker compose up -d redis  # если ещё не поднят
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Или, если в проекте есть Makefile target / start script — используй его.

Expected: сервер на http://127.0.0.1:8000, без exception в логах.

- [ ] **Step 2: Login + verify sidebar**

Открой http://127.0.0.1:8000 в браузере, залогинься (см. CLAUDE.md / .env для creds).

Проверь:
- ☑ В сайдбаре нет пункта «🛠 Настройки модели».
- ☑ Все остальные пункты на месте: Дашборд, Профили поиска, Лоты, Ценовая разведка, Reliability, Логи, Настройки.

- [ ] **Step 3: Open existing profile edit page**

Перейди на `/search-profiles`, кликни на любой профиль (например, iPhone 12 PM).

Проверь:
- ☑ Открылась форма редактирования.
- ☑ Под header'ом есть tab-nav с 3 кнопками: 🔎 Поиск (активный, brand-цвет underline), 🧩 Признаки, 🔔 Уведомления.
- ☑ Активный panel — Поиск, видна форма (URL, регион, вилки).
- ☑ Panels Признаки и Уведомления скрыты (DevTools: атрибут `hidden`).

- [ ] **Step 4: Switch to «Признаки» tab**

Кликни на «🧩 Признаки».

Проверь:
- ☑ Поиск-panel скрылся (`hidden`).
- ☑ Признаки-panel показан — таблица 22 фич × 3-state переключатели.
- ☑ URL изменился на `.../search-profiles/{id}?tab=features`.
- ☑ В DevTools → Application → Local Storage: `profile_edit_active_tab` = `features`.
- ☑ Если на этом профиле уже есть rules (iPhone 12 PM имеет 21 правило) — соответствующие кнопки подсвечены `bg-avito-brand-soft font-medium`.

- [ ] **Step 5: Set a feature rule**

Кликни на 🔴 у любой фичи (например, `display.glass_broken`).

Проверь:
- ☑ Все 3 переключателя в этой строке кратковременно `disabled` (визуально не очевидно, можно через DevTools).
- ☑ После ответа сервера — кнопка 🔴 подсветилась, остальные тусклые.
- ☑ Внизу справа toast: «Бакеты: N зелёных / N серых / N отклонено» (если rules.recompute > 0).
- ☑ В Network tab — `PATCH /profiles/{id}/feature-rules/display.glass_broken` → 200.

- [ ] **Step 6: Hard-reload page, verify tab persistence**

F5 на странице (без изменения URL).

Проверь:
- ☑ Tab «Признаки» всё ещё активный (URL `?tab=features` сохранился).
- ☑ Выбранное правило (🔴 на display.glass_broken) подсвечено корректно.

- [ ] **Step 7: Direct deep-link without localStorage**

Открой `/search-profiles/{другой-профиль-id}?tab=features` в incognito (или wipe localStorage).

Проверь:
- ☑ Сразу открылся tab «Признаки» (server-side rendering).
- ☑ В DevTools: panel `search` имеет `hidden`, `features` не имеет.

- [ ] **Step 8: Invalid tab fallback**

Открой `/search-profiles/{id}?tab=garbage`.

Проверь:
- ☑ Открылся tab «Поиск» (fallback).
- ☑ URL остался `?tab=garbage` (server не редиректит, JS не перепишет на load).

- [ ] **Step 9: Tab «Уведомления» — реальные поля + persist через submit**

Кликни на «🔔 Уведомления».

Проверь:
- ☑ Panel показывает **реальные fieldset'ы Telegram/Max** (перенесённый Step 7), а не placeholder-текст.
- ☑ URL изменился на `?tab=notifications`.
- ☑ Текущее значение `notification_channels` подсвечено корректно (telegram checked, max unchecked для дефолтных профилей).
- ☑ Сними галочку с «Telegram», нажми «Сохранить изменения» (submit-кнопка под tabs).
- ☑ После 303 redirect на `/search-profiles?msg=...` → вернись на форму → tab «Уведомления» → telegram unchecked. **Submit-flow работает с полей из любого tab.**
- ☑ Поставь галочку обратно, сохрани — чтобы не оставлять профиль без уведомлений.

- [ ] **Step 9a: Create-page — tabs работают, partial = placeholder**

Открой `/search-profiles/new`.

Проверь:
- ☑ Страница рендерится без ошибок (нет 500 / TemplateError).
- ☑ Тоже 3 tabs: «🔎 Поиск» (активный), «🧩 Признаки», «🔔 Уведомления».
- ☑ Кликни «🧩 Признаки» — показывается placeholder «Сначала создайте профиль...», **не** таблица из 22 фич.
- ☑ Кликни «🔔 Уведомления» — реальные чекboxes Telegram/Max (новый профиль создаётся с дефолтным telegram=checked, см. form.html).
- ☑ Вернись в «🔎 Поиск», введи URL Avito, имя, и сохрани — POST `/search-profiles/new` → 303 на список. Создание работает.

- [ ] **Step 10: Verify with second profile (iPhone 13 / любой new)**

Если есть iPhone 13 профиль (per CONTINUE.md он is_active=False, без rules):
- Открой его edit-страницу.
- Перейди в tab «Признаки».
- Поставь любое правило (например, `locks.icloud_linked` → 🔴).

Проверь:
- ☑ Запрос прошёл (Network 200).
- ☑ После reload правило сохранилось.

Если iPhone 13 нет — пропусти этот шаг. Главное проверено: feature-rules доступен для любого профиля без захардкоженной ссылки.

- [ ] **Step 11: Stop dev server, report**

Останови сервер (Ctrl+C). Если все 10 шагов выше ☑ — Phase 2.0 ready to merge.

Если что-то падает — открой issue / fix-задачу + соответствующий commit.

---

## Self-Review (после правок 2026-05-13)

**Spec coverage:**
- ✅ §7.1 «Удалить sidebar nav» — Task 2.
- ✅ §7.1 «3 tabs (Поиск / Признаки / Уведомления)» — Task 3.
- ✅ §7.1 «localStorage.profile_edit_active_tab» — Task 4 (с осознанным FOUC trade-off).
- ✅ §7.1 «URL `?tab=features` deep-link» — Task 4 + server-side rendering для FOUC.
- ✅ §7.1 «Inline render partial, не iframe» — Task 1 (extract partial) + Task 3 (include в tab).
- ✅ §7.1 line 244 **«если поля в форме — они переезжают»** — Task 3 явно переносит Step 7 Notifications в tab 3 (не placeholder).
- ✅ §8.1 «Smoke test: создать iPhone 13 → tab «Признаки» → выставить rules» — Task 6 Step 10.
- ✅ §8.1 «Metrics: оператор может настроить rules на iPhone 13 без захода в DB?» — Task 6 проверяет именно это.

**Изменения после code-review (2026-05-13):**
- ✅ Task 1 — переименован "failing test" → "baseline characterization test" (Step 1).
- ✅ Task 1 — partial убрал `id="rules-form"`, `id="rules-toast"` → `data-rules-root`, `data-rules-toast` (предотвращение дублирующихся ID).
- ✅ Task 1 — JS partial'а переписан на **per-root init** через `querySelectorAll().forEach` + `root.dataset.rulesInitialized` флаг, вместо глобального `window.__rulesSegInitialized` (безопасно если partial окажется на странице дважды).
- ✅ Task 2 — sidebar тест перенесён с `/` на `/search-profiles/{id}` (FakeSession не поддерживает dashboard-агрегаты); проверка `/feature-rules` ужесточена до regex по `href` (не false-positive на JS-литерал в partial'е).
- ✅ Task 2 — `feature_rules_page` route поменян с `active="model-settings"` на `active="profiles"` (orphan после удаления nav item).
- ✅ Task 3 — **критический фикс create-page:** `profile_new` и `profile_create` error-rerender теперь передают `rules={}` + `active_tab='search'`; шаблон делает `{% set active_tab = active_tab|default('search') %}` и `{% if profile and profile.id %}include partial{% else %}placeholder{% endif %}` в tab «Признаки». Без этого create-page падал бы с TemplateError или рендерил tabs без selected.
- ✅ Task 3 — добавлены тесты: `test_create_form_renders_without_partial`, `test_form_edit_search_form_action_and_key_fields_preserved` (form sanity: action/method/avito_search_url/name), `test_form_edit_features_panel_visible_when_tab_features` (panel `hidden` attr корректность).
- ✅ Task 3 — outer `<form>` теперь оборачивает все 3 panels + submit; danger zone вынесена вне form; Step 7 Notifications физически перемещён из tab «Поиск» в tab «Уведомления».
- ✅ Task 6 — Step 9 переписан под реальные fields (не placeholder); добавлен Step 9a — smoke create-page (tabs работают, partial → placeholder, submit-flow создаёт профиль).

**Placeholder scan:** no «TBD», «implement later», «similar to». Каждый code-блок имеет полный код.

**Type consistency:** PATCH endpoint `/profiles/{id}/feature-rules/{key}` body `{rule: "green|red|ignore"}` consistent во всех testах + JS. Context keys (`rules`, `active_tab`, `profile`, `defect_taxonomy`) consistent между routers.py и templates.

**Scope check:** Phase 2.0 — single subsystem (UI placement), один план — корректный размер. Trade-offs (cold-load FOUC, backwards-compat URL без редиректа, hardcoded `active_tab='search'` на create) задокументированы.

---

**Plan complete and saved to `DOCS/superpowers/plans/2026-05-12-unified-criteria-phase-2.0.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch fresh subagent per task, review between tasks, fast iteration. Хорошо для этого плана: каждая task — изолированный UI-refactor, легко проверить subagent'у.

**2. Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints.

**Which approach?**
