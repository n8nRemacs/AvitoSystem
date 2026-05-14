# Defect Catalog Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть два gap'а Project A (русификация UI + CRUD UI для device/feature nodes) одной веткой `feat/defect-catalog`, чтобы стать feature-complete перед merge в `main`.

**Architecture:** Один Jinja-filter `severity_ru` для translation `block/info/ask/skip` → русские лейблы (DB-значения не меняются). Общий партиал `node_form.html` для inline add/edit форм device+feature, 6 новых GET-routes возвращают этот партиал как HTMX-fragment. Tree-партиалы получают `[+][✏][🗑]` icon-кнопки рядом с каждой нодой; `hx-confirm` HTMX-feature даёт native browser confirm() при delete без своего JS.

**Tech Stack:** FastAPI 0.115 + Jinja2 + HTMX 1.x + pytest + fastapi.testclient. Все правки в `avito-monitor/`.

**Spec:** `DOCS/superpowers/specs/2026-05-13-defect-catalog-polish.md` (commit dae4b83).

---

## File Structure

| Файл | Что делает |
|---|---|
| `avito-monitor/app/web/defects.py` | Регистрирует Jinja-filter `severity_ru`. Добавляет 6 новых GET-routes для form-fragments — каждый возвращает партиал `node_form.html` без layout extension. |
| `avito-monitor/app/web/templates/defects/_partials/node_form.html` | **NEW.** Общий партиал inline-формы для add/edit, device/feature. Параметризован `mode`, `kind`, `parent_id`/`node_id`, `prefill`. |
| `avito-monitor/app/web/templates/defects/_partials/binding_row.html` | Применяет `severity_ru` filter к defect_action/unknown_action в display + `<option>`-labels. Меняет «← inherited from ancestor» → «← унаследовано», «← set here» → «← задано здесь», «Override» → «Задать здесь». |
| `avito-monitor/app/web/templates/defects/_partials/device_tree.html` | Каждая нода получает inline-flex с `[+][✏][🗑]` icon-кнопками. `[+]` → hx-get form-add-fragment под нодой. `[✏]` → hx-get form-edit-fragment вместо ноды. `[🗑]` → hx-delete с `hx-confirm`. |
| `avito-monitor/app/web/templates/defects/_partials/feature_tree.html` | То же для feature-nodes, с дополнительным kind. |
| `avito-monitor/app/web/templates/defects/devices.html` | Добавляет кнопку «+ Добавить корневое устройство» под tree + div `#device-form-mount` для swap form-fragment'a. |
| `avito-monitor/app/web/templates/defects/catalog.html` | То же для catalog: «+ Добавить корневой признак» + `#feature-form-mount`. |
| `avito-monitor/tests/web/test_defects_routes.py` | +7 тестов: severity_ru filter, render-form fragments (3 device + 3 feature), binding_row uses ru labels, tree renders action icons. |

---

## Task 1 — Jinja-filter `severity_ru` + регистрация

**Files:**
- Modify: `avito-monitor/app/web/defects.py` (add filter function + register)
- Test: `avito-monitor/tests/web/test_defects_routes.py` (add unit-test)

- [ ] **Step 1: Add failing test for filter**

Edit `avito-monitor/tests/web/test_defects_routes.py` — добавить в конце файла:

```python
def test_severity_ru_filter():
    """Unit-test severity_ru filter — maps DB values to Russian display labels."""
    from app.web.defects import severity_ru
    assert severity_ru("block") == "блок"
    assert severity_ru("info") == "инфо"
    assert severity_ru("ask") == "уточнить"
    assert severity_ru("skip") == "пропустить"
    # Unknown values pass through unchanged (defensive)
    assert severity_ru("unknown") == "unknown"
    assert severity_ru("") == ""
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
cd /c/Projects/Sync/AvitoSystem/avito-monitor
python -m pytest tests/web/test_defects_routes.py::test_severity_ru_filter -v
```

Expected: FAIL with `ImportError: cannot import name 'severity_ru' from 'app.web.defects'`.

- [ ] **Step 3: Implement filter + register**

В `avito-monitor/app/web/defects.py` ПОСЛЕ строки `templates = Jinja2Templates(directory=TEMPLATES_DIR)` (line 40):

```python
_SEVERITY_RU = {
    "block": "блок",
    "info": "инфо",
    "ask": "уточнить",
    "skip": "пропустить",
}


def severity_ru(value: str) -> str:
    """Translate DB severity values (block/info/ask/skip) to Russian UI labels.
    Unknown values pass through unchanged for defensive rendering."""
    return _SEVERITY_RU.get(value, value)


templates.env.filters["severity_ru"] = severity_ru
```

- [ ] **Step 4: Run test, expect PASS**

```bash
python -m pytest tests/web/test_defects_routes.py::test_severity_ru_filter -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/defects.py avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): add severity_ru Jinja-filter for Russian UI labels"
```

---

## Task 2 — Русификация `binding_row.html`

**Files:**
- Modify: `avito-monitor/app/web/templates/defects/_partials/binding_row.html`
- Test: `avito-monitor/tests/web/test_defects_routes.py`

- [ ] **Step 1: Add failing test for ru-labels in binding_row**

В `tests/web/test_defects_routes.py` добавить:

