# CONTINUE — следующая сессия (2026-05-13 после Phase 2.0 ship + Phase 2.1 pause)

> **Если ты Claude в новой сессии:** прочитай этот файл целиком + `DOCS/REFERENCE/README.md` + `DOCS/superpowers/specs/2026-05-12-unified-criteria-design.md` (spec на Phase 2.0+2.1) + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`. **Главная задача сейчас — корректное завершение Phase 2.1 (unified criteria + V2 rip).** Phase 2.0 (UI placement) уже задеплоен в prod, Phase 2.1 на паузе после audit обнаружил shared-resources blunder в плане.

---

## §1. TL;DR

**Phase 1 defect-checklist** — shipped 2026-05-12 (22 фичи, `listing_features` + `profile_feature_rules`, pipeline integrated, UI с feature-rules editor).

**Phase 2.0 unified-criteria UI placement** — shipped 2026-05-13:
- Sidebar nav «🛠 Настройки модели» удалён.
- Profile edit form реструктуризован в 3 tabs: «🔎 Поиск» / «🧩 Признаки» / «🔔 Уведомления». Tab «Признаки» содержит partial с per-feature правилами (тот же markup что standalone-страница).
- Tab «Уведомления» содержит реальные Telegram/Max checkboxes (перемещены из старого Step 7).
- localStorage persistence + URL `?tab=features` deep-link (server-side активирует правильный tab).
- Standalone `/profiles/{id}/feature-rules` остаётся для backwards-compat.
- 23/23 web tests pass. Branch `phase-2.0-tabs` (4 task commits + 1 docs commit). **Deployed на VPS 81.200.119.132**, public URL `https://avitosystem.duckdns.org`. Ветка НЕ замержена в main.

**Phase 2.1 unified-criteria schema + V2 rip** — **PAUSED 2026-05-13 mid-execution.** Tasks 1-3 done (yaml taxonomy 22→31 features, migration 0016, V2-mapping helper script). **Task 4 (V2 code rip) реверт**нут — implementer over-rip'нул shared resources. Audit показал что план перегнул палку в 2-х местах. Tasks 5-14 ещё не запускались.

**Critical NEXT ACTION:** Применить audit findings (см. §4) — fix migration 0016 + переписать Task 4 instructions + продолжить subagent-driven execution.

---

## §2. Production state

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU, 2c/4GB, Ubuntu 24.04 + Docker 29). Доступ `ssh root@81.200.119.132` (key auth). |
| **Public URL** | `https://avitosystem.duckdns.org` (Caddy → avito-monitor:8000) |
| **БД** | Cloud Supabase Frankfurt `drwgozasaypgphkxyizt`. Pooler 6543 + `?prepared_statement_cache_size=0` (transaction mode). |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Deploy в prod** | **phase-2.0-tabs branch** (НЕ main). Sync через `tar -czf - --exclude __pycache__ --exclude .git . \| ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'`, потом `docker compose build avito-monitor && docker compose up -d --force-recreate avito-monitor` |
| **Alembic head на prod** | `0015_defect_checklist` (0016 ЕЩЁ НЕ ПРИМЕНЁН — Phase 2.1 не задеплоен) |
| **Профили** | `iPhone 12 Pro Max 10500-13500` (active, 21 правило, ~120 лотов в кане) + `iPhone 13` (inactive, 0 правил) |
| **V2 reliability autoreply** | OFF (`MESSENGER_BOT_ENABLED=false`). seller_dialog ветка SSE handler жива. |

### §2.1 Containers (без изменений)
caddy / avito-xapi / avito-monitor / avito-mcp / worker / scheduler / messenger-bot / telegram-bot / health-checker / redis.

---

## §3. Phase 2.1 — state на сегодня (2026-05-13)

### §3.1 Branch state

**Branch:** `phase-2.1-unification` (от `phase-2.0-tabs`).

