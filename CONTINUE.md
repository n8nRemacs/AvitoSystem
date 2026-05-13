# CONTINUE — следующая сессия (2026-05-15 после Project A + polish bundle, перед merge)

> **Если ты Claude в новой сессии:** прочитай этот файл + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`.
>
> **Главное:** ветка `feat/defect-catalog` имеет полный Project A + polish-bundle (12 polish-коммитов поверх 30 Project-A-коммитов). **Deployed на prod**, **НЕ merged в main**. Юзер вчера вечером пошёл спать перед manual smoke. На сегодня план: smoke → merge → следующее направление (UI cleanup или сразу Project C — авто-генерация LLM-промптов через квиз).

---

## §1. TL;DR

**Что shipped (chronologically):**

| Дата | Что | Где |
|---|---|---|
| 2026-05-04 | Server Migration | main (V1) |
| 2026-05-11 | Phase 2.0 (3-tab profile-edit) | main |
| 2026-05-13 рано | Phase 2.1 (unified_criteria + V2 rip) + F1/F5/parser-tune/bucket-relax | main |
| 2026-05-13 поздно | Project A defect-catalog admin (`/defects` + alembic 0017 + 8+3+6 seed) | feat/defect-catalog (deployed, не merged) |
| 2026-05-14 | Project A polish: device_detail fix + русификация + CRUD UI + auto-slug | feat/defect-catalog (deployed, не merged) |

**На сегодня (в порядке приоритета):**

| # | Шаг | Кто | Время |
|---|---|---|---|
| §5.1 | Sanity (branch/alembic/prod 200) | Claude | 1 мин |
| §5.2 | **Manual UI smoke на /defects** (полный checklist § 4.1) | Юзер | 15-30 мин |
| §5.3 | **Final code-review** (per subagent-driven skill) на ветку перед merge | Claude (Opus subagent) | 10 мин |
| §5.4 | Merge `feat/defect-catalog` → main + push | Claude | 5 мин |
| §5.5 | «Чуть подчистить UI» — мелкие doменные правки которые увидел юзер | Юзер→Claude | 15-60 мин |
| §5.6 | **Project C brainstorm:** автогенерация LLM-промптов через квиз с Sonnet/Haiku | Юзер+Claude | 30-60 мин |

---

## §2. Production state (snapshot 2026-05-14 после deploy)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (ssh root@, key auth) |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt `drwgozasaypgphkxyizt`, pooler 6543 transaction mode |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Alembic head на prod** | `0017_defect_catalog` (без изменений vs вчера) |
| **/defects admin UI** | Live, **полностью русифицирован** (включая «блок/инфо/уточнить/пропустить» в bindings) |
| **/defects/devices/{id}** | Live, **fix `_layout_context` применён** (commit `3c92d3a`) |
| **CRUD UI** | `[+][✏][🗑]` на каждой ноде, inline-формы, `hx-confirm` на delete. Add-форма скрывает «Идентификатор» — backend выводит slug из «Название» через `title_to_slug()` (русский транслит) |
| **Активные таблицы defect-catalog** | `feature_nodes` (8 rows), `device_nodes` (3 rows), `device_feature_bindings` (6 rows) |
| **Профили** | `iPhone 12 Pro max 10500-13500` (active, ~138 ProfileListing) + `iPhone 13` (inactive) |
| **Pipeline на проде** | compute_bucket работает на старой flat-схеме (31 feature × ProfileFeatureRule). Catalog НЕ интегрирован в pipeline — это Project B |

### §2.1 Containers (10) — avito-monitor пересобран 2026-05-14 ~20:30 UTC после auto-slug commit

```
avito-system-avito-monitor-1   (FastAPI dashboard + /defects polished)
avito-system-avito-mcp-1
avito-system-avito-xapi-1
avito-system-caddy-1
avito-system-health-checker-1
avito-system-messenger-bot-1
avito-system-redis-1
avito-system-scheduler-1
avito-system-telegram-bot-1
avito-system-worker-8
```

Только avito-monitor пересобран в polish-цикле (другие 6 Python-сервисов не загружают `app.web.defects`, образы не обновлялись).

### §2.2 Git state

```
feat/defect-catalog (13 polish-коммитов поверх Project A):
  55bcefb fix(defects): catch IntegrityError on duplicate slug → 400 с русским текстом
  2e557b5 feat(defects): auto-slug + Russian-only form labels (no anglicisms)
  2b4d31e feat(defects): root-add buttons + form-mount on devices/catalog pages
  762e93d feat(defects): feature_tree action icons (add/edit/delete)
  083903a feat(defects): device_tree action icons (add/edit/delete)
  5123341 feat(defects): GET form-fragment routes for feature CRUD UI
  4f93777 feat(defects): GET form-fragment routes for device CRUD UI
  8e5a235 feat(defects): node_form.html — common inline form partial
  c32ca67 feat(defects): Russify binding_row labels + inherited/set-here/Override
  ce1299b feat(defects): add severity_ru Jinja-filter for Russian UI labels
  d8d728a docs(plan): defect-catalog polish — 12 tasks TDD implementation
  dae4b83 docs(spec): defect-catalog polish — Russification + CRUD UI
  3c92d3a fix(defects): pass _layout_context to device_detail route
  e53d1e7 docs(continue+reference): post Project A ship ← here previous CONTINUE
  8d595c9 test(defect-catalog): seed idempotency
  18b1102 feat(defect-catalog): MVP seed script with stable UUIDs
  ... (rest of Project A — 30+ commits total)