```python
def test_binding_row_uses_ru_labels(defects_client, monkeypatch):
    """GET /defects/devices/{id} renders bindings with Russian severity labels
    + inherited/set-here/Override translations."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.services.defect_catalog.resolver import ResolvedBinding
    from app.web import defects as defects_mod

    fake_dev_id = _uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_feat_id = _uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    fake_bind_id = _uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    fake_device = DeviceNodeRow(
        id=fake_dev_id, parent_id=None, slug="phone",
        title="Phone", kind=None, sort_order=0,
    )
    # Two bindings: one inherited (block/ask), one set-here (info/skip)
    inherited = ResolvedBinding(
        binding_id=fake_bind_id, feature_node_id=fake_feat_id,
        feature_path=["Корпус", "Midframe сломан"],
        defect_action="block", unknown_action="ask",
        inherited_from=_uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
    )
    set_here = ResolvedBinding(
        binding_id=_uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        feature_node_id=fake_feat_id,
        feature_path=["Дисплей", "Стекло разбито"],
        defect_action="info", unknown_action="skip",
        inherited_from=None,
    )

    async def _fake_get_device_node(session, nid):
        return fake_device

    async def _fake_resolve(session, device_id):
        return [inherited, set_here]

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get_device_node)
    monkeypatch.setattr(defects_mod, "resolve_applicable_defects", _fake_resolve)

    resp = defects_client.get(f"/defects/devices/{fake_dev_id}")
    assert resp.status_code == 200, resp.text[:500]
    # Inherited display uses ru labels
    assert "блок" in resp.text
    assert "уточнить" in resp.text
    # Set-here dropdowns also use ru in option labels
    assert "инфо" in resp.text
    assert "пропустить" in resp.text
    # Translated annotations
    assert "← унаследовано" in resp.text
    assert "← задано здесь" in resp.text
    # Override button translated
    assert "Задать здесь" in resp.text
```

(Шейп `ResolvedBinding` — dataclass из `resolver.py`. Если field name отличается — сверь перед стартом теста.)

- [ ] **Step 2: Verify ResolvedBinding shape**

```bash
grep -n "class ResolvedBinding\|^@dataclass" avito-monitor/app/services/defect_catalog/resolver.py | head -10
```

Если поля отличаются от `(binding_id, feature_node_id, feature_path, defect_action, unknown_action, inherited_from)` — поправь test fixture.

- [ ] **Step 3: Run test, expect FAIL on ru-assertions**

```bash
python -m pytest tests/web/test_defects_routes.py::test_binding_row_uses_ru_labels -v
```

Expected: FAIL (либо `"блок" not in resp.text` либо `"← унаследовано" not in resp.text`).

- [ ] **Step 4: Edit binding_row.html — apply ru-mapping**

Заменить файл `avito-monitor/app/web/templates/defects/_partials/binding_row.html` целиком:

```jinja
{# Context: b (ResolvedBinding-shaped), target_device_id (uuid str). #}
<div class="flex items-start gap-3 py-2 border-b border-avito-border-soft text-sm"
     id="binding-{{ b.binding_id }}">
  <div class="flex-1">
    <div class="font-medium">{{ b.feature_path | join(' / ') }}</div>

    {% if b.inherited_from %}
      <div class="mt-1 text-xs">
        При находке: <strong>{{ b.defect_action | severity_ru }}</strong>
        · Если неясно: <strong>{{ b.unknown_action | severity_ru }}</strong>
      </div>
      <div class="mt-1 text-xs text-avito-text-soft">← унаследовано</div>
    {% else %}
      <div class="mt-1 flex gap-3 items-center text-xs">
        <label>При находке:
          <select hx-patch="/defects/bindings/{{ b.binding_id }}"
                  hx-target="#binding-{{ b.binding_id }}"
                  hx-swap="outerHTML"
                  hx-vals='{"target_device_id": "{{ target_device_id }}"}'
                  name="defect_action"
                  class="border rounded px-1">
            <option value="block" {% if b.defect_action == 'block' %}selected{% endif %}>{{ 'block' | severity_ru }}</option>
            <option value="info"  {% if b.defect_action == 'info'  %}selected{% endif %}>{{ 'info'  | severity_ru }}</option>
          </select>
        </label>
        <label>Если неясно:
          <select hx-patch="/defects/bindings/{{ b.binding_id }}"
                  hx-target="#binding-{{ b.binding_id }}"
                  hx-swap="outerHTML"
                  hx-vals='{"target_device_id": "{{ target_device_id }}"}'
                  name="unknown_action"
                  class="border rounded px-1">
            <option value="ask"  {% if b.unknown_action == 'ask'  %}selected{% endif %}>{{ 'ask'  | severity_ru }}</option>
            <option value="skip" {% if b.unknown_action == 'skip' %}selected{% endif %}>{{ 'skip' | severity_ru }}</option>
          </select>
        </label>
      </div>
      <div class="mt-1 text-xs text-avito-text-soft">← задано здесь</div>
    {% endif %}
  </div>

  {% if b.inherited_from %}
    <form hx-post="/defects/bindings" hx-target="#binding-{{ b.binding_id }}" hx-swap="outerHTML">
      <input type="hidden" name="device_node_id"  value="{{ target_device_id }}">
      <input type="hidden" name="feature_node_id" value="{{ b.feature_node_id }}">
      <input type="hidden" name="defect_action"   value="{{ b.defect_action }}">
      <input type="hidden" name="unknown_action"  value="{{ b.unknown_action }}">
      <button type="submit"
              class="text-xs text-avito-text-soft hover:text-avito-green">Задать здесь</button>
    </form>
  {% else %}
    <button hx-delete="/defects/bindings/{{ b.binding_id }}"
            hx-target="#binding-{{ b.binding_id }}"
            hx-swap="delete"
            class="text-xs text-avito-text-soft hover:text-red-600">Удалить</button>
  {% endif %}
</div>
```

