# CONTINUE — следующая сессия (2026-05-16 после defect-catalog merge + Phase A binding UI)

> **Если ты Claude в новой сессии:** прочитай этот файл + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`.
>
> **Главное:** `feat/defect-catalog` смержена в `main` (`7cf6277`). На прод-main сегодня (2026-05-15) ещё 5 коммитов поверх merge — все живут на проде + origin. Defect catalog admin UI законнчен функционально: создание/редактирование/удаление дефектов и разделов, привязка к устройствам с раскрытием section→descendants. Pipeline integration (compute_bucket использует section bindings) — следующий блок.

---

## §1. TL;DR

**Что shipped в сессии 2026-05-15 (5 коммитов поверх merge):**

| Commit | Что |
|---|---|
| `d900157` | §4.2.4 P0 — ROOT-add форма реагирует на ОК/Отмена (B1 dropdown kind value + B2 Cancel target + B3 after-request listener) + tighter tree row layout + `kind_ru` Jinja-filter |
| `79db05e` | Tree colors — разделы blue 900→400 по глубине, дефекты slate-500 |
| `2e0f786` | Reviewer Issue 1 — PATCH device/feature ловят `IntegrityError` на дубль-слаге → 400 RU |
| `7cf6277` | **Merge feat/defect-catalog → main** (--no-ff, 51 коммитов) |
| `d32c49c` | edit-форма позволяет менять Тип (Раздел/Дефект), не только при создании |
| `0ccb688` | UI добавления binding на странице device_detail + reviewer Issue 4 (`create_binding_endpoint` ловит IntegrityError) |
| `55349e8` | **P0 bool→int bug в `create_binding`** (asyncpg строг к int vs bool) + section bindings allowed (убран kind='defect' check) + иерархия в dropdown с path-prefix |
| `010e221` | depth-first sort + nbsp-табуляция в binding dropdown (раньше «Камера раскинута по списку») |
| `3ce3a89` | section binding expansion: resolver разворачивает section в synthetic descendant rows; `inherited_from_section` поле в ResolvedBinding; binding_row.html state machine из 3 состояний |

**На сегодня (2026-05-16) в порядке приоритета:**

| # | Шаг | Время | Блокер? |
|---|---|---|---|
| §5.1 | Sanity verify | 1 мин | — |
| §5.2 | **Pipeline integration: compute_bucket использует section bindings** (резолвер уже эмитит, downstream — нет) | 2-4 ч | UI без эффекта пока |
| §5.3 | Reviewer Issue 2 — DELETE override silent vanish (inherited binding не возвращается) | 30 мин | UX-баг |
| §5.4 | Reviewer Issue 3 — visit-set guard в resolver/cycle walkers | 30 мин | defence vs corrupted data |
| §5.5 | Minor cleanups — англицизмы остатки, naming | 30 мин | низкий |
| §5.6 | Project C brainstorm — авто-генерация LLM-промптов через квиз | 30-60 мин | без блокера, но логично следующее |

---

## §2. Production state (2026-05-15 21:00 UTC)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (ssh root@, key auth) |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt `drwgozasaypgphkxyizt`, pooler 6543 transaction mode |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Alembic head** | `0017_defect_catalog` (без изменений сегодня) |
| **main HEAD** | `3ce3a89` — section binding expansion |
| **/defects admin UI** | Live, полностью функционален: CRUD устройств + разделов + дефектов, добавление binding'ов с иерархическим dropdown, section expansion в descendants, цветовая дифференциация по глубине |

### §2.1 Containers (10)
Только `avito-system-avito-monitor-1` пересобирался в этой сессии (другие 6 Python-сервисов не загружают `app.web.defects` / `app.services.defect_catalog`, образы остались).

### §2.2 Catalog state на prod

```
Разделы (11) с иерархией до 5 уровней:
  Блокировки [Раздел]
    iCloud FMI [Дефект]
    Экранный код пароль [Дефект]
  Дисплей [Раздел]
    Дисплей менялся [Дефект]
    Не показывает [Дефект]
    Полосы / пятна [Дефект]
    Стекло разбито [Дефект]
  Звук [Раздел]
    3 defects
  Камера [Раздел]
    Основная [Раздел]
      Камера 0,5 [Раздел]
        3 defects
      Камера 1х [Раздел]
        3 defects
      Камера Zoom [Раздел]
        3 defects
    Фронтальная [Раздел]
      3 defects
  Кнопки [Раздел]
    4 defects
  Корпус [Раздел]
    Midframe погнут [Дефект]
    Midframe сломан [Дефект]
    Задняя крышка разбита [Дефект]