main (без изменений сегодня):
  06d23b7 docs(plan): defect-catalog Project A — 34-task TDD implementation plan
  952c472 docs(spec): defect-catalog Project A design
  7e44d3b fix(bucket): relax compute_bucket
  c562971 fix(prompts): improve section-parser recall
  8b5c097 Merge Phase 2.1
```

Origin URL для PR (если решишь через GitHub merge): https://github.com/n8nRemacs/AvitoSystem/pull/new/feat/defect-catalog

---

## §3. Что сделано 2026-05-14 (в порядке)

### §3.1 device_detail hotfix (`3c92d3a`)

Manual smoke в начале сессии: клик на iPhone 12 Pro Max → 500 `UndefinedError: 'sidebar_profiles_count' is undefined`. Root cause — `device_detail` route не передавал `_layout_context()` (sidebar variables) в template context, хотя `device_detail.html` extends global `_layout.html`. Fix: добавил `ctx = await _layout_context(user, session, active="defects")` симметрично `devices_page`/`catalog_page`. +1 regression-test `test_defects_device_detail_renders_with_sidebar`. Deployed.

### §3.2 Project A polish: brainstorm + spec + plan + impl (commits `dae4b83`, `d8d728a`, T1-T8)

Brainstorm 3 раунда → spec `DOCS/superpowers/specs/2026-05-13-defect-catalog-polish.md` → plan `DOCS/superpowers/plans/2026-05-13-defect-catalog-polish.md` (12 tasks TDD) → subagent-driven execution (Sonnet implementers, Opus reviewers, две stage reviews per task).

Tasks 1-8 shipped:
1. `severity_ru` Jinja-filter (block→блок / info→инфо / ask→уточнить / skip→пропустить).
2. `binding_row.html` Russification (severity labels + «← унаследовано» / «← задано здесь» / «Задать здесь»).
3. `node_form.html` common partial для add/edit, device/feature.
4. 4 GET form-fragment routes для device + cancel (`/devices/new`, `/devices/cancel-form`, `/devices/{parent_id}/new`, `/devices/{node_id}/edit`).
5. То же для feature (`/catalog/...`). Импорт `get_feature_node` добавлен.
6. `device_tree.html`: action icons `[+][✏][🗑]` + `hx-confirm` на delete.
7. `feature_tree.html`: symmetric icons + `[kind]` suffix (Раздел/Дефект).
8. `devices.html` + `catalog.html`: «+ Добавить корневое устройство/признак» + form-mount + Loading→Загрузка.

Deploy после Task 8: только `avito-monitor` rebuild + recreate (другие 6 Python-сервисов не задействованы). pytest baseline: 444 passed / 8 failed (те же 8 что и раньше) / 2 skipped.

### §3.4 IntegrityError fix на duplicate slug (`55bcefb`, perед сном)

Юзер репортнул перед сном: «при удалении дефекта/раздела и попытке создать с тем же названием — не получается, возможно проблема с авто-slug».

Diagnose: prod DB чистая (никаких застрявших rows после delete). Реальный root cause — backend ловил только `ValueError` (regex-валидация), но `IntegrityError` от unique-constraint `uq_(device|feature)_nodes_parent_slug` пробрасывался → FastAPI 500 → HTMX silent ignore → юзер видит «не создаётся».

Fix: catch `IntegrityError` → `session.rollback()` → 400 с понятным русским сообщением «Уже существует устройство/признак «X» (идентификатор «slug») на этом уровне». +2 route-теста. Deployed (commit 55bcefb). 23/23 defects-tests green.

### §3.3 Auto-slug + русификация без англицизмов (`2e557b5`, поздно вечером)

Юзер во время smoke сказал: «slug должен добавляться автоматом сам на основе правил которые ты сам и придумал» + «вместо title — Название» + «UI на русском, без англицизмов».

- `title_to_slug(title: str) -> str` в `repository.py`: per-char транслит русского (а→a, б→b, …, ы→y, ё→yo, …), prepend `n_` если начинается с цифры, collapse `__`, trim leading/trailing `_`. 11 unit-тестов. Дисплей→displey, Корпус→korpus, "iPhone 13"→"iphone_13".
- POST `/devices` + `/catalog`: если slug пустой, derive из title. Если derived empty → 400 с русским сообщением.
- `node_form.html`: slug скрыт в add-режиме, показан в edit как «Идентификатор». Лейблы без англицизмов: Название / Тип (Раздел/Дефект) / Подсказка. DB-значения остаются английскими.
- Tooltip device_tree «Добавить дочернюю ноду» → «Добавить дочернее устройство».
- +5 route-level тестов. Defect-tests suite: 21/21 green.

Deployed. Stop на manual smoke (юзер пошёл спать).

---

## §4. Open / pending

### §4.1 Manual UI smoke checklist для §5.2

Юзер открывает `https://avitosystem.duckdns.org/defects/devices` в браузере:

- [ ] Sidebar — пункт «🛠 Дефекты», текст «Загрузка…» виден кратко при первом GET tree.
- [ ] **Add root device** — клик `[+] Добавить корневое устройство` → inline-форма с **только полем «Название»** (slug скрыт) + dropdown «Тип» только для catalog tab. Ввести `Test Brand` → ОК → Test Brand виден в дереве.
- [ ] **Slug auto-derived** — проверь что в DB реально записан slug `test_brand` (можно через клик `[✏]` на ноду — в edit-форме поле «Идентификатор» покажет правильно).
- [ ] **Add child** — клик `[+]` рядом с Test Brand → форма появилась под ним → ввести `Test Phone` → ОК → Test Phone виден под Test Brand.
- [ ] **Edit** — клик `[✏]` на Test Phone → форма заменила row, prefill = `test_phone` / `Test Phone` → изменить Название на `Test Phone v2` → ОК → row обновился.
- [ ] **Delete** — клик `[🗑]` на Test Phone → native confirm «Удалить «Test Phone v2» и всех потомков?» → OK → row исчез. Удалить Test Brand тем же путём.
- [ ] **Severity labels на /defects/devices/{id}** — клик iPhone 12 Pro Max в реальном дереве → 6 bindings показывают **блок**/**инфо** + **уточнить**/**пропустить** + «← унаследовано» + кнопка «Задать здесь».
- [ ] **Catalog tab** — клик «Признаки» → дерево с `[section]`/`[defect]` (в UI — «Раздел»/«Дефект» в dropdown добавления). `[+]` под root + per-node иконки работают.
- [ ] **Project C quiz** — пока всё ок, можно начинать brainstorm Project C (§5.6).

