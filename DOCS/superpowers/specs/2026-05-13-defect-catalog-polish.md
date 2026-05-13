# Defect Catalog — Project A polish (русификация + CRUD UI)

**Дата:** 2026-05-13
**Статус:** brainstorming утверждён пользователем, готово к writing-plans
**Стартовое состояние:** Project A shipped 2026-05-13 (`alembic 0017_defect_catalog`, /defects live на prod) + hotfix device_detail layout context (этой сессии, в working tree feat/defect-catalog, ещё не committed).

---

## 1. Цель

Закрыть два gap'а Project A, обнаруженных при manual UI smoke 2026-05-13, чтобы ветка `feat/defect-catalog` стала feature-complete перед merge в `main`:

1. **Русификация UI** — все user-facing строки в /defects на русском (по проектному правилу `feedback_russian.md`).
2. **CRUD UI для device/feature nodes** — добавление, переименование, удаление через UI. Backend routes (`POST/PATCH/DELETE /defects/devices` и `/defects/catalog`) уже зарегистрированы в `app/web/defects.py` (Tasks 25-26 из Project A plan), но шаблоны не содержат форм/иконок для submit'a. Без UI юзер вынужден дёргать `scripts/seed_defect_catalog.py` + redeploy для каждой новой модели — это блокер ежедневного использования.

**Scope explicit OUT:**
- Изменения в data layer (DB-значения severity остаются английскими `block`/`info`/`ask`/`skip` — translation только на UI-слое).
- Изменения в backend routes (они уже работают, тесты проходят).
- Интеграция в pipeline (это Project B).
- Reordering/drag-and-drop в tree (текущая sort_order по slug ASC достаточно).

## 2. Use case

**Юзер хочет:**

1. Добавить iPhone 13 Pro как новую модель — кликнуть `[+]` рядом с «iPhone» в дереве устройств, ввести slug+title, сразу видеть в дереве, кликнуть и переопределить severity для своих профилей.
2. Переименовать «Корпус» в «Корпус (Midframe + крышка)» — кликнуть `[✏]`, ввести новое название, увидеть update в дереве.
3. Удалить тестовую ноду — кликнуть `[🗑]`, подтвердить, увидеть исчезновение.
4. Видеть всё UI на русском, как остальные разделы (`/search-profiles`, `/listings`, `/reliability` и т.д. уже русифицированы).

## 3. Решения brainstorming'а (зафиксированы)

### 3.1 Скоуп
**Решение:** Русификация + CRUD UI одной веткой, single PR (variant A из Q1).
**Альтернативы отвергнуты:**
- Phased deploy (русификация → merge → CRUD UI) — лишний deploy-cycle.
- Только CRUD UI — UI остался бы наполовину англоязычным.

### 3.2 Размещение add-кнопок
**Решение:** `[+]` рядом с каждой нодой (variant A из Q2). Клик `[+]` на ноде → под ней появляется inline-форма `slug + title + [ОК] [Отмена]`, parent=та нода зашит. Плюс отдельная кнопка `[+] Добавить корневую` под деревом (parent=null).
**Альтернативы отвергнуты:**
- Одна кнопка внизу + dropdown parent — менее очевидно куда идёт нода.
- Без UI add — блокирует daily workflow.

### 3.3 Edit / Delete UX
**Решение:**
- **Edit:** клик `[✏]` → row заменяется inline-формой с текущими values + `[ОК] [Отмена]`. HTMX PATCH → swap дерева.
- **Delete:** клик `[🗑]` → native `confirm("Удалить узел и всех потомков?")` → HTMX DELETE → swap.
- Иконки видны постоянно (не на hover) — Avito-Cosplay style уже clutter-tolerant, hover-reveal добавил бы дополнительную JS-сложность.

### 3.4 Словарь русификации
**Решение пользователя:** **блок / инфо / уточнить** (+ skip → пропустить).

| Английское (DB-value) | UI display |
|---|---|
| `block` | **блок** |
| `info` | **инфо** |
| `ask` | **уточнить** |
| `skip` | **пропустить** |

Прочие строки:

| Английское | Русский |
|---|---|
| `← inherited from ancestor` | `← унаследовано` |
| `← set here` | `← задано здесь` |
| `Override` (button) | `Задать здесь` |
| `Loading…` | `Загрузка…` |
| `Device not found` | `Устройство не найдено` |
| `Удалить` | без изменения (уже русское) |
| `При находке:`, `Если неясно:` | без изменения (уже русские) |
| `Применимые дефекты (N)` | без изменения |
| `Настройки дефектов` (h1) | без изменения |

## 4. Архитектура

### 4.1 Слой translation (severity labels)

Реализация — **Jinja-filter** `severity_ru`, регистрируется в `app/web/defects.py` через `templates.env.filters['severity_ru'] = severity_ru`. Простая dict-функция:

```python
_SEVERITY_RU = {"block": "блок", "info": "инфо", "ask": "уточнить", "skip": "пропустить"}
def severity_ru(value: str) -> str:
    return _SEVERITY_RU.get(value, value)
```

В шаблонах: `{{ b.defect_action | severity_ru }}` вместо `{{ b.defect_action }}`. Filter применяется и в inherited-display, и в `<option>`-лейблах dropdown'ов.

Это единственная функциональная функция русификации — остальные строки просто меняются в шаблонах.

### 4.2 CRUD UI — общий партиал `node_form.html`

Один общий партиал для add/edit и device/feature, параметризованный context:
- `mode` ∈ {`add`, `edit`}
- `kind` ∈ {`device`, `feature`} — определяет endpoint POST `/defects/devices` vs `/defects/catalog`
- `parent_id` (для add) или `node_id` (для edit)
- prefill: slug, title (пустые для add, текущие для edit)
- для feature add — поле `kind` (например `section`, `defect`) и `prompt_hint`

Это меньше дублирования, чем два отдельных шаблона. JS-логика обработки form-submit через HTMX `hx-post/hx-patch`, `hx-target="#device-tree"` (или `#feature-tree`), `hx-swap="innerHTML"`.

### 4.3 Tree templates — `device_tree.html` + `feature_tree.html`

Каждая нода в макросе `render(entry)` рендерится как:

```html
<div class="flex items-center gap-1">
  <a href="/defects/devices/{{ entry.node.id }}" hx-boost="false"
     class="flex-1">{{ entry.node.title }}</a>
  <button hx-get="/defects/devices/{{ entry.node.id }}/form/add"
          hx-target="closest div" hx-swap="afterend"
          class="text-xs text-avito-text-soft hover:text-avito-green">[+]</button>
  <button hx-get="/defects/devices/{{ entry.node.id }}/form/edit"
          hx-target="closest div" hx-swap="outerHTML"
          class="text-xs text-avito-text-soft hover:text-avito-green">[✏]</button>
  <button hx-delete="/defects/devices/{{ entry.node.id }}"
          hx-target="#device-tree" hx-swap="innerHTML"
          hx-confirm="Удалить узел «{{ entry.node.title }}» и всех потомков?"
          class="text-xs text-avito-text-soft hover:text-red-600">[🗑]</button>
</div>
```

Использую `hx-confirm` (нативный HTMX feature, рендерит native browser confirm()) вместо самописного JS — встраивается, простой.

Аналогично для `feature_tree.html` с endpoints `/defects/catalog/*` (и доп. поля `kind` + `prompt_hint`).

### 4.4 Новые GET endpoints для inline-form fragments

В `app/web/defects.py` добавляются GET-routes, каждый возвращает только partial `node_form.html` (без layout extension — HTMX swap, не page navigation):

- **Add под корнем** (parent=None): `GET /defects/devices/new` и `GET /defects/catalog/new`
- **Add под существующим parent**: `GET /defects/devices/{parent_id}/new` и `GET /defects/catalog/{parent_id}/new`
- **Edit существующей ноды**: `GET /defects/devices/{node_id}/edit` и `GET /defects/catalog/{node_id}/edit`

**Важно по registration order:** literal-segment routes (`/devices/new`) должны регистрироваться в `defects.py` **до** существующего `/devices/{device_id}` — иначе FastAPI попытается распарсить «new» как UUID и вернёт 422. Конкретное место вставки — план уточнит.

### 4.5 POST/PATCH/DELETE — изменения только в HTML-response

Существующие routes уже работают и возвращают `_partials/device_tree.html` или `_partials/feature_tree.html`. Менять backend не нужно. Изменение только в template'ах tree (добавить icon-кнопки).

