# CONTINUE — следующая сессия (2026-05-13 после Phase 2.1 ship)

> **Если ты Claude в новой сессии:** прочитай этот файл + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md` (особенно `project_phase_2_1_shipped.md`). **Сейчас система в soak-периоде после Phase 2.1 deploy.** Главное — не ломать prod без необходимости, мониторить логи, чинить вылезающее на ходу.

---

## §1. TL;DR

**Phase 2.1 (unified-criteria schema + V2 rip)** — **shipped в prod 2026-05-13 07:50 UTC**.

- Ветка `phase-2.1-unification` (22 commits) запушена в `origin`, **НЕ замержена в main**.
- Migration head на prod: `0016_unified_criteria`. V2-таблицы (`criteria_templates`, `profile_criteria`, `profile_listing_evaluations`) дропнуты. `llm_analyses` сохранена (shared с /llm-budget + Price Intelligence).
- `listing_features` теперь имеет `kind` discriminator (`defect` / `price_signal` / `info_api`) и `value` JSONB.
- iPhone 12 PM backfilled — 25 лотов: `{green:0, grey:20, red:5}`. 193 defect + 12 info_api + 8 price_signal rows в DB.
- Workers + monitor + scheduler + mcp + bots — все rebuild'нуты на новый image.
- Один hotfix задеплоен после deploy: `4af53c4` — LLM возвращал `repaired_components.value` голым массивом, partial падал на `.get('items')`. Partial теперь толерантен к обеим формам.

**Сейчас:** soak 3-4 дня. После — merge в main + удаление ветки. Затем backlog (price-tiered criteria + seller dialog Phase B и т.д.).

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

## §4. Soak observations (после deploy 2026-05-13)

### §4.1 Уже подтверждено работающим

- ✅ Pipeline пишет все 3 kinds в `listing_features` (193+12+8 rows)
- ✅ LLM extracts battery_health процентами (sample: `{"percent": 83}`)
- ✅ info_api reads корректно (`{"gb": 256}`, `{"text": "Apple iPhone 12 Pro Max"}`, `{"text": "Серый"}`)
- ✅ Backfill 25 lots → `{green: 0, grey: 20, red: 5}` за 71 секунду, 0 errors
- ✅ /login + /search-profiles + form POST работают (303 redirects корректны)
- ✅ Worker logs чистые (нет V2 column errors после rebuild)
- ✅ Card UI «Цена / торг» рендерится для лотов с battery_health (после hotfix `4af53c4`)

### §4.2 Открытые finding'и для soak (1-3 дня наблюдения)

| Finding | Severity | Action |
|---|---|---|
| **LLM иногда возвращает `repaired_components.value` голым массивом** вместо `{"items":[...]}` обёртки | Mitigated by hotfix `4af53c4` (partial толерантен), но prompt можно подтянуть — посмотреть consistency over 50+ lots | Через 1-2 дня: pull статистика shape'ов из DB. Если bare-array > 30% — tune prompt в `app/prompts/extract_price_signal.md`. Иначе оставить как есть. |
| **Recall battery_health %**: правильно ли LLM ловит процент когда он в title vs description vs не упомянут | Unknown | Sample 30-50 лотов вручную, сравнить с реальными объявлениями |
| **Recall repaired_components quality detection**: original/aftermarket/unknown — правильно ли отличает? | Unknown | Sample 20-30 лотов с упоминанием замен |
| **Bucket distribution**: до 2.1 был mostly green-grey, после backfill 0 green / 20 grey / 5 red на iPhone 12 PM | Expected (Phase 1 rules жёстче V2 grader), но мониторить | UI kanban check — иконки/чипсы/счётчики |
| **TaskIQ worker pipeline в проде**: при первом новом лоте после deploy — отработает ли `evaluate_listing` task с новым body | Unknown | Подождать polling cycle (15 мин по умолчанию) и проверить worker logs |
| **`tasks/web/test_view.py::test_phase_a_stages_contains_two_stages`** failing | Pre-existing (Phase A→B transition) | Не Phase 2.1 — отдельный backlog item |

### §4.3 Pre-existing failures (baseline, не Phase 2.1)

Полный test suite (`pytest tests/`): 391/402 pass, 9 failures. Эти 9 — pre-existing, **не регрессия Phase 2.1**:
- `tests/avito_mcp/test_tools.py` (1) — стейл assertion `iPhone vs Apple`
- `tests/health_checker/test_*` (5) — пайплайн алертов
- `tests/seller_dialog/test_view.py` (1) — PHASE_A→B stage rename
- `tests/test_polling.py` (1) — Windows cp1252 codec
- `tests/test_autosearch_sync.py` (1) — async mock warning escalation

---

## §5. Что делать в следующей сессии

### §5.1 Шаг 0 — sanity verify (1 минута)

```bash
cd c:/Projects/Sync/AvitoSystem
git branch --show-current  # phase-2.1-unification
git log --oneline phase-2.0-tabs..HEAD | head -3  # последний должен быть 4af53c4 hotfix
cd avito-monitor && python -m pytest tests/web/ tests/defect_features/ tests/test_v2_rip.py -q --tb=no
# Expected: 102 passed
```

Smoke prod:
```bash
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "%{http_code}\n" https://avitosystem.duckdns.org/login'
# Expected: 200
ssh root@81.200.119.132 'docker logs avito-system-avito-monitor-1 --tail 50 2>&1 | grep -iE "error|exception" | grep -v "Event loop" | head -10'
# Expected: empty (no recent errors)
```

### §5.2 Шаг 1 — soak status check

Если soak прошёл нормально (нет краш-логов в monitor/worker, нет user complaints в TG) — переходить к §5.3 (merge в main).

Если что-то вылезло — chasing соответствующую регрессию:
- **Crash в template** → patch partial, redeploy через tar+ssh sync (см. §2)
- **Crash в pipeline** → patch pipeline.py / llm_parser.py / extractor / reader, тест + redeploy всех сервисов (worker важен)
- **LLM возвращает не то** → tune prompt в `app/prompts/`, redeploy avito-monitor + worker (prompts читаются на runtime, рестарт нужен только для гарантии cache invalidation)

### §5.3 Шаг 2 — merge `phase-2.1-unification` в `main`

После 2-3 дней без явных регрессий:

```bash
cd c:/Projects/Sync/AvitoSystem
git checkout main
git pull origin main  # на случай если что-то залетело
git merge --no-ff phase-2.1-unification -m "Merge Phase 2.1 — unified criteria + V2 rip"
git push origin main
# Опционально: git branch -d phase-2.1-unification && git push origin --delete phase-2.1-unification
```

**Внимание:** main сейчас отстаёт от `phase-2.0-tabs` (Phase 2.0 не замержен в main, deployed напрямую с ветки). После Phase 2.1 merge стоит проверить — есть ли расхождение между prod и main. Если main отстаёт — отдельный merge коммит для phase-2.0-tabs.

### §5.4 Шаг 3 — backlog (после успешного merge)

Из auto-memory + DECISIONS:

1. **Price-tiered criteria** (`project_price_tiered_criteria.md`) — строгость criteria зависит от цены внутри alert-вилки: low → relaxed cosmetics, high → pristine. Spec не написан, brainstorm нужен.
2. **Seller dialog Phase B** (`project_seller_dialog_phase_a.md`) — Phase A shipped, Phase B (questions_setup → questions etc.) ещё в дизайне.
3. **Bucket flow → urgent TG для green** (`project_bucket_flow_design.md`) — green в alert-zone должен слать urgent TG (план).
4. **Refresh-flow push gap** (`reference_refresh_flow_gap.md`) — Avito-app silent refresh = push не идёт = JWT протухает; pull-based план на ~10ч (отдельный спринт).
5. **Prompt-tuning batch** — после soak статистики improve prompts: extract_price_signal (items wrapper), parse_section_* (recall calibration).

### §5.5 Шаг 4 — что НЕ делать без подтверждения пользователя

- Удалять ветку `phase-2.1-unification` до merge в main
- Force-push в main/master/phase-2.0-tabs
- Дропать таблицы / колонки / прод-данные
- Rebuild image только для одного сервиса (см. §2.1 — нужны все Python-сервисы вместе)

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

Состояние: Phase 2.1 (unified-criteria + V2 rip) shipped в prod 2026-05-13.
Ветка phase-2.1-unification (22 commits + 1 hotfix) deployed на VPS,
НЕ замержена в main. Сейчас soak-период.

Главная задача сейчас зависит от состояния soak:
- Если 2-3 дня прошло без регрессий → §5.3 merge phase-2.1-unification в main.
- Если crash/regression → §5.2 patch + redeploy.
- Иначе — §5.4 backlog (price-tiered / seller dialog phase B / prompt tuning / push gap).

Production:
- VPS 81.200.119.132 (ssh root@, key auth)
- Cloud Supabase Frankfurt drwgozasaypgphkxyizt
- Alembic head 0016_unified_criteria
- https://avitosystem.duckdns.org

ОЧЕНЬ ВАЖНО при следующем prod-deploy: docker compose build для ВСЕХ
Python-сервисов сразу (avito-monitor worker scheduler avito-mcp
messenger-bot telegram-bot health-checker), не только avito-monitor —
иначе worker будет на старом коде.
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
