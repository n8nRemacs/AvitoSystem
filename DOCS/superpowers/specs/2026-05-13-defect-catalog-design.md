# Defect Catalog — глобальный справочник дефектов с device-hierarchy

**Дата:** 2026-05-13
**Статус:** утверждено пользователем по секциям, готово к плану (writing-plans)
**Стартовое состояние:** Phase 2.1 shipped 2026-05-13 (unified `listing_features` + flat 31-feature taxonomy + per-profile `ProfileFeatureRule` + `compute_bucket` на этой схеме). Текущий pipeline работает в проде без изменений.
**Базовое решение пользователя:** «Сделать с нуля, отдельной системой. Сначала каталог дефектов с device-hierarchy и UI, потом интегрировать в признаки на профиле/карточке (Project B), потом авто-генерация LLM-промптов из каталога (Project C).»

---

## 1. Цель

Построить **новую admin-систему «Настройки дефектов»** — глобальный каталог дефектов с двумя ортогональными иерархиями (feature catalog + device tree), связанными через bindings с severity.

Цель Project A — **только catalog + UI**, без интеграции в существующий pipeline. Текущие 31 feature / `ProfileFeatureRule` / `compute_bucket` продолжают работать неизменно в проде.

Конкретно:
- Новые таблицы (`feature_nodes`, `device_nodes`, `device_feature_bindings`) — Alembic migration 0017, аддитивная.
- Новый admin-раздел `/defects` с двумя вкладками: «Устройства» (default, рабочая) и «Признаки» (catalog editor).
- Pure Python resolution-функция «applicable defects for target device».
- Seed для MVP: 2 узла (Корпус + Дисплей) + одна device-линия (Phone → Apple → iPhone 12 PM) + 6 defects с дефолтной severity.
- Никаких изменений в `compute_bucket`, `analyze_listing_features`, kanban-cards, profile-edit-form.

После shipping Project A:
- Юзер видит admin-инструмент, может редактировать каталог и устройства, расставлять severity.
- Никакого влияния на bucket'инг / уведомления / pipeline.
- Подготовлена база для Project B (Признаки UI читает из catalog) и Project C (auto-gen LLM-промптов из `prompt_hint`).

## 2. Use case (мотивация)

**Проблемы текущего flat-каталога (выявлены 2026-05-13 после Phase 2.1 ship):**

1. **Нет переиспользования** между моделями: defect «Стекло разбито» определён для всех профилей одним feature_key=`display.glass_broken`, но severity (rule) задаётся **per-profile**. При добавлении второго профиля (e.g., iPhone 11) — ручное копирование 20+ rule'ов. Catalog ведёт к dry: «Стекло разбито» определяется один раз, биндится на Phone-уровне → все профили унаследуют.

2. **Нет device-specific defects.** Touch ID существует на iPhone 5s-8/SE, но не на X+. FRP — Android-only, не Apple. iCloud — Apple-only. Сейчас в каталоге `sensors.touch_id` есть, но никакого механизма «не применим к этой модели» — оператор просто ставит rule=ignore на каждом профиле iPhone X+. Catalog даёт `disabled` флаг в binding на конкретной модели.

3. **Иерархия дефектов отсутствует.** `display.replaced` и `display.glass_broken` — оба в `section=display`, но в плоском списке. С деревом узлов («Дисплей» → defects) UI ведёт себя естественнее, и можно добавлять подузлы для сложных компонентов (Камеры → Основная → Wide → defects).

4. **Severity-семантика бедна.** Текущий enum `{green, red, ignore}` смешивает «что делать при defect» и «что делать при unknown». В новой системе разделено: `defect_action ∈ {block, info}` и `unknown_action ∈ {ask, skip}` — 2×2 матрица, чище для UX и расширения.

**Что НЕ решает Project A:**
- Существующий pipeline продолжает работать на flat-каталоге. compute_bucket не переписывается.
- «Признаки» UI на профиле/карточке не переключается на catalog (это Project B).
- LLM-промпты остаются hand-written в `app/prompts/parse_section_*.md` (это Project C).

## 3. Non-goals