**Если что-то крашится** — fix-redeploy цикл (sync source + rebuild avito-monitor + recreate).

### §4.2 Backlog из code-review (deferred, не блокирует merge)

| # | Что | Тип | Где |
|---|---|---|---|
| BL1 | Loss of collapsibility в tree — было `<details>/<summary>`, стало flat-div дерево (всегда expanded). Для MVP 5-10 нод OK; >50 нод хуже. | Minor UX | device_tree.html / feature_tree.html |
| BL2 | Stacking `[+]` forms при повторных кликах — каждый клик добавляет ещё одну форму ниже. Cancel убирает по одной. | Minor UX | device_tree / feature_tree |
| BL3 | ARIA labels на icon buttons (только `title=`). Для single-admin tool OK. | A11y | tree templates |
| BL4 | Re-extract `_render_node_form()` helper if number of routes grows past 8 (currently 8 — borderline) | Minor refactor | defects.py |
| BL5 | Empty form-mount div remains after form clear — может убирать `#device-form-mount` content при cancel | Minor | devices.html / catalog.html |
| BL6 | Cancel-form GET route без unit-test (тривиально, low risk) | Minor | test_defects_routes.py |

### §4.2.5 ★ kind=`node` vs `section` mismatch (известный bug, найден 2026-05-14 поздно вечером)

Запрос `SELECT slug, title, kind FROM feature_nodes` на prod показал:
- Дисплей: kind=`node` (а не `section`!)
- Корпус: kind=`node`
- 6 defects: kind=`defect` ✓

Причина: seed-скрипт `scripts/seed_defect_catalog.py` использует `kind="node"` для разделов (исходный intent Project A: hierarchy node), но dropdown в `node_form.html` (Task 3 polish) использует `<option value="section">Раздел</option>`. Несогласованность.

**Что починить на сессии 2026-05-15:**

- Решить: либо seed → переименовать `node` → `section` (миграция данных), либо dropdown → переименовать `section` → `node`. Spec Project A гласит `section`/`defect`, но реализация в seed использует `node`. По спецификации правильно `section`.
- Скорее всего правильно: миграция `UPDATE feature_nodes SET kind='section' WHERE kind='node'` + поправить seed-скрипт.
- Плюс UI: tooltip `[{{ entry.node.kind }}]` в `feature_tree.html` показывает «[node]» рядом с Дисплеем — англицизм, нужен mapping `node→Раздел / section→Раздел / defect→Дефект` в Jinja-фильтре (по аналогии с severity_ru).

Не критично для merge, но красивее всё привести к одному значению до merge.

### §4.3 «Чуть подчистить UI» (§5.5) — что юзер увидит при smoke и захочет

Не знаю заранее — будет видно по фидбеку. Возможные кандидаты: spacing, hover states, индикация ошибок валидации (если slug=`123abc` пройдёт в edit и DB вернёт 400 — сейчас показывается `Invalid slug ...` английским text). Может надо переписать на «Идентификатор должен начинаться с латинской буквы и содержать только латиницу, цифры, подчёркивания» — это правки validate_slug + error response.

### §4.4 Project C — автогенерация LLM-промптов через квиз (§5.6)

**Идея пользователя** (озвучена 2026-05-14 вечером):

> «Следующим шагом будет чуть подчистить UI и потом автогенерация промпта, нужно обсудить как это будет работать, возможно в качестве квиза с хорошей моделью, например sonnet, если потянет Haiku, то вообще супер. Нужно просто написать промпт для генерации промпта будет.»

**Что есть сейчас (входы для Project C):**

- Catalog `feature_nodes` с `prompt_hint` полем на каждом defect (например, `prompt_hint = "Дисплей телефона"`).
- 6 hand-written section-prompts в `app/prompts/extract_*.md`.
- Существующий `compute_bucket` использует эти 6 + flat ProfileFeatureRule.

**Гипотеза Project C:** взять catalog + applicable defects для конкретного device-node, и сгенерировать section-prompts автоматически через **meta-prompt → Sonnet/Haiku**. Возможно в формате «квиза» где LLM задаёт уточняющие вопросы.