Всего: 11 sections + 28 defects = 39 нод (плюс 2 nested intermediate sections)

Устройства:
  Phone (root)
    Apple
      Серия 11 .. Серия 14 — каждая с подсериями (iPhone 11, 11 Pro, 11 Pro Max и т.д.)
```

### §2.3 Bindings на prod

На момент записи CONTINUE.md — нет permanent bindings (юзер очищал в smoke-тестах). Seed-binding'ов из 2026-05-13 нет — могли быть удалены через UI. **Это не блокер** — каталог структуры важнее, привязки добавляются легко.

---

## §3. Что сделано подробно (по коммитам)

### §3.1 `d900157` — §4.2.4 P0 fix + tree layout + kind_ru

**Проблема:** Юзер создавал корневой признак — ОК и Отмена не реагировали. Без DevTools диагностика через чтение кода + curl на прод:

- **B1**: dropdown был `<option value="section">Раздел</option>`, но backend (Python check + DB CheckConstraint `IN ('node','defect')`) рейзил → 400 → HTMX default не свопит 4xx → silent fail.
- **B2**: Cancel `hx-target="this"` свопил только саму кнопку, форма оставалась.
- **B3**: после успешного POST `#feature-tree` обновлялся, но форма в `#feature-form-mount` оставалась — юзер не видел feedback.

**Fix в одном файле `node_form.html`:**
- `<option value="node">Раздел</option>` (соответствует backend constraint)
- Cancel: `hx-target="closest form" hx-swap="outerHTML"`
- Form: `hx-on::htmx:after-request="if(event.detail.successful) this.remove()"`

Плюс tree row layout: `flex-1` снят с названия → кнопки `[+][✏][🗑]` вплотную к именам, `hover:bg-avito-elev` подсветка ряда.

Плюс `kind_ru` Jinja-filter: `[node]`/`[section]`→«Раздел», `[defect]`→«Дефект» (англицизмы в tree устранены).

### §3.2 `79db05e` — tree colors по глубине

`node_color(kind, depth)` Jinja-global возвращает Tailwind text-* класс:
- `defect` → `text-slate-500` (одинаково на любой глубине)
- `node|section` по глубине: 0=`text-blue-900` (тёмный), 1=`text-blue-700`, 2=`text-blue-500`, ≥3=`text-blue-400` (светлый)

`feature_tree.html` макрос `render(entry, depth=0)` рекурсивно прокидывает `depth+1` детям.

### §3.3 `2e0f786` — Reviewer Issue 1 (PATCH IntegrityError)

Final review subagent (Opus) нашёл что POST handlers уже ловят `IntegrityError` (commit `55bcefb`), но PATCH'и нет. Дубль-slug при переименовании → 500. Fix: mirror того же try/except IntegrityError в `patch_device_endpoint` + `patch_feature_endpoint`. RU error.

### §3.4 `7cf6277` — Merge feat/defect-catalog → main

51 commit, ~5k LOC, `--no-ff` merge commit. После merge на проде уже был этот код — это git hygiene, не requires deploy. Origin синхронизирован.

### §3.5 `d32c49c` — edit-форма меняет Тип