```
527bbc5  Revert "feat(v2-rip): remove V2 LLM pipeline code, models, prompts, yaml"
2a68c6b  (reverted) feat(v2-rip): remove V2 LLM pipeline code, models, prompts, yaml
f1f1803  fix(scripts): V2 mapping uses correct profile_criteria schema
97bdfe1  feat(scripts): migrate_v2_to_defect_rules helper                        ← Task 3 done
3254093  fix(migration): 0016 drop V2-orphan columns + FK before table drops    ← Task 2 fix
9b3c057  feat(migration): 0016 unified_criteria — kind/value cols + V2 drop     ← Task 2 done
0a4762c  chore(taxonomy): fix review-flagged issues
a11071e  feat(taxonomy): extend yaml to 31 features with kind discriminator     ← Task 1 done
```

Net effect:
- **Task 1 ✅** — `dialog_topics.yaml` 22→31 features (22 defect → 26 defect + 2 price_signal + 3 info_api). Loader exposes `load_defect_features()` / `load_price_signal_features()` / `load_info_api_features()`. 13 tests pass.
- **Task 2 ⚠️** — migration 0016 создана + fixed Issue 1 (FK drop before table drop). **НО** migration всё ещё дропает 2 shared resources (см. §4) — нужна правка прежде чем применять на prod.
- **Task 3 ✅** — `scripts/migrate_v2_to_defect_rules.py` с asyncpg LEFT JOIN на criteria_templates через COALESCE.
- **Task 4 🔄** — V2 rip implementer over-rip'нул shared resources, был полностью реверт'нут. Нужна переписка с precise file map (см. §4).
- **Tasks 5-14** — pending, ещё не стартовали.

### §3.2 Phase 2.1 цель (напомнить)

Унифицировать defect-features Phase 1 и V2 LLM pipeline в одну таблицу `listing_features` с дискриминатором `kind ∈ {defect, price_signal, info_api}`. 31 фича total. V2 grader + V2 UI section выпиливаются. Card получает два новых блока: «Цена / торг» (price_signal: battery_health + repaired_components) + «Параметры» (info_api: memory_gb + color + vendor_model).

Spec — `DOCS/superpowers/specs/2026-05-12-unified-criteria-design.md`.
Plan — `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` (требует правки секций Task 2 + Task 4 per §4 audit).

---

## §4. **CRITICAL: Shared Resources Audit (2026-05-13)**

После Task 4 V2 rip обнаружено что план Phase 2.1 ошибочно классифицировал 2 ресурса как «V2-only», хотя они активно используются другими частями системы. Audit прошёл через grep по 4-м ключевым файлам (listings_view, web/routers, tasks/analytics, llm_budget).

### §4.1 Таблица аудита