**Не начинать имплементацию без brainstorming:**
1. UX квиза — где живёт (admin UI? CLI? webhook?)
2. Какая модель (Sonnet preferred, Haiku если потянет cheap)
3. Design meta-prompt template
4. Возможно перед Project C сделать Project B (Признаки UI читает из catalog), чтобы catalog был в реальном использовании — решение юзера.

Brainstorm на сессии 2026-05-15.

### §4.5 Pre-existing test failures (baseline — не регрессии)

`pytest -q` показывает 459 passed / 8 failed / 2 skipped (459 = baseline 433 + 16 новых polish-тестов + 10 title_to_slug-тестов). 8 failures те же что в предыдущем CONTINUE:
- `tests/avito_mcp/test_tools.py` (1)
- `tests/health_checker/test_*` (6)
- `tests/test_polling.py` (1)

---

## §5. Что делать в новой сессии

### §5.1 Sanity verify (1 мин)

```bash
cd c:/Projects/Sync/AvitoSystem
git branch --show-current  # feat/defect-catalog
git log --oneline feat/defect-catalog -5
# Top: 2e557b5 feat(defects): auto-slug + Russian-only form labels (no anglicisms)
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "/defects=%{http_code}\n" https://avitosystem.duckdns.org/defects'
# Expected: /defects=303 (redirect to /defects/devices)
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 alembic current 2>&1 | tail -1'
# Expected: 0017_defect_catalog (head)
```

### §5.2 Шаг 1 — Manual UI smoke ★

См. §4.1 checklist. Юзер открывает в браузере, проходит по пунктам.

Если что-то крашится — Claude debug + fix + redeploy (sync source + `docker compose build avito-monitor` + `up -d --force-recreate`).

### §5.3 Шаг 2 — Final code-review subagent перед merge

Per `superpowers:subagent-driven-development` skill, после всех tasks dispatched a **final reviewer subagent** для всей ветки (от main до HEAD = 12 polish-коммитов + 30 Project A коммитов).

```
Agent (general-purpose, Opus):
  Базовый прип: code-reviewer skill (или manual prompt)
  PLAN: DOCS/superpowers/plans/2026-05-13-defect-catalog-polish.md
  BASE_SHA: $(git merge-base main feat/defect-catalog)
  HEAD_SHA: 2e557b5
  Просьба: оверолл-ревью всей ветки, не per-commit. Найти cross-task gaps, security issues, missing tests.
```

### §5.4 Шаг 3 — Merge feat/defect-catalog → main

```bash
git checkout main
git pull origin main
git merge --no-ff feat/defect-catalog -m "Merge Project A + polish — defect catalog admin (deployed 2026-05-14)"
git push origin main

# Cleanup (опционально):
git branch -d feat/defect-catalog
git push origin --delete feat/defect-catalog
```

**ВАЖНО:** prod уже работает на этом коде. Merge — это git hygiene; не требует re-deploy. Только убедиться что main = prod.

### §5.5 Шаг 4 — «Чуть подчистить UI»

Жди фидбек юзера после smoke. Возможные мелкие fixes:
- Russian error на validate_slug rejections в edit (сейчас `Invalid slug ...: must match ^[a-z][a-z0-9_]*$` английским)
- Spacing/hover в tree
- Clear form-mount при cancel

Низкий приоритет, делать только то что юзер реально просит.

### §5.6 Шаг 5 — Project C brainstorm

См. §4.4. Обязательно через `superpowers:brainstorming` skill (creative work, требует brainstorm перед implementation). Спросить юзера:
1. Где живёт квиз? (admin UI page? CLI? задача в worker?)
2. Какая модель? (Sonnet vs Haiku — start с Sonnet, тестировать Haiku потом)
3. Input для генерации: catalog state + applicable defects для конкретного device-node?
4. Output: 1 section-prompt за раз, или сразу 6?
5. Quiz mechanic: LLM спрашивает уточняющие вопросы у юзера до финального prompt'a, или batch-generation?