`update_feature_node` уже принимал `kind` параметр, но `patch_feature_endpoint` не пробрасывал из формы, и dropdown показывался только в add-режиме. Fix: убрал условие `mode == 'add'` в node_form.html (теперь dropdown и в edit), добавил `prefill.kind` для preselect, в endpoint добавил Form-параметр.

### §3.6 `0ccb688` — Add binding UI + Issue 4

На странице `/defects/devices/{id}` не было кнопки «Добавить дефект» — юзер удалял binding'и и потом не мог добавить новые.

Добавлено:
- GET `/defects/devices/{device_id}/bindings/new` → form fragment с dropdown'ом всех defects + severity selects.
- GET `/defects/devices/{device_id}/bindings/cancel-form` → empty (для Cancel).
- `+ Добавить дефект` button + `#binding-form-mount` div + `#bindings-empty-state` id в `device_detail.html`.
- POST успех → form removes self + empty-state removes (через `hx-on::after-request`).
- Reviewer Issue 4: `create_binding_endpoint` ловит `IntegrityError` (`uq_dfb_device_feature`) → 400 «Привязка для этого дефекта уже существует».

### §3.7 `55349e8` — **P0 bool bug + section bindings + hierarchy**

**Юзер обнаружил manual smoke'ом:** «дефект не добавляется, на ОК нет реакции». Диагностика через curl POST на прод → 500 от asyncpg:

```
asyncpg.exceptions.DataError: invalid input for query argument $6: 0
(a boolean is required (got type int))
```

Root cause: `repository.py:424` `create_binding` передавал `"dis": 1 if disabled else 0`, но Postgres колонка `disabled` BOOLEAN. asyncpg строгий: int не кастит в bool. SQLite-тесты не ловили (там типы мягкие). Тот же класс багов как `b134165` (dialect-aware NOW).

Fix:
- `"dis": bool(disabled)` в `create_binding` + `update_binding`.
- Убран check `kind != 'defect'` в `create_binding` — section bindings allowed (юзер запросил «добавлять любую ветвь»).
- `list_all_features_with_path(session)` репо-хелпер: возвращает `[(FeatureNodeRow, path_list), ...]` — все feature_nodes с их полными paths.
- `binding_form.html` dropdown: «Раздел / Дефект [тип]» формат с полным path-prefix.

### §3.8 `010e221` — depth-first sort + индентация

Юзер запросил: «Камера раскинута по списку, нужна сортировка». Python tuple-sort натурально даёт depth-first walk:

```python
out.sort(key=lambda x: x[1])  # path is list[str]
```

Plus `indent_for_path(path)` Jinja-global возвращает `'  ' * (depth-1)` (nbsp × 2 per level). Template option = indent + leaf_title + [kind_ru], path-prefix убран — табуляция самодостаточна.

### §3.9 `3ce3a89` — **section binding expansion** (главное архитектурное)

Юзер запросил: «нужно отображать всю ветку, ветка принимает значение основного раздела, но это по умолчанию, потом можно изменить».

**Resolver changes:**
- Новое поле `ResolvedBinding.inherited_from_section: uuid.UUID | None`.
- Второй проход в `resolve_applicable_defects`: для каждого section-binding (kind != 'defect') получает descendants через `list_descendant_defects()` (BFS, visit-set guard) и эмитит synthetic ResolvedBinding для каждого defect descendant, **если у него нет direct binding** (direct wins, override).

**`list_descendant_defects(session, root_id)`** — новый репо-хелпер: BFS по feature tree от root_id, возвращает только `kind='defect'` listья.

**`binding_row.html` — 3-state machine:**
- `is_own` (no `inherited_from`, no `inherited_from_section`): editable severity + «← задано здесь» + Удалить
- `is_inherited_device` (`inherited_from` set, не synthetic): read-only + «← унаследовано» + Задать здесь
- `is_synthetic` (`inherited_from_section` set): read-only + «← по умолчанию из раздела» + Задать здесь + margin-left отступ по `feature_path` depth