| Ресурс | План говорил | Реальность | Решение |
|---|---|---|---|
| Таблица `criteria_templates` | DROP | V2-only ✅ | **DROP** |
| Таблица `profile_criteria` | DROP | V2-only ✅ | **DROP** |
| Таблица `profile_listing_evaluations` | DROP | V2-only ✅ | **DROP** |
| Таблица `llm_analyses` | DROP | ❌ Shared. Используют: `/llm-budget` команда Telegram (`integrations/telegram/commands.py:90`), `llm_budget.py` cost tracker, `LLMAnalyzer.compare_to_reference` (Price Intelligence cache) | **KEEP** |
| Колонка `profile_listings.bucket` | DROP | ❌ Shared. **Phase 1 defect-features АКТИВНО пишет** (`web/routers.py:569` после `recompute_buckets_for_profile`) и читает (`listings_view.py:170` kanban filter, `:319-323` chip counts, `tasks/analytics.py:263` clean-price filter) | **KEEP** |
| Колонка `profile_listings.latest_evaluation_id` | DROP | V2-only (`tasks/analysis.py:481,619` — V2 evaluate flow) ✅ | **DROP** (+drop FK constraint первым) |
| Колонки `search_profiles.evaluate_strategy / confidence_threshold / criteria_set_hash / bucket_routing` | DROP | V2-only ✅ | **DROP** |
| Модель `criteria_template.py` | DELETE | V2-only ✅ | **DELETE** |
| Модель `profile_criteria.py` | DELETE | V2-only ✅ | **DELETE** |
| Модель `profile_listing_evaluation.py` | DELETE | V2-only ✅ | **DELETE** |
| Модель `llm_analysis.py` | DELETE | ❌ Used by Telegram /llm-budget + llm_budget.py | **KEEP** |
| Модели stale fields `profile_listing.{match_result_id, condition_classification_id}` | (план не упоминал) | DB columns already dropped in 0009 — модель stale | **Clean model only** (не migration) |
| Файл `llm_cache.py` (`DBLLMCache`) | (implementer заstubили) | Кэширует Price Intelligence через `llm_analyses` | **KEEP active** |
| Файл `llm_budget.py` | (implementer заstubили) | Cost tracking через `llm_analyses` | **KEEP active** |
| Yaml `criteria_templates.yaml` | DELETE | V2 library source ✅ | **DELETE** |
| Prompts `evaluate_criterion.md / evaluate_listing_batch.md / extract_info.md` | DELETE | V2 prompts ✅ | **DELETE** |
| `LLMAnalyzer.evaluate_listing` метод + `_eval_*` helpers + `_compute_bucket` helper | DELETE | V2-only ✅ | **DELETE** |
| `LLMAnalyzer.compare_to_reference` метод + `_cache_key_for_compare` | KEEP | Price Intelligence Block 7 ✅ | **KEEP** |
| Module-level functions в `llm_analyzer.py`: `detect_yes_selling`, `formulate_question`, `parse_topic_answer`, `formulate_recap`, `parse_seller_agreement` | KEEP | seller_dialog ✅ | **KEEP** |
| Module-level helpers `_criterion_flag_from_dict`, `_info_extract_from_dict` | DELETE | V2-only ✅ | **DELETE** |
| Module-level `_llm_call_json` | KEEP | Используется другими модулями (price_signal_extractor в Task 7) ✅ | **KEEP** |
| Task `tasks/analysis.py:evaluate_listing` (TaskIQ worker entrypoint) | DELETE | ⚠️ Partial. Polling.py:832 enqueueит этот task per discovered lot. Сам task в текущей версии имеет: (a) V2 path (criteria specs + LLMAnalyzer.evaluate_listing + latest_evaluation_id write), (b) NEW Phase 1 call to `analyze_listing_features` from `defect_features/pipeline.py`. | **REFACTOR**: оставить task wrapper, тело упростить до Phase 1 пути — `await analyze_listing_features(...)`, потом `pl.bucket = bucket`. Drop V2-specific setup (criteria specs, LLMAnalyzer.evaluate_listing call, latest_evaluation_id) |
| `tasks/analytics.py:has_v2_criteria` branch | DELETE | V2-only ✅ | **DELETE** branch (но KEEP `pl.bucket` reads — это Phase 1) |

### §4.2 Почему Task 2 migration не катится на prod как есть

**Текущая migration 0016 на ветке (commit 3254093) сейчас содержит:**
1. `op.drop_column("profile_listings", "bucket")` — **СЛОМАЕТ Phase 1 defect-features pipeline** (kanban filter без значения, chip counts нули, feature-rules-recompute не сохраняет результат).
2. `op.drop_table("llm_analyses")` — **СЛОМАЕТ** `/llm-budget` Telegram-команду, `llm_budget.py` cost tracking, и Price Intelligence cache (compare_to_reference будет работать но без кэша → +cost +latency).

**Эти 2 drops НЕОБХОДИМО удалить из migration 0016 до prod deploy.**

### §4.3 Почему Task 4 был реверт'нут

Implementer **корректно следовал инструкциям плана**, но план + Task 2 review были неправы про shared resources. После V2 rip:
1. Polling.py:832 импортировал `evaluate_listing` task → ImportError (task удалён) → polling не enqueueит → **новые лоты не обрабатываются**.
2. ProfileListing.bucket column в модели удалён → SQLAlchemy reads/writes в listings_view → AttributeError на kanban → **kanban сломан**.
3. llm_analyses dropped → /llm-budget команда сломана + llm_budget стал no-op stub.

Сам по себе implementer был thorough — он зафлажил concerns в DONE_WITH_CONCERNS. Но проблемы были fundamental, не fixable инлайн. Revert был правильным шагом.

---

## §5. Что делать в следующей сессии

### §5.1 Шаг 0 — sanity verify

```bash
cd c:/Projects/Sync/AvitoSystem
git branch --show-current  # → phase-2.1-unification
git log --oneline phase-2.0-tabs..HEAD  # → 5 commits, последний 527bbc5 (revert)
cd avito-monitor && python -m pytest tests/web/ tests/defect_features/ -v --tb=no -q 2>&1 | tail -5
# Expected: ~60 PASS (Phase 2.0 + Phase 1 unchanged after revert)
```