## 5. Файлы

| Файл | Что |
|---|---|
| `avito-monitor/app/web/defects.py` | +6 GET endpoints для form-fragments, +Jinja-filter `severity_ru` |
| `avito-monitor/app/web/templates/defects/_partials/device_tree.html` | +`[+][✏][🗑]` buttons + render mount-point |
| `avito-monitor/app/web/templates/defects/_partials/feature_tree.html` | то же |
| `avito-monitor/app/web/templates/defects/_partials/binding_row.html` | `severity_ru` filter в display + `<option>`-labels, `Override` → `Задать здесь`, `inherited from ancestor` → `унаследовано`, `set here` → `задано здесь` |
| `avito-monitor/app/web/templates/defects/_partials/node_form.html` | **NEW** общий партиал add/edit для device+feature |
| `avito-monitor/app/web/templates/defects/devices.html` | +кнопка `[+] Добавить корневую` под tree + form-mount div |
| `avito-monitor/app/web/templates/defects/catalog.html` | то же |
| `avito-monitor/tests/web/test_defects_routes.py` | +5-7 тестов: severity_ru filter, render-form fragments, POST add-via-UI, PATCH edit, DELETE через UI |

Никаких миграций. Никаких изменений в repository / resolver / models.

## 6. Тесты

Все новые тесты добавляются в `tests/web/test_defects_routes.py`, используют существующий `defects_client` fixture.

```python
def test_severity_ru_filter():
    # Unit-test filter напрямую — block→блок, info→инфо, ask→уточнить, skip→пропустить, unknown→passthrough

def test_get_device_form_add(defects_client):
    # GET /defects/devices/{parent_id}/form/add → 200, содержит <form>, hx-post target /defects/devices

def test_get_device_form_edit(defects_client, monkeypatch):
    # GET /defects/devices/{node_id}/form/edit → 200, форма с prefilled values

def test_get_feature_form_add(defects_client):
    # GET /defects/catalog/{parent_id}/form/add → 200, содержит fields kind + prompt_hint

def test_binding_row_uses_ru_labels(defects_client, monkeypatch):
    # GET /defects/devices/{id} (с fake device + 1 binding) → response содержит «блок», «уточнить», «Задать здесь», «унаследовано»

def test_tree_renders_action_icons(defects_client):
    # GET /defects/devices/tree → 200; (с пустым деревом проверяем рендер пустой root-кнопки добавления)
```

POST/PATCH/DELETE routes уже покрыты на repository-уровне (Tasks 12-23 Project A); добавлять route-level dup-тесты лишнее. UI-form тесты выше покрывают именно UI-слой.

## 7. Implementation order

Predicted ~2-3 часа кодинга.

1. **Phase 1 — Jinja-filter + binding_row русификация** (30 мин). Register filter, swap labels в `binding_row.html`. Test `test_severity_ru_filter` + `test_binding_row_uses_ru_labels`.
2. **Phase 2 — node_form.html + 6 GET form-fragment routes** (45 мин). New partial + 6 routes. Tests `test_get_device_form_*` и `test_get_feature_form_*`.
3. **Phase 3 — tree templates: icons + mount-points** (45 мин). Update `device_tree.html` + `feature_tree.html` + mount-points в `devices.html`/`catalog.html`. Test `test_tree_renders_action_icons`.
4. **Phase 4 — deploy + manual UI smoke** (15 мин). Sync source, rebuild только `avito-monitor` (другие 6 не загружают defects.py), recreate. Юзер проходит ручной smoke (add iPhone 13 Pro, edit его title, delete).
5. **Phase 5 — merge feat/defect-catalog → main** (5 мин) после smoke OK.

Между Phase 1-3 запускать `pytest tests/web/test_defects_routes.py` чтобы новые тесты держались зелёными.

## 8. Open вопросы

Нет — все вопросы закрыты на brainstorming-стадии.

## 9. Связано

- `DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md` — основной spec Project A
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-impl.md` — план Project A (34 tasks shipped)
- `CONTINUE.md` §4.2 — manual UI smoke checklist (этот polish удовлетворит все check-box'ы)
- `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/feedback_russian.md` — правило «алерты, UI, тексты бота — на русском»
