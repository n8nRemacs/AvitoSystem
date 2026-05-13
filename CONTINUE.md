# CONTINUE — следующая сессия (2026-05-13 после Phase 2.1 ship, юзер skip soak)

> **Если ты Claude в новой сессии:** прочитай этот файл + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md` (особенно `project_phase_2_1_shipped.md`). **Phase 2.1 уже в проде, юзер решил skip soak и делать всё по порядку.** Идёшь по §5: Шаг 0 sanity → Шаг 1 prompt-fix F1 → Шаг 2 merge → Шаг 3 bucket decision → Шаг 4 manual UI smoke (юзер) → Шаг 5 stale test → Шаг 6 backlog. Шаги blocking друг для друга (кроме §5.6 — параллельно).

---

## §1. TL;DR

**Phase 2.1 (unified-criteria schema + V2 rip)** — **shipped в prod 2026-05-13 07:50 UTC**.

- Ветка `phase-2.1-unification` (23 commits) запушена в `origin`, **НЕ замержена в main**.
- Migration head на prod: `0016_unified_criteria`. V2-таблицы (`criteria_templates`, `profile_criteria`, `profile_listing_evaluations`) дропнуты. `llm_analyses` сохранена.
- `listing_features` теперь имеет `kind` discriminator (`defect` / `price_signal` / `info_api`) и `value` JSONB.
- Worker processed 130+ новых лотов за 1.5 часа после deploy. Snapshot 09:00 UTC: 1934 defect + 258 info_api + 172 price_signal rows.
- 1 hotfix задеплоен (`4af53c4`) — `repaired_components` shape mismatch.

**Что прямо сейчас делать** (юзер решил skip soak 2026-05-13 09:05 UTC):

| # | Шаг | Кто | Время | Status |
|---|---|---|---|---|
| §5.1 | Sanity verify | Claude | 1 мин | pending |
| §5.2 | **Fix F1 — prompt drift `repaired_components`** ★ | Claude | ~15 мин + deploy | pending |
| §5.3 | Merge `phase-2.0-tabs` + `phase-2.1-unification` → main | Claude | ~5 мин | pending |
| §5.4 | F2 — bucket=0 green decision (нужен brainstorm с юзером) | Claude+юзер | ~30 мин | pending |
| §5.5 | Manual UI smoke (только юзер в браузере) | Юзер | 15-30 мин | pending |
| §5.6 | F5 — fix стейл test `PHASE_A_STAGES` | Claude (параллельно) | 5 мин | pending |
| §5.7 | Backlog | TBD | TBD | pending |

---

## §2. Production state

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (ssh root@81.200.119.132, key auth). Все Python-сервисы rebuild'нуты 2026-05-13 07:48. |
| **Public URL** | `https://avitosystem.duckdns.org` (Caddy → avito-monitor:8000) |
| **БД** | Cloud Supabase Frankfurt `drwgozasaypgphkxyizt`. Pooler 6543 transaction mode + `?ssl=require&prepared_statement_cache_size=0`. |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Deploy** | `tar -czf - --exclude __pycache__ --exclude .git . \| ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'` → `docker compose build avito-monitor worker scheduler avito-mcp messenger-bot telegram-bot health-checker` → `docker compose up -d --force-recreate <same list>` |
| **Alembic head на prod** | `0016_unified_criteria` (head) |
| **Профили** | `iPhone 12 Pro max 10500-13500` (active, ~25 ProfileListing) + `iPhone 13` (inactive) |
| **V2 reliability autoreply** | OFF (`MESSENGER_BOT_ENABLED=false`). seller_dialog ветка жива. |
| **pg_dump pre-2.1 backup** | `/opt/avito-system/data/pre-phase-2.1-backup-20260513-0742.dump` (2.0M) |

### §2.1 Containers — все на новом image после deploy

```
avito-system-avito-monitor-1  (gunicorn/uvicorn + FastAPI dashboard)
avito-system-avito-mcp-1
avito-system-avito-xapi-1     (не Phase 2.1 — не пересобирался)
avito-system-caddy-1
avito-system-health-checker-1
avito-system-messenger-bot-1
avito-system-redis-1
avito-system-scheduler-1
avito-system-telegram-bot-1
avito-system-worker-8
```