DOM id ряда изменён с `binding-{binding_id}` на `binding-{binding_id}-{feature_node_id}` — synthetic rows шарят `binding_id`, нужен unique id для HTMX swap.

Тестов: +2 (section expansion + override precedence). Total 84 defects+resolver tests, все green.

---

## §4. Backlog (приоритизированный)

### §4.1 ★★★ Pipeline integration (Phase B) — `compute_bucket` использует section bindings

**Сейчас:** UI/DB готовы. Юзер биндит section «Корпус» → resolver возвращает 4 ResolvedBinding (1 section + 3 synthetic descendants). На странице device_detail видно.

**Не работает:** `compute_bucket` (real-time классификация лотов) использует старую flat-схему `ProfileFeatureRule` или просто `resolve_applicable_defects`. Если он использует resolver — то synthetic rows уже эмитятся, проверить что обработка корректна на kind='defect' feature_node_id (а они корректны — synthetic emit-ит для defect descendants). **Возможно уже работает после `3ce3a89`!**

**Что проверить на сессии 2026-05-16:**

1. Найти где `compute_bucket` или его аналог вызывает resolver: `grep -rn "resolve_applicable_defects" avito-monitor/`
2. Прогнать unit-test или integration-test compute_bucket с section binding на тестовом профиле.
3. Если нужно — adapter layer для синтетических rows.

Скорее всего работает out-of-the-box (synthetic rows имеют корректный `feature_node_id` defect-leaf и severity), но это нужно подтвердить.

### §4.2 ★★ Reviewer Issue 2 — DELETE override → inherited не возвращается

**Где:** `defects.py:323-330` (`delete_binding_endpoint`)
**Симптом:** Юзер кликает «Удалить» на override binding (например, override на iCloud FMI при наличии inherited от section «Блокировки»). Row vanishes. **Но section binding всё ещё существует** — synthetic row должен вернуться. Сейчас не возвращается до reload.
**Fix:** После delete, перерезолвить device → найти если есть applicable binding для этого feature_node_id (synthetic из section или inherited из ancestor device) → отдать его HTML; иначе отдать empty.

Реализация:
```python
@router.delete("/bindings/{binding_id}", ...)
async def delete_binding_endpoint(binding_id, target_device_id, feature_node_id, ...):
    # Get feature_node_id from form/query param (need to add)
    await delete_binding(session, binding_id)
    # Re-resolve and find any binding that still applies to this feature_node_id
    resolved = await resolve_applicable_defects(session, uuid.UUID(target_device_id))
    for r in resolved:
        if r.feature_node_id == feature_node_id:
            return render_binding_row(r, target_device_id)
    return HTMLResponse("", status_code=200)  # truly gone
```

Front-end: добавить `hx-vals` с `target_device_id` + `feature_node_id` на Удалить кнопку, обновить swap target.

### §4.3 ★ Reviewer Issue 3 — visit-set guard в walker'ах

**Где:** `resolver.py:22-35` (`_walk_up_device`), `:38-51` (`_feature_path`); `repository.py` cycle checks в `update_feature_node`/`update_device_node`.

**Симптом:** Если DB ever ends up with pre-existing cycle (через прямой SQL, backup restore, или future bug), walker'ы зависают.

**Fix:** добавить `seen: set[uuid.UUID]` в каждый цикл, на duplicate break (или raise RuntimeError в cycle-check).

Уже сделано в `list_descendant_defects` и `list_all_features_with_path` (path_for). Нужно добавить в остальные 4 walker'а.

### §4.4 ★ Minor (8 reviewer items)

- `defects.py:38-39` — комментарий «lazily inside handlers» врёт (import на module level)
- `defects.py:254` — `"Device not found"` → `"Устройство не найдено"` (уже сделано в `0ccb688`, проверить)
- `_partials/device_detail.html:7` — `"Loading…"` → `"Загрузка…"` (уже сделано в `0ccb688`, проверить)
- `_partials/device_detail.html` — extends full `_layout.html`, имя не должно быть `_partials/` — переименовать в `defects/device_detail.html`
- `_UNSET` экспортируется с underscore — code smell
- Edit form `prompt_hint=""` пишет пустую строку в DB вместо NULL — может ломать downstream `if prompt_hint is None`
- `INSERT OR IGNORE` тест vs `ON CONFLICT` production — гap в покрытии
- `test_defects_devices_tree_empty_200` без content assertions