### §5.2 Шаг 1 — Fix migration 0016

Задача: убрать 2 over-aggressive drops + их downgrade additions.

**Файл:** `avito-monitor/alembic/versions/20260513_1000_unified_criteria.py`

**Upgrade — удалить:**
```python
# 3b) Drop profile_listings.bucket (V2 cache column added by 0006).
if "bucket" in pl_cols:
    op.drop_column("profile_listings", "bucket")
```
И из списка `tables_to_drop` убрать `"llm_analyses"`.

**Downgrade — удалить соответствующие add_column для `profile_listings.bucket`** + удалить `op.create_table("llm_analyses", ...)` block.

Также проверить — в downgrade `latest_evaluation_id` re-add'ит column как FK на `profile_listing_evaluations.id`. Если он был originally added в 0006 как FK на `llm_analyses` через какой-то joint setup — это не наш случай (он FK на profile_listing_evaluations.id per 0006). OK as-is.

**После правки прогон:**
```bash
cd avito-monitor
alembic heads  # → 0016_unified_criteria (head)
python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_revision('0016_unified_criteria').revision)"
# → 0016_unified_criteria
```

Commit:
```
git add avito-monitor/alembic/versions/20260513_1000_unified_criteria.py
git commit -m "fix(migration): 0016 keep llm_analyses + profile_listings.bucket

Audit 2026-05-13 revealed both are shared resources, not V2-only:
- llm_analyses: used by Telegram /llm-budget command, llm_budget.py cost
  tracker, and LLMAnalyzer.compare_to_reference (Price Intelligence cache).
- profile_listings.bucket: Phase 1 defect-features pipeline actively writes
  this column (web/routers.py:569 after recompute_buckets_for_profile) and
  reads it in listings_view.py kanban filter + chip counts + tasks/analytics
  clean-price filter.

Migration now drops only V2-only artifacts: criteria_templates,
profile_criteria, profile_listing_evaluations tables; profile_listings
.latest_evaluation_id FK+column; search_profiles V2 columns."
```

### §5.3 Шаг 2 — Re-execute Task 4 (V2 rip — corrected)

**Цель:** удалить V2-only код, СОХРАНИТЬ shared resources, отрефакторить task wrapper.

**Файлы для DELETE (8):**
- `app/db/models/criteria_template.py`
- `app/db/models/profile_criteria.py`
- `app/db/models/profile_listing_evaluation.py`
- `app/data/criteria_templates.yaml`
- `app/prompts/evaluate_criterion.md`
- `app/prompts/evaluate_listing_batch.md`
- `app/prompts/extract_info.md`
- `tests/services/test_llm_analyzer.py` (старые V2 тесты — все 8 уже падают per pre-existing baseline)

**Файлы для MODIFY:**
- `app/db/models/__init__.py` — убрать импорты `CriteriaTemplate`, `ProfileCriterion`, `ProfileListingEvaluation` (но **сохранить `LLMAnalysis`**)
- `app/db/models/profile_listing.py` — убрать атрибуты `latest_evaluation_id`, `match_result_id`, `condition_classification_id` (DB columns dropped in 0009 + 0016). **Сохранить `bucket` column** (Phase 1 пишет).
- `app/db/models/search_profile.py` — убрать `evaluate_strategy`, `confidence_threshold`, `criteria_set_hash`, `bucket_routing`. Остальное keep.
- `app/services/llm_analyzer.py` — большая хирургия:
  - DELETE: `LLMAnalyzer.evaluate_listing`, `_eval_batch`, `_eval_one_criterion`, `_eval_info_batch`, `_cache_key_for_criterion`, `_cache_key_for_info_llm`, `_fallback_unknown_for_specs`
  - DELETE module-level: `_criterion_flag_from_dict`, `_info_extract_from_dict`, `_compute_bucket`
  - KEEP: `LLMAnalyzer.__init__`, `_cache_key_for_compare`, `compare_to_reference`, `CriterionSpec`, `InfoFieldSpec`, `_OpenRouterProto`, `_CacheProto`, `_llm_call_json`, `_read_prompt`, `_listing_to_render_dict`, `_hash`, `_safe_json_loads`, all `detect_yes_selling` / `formulate_*` / `parse_topic_answer` / `parse_seller_agreement`, `_render_fragment_cached`, `_render_fragment`, `_comparison_from_dict`
  - UPDATE docstring (lines 1-25): убрать упоминание `evaluate_listing` как «entry point», оставить только compare_to_reference + seller_dialog.
  - UPDATE imports: remove `BatchEvaluationResponse`, `CriterionFlag`, `InfoFieldExtract`, `ListingEvaluation` from shared.models.llm. Keep `ComparisonResult`, `LLMResponse`.