**Важно:** `docker compose build avito-monitor` НЕ обновляет образы worker/scheduler/messenger-bot/telegram-bot/health-checker/avito-mcp — у каждого свой image SHA, хотя build context один (`./repo/avito-monitor`). При следующем code-deploy надо `docker compose build` для ВСЕХ Python-сервисов сразу, иначе worker будет на старом коде и ловить column-not-found.

---

## §3. Phase 2.1 — что было сделано (22 commits)

Полный список — `git log --oneline phase-2.0-tabs..phase-2.1-unification`:

```
4af53c4  fix(card-price-signal): tolerate bare-array repaired_components value   ← Hotfix
8b68b3c  fix(tests): move web fixtures into top-level conftest
9f5bc16  feat(backfill): add --limit option for smoke runs                       ← Task 12
58dcf0f  feat(card): «Параметры» block — vendor_model + memory_gb + color        ← Task 11
09fcaa7  feat(card): «Цена / торг» block — battery_health + repaired_components  ← Task 10
c04884c  fix(pipeline): set source on price_signal + info_api rows
a79664f  feat(pipeline): integrate price_signal + info_api into analyze_listing  ← Task 9
a1c6118  feat(defect-features): info_api reader module                           ← Task 8
3a3cbf4  feat(defect-features): price_signal extractor module                    ← Task 7
50608d8  feat(defect-parser): recognize 4 new defect keys                        ← Task 6
0a92fd6  feat(profile-form): remove V2 LLM-criteria + V2 pipeline UI sections    ← Task 5
1212752  fix(v2-rip): preserve notification_settings on edit
770b6f9  feat(v2-rip): remove V2 LLM pipeline                                    ← Task 4
d3a1348  fix(migration): 0016 keep llm_analyses + profile_listings.bucket
527bbc5  Revert "feat(v2-rip): remove V2 LLM pipeline code, models, prompts, yaml"
2a68c6b  (reverted) feat(v2-rip)
f1f1803  fix(scripts): V2 mapping uses correct profile_criteria schema
97bdfe1  feat(scripts): migrate_v2_to_defect_rules helper                        ← Task 3
3254093  fix(migration): 0016 drop V2-orphan columns + FK
9b3c057  feat(migration): 0016 unified_criteria                                  ← Task 2
0a4762c  chore(taxonomy): fix review-flagged issues
a11071e  feat(taxonomy): extend yaml to 31 features                              ← Task 1
```

### Архитектурные изменения

- **Schema:** 31 фича в `dialog_topics.yaml` (26 defect + 2 price_signal + 3 info_api). Discriminator `kind` + `value` JSONB. `compute_bucket` фильтрует только `kind='defect'`.
- **Pipeline:** `analyze_listing_features` теперь делает 3 вещи в одном проходе: `parse_defect_features` (LLM section parsers) → `extract_price_signal_features` (batched LLM) → `read_info_api_features` (pure Python). Все три UPSERT'ятся в `listing_features`.
- **V2 rip:** удалены V2 модели (`criteria_template`, `profile_criteria`, `profile_listing_evaluation`), V2 prompts, V2 UI sections (Step 5/5b из form.html), V2 grader (`LLMAnalyzer.evaluate_listing`). Сохранены shared: `llm_analyses`, `profile_listings.bucket`, `LLMAnalyzer.compare_to_reference` (Price Intelligence), seller_dialog functions, `DBLLMCache`, `llm_budget`.
- **UI:** profile-edit-form упрощён до 3 tabs (Поиск/Признаки/Уведомления). Card получает 2 новых блока: «Цена / торг» + «Параметры».
- **Backfill:** `python -m scripts.backfill_features --limit N --profile UUID` обрабатывает все 3 kinds через единый orchestrator.

### V2 → defect-rules mapping (выполнен на prod)

5 inserts применено через `scripts/migrate_v2_to_defect_rules --all --apply`:

```
iPhone 13:
  account_blocked  → locks.vendor_account   = 'red'
  frp_locked       → locks.frp_locked       = 'red'
iPhone 12 PM:
  account_blocked  → locks.vendor_account   = 'red'
  frp_locked       → locks.frp_locked       = 'red'
  biometric_broken → sensors.touch_id       = 'red'
```

`color`, `memory_gb`, `vendor_model`, `repaired_components` — V2 ключи без defect-эквивалента (теперь info_api / price_signal kind, не criteria-rules).

---

## §4. Post-deploy prod stats (snapshot 2026-05-13 ~09:00 UTC)

### §4.1 Уже подтверждено работающим

- ✅ Pipeline пишет все 3 kinds в `listing_features`. **Свежий snapshot**: 1934 defect + 258 info_api + 172 price_signal rows (worker отработал ~130 новых лотов за 1.5 часа после deploy).
- ✅ LLM extracts battery_health процентами (sample: `{"percent": 83}`)
- ✅ info_api reads корректно (`{"gb": 256}`, `{"text": "Apple iPhone 12 Pro Max"}`)
- ✅ /login + /search-profiles + form POST работают (303 redirects корректны)
- ✅ Worker logs чистые (нет V2 column errors после rebuild)
- ✅ Card UI «Цена / торг» рендерится для лотов с battery_health (после hotfix `4af53c4`)
- ✅ V2 mapping применён: 5 inserts (locks.vendor_account ×2, locks.frp_locked ×2, sensors.touch_id ×1)

### §4.2 Конкретные finding'и из prod-DB (юзер решил skip soak — фиксим сразу)

| # | Finding | Severity | План фикса |
|---|---|---|---|
| F1 | **LLM drift `repaired_components` 71%**: из 14 non-null cases — 10 bare-array `[{...}]` vs 4 canonical `{"items":[...]}` (DB-stat 2026-05-13). Сейчас спасает template hotfix `4af53c4`, но prompt symptom-level. | High (cosmetic/UI) | Шаг 1 §5.2 — prompt-tune `app/prompts/extract_price_signal.md` |
| F2 | **Bucket distribution iPhone 12 PM: 133 grey + 3 red + 0 green** из 136 лотов. 34 лота имеют `state='unknown'` для всех red-rules. Зелёного bucket нет — `compute_bucket` требует подтверждённого `state='ok'` для всех правил, а unknown ≠ ok. | Medium (product semantics) | Шаг 3 §5.4 — review `compute_bucket` logic + decision: треатить unknown как neutral или как not-green? Возможно надо relax semantics. |
| F3 | **111 лотов без single defect=defect row** (`SELECT COUNT(DISTINCT pl.listing_id) WHERE NOT EXISTS state='defect'`). Это либо LLM не нашёл defect (good), либо feature pipeline не дошёл до них (bad). Backfill обрабатывал только `user_action IN (NULL/pending/viewed/accepted)`, а 109 rejected лотов остались с pre-Phase 2.1 features. | Low (intentional) | Опционально: backfill rejected лоты тоже, для consistency. |
| F4 | **Recall battery_health %**: 17 non-null из 86 (`has_value=86`, всего `null` 69). Из 17 — 12 с percent, 5 с text. Похоже LLM ловит АКБ только когда явно упомянут. | Unknown — нужна manual проверка | Шаг 4 §5.5 — sample 20-30 лотов вручную, сравнить с описанием. |
| F5 | **`PHASE_A_STAGES` test failing** (pre-existing) | Low (test-only) | Шаг 5 §5.6 — фикс теста под Phase B alias |

### §4.3 Pre-existing failures (baseline, не Phase 2.1)

Полный test suite (`pytest tests/`): 391/402 pass, 9 failures. Эти 9 — pre-existing, **не регрессия Phase 2.1**:
- `tests/avito_mcp/test_tools.py` (1) — стейл assertion `iPhone vs Apple`
- `tests/health_checker/test_*` (5) — пайплайн алертов
- `tests/seller_dialog/test_view.py` (1) — PHASE_A→B stage rename (F5 выше)
- `tests/test_polling.py` (1) — Windows cp1252 codec
- `tests/test_autosearch_sync.py` (1) — async mock warning escalation