- [ ] **Step 5: Run test, expect PASS**

```bash
python -m pytest tests/web/test_defects_routes.py::test_binding_row_uses_ru_labels -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/templates/defects/_partials/binding_row.html avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): Russify binding_row labels + inherited/set-here/Override"
```

---

## Task 3 — Партиал `node_form.html`

**Files:**
- Create: `avito-monitor/app/web/templates/defects/_partials/node_form.html`

(Без отдельного теста — партиал тестируется через route-тесты в Tasks 4-5.)

- [ ] **Step 1: Create node_form.html**

Создать `avito-monitor/app/web/templates/defects/_partials/node_form.html`:

```jinja
{# Inline form for add/edit device or feature node.

   Context:
     mode       : 'add' or 'edit'
     kind       : 'device' or 'feature' — chooses endpoint prefix /devices vs /catalog
     parent_id  : UUID str (for mode=add) or None (root)
     node_id    : UUID str (for mode=edit)
     prefill    : dict with slug/title/[feature_kind]/[prompt_hint] for edit prefill
#}
{% set endpoint_prefix = '/defects/devices' if kind == 'device' else '/defects/catalog' %}
{% set tree_target    = '#device-tree'    if kind == 'device' else '#feature-tree' %}

{% if mode == 'add' %}
  {% set hx_method = 'hx-post' %}
  {% set hx_url    = endpoint_prefix %}
{% else %}
  {% set hx_method = 'hx-patch' %}
  {% set hx_url    = endpoint_prefix + '/' + node_id + '/edit' %}
{% endif %}

<form id="node-form-inline"
      {{ hx_method }}="{{ hx_url }}"
      hx-target="{{ tree_target }}"
      hx-swap="innerHTML"
      class="ml-4 my-1 p-2 bg-avito-elev rounded text-xs flex flex-wrap gap-2 items-center">
  {% if mode == 'add' and parent_id %}
    <input type="hidden" name="parent_id" value="{{ parent_id }}">
  {% endif %}

  {% if kind == 'feature' and mode == 'add' %}
    <label>kind:
      <select name="kind" class="border rounded px-1">
        <option value="section">section</option>
        <option value="defect" selected>defect</option>
      </select>
    </label>
  {% endif %}

  <label>slug:
    <input type="text" name="slug" required pattern="[a-z][a-z0-9_]*"
           value="{{ prefill.slug if prefill else '' }}"
           class="border rounded px-1 w-32">
  </label>
  <label>title:
    <input type="text" name="title" required
           value="{{ prefill.title if prefill else '' }}"
           class="border rounded px-1 w-48">
  </label>

  {% if kind == 'feature' %}
    <label>prompt_hint:
      <input type="text" name="prompt_hint"
             value="{{ prefill.prompt_hint if prefill else '' }}"
             class="border rounded px-1 w-48">
    </label>
  {% endif %}

  <button type="submit"
          class="px-2 py-0.5 bg-avito-brand text-white rounded">ОК</button>
  <button type="button"
          hx-get="{{ '/defects/devices/cancel-form' if kind == 'device' else '/defects/catalog/cancel-form' }}"
          hx-target="this" hx-swap="outerHTML"
          class="px-2 py-0.5 border rounded">Отмена</button>
</form>
```