### §4.5 §4.2.5 kind=node/section rename (deferred)

**Известно:** seed использует `kind='node'` для разделов, спека Project A → `section`. UI через `kind_ru` маппит обе версии в «Раздел» — forward-compatible.

**Не делать без брейнсторма** — нужна alembic-миграция + UPDATE seed + check всех мест где kind проверяется (`repository.py:109`, `:232`, dropdown в `node_form.html`). Имеет смысл сделать совместно с §4.1 pipeline integration или после.

### §4.6 Project C brainstorm — авто-генерация LLM-промптов

**Идея юзера:** взять catalog (feature_nodes с `prompt_hint`) + applicable defects для конкретного device-node, и сгенерировать section-prompts автоматически через **meta-prompt → Sonnet/Haiku**. Возможно в формате «квиза» где LLM задаёт уточняющие вопросы.

**Что есть сейчас:**
- Catalog `feature_nodes` с `prompt_hint` полем на каждом defect.
- 6 hand-written section-prompts в `app/prompts/extract_*.md`.
- Существующий `compute_bucket` использует эти 6 + flat `ProfileFeatureRule`.

**НЕ начинать имплементацию без brainstorm.** Обязательно через `superpowers:brainstorming` skill. Вопросы:
1. UX квиза — где живёт (admin UI? CLI? webhook?)
2. Какая модель (Sonnet preferred, Haiku если потянет)
3. Design meta-prompt template
4. Возможно перед Project C сделать Project B (Признаки UI читает из catalog для compute_bucket)

### §4.7 Pre-existing test failures (baseline — не регрессии)

`pytest -q` на main:
- 465+ passed (84 defects+resolver+repo, остальное)
- 8 failed (те же что и до — `avito_mcp`, `health_checker`, `polling`)
- 2 skipped

8 failures не трогать — это backlog других модулей.

---

## §5. Что делать в новой сессии

### §5.1 Sanity verify (1 мин)

```bash
cd c:/Projects/Sync/AvitoSystem
git status --short                     # должно быть пусто (untracked DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md ОК)
git log --oneline main -5              # top: 3ce3a89 section binding expansion
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "/defects=%{http_code}\n" https://avitosystem.duckdns.org/defects'
# Expected: /defects=303
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 alembic current 2>&1 | tail -1'
# Expected: 0017_defect_catalog (head)
```

### §5.2 Pipeline integration check (приоритет 1)

**Цель:** убедиться что compute_bucket (или его эквивалент) уже корректно обрабатывает synthetic ResolvedBinding rows, или внести изменения.

```bash
# 1. Найти где resolver используется
grep -rn "resolve_applicable_defects" avito-monitor/app/ avito-monitor/tests/ | grep -v "\.pyc"

# 2. Проверить compute_bucket код (если он использует defect_catalog)
ls avito-monitor/app/services/defect_features/
# Это старый Phase 2.1 модуль — отдельный от defect_catalog. Возможно compute_bucket
# ещё на старой flat-схеме ProfileFeatureRule. Тогда integration с catalog — отдельная
# задача (Project B).
```

Если compute_bucket НЕ использует resolver → нужен Project B первым (UI «Признаки» читает из catalog). Скорее всего так и есть. Тогда §5.2 → brainstorm Project B перед Project C.

### §5.3 Issue 2 fix (DELETE override returns inherited)

См. §4.2 для plan. TDD:
1. Test: DELETE override binding when section binding exists → response contains synthetic row HTML.
2. Implement re-resolve in delete_binding_endpoint.
3. Update front-end (binding_row.html `hx-delete` to pass `target_device_id` + `feature_node_id`, swap target = own row id).