---

## §5. Что делать в следующей сессии

**Решение юзера 2026-05-13 09:05 UTC: skip soak, делать всё по порядку.** Шаги ниже в строгом порядке — каждый шаг blocking для следующего (кроме §5.6, который можно параллельно).

### §5.1 Шаг 0 — sanity verify (1 минута)

```bash
cd c:/Projects/Sync/AvitoSystem
git branch --show-current  # phase-2.1-unification
git log --oneline phase-2.0-tabs..HEAD | head -5
# Top: 1ee7bc4 docs(continue): rewrite for post-Phase-2.1-ship state
#      4af53c4 fix(card-price-signal): tolerate bare-array
cd avito-monitor && python -m pytest tests/web/ tests/defect_features/ tests/test_v2_rip.py -q --tb=no
# Expected: 102 passed
```

Smoke prod:
```bash
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "%{http_code}\n" https://avitosystem.duckdns.org/login'
# Expected: 200
ssh root@81.200.119.132 'docker logs avito-system-avito-monitor-1 --tail 50 2>&1 | grep -iE "error|exception" | grep -v "Event loop" | head -10'
# Expected: empty
```

### §5.2 Шаг 1 — Fix F1 (LLM drift `repaired_components`) ★

**Что:** Переписать `app/prompts/extract_price_signal.md` чтобы LLM стабильно возвращал `{"items":[...]}` обёртку (сейчас 71% drift на bare array).

**Acceptance:** После 100+ новых лотов через polling — `SELECT jsonb_typeof(value) FROM listing_features WHERE feature_key='repaired_components' AND value IS NOT NULL` показывает >85% `object` (canonical).

**Steps:**
1. Прочитать текущий `app/prompts/extract_price_signal.md`. Найти секцию про `repaired_components`.
2. Усилить инструкцию:
   - В начале: «**STRICT JSON SHAPE**: верхний уровень обязательно ОБЪЕКТ с двумя ключами `battery_health` и `repaired_components`. Каждый ключ — либо объект, либо null. НЕ массив на верхнем уровне.»
   - Для `repaired_components`: добавить явный canonical example блок:
     ```
     CORRECT: {"repaired_components": {"items": [{"component":"экран","quality":"original","evidence":"..."}]}}
     WRONG:   {"repaired_components": [{"component":"экран", ...}]}    ← массив на верхнем уровне НЕДОПУСТИМ
     ```
   - В конце добавить «If you return a bare array instead of an object with items, your response will be rejected and re-asked.»
3. Локальный тест `python -m pytest tests/defect_features/test_price_signal_extractor.py -v` — все 5 должны pass без изменений (моки не зависят от prompt).
4. Sync + rebuild + recreate. **ВАЖНО: rebuild всех Python-services**:
   ```bash
   tar -czf - --exclude __pycache__ --exclude .git . | ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'
   ssh root@81.200.119.132 'cd /opt/avito-system && docker compose build avito-monitor avito-mcp messenger-bot scheduler worker health-checker telegram-bot && docker compose up -d --force-recreate avito-monitor worker scheduler avito-mcp messenger-bot telegram-bot health-checker'
   ```
5. Commit message:
   ```
   fix(prompt): force {"items":[...]} wrapper for repaired_components
   
   Phase 2.1 post-deploy finding F1 — LLM returned bare array 71% of
   non-null cases (10/14). Add STRICT JSON SHAPE block + correct/wrong
   examples + rejection-warning sentence. Template hotfix in 4af53c4
   remains as defence-in-depth.
   ```

### §5.3 Шаг 2 — Merge `phase-2.1-unification` в `main`

После §5.2 deploy чистый — мержим.

```bash
cd c:/Projects/Sync/AvitoSystem
git checkout main
git pull origin main
# Phase 2.0 НЕ замержен в main (deployed напрямую с phase-2.0-tabs).
# Сначала мержим phase-2.0-tabs в main (если ещё не):
git merge --no-ff phase-2.0-tabs -m "Merge Phase 2.0 — unified-criteria UI placement (deployed 2026-05-13)"
# Затем phase-2.1-unification:
git merge --no-ff phase-2.1-unification -m "Merge Phase 2.1 — unified criteria + V2 rip (deployed 2026-05-13)"
git push origin main
```