- [ ] **Step 2: Commit (template-only, no test yet)**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/templates/defects/_partials/node_form.html
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): node_form.html — common inline form partial"
```

---

## Task 4 — GET form-fragment routes для device + cancel

**Files:**
- Modify: `avito-monitor/app/web/defects.py` (add 4 routes — new-root, new-child, edit, cancel-form)
- Test: `avito-monitor/tests/web/test_defects_routes.py`

**Важно:** routes для literal-segments (`/devices/new`, `/devices/cancel-form`) должны быть **зарегистрированы выше** существующего `/devices/{device_id}` route. FastAPI сканирует в порядке регистрации; literal должен совпасть первым. Существующий `/devices/{device_id}` сейчас на ~line 108. Новые routes вставить **до** строки `@router.get("/devices/{device_id}"...`.

- [ ] **Step 1: Add 3 failing tests**

В `tests/web/test_defects_routes.py`:

```python
def test_get_device_form_add_root(defects_client):
    """GET /defects/devices/new → 200, partial form, hx-post target /defects/devices."""
    resp = defects_client.get("/defects/devices/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/devices"' in resp.text
    # No parent_id hidden input for root
    assert 'name="parent_id"' not in resp.text


def test_get_device_form_add_child(defects_client):
    """GET /defects/devices/{parent_id}/new → 200, parent_id hidden input present."""
    parent_id = "11111111-1111-1111-1111-111111111111"
    resp = defects_client.get(f"/defects/devices/{parent_id}/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/devices"' in resp.text
    assert f'name="parent_id" value="{parent_id}"' in resp.text


def test_get_device_form_edit(defects_client, monkeypatch):
    """GET /defects/devices/{id}/edit → 200, prefill values + hx-patch target."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("22222222-2222-2222-2222-222222222222")
    fake_device = DeviceNodeRow(
        id=nid, parent_id=None, slug="apple", title="Apple",
        kind=None, sort_order=0,
    )

    async def _fake_get_device_node(session, _nid):
        return fake_device

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get_device_node)

    resp = defects_client.get(f"/defects/devices/{nid}/edit")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert f'hx-patch="/defects/devices/{nid}/edit"' in resp.text
    assert 'value="apple"' in resp.text
    assert 'value="Apple"' in resp.text
```

- [ ] **Step 2: Run tests, expect FAIL with 404 (routes не зарегистрированы)**

```bash
python -m pytest tests/web/test_defects_routes.py::test_get_device_form_add_root tests/web/test_defects_routes.py::test_get_device_form_add_child tests/web/test_defects_routes.py::test_get_device_form_edit -v
```

Expected: 3 FAIL.

- [ ] **Step 3: Add 4 routes in defects.py**

Открыть `avito-monitor/app/web/defects.py`, найти строку `@router.get("/devices/{device_id}", response_class=HTMLResponse)` (~line 108). **Перед** этой строкой вставить:

```python
@router.get("/devices/new", response_class=HTMLResponse)
async def device_form_add_root(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "device", "parent_id": None, "prefill": None},
    )


@router.get("/devices/cancel-form", response_class=HTMLResponse)
async def device_form_cancel(
    user: Annotated[User, Depends(require_user)],
) -> HTMLResponse:
    return HTMLResponse("")


@router.get("/devices/{parent_id}/new", response_class=HTMLResponse)
async def device_form_add_child(
    parent_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "device", "parent_id": str(parent_id), "prefill": None},
    )


@router.get("/devices/{node_id}/edit", response_class=HTMLResponse)
async def device_form_edit(
    node_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    device = await get_device_node(session, node_id)
    if device is None:
        return HTMLResponse("Устройство не найдено", status_code=404)
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {
            "mode": "edit", "kind": "device", "node_id": str(node_id),
            "prefill": {"slug": device.slug, "title": device.title},
        },
    )
```

- [ ] **Step 4: Run device-form tests, expect PASS**

```bash
python -m pytest tests/web/test_defects_routes.py::test_get_device_form_add_root tests/web/test_defects_routes.py::test_get_device_form_add_child tests/web/test_defects_routes.py::test_get_device_form_edit -v
```

Expected: 3 PASS.

- [ ] **Step 5: Smoke — все остальные defects-тесты не сломались**

```bash
python -m pytest tests/web/test_defects_routes.py -v
```

Expected: All PASS (existing 6 + 4 new = 10).

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/defects.py avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): GET form-fragment routes for device CRUD UI"
```

---

## Task 5 — GET form-fragment routes для feature + cancel

**Files:**
- Modify: `avito-monitor/app/web/defects.py` (add 4 routes for catalog)
- Test: `avito-monitor/tests/web/test_defects_routes.py`

Симметрично Task 4. Routes `/catalog/new`, `/catalog/cancel-form`, `/catalog/{parent_id}/new`, `/catalog/{node_id}/edit` регистрируются **до** существующих POST/PATCH/DELETE для catalog. Существующий `@router.get("/catalog", ...)` это full page, не конфликтует.

- [ ] **Step 1: Add 3 failing tests**

```python
def test_get_feature_form_add_root(defects_client):
    """GET /defects/catalog/new → 200, partial form has kind+prompt_hint inputs."""
    resp = defects_client.get("/defects/catalog/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/catalog"' in resp.text
    # Feature-specific fields present in add mode
    assert 'name="kind"' in resp.text
    assert 'name="prompt_hint"' in resp.text
    assert 'name="parent_id"' not in resp.text


def test_get_feature_form_add_child(defects_client):
    parent_id = "33333333-3333-3333-3333-333333333333"
    resp = defects_client.get(f"/defects/catalog/{parent_id}/new")
    assert resp.status_code == 200
    assert f'name="parent_id" value="{parent_id}"' in resp.text


def test_get_feature_form_edit(defects_client, monkeypatch):
    """GET /defects/catalog/{id}/edit → 200, prefill including prompt_hint."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("44444444-4444-4444-4444-444444444444")
    fake_feat = FeatureNodeRow(
        id=nid, parent_id=None, kind="section", slug="display",
        title="Дисплей", sort_order=0, prompt_hint="Дисплей телефона",
    )

    async def _fake_get(session, _nid):
        return fake_feat

    # get_feature_node is in repository — defects.py uses it indirectly via resolver path.
    # For form-edit, we need defects.py to call get_feature_node(session, node_id).
    # Patch on defects module — same import path pattern as device case.
    monkeypatch.setattr(defects_mod, "get_feature_node", _fake_get)

    resp = defects_client.get(f"/defects/catalog/{nid}/edit")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert f'hx-patch="/defects/catalog/{nid}/edit"' in resp.text
    assert 'value="display"' in resp.text
    assert 'value="Дисплей"' in resp.text
    assert 'value="Дисплей телефона"' in resp.text
```

- [ ] **Step 2: Check import for `get_feature_node` in defects.py**

```bash
grep -n "get_feature_node\|FeatureNodeRow" avito-monitor/app/web/defects.py
```

Если `get_feature_node` НЕ импортирован — добавить в импорт из `repository`. Если в `repository.py` функция называется иначе (e.g., `get_feature`) — adjust accordingly. Используй `grep -n "^async def get_" avito-monitor/app/services/defect_catalog/repository.py` чтобы найти actual name.

- [ ] **Step 3: Run tests, expect FAIL with 404**

```bash
python -m pytest tests/web/test_defects_routes.py::test_get_feature_form_add_root tests/web/test_defects_routes.py::test_get_feature_form_add_child tests/web/test_defects_routes.py::test_get_feature_form_edit -v
```

- [ ] **Step 4: Add 4 routes + ensure get_feature_node imported**

В `defects.py` найти секцию `# Task 25: POST endpoints for device / feature creation` (~line 207). **Перед** существующими POST endpoints вставить (порядок важен — literal сегменты перед `{feature_id}` в существующих PATCH/DELETE):

```python
@router.get("/catalog/new", response_class=HTMLResponse)
async def feature_form_add_root(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "feature", "parent_id": None, "prefill": None},
    )


@router.get("/catalog/cancel-form", response_class=HTMLResponse)
async def feature_form_cancel(
    user: Annotated[User, Depends(require_user)],
) -> HTMLResponse:
    return HTMLResponse("")


@router.get("/catalog/{parent_id}/new", response_class=HTMLResponse)
async def feature_form_add_child(
    parent_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {"mode": "add", "kind": "feature", "parent_id": str(parent_id), "prefill": None},
    )


@router.get("/catalog/{node_id}/edit", response_class=HTMLResponse)
async def feature_form_edit(
    node_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> HTMLResponse:
    feat = await get_feature_node(session, node_id)
    if feat is None:
        return HTMLResponse("Признак не найден", status_code=404)
    return templates.TemplateResponse(
        request, "defects/_partials/node_form.html",
        {
            "mode": "edit", "kind": "feature", "node_id": str(node_id),
            "prefill": {
                "slug": feat.slug, "title": feat.title,
                "prompt_hint": feat.prompt_hint or "",
            },
        },
    )
```

Если `get_feature_node` ещё не импортирован — добавить в `from app.services.defect_catalog.repository import (...)` блок на верху файла.

- [ ] **Step 5: Run tests, expect PASS + full suite green**

```bash
python -m pytest tests/web/test_defects_routes.py -v
```

Expected: All PASS (existing + Tasks 1-5 new = 13).

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/defects.py avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): GET form-fragment routes for feature CRUD UI"
```

---

## Task 6 — `device_tree.html`: action icons + Russification

**Files:**
- Modify: `avito-monitor/app/web/templates/defects/_partials/device_tree.html`
- Test: `avito-monitor/tests/web/test_defects_routes.py`

- [ ] **Step 1: Add failing test для action-icons в tree**

```python
def test_device_tree_renders_action_icons(defects_client, monkeypatch):
    """GET /defects/devices/tree renders [+][✏][🗑] icons per node + hx-confirm для delete."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_node = DeviceNodeRow(
        id=nid, parent_id=None, slug="apple", title="Apple",
        kind=None, sort_order=0,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        # First call (parent_id=None) returns the apple node; recursive calls return [].
        if call_count["n"] == 1:
            return [fake_node]
        return []

    monkeypatch.setattr(defects_mod, "list_device_children", _fake_list_children)

    resp = defects_client.get("/defects/devices/tree")
    assert resp.status_code == 200
    # Icon buttons for the apple node
    assert f'hx-get="/defects/devices/{nid}/new"'  in resp.text  # [+]
    assert f'hx-get="/defects/devices/{nid}/edit"' in resp.text  # [✏]
    assert f'hx-delete="/defects/devices/{nid}"'   in resp.text  # [🗑]
    # Native confirm на delete
    assert "hx-confirm=" in resp.text
    assert "Apple" in resp.text
```

- [ ] **Step 2: Run test, expect FAIL (старый template не имеет hx-get/hx-delete на ноду)**

```bash
python -m pytest tests/web/test_defects_routes.py::test_device_tree_renders_action_icons -v
```

- [ ] **Step 3: Rewrite `device_tree.html`**

Заменить файл `avito-monitor/app/web/templates/defects/_partials/device_tree.html` целиком:

```jinja
{% macro render(entry) %}
  <div class="ml-2">
    <div class="flex items-center gap-1 py-1 text-sm">
      <a href="/defects/devices/{{ entry.node.id }}" hx-boost="false"
         class="flex-1 hover:text-avito-green">{{ entry.node.title }}</a>
      <button hx-get="/defects/devices/{{ entry.node.id }}/new"
              hx-target="this" hx-swap="afterend"
              class="text-xs text-avito-text-soft hover:text-avito-green px-1"
              title="Добавить дочернюю ноду">[+]</button>
      <button hx-get="/defects/devices/{{ entry.node.id }}/edit"
              hx-target="closest div.flex" hx-swap="outerHTML"
              class="text-xs text-avito-text-soft hover:text-avito-green px-1"
              title="Переименовать">[✏]</button>
      <button hx-delete="/defects/devices/{{ entry.node.id }}"
              hx-target="#device-tree" hx-swap="innerHTML"
              hx-confirm="Удалить «{{ entry.node.title }}» и всех потомков?"
              class="text-xs text-avito-text-soft hover:text-red-600 px-1"
              title="Удалить">[🗑]</button>
    </div>
    {% if entry.children %}
      <div class="ml-3">
        {% for child in entry.children %}{{ render(child) }}{% endfor %}
      </div>
    {% endif %}
  </div>
{% endmacro %}
{% for entry in tree %}{{ render(entry) }}{% endfor %}
```

- [ ] **Step 4: Run test, expect PASS**

```bash
python -m pytest tests/web/test_defects_routes.py::test_device_tree_renders_action_icons -v
```

- [ ] **Step 5: Smoke full suite**

```bash
python -m pytest tests/web/test_defects_routes.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/templates/defects/_partials/device_tree.html avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): device_tree action icons (add/edit/delete)"
```

---

## Task 7 — `feature_tree.html`: action icons + Russification

**Files:**
- Modify: `avito-monitor/app/web/templates/defects/_partials/feature_tree.html`
- Test: `avito-monitor/tests/web/test_defects_routes.py`

Симметрично Task 6.

- [ ] **Step 1: Read existing feature_tree.html**

```bash
cat avito-monitor/app/web/templates/defects/_partials/feature_tree.html
```

Чтобы сверить структуру (вероятно похоже на device_tree старый).

- [ ] **Step 2: Add failing test**

```python
def test_feature_tree_renders_action_icons(defects_client, monkeypatch):
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("66666666-6666-6666-6666-666666666666")
    fake_feat = FeatureNodeRow(
        id=nid, parent_id=None, kind="section", slug="display",
        title="Дисплей", sort_order=0, prompt_hint=None,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [fake_feat]
        return []

    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    resp = defects_client.get("/defects/catalog/tree")
    assert resp.status_code == 200
    assert f'hx-get="/defects/catalog/{nid}/new"'  in resp.text
    assert f'hx-get="/defects/catalog/{nid}/edit"' in resp.text
    assert f'hx-delete="/defects/catalog/{nid}"'   in resp.text
    assert "hx-confirm=" in resp.text
    assert "Дисплей" in resp.text
```

- [ ] **Step 3: Run, expect FAIL**

```bash
python -m pytest tests/web/test_defects_routes.py::test_feature_tree_renders_action_icons -v
```

- [ ] **Step 4: Rewrite `feature_tree.html`**

Заменить файл целиком:

```jinja
{% macro render(entry) %}
  <div class="ml-2">
    <div class="flex items-center gap-1 py-1 text-sm">
      <span class="flex-1">{{ entry.node.title }}
        <span class="text-xs text-avito-text-soft">[{{ entry.node.kind }}]</span>
      </span>
      <button hx-get="/defects/catalog/{{ entry.node.id }}/new"
              hx-target="this" hx-swap="afterend"
              class="text-xs text-avito-text-soft hover:text-avito-green px-1"
              title="Добавить дочерний признак">[+]</button>
      <button hx-get="/defects/catalog/{{ entry.node.id }}/edit"
              hx-target="closest div.flex" hx-swap="outerHTML"
              class="text-xs text-avito-text-soft hover:text-avito-green px-1"
              title="Редактировать">[✏]</button>
      <button hx-delete="/defects/catalog/{{ entry.node.id }}"
              hx-target="#feature-tree" hx-swap="innerHTML"
              hx-confirm="Удалить «{{ entry.node.title }}» и всех потомков?"
              class="text-xs text-avito-text-soft hover:text-red-600 px-1"
              title="Удалить">[🗑]</button>
    </div>
    {% if entry.children %}
      <div class="ml-3">
        {% for child in entry.children %}{{ render(child) }}{% endfor %}
      </div>
    {% endif %}
  </div>
{% endmacro %}
{% for entry in tree %}{{ render(entry) }}{% endfor %}
```

- [ ] **Step 5: Run test + full suite, expect PASS**

```bash
python -m pytest tests/web/test_defects_routes.py -v
```

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/templates/defects/_partials/feature_tree.html avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): feature_tree action icons (add/edit/delete)"
```

---

## Task 8 — `devices.html` + `catalog.html`: «+ Добавить корневую» buttons + form-mount

**Files:**
- Modify: `avito-monitor/app/web/templates/defects/devices.html`
- Modify: `avito-monitor/app/web/templates/defects/catalog.html`
- Test: `avito-monitor/tests/web/test_defects_routes.py` (extend existing page tests + Loading→Загрузка)

- [ ] **Step 1: Update existing devices/catalog page tests + Loading→Загрузка**

В `tests/web/test_defects_routes.py` найти `test_defects_devices_page_200` и `test_defects_catalog_page_200`, заменить assertions:

```python
def test_defects_devices_page_200(defects_client):
    resp = defects_client.get("/defects/devices")
    assert resp.status_code == 200
    assert "Настройки дефектов" in resp.text
    assert "Загрузка" in resp.text  # Loading → Загрузка
    assert 'hx-get="/defects/devices/new"' in resp.text  # root-add button
    assert "Добавить корневое устройство" in resp.text


def test_defects_catalog_page_200(defects_client):
    resp = defects_client.get("/defects/catalog")
    assert resp.status_code == 200
    assert "Каталог признаков" in resp.text
    assert "Загрузка" in resp.text
    assert 'hx-get="/defects/catalog/new"' in resp.text
    assert "Добавить корневой признак" in resp.text
```

- [ ] **Step 2: Run tests, expect FAIL**

```bash
python -m pytest tests/web/test_defects_routes.py::test_defects_devices_page_200 tests/web/test_defects_routes.py::test_defects_catalog_page_200 -v
```

- [ ] **Step 3: Update `devices.html`**

```jinja
{# app/web/templates/defects/devices.html #}
{% extends "defects/_layout.html" %}
{% block defects_content %}
<div class="grid grid-cols-4 gap-4">
  <aside class="col-span-1 bg-white rounded border border-avito-border-soft p-3">
    <div class="flex items-center justify-between mb-2">
      <div class="text-xs uppercase text-avito-text-soft">Устройства</div>
      <button hx-get="/defects/devices/new"
              hx-target="#device-form-mount" hx-swap="innerHTML"
              class="text-xs text-avito-text-soft hover:text-avito-green">[+] Добавить корневое устройство</button>
    </div>
    <div id="device-form-mount"></div>
    <div id="device-tree" hx-get="/defects/devices/tree" hx-trigger="load" hx-swap="innerHTML">
      <div class="text-avito-text-soft">Загрузка…</div>
    </div>
  </aside>
  <section class="col-span-3 bg-white rounded border border-avito-border-soft p-3 min-h-[40vh]">
    <div class="text-avito-text-soft">Выберите устройство в дереве слева.</div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 4: Update `catalog.html`**

```jinja
{# app/web/templates/defects/catalog.html #}
{% extends "defects/_layout.html" %}
{% block defects_content %}
<div class="bg-white rounded border border-avito-border-soft p-3">
  <div class="flex items-center justify-between mb-2">
    <div class="text-xs uppercase text-avito-text-soft">Каталог признаков</div>
    <button hx-get="/defects/catalog/new"
            hx-target="#feature-form-mount" hx-swap="innerHTML"
            class="text-xs text-avito-text-soft hover:text-avito-green">[+] Добавить корневой признак</button>
  </div>
  <div id="feature-form-mount"></div>
  <div id="feature-tree" hx-get="/defects/catalog/tree" hx-trigger="load" hx-swap="innerHTML">
    <div class="text-avito-text-soft">Загрузка…</div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests, expect PASS + full suite green**

```bash
python -m pytest tests/web/test_defects_routes.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git -C /c/Projects/Sync/AvitoSystem add avito-monitor/app/web/templates/defects/devices.html avito-monitor/app/web/templates/defects/catalog.html avito-monitor/tests/web/test_defects_routes.py
git -C /c/Projects/Sync/AvitoSystem commit -m "feat(defects): root-add buttons + form-mount on devices/catalog pages"
```

---

## Task 9 — Локальный full pytest sweep

- [ ] **Step 1: Запустить ВСЕ тесты avito-monitor**

```bash
cd /c/Projects/Sync/AvitoSystem/avito-monitor
python -m pytest -q
```

Expected: ≥433 passed (baseline from CONTINUE.md §4.5 = 433 passed / 8 failed pre-existing). Polish tasks НЕ должны увеличить число failed. Если новые тесты вызывают регрессии в каком-то другом модуле — STOP, диагностируй.

- [ ] **Step 2: Если есть НОВЫЕ failures (не из baseline 8) — fix**

Baseline pre-existing 8 failures:
- `tests/avito_mcp/test_tools.py` (1)
- `tests/health_checker/test_*` (5)
- `tests/test_polling.py` (1)
- (`tests/seller_dialog/test_view.py` уже исправлен в этой сессии)

Если pytest показывает 9+ failures — последний > baseline, надо смотреть какой именно новый тест ломается и fix-нуть. Не commit-ить пока не выправишь.

---

## Task 10 — Deploy на prod

- [ ] **Step 1: Sync новых/изменённых файлов на VPS**

```bash
tar -cf - -C /c/Projects/Sync/AvitoSystem \
  avito-monitor/app/web/defects.py \
  avito-monitor/app/web/templates/defects/devices.html \
  avito-monitor/app/web/templates/defects/catalog.html \
  avito-monitor/app/web/templates/defects/_partials/binding_row.html \
  avito-monitor/app/web/templates/defects/_partials/device_tree.html \
  avito-monitor/app/web/templates/defects/_partials/feature_tree.html \
  avito-monitor/app/web/templates/defects/_partials/node_form.html \
  avito-monitor/tests/web/test_defects_routes.py \
  | ssh root@81.200.119.132 'cd /opt/avito-system/repo && tar -xf -'
```

- [ ] **Step 2: Verify на prod все файлы на месте**

```bash
ssh root@81.200.119.132 'stat -c "%y %s %n" \
  /opt/avito-system/repo/avito-monitor/app/web/defects.py \
  /opt/avito-system/repo/avito-monitor/app/web/templates/defects/_partials/node_form.html \
  /opt/avito-system/repo/avito-monitor/app/web/templates/defects/_partials/device_tree.html'
```

Expected: свежие mtime для всех файлов, sensible sizes.

- [ ] **Step 3: Rebuild ТОЛЬКО avito-monitor (другие 6 сервисов не загружают defects.py)**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose build avito-monitor 2>&1 | tail -10'
```

Expected: `Image avito-system-avito-monitor Built`.

- [ ] **Step 4: Recreate avito-monitor**

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose up -d --force-recreate avito-monitor 2>&1 | tail -10'
```

Expected: `Container avito-system-avito-monitor-1  Started`.

- [ ] **Step 5: Smoke logs + endpoints**

```bash
ssh root@81.200.119.132 'sleep 3 && docker logs avito-system-avito-monitor-1 --tail 15 2>&1'
```

Expected: чистый старт, `Application startup complete.` Нет traceback.

```bash
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "%{http_code}\n" https://avitosystem.duckdns.org/defects/devices'
```

Expected: `200` (или `303` если без auth cookie, тоже OK — не 500).

---

## Task 11 — Manual UI smoke (юзер)

Передать юзеру чеклист — он открывает `https://avitosystem.duckdns.org/defects` в браузере.

- [ ] **Step 1: Sidebar + tabs + Loading**
  - Sidebar пункт «🛠 Дефекты» виден.
  - Открыть /defects → 303 → /defects/devices. Загрузка → дерево рендерится.
  - Текст «Загрузка…» не виден дольше 1 сек (т.е. реально загружается).

- [ ] **Step 2: Add root device**
  - Клик «[+] Добавить корневое устройство» в правом-верхнем углу sidebar.
  - Inline-форма появилась.
  - Ввести slug=`test_brand`, title=`Test Brand`, [ОК].
  - Tree обновился — Test Brand виден.

- [ ] **Step 3: Add child**
  - Клик `[+]` рядом с Test Brand.
  - Форма появилась под ним.
  - Ввести slug=`test_phone`, title=`Test Phone`, [ОК].
  - Test Phone виден под Test Brand.

- [ ] **Step 4: Edit**
  - Клик `[✏]` на Test Phone.
  - Форма заменила row. Prefill — `test_phone` + `Test Phone`.
  - Изменить title на `Test Phone v2`, [ОК].
  - Row обновился.

- [ ] **Step 5: Delete**
  - Клик `[🗑]` на Test Phone.
  - Native confirm() появился с текстом «Удалить «Test Phone v2» и всех потомков?»
  - OK → row исчез.
  - Test Brand остался, удалить его таким же образом.

- [ ] **Step 6: Severity labels в binding panel**
  - Кликнуть iPhone 12 Pro Max в существующем дереве.
  - Справа панель «Применимые дефекты (6)».
  - Все bindings показывают «инфо»/«блок» (не «info»/«block»).
  - «уточнить»/«пропустить» вместо «ask»/«skip».
  - Hint «← унаследовано» под каждой нодой.
  - Кнопки «Задать здесь» (не «Override»).

- [ ] **Step 7: Catalog tab**
  - Клик «Признаки» (top tabs).
  - Дерево «Корпус (3 defects)» + «Дисплей (3 defects)» рендерится.
  - Add/Edit/Delete иконки видны на каждой ноде.
  - Add root → форма с `kind` dropdown + slug + title + prompt_hint появляется.

Если что-то крашится — STOP, debug, fix-redeploy.

---

## Task 12 — Merge feat/defect-catalog → main

После Task 11 smoke OK:

- [ ] **Step 1: Update CONTINUE.md (опционально — снизу под §10)**

Если хочешь поддерживать historical log — добавь короткий entry «Project A polish: shipped 2026-05-13 evening». Иначе пропусти.

- [ ] **Step 2: Merge**

```bash
git -C /c/Projects/Sync/AvitoSystem checkout main
git -C /c/Projects/Sync/AvitoSystem pull origin main
git -C /c/Projects/Sync/AvitoSystem merge --no-ff feat/defect-catalog -m "Merge Project A + polish — defect catalog admin (deployed 2026-05-13)"
git -C /c/Projects/Sync/AvitoSystem push origin main
```

- [ ] **Step 3: Branch cleanup (опционально)**

```bash
git -C /c/Projects/Sync/AvitoSystem branch -d feat/defect-catalog
git -C /c/Projects/Sync/AvitoSystem push origin --delete feat/defect-catalog
```

- [ ] **Step 4: Verify**

```bash
git -C /c/Projects/Sync/AvitoSystem log --oneline main -5
```

Expected: Merge commit на топе, Project A + polish commits в истории.

---

## Self-Review checklist (для writer)

- ✅ Spec §3.4 (русификация словарь) — Task 1 + Task 2 implement.
- ✅ Spec §3.2 (add UI per-node + root button) — Tasks 6, 7, 8.
- ✅ Spec §3.3 (edit inline form, delete native confirm) — Tasks 6, 7 (через hx-confirm).
- ✅ Spec §4.1 (Jinja filter) — Task 1.
- ✅ Spec §4.2 (node_form.html) — Task 3.
- ✅ Spec §4.3 (tree icon-кнопки) — Tasks 6, 7.
- ✅ Spec §4.4 (6 GET routes + registration order) — Tasks 4, 5 (with explicit note про registration order до `{device_id}` / `{feature_id}` catch-all).
- ✅ Spec §6 (7 тестов) — все есть: severity_ru filter (Task 1), binding_row ru (Task 2), 3 device form (Task 4), 3 feature form (Task 5), 2 tree icons (Tasks 6+7), 2 page updates (Task 8) — итого больше 7.
- ✅ Все code-блоки полные, без placeholder'ов.
- ✅ Registration order для FastAPI literal-vs-UUID conflict явно прописан в Task 4.

Open уязвимость: Task 5 предполагает что в `repository.py` есть `get_feature_node`. Step 2 явно даёт grep команду чтобы проверить — implementer adapt-ит если имя другое.