### §5.4 Issue 3 fix (visit-set guard)

Добавить `seen: set[uuid.UUID]` в:
- `resolver._walk_up_device`
- `resolver._feature_path`
- `repository.update_feature_node` cycle-check (L186-199)
- `repository.update_device_node` cycle-check (L317-327)

Тесты для каждого — сложно создать cycle в SQLite (FK CASCADE мешает), может быть достаточно RuntimeError-raise теста через мок.

### §5.5 Minor cleanups (по желанию)

См. §4.4. Маленькие правки.

### §5.6 Project C brainstorm

`superpowers:brainstorming` skill обязательно. См. §4.6 вопросы.

### §5.7 Что НЕ делать без подтверждения

- Force-push в main
- Дропать `feature_nodes` / `device_nodes` / `device_feature_bindings`
- Изменять backend POST/PATCH/DELETE routes без тестов
- Менять словарь severity_ru / kind_ru без подтверждения
- Touch `app/services/defect_features/` (старый Phase 2.1 — отдельный модуль, не путать с `defect_catalog`)

---

## §6. Архитектурные нюансы (нужно помнить)

### §6.1 Два модуля с похожим именем

| Модуль | Где | Что |
|---|---|---|
| `app.services.defect_features` | `services/defect_features/` | Phase 2.1: flat-схема (31 feature, ProfileFeatureRule), используется compute_bucket. Старый. |
| `app.services.defect_catalog` | `services/defect_catalog/` | Project A: hierarchical (sections + defects + bindings), новый. UI на /defects. **Пока НЕ интегрирован в compute_bucket** — это Project B. |

**Никогда не путать.** Текущий compute_bucket работает на flat-схеме, lot classification жива и работает на проде. Catalog — параллельный, для admin UI.

### §6.2 ResolvedBinding state machine (важно для binding_row.html)

После `3ce3a89`:

```python
@dataclass
class ResolvedBinding:
    binding_id: uuid.UUID          # DB row id (может шариться synthetic rows из одного section binding)
    feature_node_id: uuid.UUID     # для synthetic — descendant defect, не source section
    feature_path: list[str]
    defect_action: Literal["block", "info"]
    unknown_action: Literal["ask", "skip"]
    inherited_from: uuid.UUID | None         # device-tree inheritance (другой device, не current)
    inherited_from_section: uuid.UUID | None # feature-tree inheritance (section на same device)
```

Три состояния в UI:
- `is_own`: `inherited_from is None AND inherited_from_section is None` → editable, Удалить
- `is_inherited_device`: `inherited_from is not None AND inherited_from_section is None` → read-only, Задать здесь
- `is_synthetic`: `inherited_from_section is not None` → read-only, Задать здесь, indented

### §6.3 Section binding override precedence

В resolver:
1. Direct bindings collected first (sections + defects вместе).
2. Section expansion only adds synthetic rows для descendants which don't already have direct binding.
3. **Multiple section bindings**: если два разных section binding'а покрывают один defect, первый encountered wins (в текущей implementation). В реальности это редкий случай (юзер бы вручную не создал такое).

### §6.4 DOM id для binding row

`binding-{binding_id}-{feature_node_id}` — НЕ просто `binding-{binding_id}`. Synthetic rows шарят `binding_id` (source section) но имеют разные `feature_node_id`. Шаблон правильно генерит unique IDs.

### §6.5 SQLite vs Postgres gotchas

- **bool/int**: asyncpg строг (см. §3.7). Always pass Python bool, not int.
- **datetime**: `_now_expr(session)` helper — dialect-aware.
- **prepared statements**: pooler transaction mode + asyncpg = `prepared_statement_cache_size=0` обязательно (см. main DATABASE_URL).

### §6.6 HTMX 2.0 swap of 4xx ignored by default