- `app/schemas/search_profile.py` — DELETE `ProfileCriterionSpec` Pydantic. Remove V2 fields from `SearchProfileBase`/`Update` (`evaluate_strategy`, `confidence_threshold`, etc).
- `app/services/search_profiles.py` — DELETE `set_profile_criteria`, `_compute_criteria_set_hash`, `_slugify_key`, любые helpers работающие с V2 criteria. Keep остальное.
- `app/tasks/analysis.py` — **REFACTOR не DELETE**:
  - Сохранить `@broker.task(task_name="...")` декоратор и сигнатуру `async def evaluate_listing(...)` (polling.py:832 импортирует).
  - **Полностью переписать тело**: убрать V2 spec building, LLMAnalyzer.evaluate_listing call, latest_evaluation_id write. Вместо этого:
    ```python
    @broker.task(task_name="app.tasks.analysis.evaluate_listing")
    async def evaluate_listing(profile_id: uuid.UUID, listing_id: uuid.UUID, ...) -> ...:
        async with session_factory() as session:
            listing = await session.get(Listing, listing_id)
            profile = await session.get(SearchProfile, profile_id)
            if not listing or not profile:
                return
            # Phase 1 defect-features pipeline
            from app.services.defect_features.pipeline import analyze_listing_features
            await analyze_listing_features(session, listing, profile)
            # NOTE: Phase 2.1 Task 9 will replace this with full analyze_listing
            # that also handles price_signal + info_api extraction in one call.
            await session.commit()
    ```
  - Drop `check_api_killers` если оно V2-only (проверь grep'ом).
- `app/tasks/analytics.py` — DELETE V2 `has_v2_criteria` branch + `ProfileCriterion` import. **Сохранить** `ProfileListing.bucket` reads (Phase 1).
- `app/tasks/polling.py` — НЕ ТРОГАТЬ (он импортирует evaluate_listing task который остаётся).
- `app/web/routers.py` — DELETE V2-related imports (`CriteriaTemplate`, `ProfileCriterion`, `ProfileCriterionSpec`), V2 criteria editor helpers (`_load_criteria_library`, `_load_profile_criteria_state` — будут удалены в Task 5 anyway). Keep `pl.bucket = new_bucket` write (Phase 1 path).
- `app/integrations/telegram/callbacks.py` — `ACTION_RECLASSIFY` — проверить, V2-only или нет. Если только для evaluate_listing path — drop.

**Файлы НЕ ТРОГАТЬ (вопреки instinct'у):**
- `app/db/models/llm_analysis.py` — **KEEP**, used by /llm-budget + llm_budget.
- `app/services/llm_cache.py` — **KEEP**, used by compare_to_reference.
- `app/services/llm_budget.py` — **KEEP**.

**Тест файл:** Заменить `tests/test_v2_rip.py` (был в Task 4) — на проверки, что только V2-only вещи удалены. Не тестировать удаление shared resources.

### §5.4 Шаг 3 — Continue Tasks 5-14 согласно plan

После Task 4 corrected re-execution — Tasks 5-14 как в plan'е, но Task 5 (UI rip из form.html) и Task 9 (pipeline integration) должны учесть что:
- Task 5: bucket-column writes в feature-rules-recompute endpoint остаются (Phase 1). Только Step 5/5b sections из form.html удаляются.
- Task 9: `evaluate_listing` task wrapper уже отрефакторен в Шаге 2 — Task 9 ДОБАВЛЯЕТ price_signal + info_api вызовы в `analyze_listing_features` (или внутрь самого task body), плюс upsert_listing_features с kind/value.

Plan file `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` имеет полные подробности по Tasks 5-14. Но **Task 2 + Task 4 секции плана требуют переписки** перед использованием (план не отражает audit findings — sections все еще описывают V2 rip без shared-resource карантина).

### §5.5 Шаг 4 — Deploy на VPS (после всех 14 tasks ✅)

Critical sequence:
1. `pg_dump $DATABASE_URL -F c -f /opt/avito-system/data/pre-phase-2.1-backup-$(date +%Y%m%d-%H%M).dump` на VPS.
2. **Pre-migration:** запустить `migrate_v2_to_defect_rules.py --all --apply` в running container (V2 таблицы ещё существуют).
3. tar+ssh sync source.
4. `alembic upgrade head` через `docker compose run --rm avito-monitor`.
5. `docker compose build avito-monitor && docker compose up -d --force-recreate avito-monitor`.
6. backfill для iPhone 12 PM: `python -m scripts.backfill_features --profile <uuid>` — ~120 лотов, +price_signal +info_api populated.
7. Manual smoke per plan §Task 14 checklist.

---

## §6. Что НЕ работает / избежать повторений (актуально)

- ❌ **Postgres НЕ каскадирует FK при UPDATE/DROP** — нужны explicit drop constraints. Task 2 fix (`3254093`) разобрался с FK блокером.
- ❌ **`op.drop_table` НЕ эквивалентно `DROP TABLE ... CASCADE`** — оставшиеся FK ломают drop. Inspector.get_foreign_keys + explicit drop_constraint.
- ❌ **Docker container НЕ видит изменений в host filesystem** — для миграций `docker compose build avito-monitor` после правки. `docker compose run --rm avito-monitor alembic upgrade head`.
- ❌ **Никогда не пересобирай только один service** через `docker compose build avito-monitor` — shared image. **EXCEPT** для Phase 2.x где Phase 2.0 / 2.1 затрагивает ТОЛЬКО UI/templates — там per-service rebuild OK. Но при изменении `app/services/*` shared code → `docker compose build` без аргументов + `up -d --force-recreate` всех потребителей.
- ❌ **`<script>` теги в HTML, инжектируемом через `innerHTML`, НЕ выполняются**. Delegated handlers в parent template.
- ❌ **`templates.TemplateResponse` новая сигнатура**: `(request, name, context)` позиционно.
- ❌ **JWT-сессии могут стать server-side-зомби** — manual refresh launch Avito-app 60 сек.
- ❌ **TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`** через import.
- ❌ **Не deploy'ить через rsync с Windows** — нет в системе. `tar + scp + ssh tar -xf`.
- ❌ **PowerShell не имеет grep** — либо grep внутри ssh, либо PowerShell `Select-String`, либо Grep tool (Claude).
- ❌ **SQLite не поддерживает JSONB + `pg_insert.on_conflict_do_update`** — для тестов в `tests/defect_features/conftest.py` dialect-aware UPSERT (`_is_postgres(session)` check).

### §6.1 Новое в Phase 2.0 / 2.1

- ❌ **Spec § «V2 удаляется целиком» — НЕ значит drop любого V2-era resource.** Проверять каждый ресурс через grep по `app/` на актуальное использование. Phase 2.1 audit (§4) — единственный source of truth для shared-vs-V2 классификации.
- ❌ **При V2 rip — task wrapper в `tasks/analysis.py:evaluate_listing` НЕ удалять.** Polling.py:832 импортирует. Рефакторить body, оставить декоратор + сигнатуру.
- ❌ **`llm_analyses` таблица — KEEP**: `/llm-budget` Telegram + `llm_budget.py` + Price Intelligence cache.
- ❌ **`profile_listings.bucket` колонка — KEEP**: Phase 1 defect-features активно использует.
- ❌ **`LLMAnalyzer.compare_to_reference` — KEEP**: Price Intelligence Block 7.
- ❌ **При нескольких реверт'нутых коммитах** — repo нормально работает, но Phase 2.1 в half-state: Task 2 migration ещё имеет drop'ы которые нельзя катить (см. §5.2).
- ❌ **Tailwind версия — v3.4.17** (CDN). `aria-selected:` variants работают.

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md целиком, потом DOCS/REFERENCE/README.md (общая карта state'а),
DOCS/superpowers/specs/2026-05-12-unified-criteria-design.md (spec на Phase 2.0+2.1).

Состояние:
- Phase 2.0 (UI placement) shipped 2026-05-13. Branch phase-2.0-tabs deployed
  на VPS, public URL https://avitosystem.duckdns.org. Ветка НЕ замержена в main.
- Phase 2.1 (schema unification + V2 rip) paused mid-execution. Branch
  phase-2.1-unification (5 commits). Tasks 1-3 done. Task 4 реверт'нут после
  audit показал shared-resource blunder. Tasks 5-14 не стартовали.

ГЛАВНАЯ ЗАДАЧА: довести Phase 2.1 до конца БЕЗ повторения over-rip ошибок.

Read first:
1. CONTINUE.md §4 (audit table) — кто V2-only, кто shared.
2. DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md — план, но
   секции Task 2 + Task 4 устарели (план не отражает audit findings).
3. CONTINUE.md §5 — точные next-step инструкции.

V1 + V1.5 production:
- VPS 81.200.119.132 + Cloud Supabase Frankfurt.
- ssh root@81.200.119.132 (key auth).
- Deploy: tar+ssh sync на /opt/avito-system/repo/avito-monitor + docker compose
  build + up -d --force-recreate.
- На prod alembic head = 0015_defect_checklist (0016 НЕ применён, Phase 2.1 не deployed).
- V2 reliability bot выключен (MESSENGER_BOT_ENABLED=false).
```

---

## §8. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## §9. Ссылки на актуальные документы

- `DOCS/superpowers/specs/2026-05-12-unified-criteria-design.md` — spec на Phase 2.0+2.1 (rev 1).
- `DOCS/superpowers/plans/2026-05-12-unified-criteria-phase-2.0.md` — план Phase 2.0 (executed, 6 tasks).
- `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` — план Phase 2.1 (Tasks 1-3 done, Task 4 нужно переписать per §4 audit, Tasks 5-14 pending).
- `DOCS/superpowers/specs/2026-05-12-defect-checklist-design.md` — spec на Phase 1 (executed, базис для Phase 2).
- `DOCS/REFERENCE/README.md` — общая карта production state.
- `DOCS/DECISIONS.md` — ADR-001..011.

---

## §10. Recap Phase 2.0 changelog (deployed)

5 commits на ветке `phase-2.0-tabs` (от `main`):

```
922e963  docs(phase-2.0): plan + spec for unified-criteria UI placement
ed99f4e  feat(profile-form): wire tabs JS + ?tab= deep-link + localStorage persistence
92938b0  feat(profile-form): restructure edit form into 3-tab layout
48d776a  refactor(sidebar): drop hardcoded «Настройки модели» nav item
10686ea  refactor(feature-rules): extract editor markup into reusable partial
```

Net: 6 files changed.
- `app/web/templates/_partials/feature_rules_section.html` (new partial, ~105 lines)
- `app/web/templates/profiles/feature_rules.html` (thin wrapper, 7 lines)
- `app/web/templates/profiles/form.html` (3-tabs restructure)
- `app/web/templates/_layout.html` (sidebar nav item removed)
- `app/web/routers.py` (5 routes touched: `_layout_context`, `profile_new`, `profile_create`, `profile_edit_form`, `feature_rules_page`)
- `tests/web/test_profile_edit_tabs.py` (13 new tests, all passing)

Plus 1 docs commit добавляющий plan + spec в репо.

Deployed 2026-05-13 на VPS 81.200.119.132:
- tar+ssh sync source → `/opt/avito-system/repo/avito-monitor/`
- `docker compose build avito-monitor && docker compose up -d --force-recreate avito-monitor`
- Public URL `https://avitosystem.duckdns.org` → HTTP 200, app boots clean, 66 routes.

**Smoke test пройден пользователем 2026-05-13** — tabs работают, deep-link `?tab=` работает, persistence через localStorage активна. Один UX-нит: tab «Поиск» всё ещё содержит V2 LLM-criteria + V2 pipeline UI (это будет удалено в Phase 2.1 Task 5 — by design).