- **Миграция текущих 31 feature в новый catalog.** Каталог seed'ится с нуля, минимально (6 defects). Миграция (если решат) — отдельный проект.
- **Замена `ProfileFeatureRule`.** Per-profile rules продолжают существовать для bucket'инга. Catalog — параллельная система.
- **Интеграция с `compute_bucket`.** Catalog не консультируется при bucket-расчёте. Project B решит как.
- **Кнопка «Сгенерировать промпт».** Auto-gen промптов — Project C; в catalog'е только опциональное поле `prompt_hint` для будущего использования.
- **Per-profile overrides поверх catalog'а.** Severity в catalog — глобальная, без per-profile customization (см. §1 Q1).
- **Visual diff** между inherited / set-here / overridden bindings — есть в UI как badge-текст, но без сложной визуализации (highlighting, цветовые подложки).
- **Bulk operations** (привязать сразу все defects узла «Дисплей» одним кликом). MVP — по одному.
- **Soft-delete / audit trail.** Удаление узлов / bindings — hard delete. Recovery — через restore из БД-бэкапа.
- **Multi-language UI.** Только RU.
- **Permissions / роли.** Доступ к `/defects` — тот же `require_user`, что у `/profiles/{id}/feature-rules`.

## 4. Принятые решения (brainstorm 2026-05-13)

| # | Решение | Обоснование |
|---|---|---|
| Q1 | **Глобальный каталог** — severity задаётся при определении defect'а в catalog'е, все profiles используют как есть. Без per-profile overrides в MVP. | Single-operator система; overrides добавим если понадобится. Минимум сложности. |
| Q2 | **Свободная глубина дерева** (free depth) для обоих иерархий. | Корпус/Дисплей остаются 2-level, Камеры/Звук могут быть 3-4 level. Schema = parent_id self-FK. |
| Q3 | **2-dim severity matrix** (`defect_action × unknown_action`). | Чистая семантика (defect-handling vs unknown-handling), легко расширяется. UI = 2 dropdown'а. |
| Q4 | **Две независимые иерархии + bindings таблица.** Feature catalog описывает defects без device-привязки; device tree — отдельно; bindings связывают. | Reuse: «Стекло разбито» описано один раз, биндится на Phone-уровне. Чистое разделение определения и привязки. |
| Q5 | **Inheritance bottom-up resolution.** Для target device walks up до root, для каждого feature берётся binding ближайшего предка. Child может override через создание собственного binding'а или флага `disabled`. | Стандартная CSS-подобная каскадная модель, понятна без долгого объяснения. |
| Q6 | **Bindings только на defect-leaf nodes** (kind='defect'), не на структурных узлах (kind='node'). | App-layer validation. MVP без bulk-bind'а к целому узлу — каждый defect отдельно. |
| Q7 | **`prompt_hint` поле на defect** — опциональный текст для будущего Project C (auto-gen промптов). | Сейчас не используется, но позволит подготовить данные в catalog'е во время Project A работы. |

## 5. Архитектура

Три независимых сущности, связанных через bindings:

### 5.1 Feature catalog (одно дерево)

```
Корпус (узел)
├─ Задняя крышка разбита (defect)
└─ Midframe погнут (defect)
Дисплей (узел)
├─ Стекло разбито (defect)
├─ Полосы / пятна (defect)
└─ Дисплей менялся (defect)
Блокировки (узел)
├─ iCloud привязан (defect)
├─ FRP / MDM (defect)
└─ Vendor account (defect)
```

Чистые определения. Никакой device-привязки. `kind='node'` — структурный узел (имеет детей, не биндится). `kind='defect'` — лист (биндится в bindings).

### 5.2 Device tree (другое дерево)

```
Phone
├─ Apple
│  └─ iPhone 12 Pro Max
└─ Android
   ├─ Xiaomi
   │  └─ Mi 11
   └─ Samsung
      └─ Galaxy S22
```

Free depth. `kind` — soft tag (`type | brand | model`), не enforce.

### 5.3 Bindings

Связь «у этого device-узла применим этот feature-defect с такой severity»:

```
binding: device="Phone"          feature="Стекло разбито"   severity=(block, ask)
binding: device="Apple"          feature="iCloud привязан"  severity=(block, ask)
binding: device="Android"        feature="FRP/MDM"          severity=(block, ask)
binding: device="iPhone 12 PM"   feature="Стекло разбито"   severity=(info, skip)  ← override
```