`htmx.config.responseHandling` НЕ свопит 4xx default. Если backend returns 400 RU error, юзер видит **silent fail**. Нужно либо настроить config, либо использовать HX-Trigger headers, либо вызывать errors на success-path.

Сейчас 400-ответы написаны для случая «user видит через DevTools». Можно потом улучшить UX.

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md + auto-memory (особенно defect-catalog-merged-2026-05-15
и project_c_quiz_prompts.md).

Состояние main:
  3ce3a89 feat(defects): section binding expansion в descendant defect rows
  010e221 feat(defects): depth-first sort + табуляция в binding dropdown
  55349e8 fix(defects): create_binding bool→int + section bindings + иерархия
  0ccb688 feat(defects): UI добавления binding + Issue 4 fix
  d32c49c feat(defects): edit-форма позволяет менять Тип (Раздел/Дефект)
  7cf6277 Merge Project A + polish — defect catalog admin
  ... плюс 2e0f786, 79db05e, d900157 (этого утра)

Defect catalog admin полностью функционален: CRUD устройств/разделов/дефектов,
binding UI с иерархическим dropdown, section→descendant expansion, цветовая
дифференциация по глубине. Deployed + verified на проде.

На сегодня (приоритет):
  1. §5.2 Pipeline integration check — compute_bucket уже работает с section
     bindings через resolver, или нужна интеграция?
  2. §5.3 Reviewer Issue 2 — DELETE override should return inherited binding
  3. §5.4 Reviewer Issue 3 — visit-set guard в walker'ах (defence)
  4. §5.6 Project C brainstorm — auto-gen LLM-промптов через квиз

Production:
- VPS 81.200.119.132 (ssh root@, key auth)
- Cloud Supabase Frankfurt drwgozasaypgphkxyizt
- Alembic head 0017_defect_catalog
- https://avitosystem.duckdns.org/defects — full CRUD + binding management

Архитектура (ВАЖНО):
- defect_features (старый Phase 2.1, flat) ≠ defect_catalog (новый Project A,
  hierarchical). compute_bucket пока на старой схеме.
- ResolvedBinding имеет 3 состояния: own / inherited_from device / synthetic
  (inherited_from_section).
- bool/int в asyncpg: always Python bool, никогда int.
- DOM id ряда binding: `binding-{binding_id}-{feature_node_id}` для synthetic
  rows которые шарят binding_id.

НЕ делать без подтверждения:
- Force-push, drop tables, изменения compute_bucket schema
- Brainstorm Project C перед имплементацией (через superpowers:brainstorming)
- §4.2.5 kind=node→section rename — отдельная задача с миграцией
```

---

## §8. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md` (Supabase URLs, ключи, VPS IPs, JWT secrets)
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## §9. Ссылки на актуальные документы

- `DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md` — spec Project A core
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-impl.md` — план Project A (34 tasks, shipped)
- `DOCS/superpowers/specs/2026-05-13-defect-catalog-polish.md` — spec polish bundle
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-polish.md` — план polish bundle (12 tasks, shipped)
- `DOCS/REFERENCE/README.md` — карта production
- `DOCS/DECISIONS.md` — ADR-001..011

---

## §10. Известные грабли (актуальны 2026-05-15)

### Из этой сессии (новое)

- ❌ **asyncpg bool/int**: `1 if disabled else 0` ломает Postgres BOOLEAN column. SQLite-тесты не ловят. Always `bool(disabled)`. См. §3.7.
- ❌ **HTMX 4xx silent fail**: default config не свопит 4xx. RU error в backend → невидимо юзеру. См. §6.6.
- ❌ **Synthetic binding row DOM id**: `binding-{bid}-{fnid}` для unique. См. §6.4.
- ❌ **3-state binding_row.html**: own/inherited_device/synthetic. См. §6.2.
- ❌ **node_color / kind_ru / indent_for_path** — три Jinja globals/filter, регистрируются в `defects.py` после `templates = Jinja2Templates(...)`.

### Sticky из предыдущих sessions