**Проверка после merge:**
```bash
git log --oneline main -5  # должны быть оба merge коммита
git diff main..phase-2.1-unification  # должно быть пусто
```

**Cleanup (опционально, после подтверждения что main pushed чисто):**
```bash
# Локально и на origin:
git branch -d phase-2.0-tabs phase-2.1-unification
git push origin --delete phase-2.0-tabs phase-2.1-unification
```

### §5.4 Шаг 3 — Bucket=0 green decision (F2)

**Контекст:** 133/136 grey, 0 green. Из 34 grey-лотов все red-rules имеют `state='unknown'` — `compute_bucket` не считает их green потому что требует `state='ok'`.

**Decision tree:**

```
Семантика green = "лот точно ok по всем red-rules"?
├── YES → текущая логика правильна. 0 green = LLM не подтверждает явно "АКБ ok" / "экран ok" / "сенсоры ok" для большинства лотов.
│         Fix: либо tune parser-prompts чтобы chess ok-state увереннее, либо relax compute_bucket чтобы unknown ≈ ok.
│
└── NO → green = "нет ни одного defect=defect", unknown ОК.
         Fix: правка compute_bucket — `unknown` treated like `ok` для green decision.
```

**Steps:**
1. Прочитать `app/services/defect_features/bucket.py` — текущую логику.
2. Brainstorm с юзером (через AskUserQuestion если нужно): какая семантика правильная?
3. Если меняем семантику — patch + test + redeploy.
4. Если меняем prompts (option YES) — это §5.6 ниже.

**Acceptance:** После решения и фикса — бакет distribution на iPhone 12 PM имеет non-zero green count.

### §5.5 Шаг 4 — Manual UI smoke (только юзер) — F4 recall verification