После brainstorm → spec → plan → execute (subagent-driven как сегодня).

### §5.7 Что НЕ делать без подтверждения

- Force-push в main / feat/defect-catalog
- Дропать `feature_nodes` / `device_nodes` / `device_feature_bindings`
- Изменять backend POST/PATCH/DELETE routes (полное Project A покрытие тестами уже есть)
- Удалить `app/services/defect_catalog/` или `app/web/defects.py`
- Менять словарь severity_ru без подтверждения (block/info/ask/skip — settled)

---

## §6. Известные грабли (актуальны 2026-05-14)

### Polish session learnings (новое)

- ❌ **`device_detail.html` extends `defects/_layout.html` который extends `_layout.html` (sidebar+topbar)**. Любой route что рендерит этот partial должен передавать full `_layout_context(...)` — иначе UndefinedError на `sidebar_profiles_count`. Симметрично делают `devices_page` / `catalog_page`. Проверено regression-тестом `test_defects_device_detail_renders_with_sidebar`.
- ❌ **FastAPI route registration order: literal-segments перед UUID-catchall**. `/defects/devices/new`, `/defects/devices/cancel-form`, `/defects/catalog/new`, `/defects/catalog/cancel-form` ДОЛЖНЫ быть зарегистрированы ПЕРЕД `/devices/{device_id}` и `/catalog/{feature_id}/edit` — иначе FastAPI попытается распарсить `"new"` как UUID и вернёт 422.
- ❌ **DB-значения severity (`block/info/ask/skip`) остаются английскими** — translation только в UI через `severity_ru` Jinja filter. `option value="block"` (English) → display text `{{ 'block' | severity_ru }}` = `блок` (Russian). HTMX form post отправляет англ. value на backend.
- ❌ **Slug auto-derive: backend выводит из title через `title_to_slug()`**. Если slug пустой в POST — derive. Если derive yields '' (title без букв) — 400 с русским error. UI: add-форма скрывает slug, edit-форма показывает как «Идентификатор».
- ❌ **«Слаг» / «нода» / «промпт» — англицизмы, нельзя в UI**. Правильно: «Идентификатор», «узел/устройство/признак» (по контексту), «Подсказка».

### Sticky из предыдущих sessions

- ❌ Alembic в старом контейнере не видит новый migration файл — recreate ВСЕХ Python-сервисов перед `alembic upgrade head` (НЕ в этом polish-цикле — миграций не было).
- ❌ Docker compose `build avito-monitor` НЕ обновляет образы worker/scheduler/messenger-bot/telegram-bot/health-checker/avito-mcp — у каждого свой image SHA. Для polish-only изменений в defects.py это OK (другие сервисы не загружают этот модуль).
- ❌ pg_dump 16 vs server 17.6 — use `docker run --rm postgres:17 pg_dump ...`
- ❌ Cloud Supabase pooler search_path пустой — psql напрямую нужен `SET search_path=public` или `public.<table>`.
- ❌ DATABASE_URL preprocessing для libpq tools: `s|postgresql+asyncpg://|postgresql://|; s/[?&]prepared_statement_cache_size=0//; s/[?&]ssl=require/?sslmode=require/`.
- ❌ pgbouncer/Supavisor transaction-mode + asyncpg prepared statements = `DuplicatePreparedStatementError`. Raw asyncpg `statement_cache_size=0`.
- ❌ `pytest_plugins` в non-top-level conftest deprecated. Define fixtures напрямую.
- ❌ Никогда не deploy'ить через rsync с Windows — нет в системе. Use `tar | ssh tar -xf`.
- ❌ TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`.
- ❌ Hardcoded `datetime('now')` в UPDATE — SQLite-only. Use `_now_expr(session)` helper (есть в `repository.py`).

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md + auto-memory (особенно project_defect_catalog_polish.md
и project_c_quiz_prompts.md).

Состояние:
- main: Phase 2.0 + 2.1 + F1/F5/parser-tune/bucket-relax + Project A specs/plans merged.
- feat/defect-catalog: Project A + 12 polish-коммитов (русификация + CRUD UI +
  auto-slug + Russian-only labels). Deployed на prod, НЕ merged. 21/21
  defect-tests + 11 title_to_slug-tests green.

Юзер вчера вечером пошёл спать перед manual smoke. На сегодня:
  1. §5.2 — manual UI smoke юзера на /defects (см. §4.1 checklist)
  2. §5.3 — final code-review subagent перед merge
  3. §5.4 — merge feat/defect-catalog → main + push
  4. §5.5 — «чуть подчистить UI» по feedback'у юзера (см. §4.3)
  5. §5.6 — Project C brainstorm: автогенерация LLM-промптов через квиз
     с Sonnet/Haiku из catalog prompt_hints (см. §4.4)

Production:
- VPS 81.200.119.132 (ssh root@, key auth)
- Cloud Supabase Frankfurt drwgozasaypgphkxyizt
- Alembic head 0017_defect_catalog (без изменений vs 2026-05-13)
- https://avitosystem.duckdns.org/defects полностью русифицирован,
  CRUD UI работает, auto-slug деривирует из «Название»

ВАЖНО:
- UI без англицизмов — Идентификатор / узел / Подсказка (НЕ слаг/нода/промпт)
- Brainstorm Project C перед имплементацией (через superpowers:brainstorming skill)
- Final code-review subagent перед merge feat/defect-catalog → main
```