Resolution для iPhone 12 PM:
- «Стекло разбито» — берём (info, skip) с уровня iPhone 12 PM, **не** (block, ask) с Phone (ближайший предок wins)
- «iCloud привязан» — берём (block, ask) с уровня Apple (унаследовано)
- «FRP/MDM» — не применим (нет binding'а на пути iPhone 12 PM → Apple → Phone; есть только на Android)

## 6. Data model (SQL schema, Alembic 0017)

### `feature_nodes`

```sql
CREATE TABLE feature_nodes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id     UUID REFERENCES feature_nodes(id) ON DELETE CASCADE,
    kind          VARCHAR(16) NOT NULL CHECK (kind IN ('node', 'defect')),
    slug          VARCHAR(64) NOT NULL,
    title         TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    prompt_hint   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (parent_id, slug)
);
CREATE INDEX idx_feature_nodes_parent ON feature_nodes(parent_id);
```

### `device_nodes`

```sql
CREATE TABLE device_nodes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id     UUID REFERENCES device_nodes(id) ON DELETE CASCADE,
    slug          VARCHAR(64) NOT NULL,
    title         TEXT NOT NULL,
    kind          VARCHAR(16),
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (parent_id, slug)
);
CREATE INDEX idx_device_nodes_parent ON device_nodes(parent_id);
```

### `device_feature_bindings`

```sql
CREATE TABLE device_feature_bindings (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_node_id    UUID NOT NULL REFERENCES device_nodes(id) ON DELETE CASCADE,
    feature_node_id   UUID NOT NULL REFERENCES feature_nodes(id) ON DELETE CASCADE,
    defect_action     VARCHAR(16) NOT NULL CHECK (defect_action IN ('block', 'info')),
    unknown_action    VARCHAR(16) NOT NULL CHECK (unknown_action IN ('ask', 'skip')),
    disabled          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (device_node_id, feature_node_id)
);
CREATE INDEX idx_dfb_device ON device_feature_bindings(device_node_id);
CREATE INDEX idx_dfb_feature ON device_feature_bindings(feature_node_id);
```

### App-layer constraints (не в SQL, в repository-layer)

- При создании binding'а — проверка `feature_node.kind = 'defect'` (CHECK constraint в SQL опционально).
- Cycle detection при изменении `parent_id` (рекурсивный обход).
- Slug normalization — kebab-case или snake-case, валидация regex `^[a-z0-9_]+$`.

## 7. Resolution algorithm

Pure Python функция в `app/services/defect_catalog/resolver.py`:

```python
@dataclass
class ResolvedBinding:
    feature_node_id: uuid.UUID
    feature_path: list[str]  # ["Корпус", "Задняя крышка разбита"]
    defect_action: Literal["block", "info"]
    unknown_action: Literal["ask", "skip"]
    inherited_from: uuid.UUID | None  # device_node_id где binding объявлен, или None если на target

async def resolve_applicable_defects(
    session: AsyncSession, target_device_node_id: uuid.UUID
) -> list[ResolvedBinding]:
    """Walk up device tree, collect bindings; for each feature take nearest-ancestor binding.
    Drop disabled. Return list sorted by feature_path."""
    ancestors_desc = await _walk_up(session, target_device_node_id)  # [target, ..., root]
    resolved: dict[uuid.UUID, _Binding] = {}
    for anc in ancestors_desc:
        for b in await _bindings_at(session, anc):
            resolved.setdefault(b.feature_node_id, b)
    return [_render(b, target_device_node_id) for b in resolved.values() if not b.disabled]
```

Производительность для MVP размера (десятки device-узлов, сотни bindings) — O(depth × bindings_per_node), еле заметно. Если catalog вырастет — будем оптимизировать через materialized view или денормализацию.

## 8. Admin UI

### URL и нав

- Sidebar: новый пункт «Дефекты» под «Аналитика».
- Routes:
  - `GET /defects` → redirect на `/defects/devices`
  - `GET /defects/devices` → tab «Устройства»
  - `GET /defects/devices/{id}` → device detail с applicable bindings
  - `GET /defects/catalog` → tab «Признаки»
- Auth: `require_user` (как `/profiles/{id}/feature-rules`).

### Tab «Устройства» (default)

Split-pane: дерево слева, defects справа.

```
┌────────────────────────────────────────────────────────────────┐
│ Дефекты                  [Устройства] [Признаки]               │
├──────────────────┬─────────────────────────────────────────────┤
│ Устройства  [+]  │ iPhone 12 Pro Max                           │
│                  │ Применимые дефекты (12)       [+ Добавить]  │
│ ▼ Phone     [⋯]  ├─────────────────────────────────────────────┤
│   ▼ Apple   [⋯]  │ Корпус / Задняя крышка разбита              │
│     • iPhone 12  │   При находке:    [block  ▾]                │
│     • iPhone 13  │   Если неясно:    [ask    ▾]                │
│   ▼ Android      │   ← inherited from "Phone"      [Override]  │
│     ▼ Xiaomi     │                                             │
│       • Mi 11    │ Корпус / Midframe погнут                    │
│     • Samsung    │   При находке:    [info   ▾]                │
│                  │   Если неясно:    [skip   ▾]                │
│                  │   ← set here                    [Удалить]   │
│                  │                                             │
│                  │ Блокировки / iCloud привязан                │
│                  │   При находке:    [block  ▾]                │
│                  │   Если неясно:    [ask    ▾]                │
│                  │   ← inherited from "Apple"      [Override]  │
│                  │                                             │
│                  │ Блокировки / Touch ID не работает           │
│                  │   ⊘ Disabled (модель без Touch ID)          │
│                  │   ← was inherited from "Apple"  [Re-enable] │
└──────────────────┴─────────────────────────────────────────────┘
```

**Поведение dropdown'ов**:
- На inherited row — изменение severity автоматически создаёт override binding на target device_node.
- На «set here» row — апдейт существующего binding'а.
- «Override» button (явный) — создаёт binding с теми же значениями, после чего можно редактировать.
- «Удалить» (на set-here) — DELETE binding'а; feature снова inherited если есть у предка.
- «Re-enable» — снимает disabled-флаг.

**Кнопка [+ Добавить]** — modal с feature-catalog tree, выбор defect-листа, severity → POST binding.

### Tab «Признаки»

Tree editor:

```
┌────────────────────────────────────────────────────────────────┐
│ Дефекты              [Устройства] [Признаки]                   │
├────────────────────────────────────────────────────────────────┤
│ Каталог признаков                              [+ Корневой узел]│
│                                                                │
│ ▼ Корпус                                              [⋯]      │
│   • Задняя крышка разбита                            [⋯]       │
│   • Midframe погнут                                  [⋯]       │
│ ▼ Дисплей                                             [⋯]      │
│   • Стекло разбито                                   [⋯]       │
│   • Полосы / пятна                                   [⋯]       │
│   • Дисплей менялся                                  [⋯]       │
└────────────────────────────────────────────────────────────────┘

Edit modal:
┌─────────────────────────────────────┐
│ Изменить: iCloud привязан           │
├─────────────────────────────────────┤
│ Title:  [iCloud привязан         ]  │
│ Slug:   [icloud_linked           ]  │
│ Parent: [Блокировки           ▾ ]   │
│ Kind:   [defect              ▾ ]    │
│                                     │
│ Prompt hint (для Project C, опц):   │
│ ┌─────────────────────────────────┐ │
│ │ defect — упоминания «iCloud»…   │ │
│ │ ok — «iCloud чист»              │ │
│ └─────────────────────────────────┘ │
│                       [Cancel] [Save]│
└─────────────────────────────────────┘
```

### Стек реализации

- FastAPI routes под `/defects/*` в `app/web/routers/defects.py` (новый файл).
- Jinja2 templates в `app/web/templates/defects/`:
  - `_layout.html` (общий wrapper с табами)
  - `devices.html` (split-pane)
  - `catalog.html` (tree)
  - `_partials/feature_node_row.html`, `_partials/binding_row.html`, `_partials/device_node_row.html` (HTMX-friendly partials)
- HTMX для inline-edits: severity dropdown `hx-post="/defects/bindings/{id}" hx-swap="outerHTML"`.
- Tree collapse через `<details>` — без JS.
- Modal через HTMX `hx-target="#modal"`.
- Tailwind + Avito-Cosplay tokens (off-white surface + green accents per `AvitoSystemUI/styles.css`).

## 9. API routes

| Method | Path | Описание |
|--------|------|----------|
| GET    | `/defects` | redirect → `/defects/devices` |
| GET    | `/defects/devices` | список device-узлов (root level + один selected) |
| GET    | `/defects/devices/{id}` | device detail + applicable bindings |
| POST   | `/defects/devices` | создать device-узел `{parent_id, slug, title, kind}` |
| PATCH  | `/defects/devices/{id}` | rename / move / re-sort |
| DELETE | `/defects/devices/{id}` | удалить (CASCADE на детей + bindings) |
| GET    | `/defects/catalog` | feature-catalog tree |
| POST   | `/defects/catalog` | создать feature-node `{parent_id, slug, title, kind, prompt_hint}` |
| PATCH  | `/defects/catalog/{id}` | edit |
| DELETE | `/defects/catalog/{id}` | удалить |
| POST   | `/defects/bindings` | создать binding `{device_node_id, feature_node_id, defect_action, unknown_action}` |
| PATCH  | `/defects/bindings/{id}` | update severity / toggle disabled |
| DELETE | `/defects/bindings/{id}` | удалить binding |

Все POST/PATCH/DELETE возвращают HTMX-rendered partial для inline-swap. JSON-API не нужен для MVP (no external consumers).

## 10. MVP seed

Отдельный скрипт `scripts/seed_defect_catalog.py` (не в migration, чтобы можно было перезапускать и менять seed без `alembic stamp`):

**Feature catalog** (2 узла + 6 defects):
- Корпус (node)
  - Задняя крышка разбита (defect)
  - Midframe погнут (defect)
  - Midframe сломан (defect)
- Дисплей (node)
  - Стекло разбито (defect)
  - Полосы / пятна (defect)
  - Дисплей менялся (defect)

**Device tree** (1 линия):
- Phone (type)
  - Apple (brand)
    - iPhone 12 Pro Max (model)

**Bindings** (6, все на Phone-уровне для inheritance):
- Phone × Задняя крышка разбита → (info, skip) — cosmetic, не блочим
- Phone × Midframe погнут → (info, ask) — лучше уточнить
- Phone × Midframe сломан → (block, ask) — критичный
- Phone × Стекло разбито → (info, skip) — cosmetic
- Phone × Полосы / пятна → (info, ask) — может быть критичным
- Phone × Дисплей менялся → (info, ask) — важно для цены, не блочим

Юзер может изменить любую severity через UI после seed'а.

## 11. Error handling

- **Cycle при изменении parent_id**: 400 Bad Request, сообщение «Узел не может быть собственным предком».
- **Удаление узла с детьми / bindings**: CASCADE — без подтверждения в MVP (UI показывает counter «N defects, K bindings будут удалены», но не блокирует).
- **Binding на kind='node'**: 400 Bad Request, «Binding можно создать только на defect (leaf)».
- **Duplicate slug в parent**: 400 Bad Request, «Slug уже занят».
- **Inline-edit failure** (HTMX): swap partial с error state (red border + text).

## 12. Testing strategy

**Unit tests** (`tests/defect_catalog/`):
- `test_resolver.py` — resolution с inheritance, override, disabled, multi-level
- `test_cycle_detection.py` — parent_id changes
- `test_slug_validation.py` — regex, uniqueness
- `test_seed_idempotent.py` — повторный запуск seed не дублирует rows

**Integration tests** (`tests/web/`):
- `test_defects_routes.py` — все 12 endpoints, проверка HTML responses
- `test_defects_htmx.py` — inline edits возвращают правильные partials
- `test_defects_cascade.py` — DELETE с children корректно каскадит

Target: 25-30 новых тестов, все pass перед мержем.

## 13. Path forward (Project B / C)

**Project B — Признаки UI на профиле/карточке (после Project A):**
- Profile-edit form читает applicable defects через resolver (target = profile.device_node_id, новое поле в SearchProfile).
- Kanban-card «Признаки» блок берёт defect-list из catalog'а (вместо текущего `defect_taxonomy` global).
- `compute_bucket` подменяется: на input приходит resolved bindings + listing_features.state, severity (defect_action/unknown_action) определяет poведение.
- Backward-compat: profile без `device_node_id` продолжает работать на старом `ProfileFeatureRule`.

**Project C — Auto-gen LLM-промптов:**
- Catalog defects имеют `prompt_hint`. Project C добавит code-generator: для target device_node берёт all applicable defects, группирует по feature-tree узлу, генерит section-prompts в формате `parse_section_*.md`.
- Заменяет hand-written prompts.
- Cache invalidation при изменении catalog'а.

**Не часть Project A.** Перечислено для понимания roadmap'а.

## 14. Open questions

- **Q14.1 Cycle detection performance.** Для MVP размера (десятки узлов) — обход рекурсивно. Если catalog вырастет до 1000+ узлов — нужно closure-table или materialized path. Откладываем до данных.
- **Q14.2 Seed re-runs.** Если юзер хочет переseed'ить catalog (сбросить bindings), нужен ли admin endpoint «Reset catalog to defaults»? MVP — нет, манипуляция через psql.
- **Q14.3 Bulk-bind на узел.** Юзер выразил желание «привязать все defects узла Дисплей одним кликом». MVP — нет, добавим в Project A.1 если понадобится. Workaround — несколько кликов.
- **Q14.4 Импорт/экспорт catalog'а.** JSON dump для бэкапа catalog state — полезно но не блокирует MVP. Добавим если возникнет.