Юзер в браузере (https://avitosystem.duckdns.org):

- ☐ Sidebar — без «Настройки модели»
- ☐ Profile edit (iPhone 12 PM) — 3 tabs, tab «Поиск» без Step 5/5b
- ☐ Tab «Признаки» — 26 фич, видны Touch ID / FRP / vendor_account / parts_only
- ☐ Kanban — на лотах с battery_health виден блок «Цена / торг» (🔋)
- ☐ Kanban — на лотах с params (память/цвет/модель) виден блок «Параметры» (📱💾🎨)
- ☐ Sample 20-30 лотов с упоминанием АКБ %: проверить что extractor поймал процент правильно
- ☐ Sample 20-30 лотов с replaced экраном/АКБ: проверить quality detection (original/aftermarket/unknown)
- ☐ Bucket counts на kanban: green/grey/red chips отображают правильные числа

**Если что-то крашится в UI** — back to §5.2 паттерн (patch + redeploy всех сервисов).

### §5.6 Шаг 5 — Cleanup pre-existing test failure F5

`tests/seller_dialog/test_view.py::test_phase_a_stages_contains_two_stages` — assertion ожидает `["contact", "questions_setup"]`, а `PHASE_A_STAGES` (alias `PHASE_B_STAGES`) теперь `["contact", "questions_setup", "questions"]`. Стейл тест.

**Fix:** обновить assertion в тесте под новый stage flow. ~5 минут.

```python
# tests/seller_dialog/test_view.py
def test_phase_a_stages_contains_two_stages():
    # Phase A→B transition: PHASE_A_STAGES is now alias for PHASE_B_STAGES (3 stages)
    assert PHASE_A_STAGES == ["contact", "questions_setup", "questions"]
```

Можно делать параллельно с §5.2-5.4. Не блокирует прод.

### §5.7 Шаг 6 — Backlog (после §5.2-5.6)

Из auto-memory + DECISIONS, по приоритету:

1. **Bucket flow → urgent TG для green** (`project_bucket_flow_design.md`) — green в alert-zone должен слать urgent TG. Сейчас зелёных 0 (см. F2), так что blocked на §5.4 decision.
2. **Refresh-flow push gap** (`reference_refresh_flow_gap.md`) — Avito-app silent refresh = push не идёт = JWT протухает; pull-based план ~10ч.
3. **Price-tiered criteria** (`project_price_tiered_criteria.md`) — строгость criteria зависит от цены: low → relaxed cosmetics, high → pristine. Spec не написан, brainstorm нужен.
4. **Seller dialog Phase B** (`project_seller_dialog_phase_a.md`) — Phase A shipped (Hi-greeting MVP), Phase B (questions_setup → questions etc.) ещё в дизайне.
5. **Prompt-tuning batch (parse_section_*)** — после §5.5 sample проверок может вылезти recall problems в section parsers.

### §5.8 Что НЕ делать без подтверждения

- Force-push в main / phase-2.0-tabs / phase-2.1-unification
- Дропать таблицы / колонки / прод-данные
- Rebuild image только для одного сервиса (§2.1 — нужны все Python-services вместе)
- `git branch -d phase-2.X-...` до merge в main и smoke verification

---

## §6. Известные грабли (актуально на 2026-05-13)

### Из Phase 2.1 deploy

- ❌ **`docker compose build avito-monitor` НЕ обновляет образы worker/scheduler/messenger-bot/telegram-bot/health-checker/avito-mcp** — у каждого свой image SHA, хоть build context общий. Надо `docker compose build` для ВСЕХ Python-сервисов вместе.
- ❌ **pg_dump 16 vs server 17.6** — host pg-client несовместим с Cloud Supabase 17. Use `docker run --rm postgres:17 pg_dump ...`.
- ❌ **Cloud Supabase pooler search_path пустой** — `psql` запросы требуют `SET search_path=public` ИЛИ schema-qualified `public.table_name`. SQLAlchemy/asyncpg в коде работает потому что queries автоматически используют public (default). Если будешь дебажить через psql напрямую — добавляй `--set=search_path=public` или `public.<table>`.
- ❌ **DATABASE_URL preprocessing для pg_dump/psql** — у нас `postgresql+asyncpg://...?ssl=require&prepared_statement_cache_size=0`. Для libpq tools конвертация: `s|postgresql+asyncpg://|postgresql://|; s/[?&]prepared_statement_cache_size=0//; s/[?&]ssl=require/?sslmode=require/`.
- ❌ **`Event loop is closed` в shell scripts на shutdown** — asyncpg+SQLAlchemy quirk при `dispose_engine()`. Не fatal, ignore.
- ❌ **`pytest_plugins` в non-top-level conftest deprecated** — pytest 8+ блокирует. Define fixtures прямо в conftest.

### Из Phase 2.1 spec/audit

- ❌ **При V2 rip — НЕ удалять**: `llm_analyses` (Telegram /llm-budget + Price Intelligence cache), `profile_listings.bucket` (Phase 1 пишет/читает), `LLMAnalyzer.compare_to_reference`, seller_dialog functions, `DBLLMCache`, `llm_budget`.
- ❌ **`tasks/analysis.py:evaluate_listing` НЕ удалять** task wrapper — `polling.py:832` импортирует. Рефакторить body, не сигнатуру.
- ❌ **Spec § «V2 удаляется целиком» — НЕ значит drop любого V2-era resource.** Audit table в `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` после-fact'ум устарел в части shared resources — реальный список см. в `c04884c` и `1212752` коммитах.
- ❌ **`listing_features.source` — NOT NULL в DB.** Pipeline должен сетить `source` для всех kinds: defect → 'llm' / 'avito_params' / 'description_kw' (LLM parser сам решает), price_signal → 'llm', info_api → 'avito_params'.
- ❌ **`upsert_listing_features` принимает `list[dict]`** (не `dict[str, dict]`). Каждый dict: `{feature_key, kind, state?, value?, confidence?, source, evidence?}`.

### Из общей prod-эксплуатации

- ❌ **Никогда не пересобирай только один service** (повтор) — shared image, нужны все consumers.
- ❌ **JWT-сессии могут стать server-side-зомби** — manual refresh launch Avito-app 60 сек.
- ❌ **TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`** через import.
- ❌ **Не deploy'ить через rsync с Windows** — нет в системе. Use `tar + ssh tar -xf`.
- ❌ **SQLite не поддерживает JSONB + `pg_insert.on_conflict_do_update`** — для тестов в `tests/defect_features/conftest.py` dialect-aware UPSERT (`_is_postgres(session)` check).

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md + auto-memory (особенно project_phase_2_1_shipped.md).

Состояние: Phase 2.1 в проде с 2026-05-13. Юзер решил skip soak.
Идём по §5 по порядку:

  Шаг 0  §5.1  sanity verify (1 мин)
  Шаг 1  §5.2  ★ Fix F1 — prompt drift repaired_components (71% bare-array)
              переписать app/prompts/extract_price_signal.md с STRICT JSON
              SHAPE + canonical/wrong examples + rejection-warning.
              Deploy via tar+ssh sync + rebuild ВСЕХ 7 Python-сервисов.
  Шаг 2  §5.3  merge phase-2.0-tabs + phase-2.1-unification в main
  Шаг 3  §5.4  bucket=0 green decision (F2) — brainstorm с юзером
              про семантику compute_bucket (unknown ≈ ok или нет?)
  Шаг 4  §5.5  manual UI smoke (юзер сам в браузере)
  Шаг 5  §5.6  fix стейл PHASE_A_STAGES test (параллельно)
  Шаг 6  §5.7  backlog (bucket→TG / push gap / price-tiered / Phase B)

Production:
- VPS 81.200.119.132 (ssh root@, key auth)
- Cloud Supabase Frankfurt drwgozasaypgphkxyizt
- Alembic head 0016_unified_criteria
- https://avitosystem.duckdns.org

ОЧЕНЬ ВАЖНО при prod-deploy: docker compose build для ВСЕХ Python-сервисов
сразу (avito-monitor worker scheduler avito-mcp messenger-bot telegram-bot
health-checker), не только avito-monitor — иначе worker будет на старом коде.
Это уже один раз нас укусило (см. §10 deploy log).
```

---

## §8. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`
- **pg_dump бэкапы:** `/opt/avito-system/data/`

---

## §9. Ссылки на актуальные документы

- `DOCS/superpowers/specs/2026-05-12-unified-criteria-design.md` — spec Phase 2.0+2.1
- `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` — план 14 tasks (выполнен, §Task 4 + §Task 2 устарели per audit — см. `d3a1348`/`1212752`/`c04884c`)
- `DOCS/superpowers/plans/2026-05-12-unified-criteria-phase-2.0.md` — план Phase 2.0 (shipped earlier)
- `DOCS/REFERENCE/README.md` — общая карта production
- `DOCS/DECISIONS.md` — ADR-001..011

---

## §10. Phase 2.1 deploy log (для архива)

```
2026-05-13 07:42 UTC  pg_dump (2.0M) via docker postgres:17
2026-05-13 07:43 UTC  tar+ssh sync source
2026-05-13 07:43 UTC  docker compose build avito-monitor
2026-05-13 07:44 UTC  V2 mapping --apply: 5 inserts
2026-05-13 07:44 UTC  alembic upgrade head: 0015 → 0016_unified_criteria
2026-05-13 07:44 UTC  docker compose up -d --force-recreate avito-monitor (partial)
2026-05-13 07:45 UTC  worker logs показали V2 column errors → старый image
2026-05-13 07:48 UTC  docker compose build для всех 7 Python-сервисов
2026-05-13 07:48 UTC  docker compose up -d --force-recreate всех
2026-05-13 07:49 UTC  worker logs чистые, monitor запросы 200/303
2026-05-13 07:50 UTC  backfill iPhone 12 PM (25 lots): {green:0, grey:20, red:5}
2026-05-13 07:52 UTC  User report: Internal Server Error
2026-05-13 07:53 UTC  Diagnose: repaired_components shape mismatch (LLM bare array)
2026-05-13 07:54 UTC  Hotfix 4af53c4 deployed, /listings 303 (no crash)
2026-05-13 07:54 UTC  git push origin phase-2.1-unification (с hotfix)
```