---

## §8. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## §9. Ссылки на актуальные документы

- `DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md` — spec Project A core
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-impl.md` — план Project A (34 tasks, shipped)
- `DOCS/superpowers/specs/2026-05-13-defect-catalog-polish.md` — **spec polish bundle** (commit `dae4b83`)
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-polish.md` — **plan polish bundle** (commit `d8d728a`, 12 tasks shipped)
- `DOCS/REFERENCE/README.md` — карта production
- `DOCS/DECISIONS.md` — ADR-001..011

---

## §10. Deploy log (для архива)

```
== 2026-05-14 morning — Project A polish kick-off ==
~14:00 Z  Read CONTINUE.md, sanity verify prod
~14:15 Z  Detected device_detail 500 via user smoke
~14:30 Z  Fix _layout_context, regression test, deploy (commit 3c92d3a)

== 2026-05-14 afternoon — polish brainstorm + spec/plan ==
~15:00 Z  Brainstorm 3 раунда (scope + add-UX + словарь)
~15:30 Z  Spec dae4b83 + plan d8d728a committed
~15:45 Z  Subagent-driven execution start (Sonnet implementers, Opus reviewers)

== 2026-05-14 evening — Tasks 1-8 ==
~16:00 Z  T1: severity_ru filter (ce1299b)
~16:10 Z  T2: binding_row russification (c32ca67)
~16:20 Z  T3: node_form.html partial (8e5a235)
~16:35 Z  T4: device form-fragment routes (4f93777)
~16:50 Z  T5: feature form-fragment routes (5123341)
~17:05 Z  T6: device_tree action icons (083903a)
~17:15 Z  T7: feature_tree action icons (762e93d)
~17:25 Z  T8: root-add buttons + Loading→Загрузка (2b4d31e)
~17:35 Z  T9: full pytest sweep — 444/8/2 baseline
~17:40 Z  T10: deploy avito-monitor rebuild + recreate
~17:50 Z  Manual smoke юзера start

== 2026-05-14 late evening — auto-slug feedback ==
~20:00 Z  Юзер: «slug автоматом + UI без англицизмов + Название вместо title»
~20:15 Z  Helper title_to_slug + 11 unit-tests
~20:20 Z  POST handlers: derive slug if empty + Russian error
~20:25 Z  node_form.html: hide slug in add, russify labels (Название/Тип/Подсказка)
~20:28 Z  +5 route tests; full suite 21/21 green
~20:30 Z  Deploy avito-monitor (commit 2e557b5)
~20:32 Z  Юзер ушёл спать; запись CONTINUE.md под завтра
```