- ❌ Alembic в старом контейнере не видит новый migration — recreate ALL Python-сервисов перед `alembic upgrade head` (НЕ в этой сессии — миграций не было).
- ❌ Docker compose `build avito-monitor` НЕ обновляет образы worker/scheduler/messenger-bot/telegram-bot/health-checker/avito-mcp — у каждого свой image SHA. Для polish-only изменений в defects.py это OK.
- ❌ pg_dump 16 vs server 17.6 — use `docker run --rm postgres:17 pg_dump ...`
- ❌ Cloud Supabase pooler search_path пустой — psql напрямую нужен `SET search_path=public` или `public.<table>`.
- ❌ DATABASE_URL preprocessing для libpq tools: `s|postgresql+asyncpg://|postgresql://|; s/[?&]prepared_statement_cache_size=0//; s/[?&]ssl=require/?sslmode=require/`.
- ❌ pgbouncer/Supavisor transaction-mode + asyncpg prepared statements = `DuplicatePreparedStatementError`. Raw asyncpg `statement_cache_size=0`.
- ❌ `pytest_plugins` в non-top-level conftest deprecated. Define fixtures напрямую.
- ❌ Никогда не deploy'ить через rsync с Windows — нет в системе. Use `tar | ssh tar -xf`.
- ❌ TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`.
- ❌ Hardcoded `datetime('now')` в UPDATE — SQLite-only. Use `_now_expr(session)`.
- ❌ FastAPI route registration order: literal-segments перед UUID-catchall в `defects.py`.
- ❌ `device_detail.html` extends full `_layout.html` → требует `_layout_context()` в route. См. `3c92d3a`.
- ❌ Jinja templates на module-load level vs lazy — `routers.py` импортируется первым, `defects.py` после, поэтому import `_layout_context` из routers безопасен.

---

## §11. Deploy log (для архива)

```
== 2026-05-15 morning ==
~07:00 Z  CONTINUE.md прочитан
~07:05 Z  §4.2.4 P0 диагноз через код-чтение + curl (без DevTools)
~07:15 Z  TDD: 3 failing tests → fix node_form.html
~07:25 Z  Deploy avito-monitor (d900157)
~07:35 Z  Юзер confirm работает

== 2026-05-15 afternoon ==
~08:00 Z  Tree row layout polish (79db05e продолжение d900157)
~08:30 Z  kind_ru filter (d900157)
~09:00 Z  Tree colors по глубине (79db05e)

== 2026-05-15 — review + merge ==
~10:00 Z  Final code-review Opus subagent — Yes with Issue 1
~10:15 Z  Issue 1 fix (2e0f786) + deploy
~10:30 Z  Merge feat/defect-catalog → main (7cf6277) + push origin

== 2026-05-15 — kind edit + binding UI ==
~11:00 Z  edit-форма меняет Тип (d32c49c) + deploy + push
~12:00 Z  Add binding UI + Issue 4 (0ccb688) + deploy + push

== 2026-05-15 — bool bug + sections + hierarchy ==
~13:00 Z  Юзер: «ОК не реагирует на binding»
~13:10 Z  Curl на прод → asyncpg bool/int DataError found
~13:30 Z  Fix bool + section bindings allowed + hierarchy в dropdown (55349e8) + deploy

== 2026-05-15 — sort + indent ==
~14:30 Z  Юзер: «Камера раскинута, нужна табуляция»
~14:45 Z  Depth-first sort + nbsp-indent (010e221) + deploy

== 2026-05-15 — section expansion ==
~15:30 Z  Юзер: «нужно отображать всю ветку»
~16:00 Z  Resolver expansion + binding_row state machine (3ce3a89) + deploy
~17:00 Z  CONTINUE.md записан под завтра
```

---

**Total в сессии:** 9 commits, ~600 строк добавлено в `defect_catalog/` модуль, **0 регрессий**. Defects суite вырос с 27 до 84 (+57 новых тестов, все green). Pipeline integration осталась следующим блоком.
