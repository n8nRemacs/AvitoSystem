# CONTINUE — следующая сессия (2026-05-13 после Phase 2.1 hotfixes + Project A defect-catalog ship)

> **Если ты Claude в новой сессии:** прочитай этот файл + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`. **Главное:** на main замержены Phase 2.0 + 2.1 + F1+F5 фиксы + parser-tune + bucket relax. Project A «defect-catalog» полностью отгружен на ветку `feat/defect-catalog`, deployed на prod (alembic head `0017_defect_catalog`), НЕ замержен в main. Юзер должен сделать manual UI smoke перед мержем.

---

## §1. TL;DR

**Что shipped 2026-05-13:**

| # | Что | Где | Merge state |
|---|---|---|---|
| A | Phase 2.0 (3-tab profile-edit + sidebar cleanup) | `main` | merged |
| B | Phase 2.1 (unified_criteria schema + V2 rip + info_api/price_signal) | `main` | merged |
| C | F1 fix — STRICT JSON SHAPE в `extract_price_signal.md` (LLM bare-array repaired_components 71%) | `main` (commit `fa1d296`) | merged |
| D | F5 fix — стейл PHASE_A_STAGES test rename | `main` (commit `7f2abf6`) | merged |
| E | Parser-tune (6 section prompts с negation-as-ok + euphemism examples) | `main` (commit `c562971`) | merged |
| F | Bucket relax (`unknown ≈ ok` + missing→grey safety + backfill persistence) | `main` (commit `7e44d3b`) | merged |
| G | **Project A — defect-catalog admin tool (новый раздел `/defects`)** | `feat/defect-catalog` (30 commits) | **НЕ merged**, deployed на prod |

**Recall improvement** после parser-tune: `red:5→14` (+9 confirmed defects поймано), sensors.sim ok 10→34, operability.no_boot ok 0→8. Green по-прежнему 0 из 32 active — потому что 18 grey-лотов имеют defect на green-rule cosmetic (стекло разбито / задняя крышка). Per `project_screen_broken_not_killer.md` memory — это интенциональное (косметика не killer для байера).

**Что прямо сейчас делать в новой сессии (по убыванию приоритета):**

| # | Шаг | Кто | Время |
|---|---|---|---|
| §5.1 | Sanity verify (main + branch state, prod /login, /defects, alembic head) | Claude | 1 мин |
| §5.2 | **Manual UI smoke на /defects** | Юзер в браузере | 15-30 мин |
| §5.3 | Merge `feat/defect-catalog` → main + cleanup branches | Claude | 5 мин (после §5.2) |
| §5.4 | Решение про cosmetic green-rules (переключить в `ignore` чтобы получить non-zero green count?) | Юзер | brainstorm |
| §5.5 | Backlog приоритезация (Project B Признаки UI, бэклог CQ-ревью) | Юзер+Claude | 10 мин |

---

## §2. Production state (snapshot 2026-05-13 после deploy)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (ssh root@, key auth). Все 7 Python-сервисов rebuild + recreated 2026-05-13. |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt `drwgozasaypgphkxyizt`. Pooler 6543 transaction mode + `?ssl=require&prepared_statement_cache_size=0`. |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Alembic head на prod** | `0017_defect_catalog` (Phase 2.1 → defect-catalog) |
| **Активные таблицы (новые post-Phase 2.1):** | `listing_features` (с `kind` + `value` JSONB); `profile_feature_rules` (старая flat rule-схема, продолжает работать); **`feature_nodes`, `device_nodes`, `device_feature_bindings`** (Project A — 8+3+6 rows seeded) |
| **V2 артефакты дропнуты** | `criteria_templates`, `profile_criteria`, `profile_listing_evaluations` ушли в migration 0016 |
| **/defects admin** | NEW. Sidebar entry «🛠 Дефекты». Tab «Устройства» — split-pane (device tree + applicable bindings). Tab «Признаки» — catalog editor. HTMX inline edits для severity. |
| **Профили** | `iPhone 12 Pro max 10500-13500` (active, ~138 ProfileListing) + `iPhone 13` (inactive) |
| **Pipeline на проде** | compute_bucket работает на старой flat-схеме (31 feature × ProfileFeatureRule). Catalog НЕ интегрирован в pipeline — это Project B. |
| **V2 reliability autoreply** | OFF (`MESSENGER_BOT_ENABLED=false`). seller_dialog ветка жива. |
| **pg_dump pre-2.1 backup** | `/opt/avito-system/data/pre-phase-2.1-backup-20260513-0742.dump` (2.0M) |

### §2.1 Containers (10) — все на новом image post-deploy

```
avito-system-avito-monitor-1  (FastAPI dashboard + /defects)
avito-system-avito-mcp-1
avito-system-avito-xapi-1     (НЕ Phase 2.1, не пересобирался)
avito-system-caddy-1
avito-system-health-checker-1
avito-system-messenger-bot-1
avito-system-redis-1
avito-system-scheduler-1
avito-system-telegram-bot-1
avito-system-worker-8
```

### §2.2 Git state

```
main:
  c562971 fix(prompts): improve section-parser recall (F2 root cause)
  7e44d3b fix(bucket): relax compute_bucket — unknown counts as not-a-defect
  8b5c097 Merge Phase 2.1 — unified criteria + V2 rip (deployed 2026-05-13)
  4b0a7e5 Merge Phase 2.0 — unified-criteria UI placement (deployed 2026-05-13)
  ... (84+ commits ahead of pre-merge state)

feat/defect-catalog (off main, 30 commits):
  spec + 34-task plan committed in DOCS/
  Phase 1: 3 models (feature_node, device_node, device_feature_binding) + alembic 0017
  Phase 2: SQLite test conftest
  Phase 3: repository.py — slug validator + 3 CRUDs + cycle detection (+ critical fix: dialect-aware NOW)
  Phase 4: resolver.py — walk-up inheritance + override + disabled
  Phase 5: app/web/defects.py + 7 templates (NOT in app/web/routers/ — name collision avoided)
  Phase 6: POST/PATCH/DELETE endpoints + sidebar nav entry
  Phase 7: scripts/seed_defect_catalog.py + idempotency test
  Phase 8: deployed to prod
```

Origin URL для PR: https://github.com/n8nRemacs/AvitoSystem/pull/new/feat/defect-catalog

---

## §3. Что сделано в сессии 2026-05-13 (по порядку)

### §3.1 CONTINUE.md TODO выполнен (§5.1-5.6 предыдущей сессии)

1. **§5.1 sanity** — branch verified, 102 pytest pass, prod /login 200
2. **§5.2 F1 fix** — `extract_price_signal.md` переписан с STRICT JSON SHAPE block + canonical/wrong examples + rejection-warning. Deploy: rebuild всех 7 services + recreate. 5 unit tests pass (моки не зависят от prompt).
3. **§5.3 Merge** — `phase-2.0-tabs` + `phase-2.1-unification` → `main`. Push origin/main. 84 commits ahead.
4. **§5.4 Bucket=0 green decision** — DEEP investigation:
   - Diag показал: 102/133 grey-лотов имеют no_row для ВСЕХ rule-features (pre-Phase-2.1 rejected лоты)
   - 31 backfilled лот: parser почти всегда возвращает 'unknown' даже на очевидных фразах
   - 3 examples: «корпус в хорошем состоянии без трещин» → display.glass_broken=unknown (должно быть ok); «Айфон на айклауде заблокирован» → locks.icloud_linked=unknown (должно быть defect!)
   - **Parser-tune 6 section prompts** с расширенным «ok» определением (positive confirm OR negation-of-defect OR общее положительное состояние) + explicit euphemism lists + concrete examples. После tune: recall +200% (sensors.sim 10→34 ok, operability.no_boot 0→8 ok, display.glass_broken 0→25 detected = 7 ok + 18 defect)
   - **Bucket relax** — `compute_bucket` теперь: explicit `state='unknown'` НЕ блокирует green; только missing-feature (None default) → grey safety. Конкретно: bucket=green если нет confirmed defect на любом rule + все rules покрыты parser'ом.
5. **§5.5 manual UI smoke** — юзер начал, увидел: SIM defect показывается как зелёная галочка вместо красного indicator. Brainstorm про визуал переключился в Project A redesign.
6. **§5.6 F5 fix** — `tests/seller_dialog/test_view.py::test_phase_a_stages_contains_two_stages` rename + assertion update под Phase B alias.

### §3.2 Project A defect-catalog — спецификация + план + реализация

Юзер запросил greenfield-редизайн дефект-системы с двумя иерархиями (feature catalog + device tree) и наследованием.

- **Brainstorming** (3 раунда AskUserQuestion): глобальный catalog vs per-profile, свободная глубина дерева, 2-dim severity matrix (defect_action × unknown_action), device hierarchy с inheritance.
- **Spec** `DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md` (410 строк, 14 секций) — commit `952c472`
- **Implementation plan** `DOCS/superpowers/plans/2026-05-13-defect-catalog-impl.md` (~3000 строк, 34 tasks) — commit `06d23b7`
- **Реализация** через subagent-driven-development (Sonnet для implementers, Opus для reviewers + parent). 34 tasks done, 30 commits на `feat/defect-catalog`. **2 critical fixes по review:**
  - F31: `datetime('now')` в update_feature_node — SQLite-only, фейлило бы на Postgres. Fix: dialect-aware `_now_expr(session)` helper.
  - F18.5: `app/web/routers/` directory shadowed existing `app/web/routers.py` — ImportError на `web_router`. Fix: переехал в `app/web/defects.py` как sibling.

### §3.3 Deploy Phase 8 (Tasks 31-34)

```
2026-05-13 ~16:00 UTC  Sync feat/defect-catalog source via tar+ssh
2026-05-13 ~16:05 UTC  docker compose build для всех 7 Python-сервисов
2026-05-13 ~16:10 UTC  docker compose up -d --force-recreate всех 7 (это критично — alembic в старом контейнере НЕ видит новый migration файл)
2026-05-13 ~16:11 UTC  alembic upgrade head → Running upgrade 0016_unified_criteria → 0017_defect_catalog
2026-05-13 ~16:12 UTC  /login HTTP 200, /defects HTTP 303 → /defects/devices
2026-05-13 ~16:13 UTC  python -m scripts.seed_defect_catalog → 8 features + 3 devices + 6 bindings inserted
2026-05-13 ~16:13 UTC  Verified row counts через asyncpg query — все таблицы populated
```

---

## §4. Open findings и backlog

### §4.1 Подтверждено работающим

- ✅ Phase 2.1 pipeline — все 3 kinds в `listing_features` (defect + price_signal + info_api)
- ✅ F1 prompt fix задеплоен — repaired_components shape должен быть canonical (нужно подтвердить через мониторинг 100+ новых лотов)
- ✅ Parser-tune задеплоен — recall +200% на iPhone 12 PM
- ✅ Bucket relax задеплоен — `unknown ≈ ok` semantics live
- ✅ Project A `/defects` admin page — все 8 routes registered, 33 unit tests pass, seed данные видны
- ✅ V2 mapping применён ранее (5 inserts: locks.vendor_account ×2, locks.frp_locked ×2, sensors.touch_id ×1)

### §4.2 Pending — Project A manual UI smoke (§5.2)

Юзер должен открыть `https://avitosystem.duckdns.org/defects/devices` и проверить:

- [ ] Sidebar — пункт «🛠 Дефекты»
- [ ] Tab «Устройства» — слева дерево Phone → Apple → iPhone 12 Pro Max
- [ ] Клик на iPhone 12 Pro Max — справа 6 inherited bindings (all «← inherited from ancestor»), severity dropdowns скрыты, кнопка «Override»
- [ ] Клик «Override» на одном binding — копируется на iPhone 12 PM level, dropdowns активируются, label меняется на «← set here»
- [ ] Меняешь severity в dropdown — HTMX PATCH, row swap, новые значения сохраняются
- [ ] Клик «Удалить» на set-here row — binding удаляется, row возвращается в inherited mode (если предок имел binding)
- [ ] Tab «Признаки» — дерево «Корпус → 3 defects» + «Дисплей → 3 defects»
- [ ] Все 3 page paths (/defects, /defects/devices, /defects/catalog) рендерятся без crash

**Если что-то крашится** — back to fix-and-redeploy cycle (sync source + rebuild ВСЕХ 7 сервисов + recreate).

### §4.3 Backlog из CQ-ревью (deferred, не блокирует MVP)

| # | Что | Тип | Где |
|---|---|---|---|
| BL1 | Repository: миграция raw `text()` SQL → SQLAlchemy ORM (FeatureNode/DeviceNode/DeviceFeatureBinding модели уже есть, не используются) | Important refactor | `app/services/defect_catalog/repository.py` |
| BL2 | Repository: per-call `session.commit()` → caller commits (нарушает «service composes, caller commits» pattern) | Important refactor | same |
| BL3 | Resolver: N+1 queries (`_feature_path` + walk_up_device) → single CTE query когда catalog масштабируется | Minor | `app/services/defect_catalog/resolver.py` |
| BL4 | POST /bindings: try/except на cycle/duplicate с inline-HTML error fragment | Minor UX | `app/web/defects.py` |
| BL5 | Empty commits Tasks 14-17 (implementer написал все 5 resolver-тестов в Task 13 commit, потом 4 пустых маркера) | Cosmetic | можно squash при merge |
| BL6 | Cycle detection логика дублирована между update_feature_node и update_device_node — extract `_assert_no_cycle` helper | Minor refactor | repository.py |
| BL7 | Index naming `idx_*` vs project convention `ix_*` в migration 0017 | Cosmetic | migration |
| BL8 | Repository: тесты gaps (parent_id=None update path, slug update happy path, bare `pytest.raises(Exception)` → narrow IntegrityError) | Minor | test_repository.py |

### §4.4 Backlog продуктовый

| # | Что | Приоритет |
|---|---|---|
| P1 | **Project B — «Признаки» UI на profile/cards читает из catalog'а.** Требует: добавить `device_node_id` FK к `SearchProfile`, integrate resolver в Признаки-render. Отдельный spec/plan. | После manual UI smoke + decision |
| P2 | **Project C — auto-gen LLM prompts из catalog `prompt_hint`.** Generator берёт applicable defects → группирует по feature_tree узлу → генерит section-prompts. Заменяет hand-written. | После Project B |
| P3 | **Cosmetic green-rules → ignore.** Сейчас display.glass_broken / case.back_broken / display.stains_stripes — green-rule, что блокирует бакет в grey даже при tuned parsers. Юзер мог бы переключить в `ignore` на iPhone 12 PM профиле → non-zero green count. | Юзер decision |
| P4 | **Backfill rejected лоты (109 шт)** — текущий backfill пропускает user_action='rejected'. Для consistency можно прогнать с relaxed фильтром. | Опционально |
| P5 | **Refresh-flow push gap** — Avito-app silent refresh = push не идёт = JWT протухает. Pull-based план ~10ч. | Из старого backlog |
| P6 | **Price-tiered criteria** — строгость criteria зависит от цены в alert-вилке (low → relaxed cosmetics, high → pristine). Spec не написан. | Из старого backlog |
| P7 | **Seller dialog Phase B** — questions_setup → questions stages. Phase A shipped. | Из старого backlog |

### §4.5 Pre-existing test failures (baseline — не регрессии нашей работы)

`pytest -q` показывает 433 passed / 8 failed / 2 skipped. 8 failures те же что в CONTINUE.md предыдущей сессии (§4.3):
- `tests/avito_mcp/test_tools.py` (1) — стейл assertion
- `tests/health_checker/test_*` (5) — alerts pipeline
- `tests/test_polling.py` (1) — Windows cp1252 codec
- (`tests/seller_dialog/test_view.py` F5 — FIXED in этой сессии)

---

## §5. Что делать в новой сессии

### §5.1 Шаг 0 — Sanity verify (1 минута)

```bash
cd c:/Projects/Sync/AvitoSystem
git branch --show-current  # либо main либо feat/defect-catalog
git log --oneline main -3
# Top: c562971 fix(prompts): improve section-parser recall
#      7e44d3b fix(bucket): relax compute_bucket
git log --oneline feat/defect-catalog -3
# Top: 8d595c9 test(defect-catalog): seed idempotency
#      18b1102 feat(defect-catalog): MVP seed script
#      243c8b6 feat(defect-catalog): sidebar nav entry
```

Smoke prod:
```bash
ssh root@81.200.119.132 'curl -sS --resolve avitosystem.duckdns.org:443:127.0.0.1 -k -o /dev/null -w "HTTP %{http_code}\n" https://avitosystem.duckdns.org/login'
# Expected: 200
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 alembic current 2>&1 | tail -2'
# Expected: 0017_defect_catalog (head)
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 python -c "
import asyncio, os, re, asyncpg
def strip(u):
    u = u.replace(\"postgresql+asyncpg://\", \"postgresql://\")
    u = re.sub(r\"[?&]prepared_statement_cache_size=\d+\", \"\", u)
    return u.replace(\"?ssl=require\", \"?sslmode=require\")
async def go():
    c = await asyncpg.connect(strip(os.environ[\"DATABASE_URL\"]), statement_cache_size=0)
    for t in (\"feature_nodes\", \"device_nodes\", \"device_feature_bindings\"):
        print(f\"{t}:\", await c.fetchval(f\"SELECT COUNT(*) FROM {t}\"))
    await c.close()
asyncio.run(go())
"'
# Expected: feature_nodes: 8 / device_nodes: 3 / device_feature_bindings: 6
```

### §5.2 Шаг 1 — Manual UI smoke на /defects (юзер) ★

См. §4.2 checklist. Юзер открывает в браузере, проходит по пунктам.

Если что-то крашится — Claude debug + fix + redeploy.

### §5.3 Шаг 2 — Merge `feat/defect-catalog` → main (после §5.2)

```bash
git checkout main
git pull origin main
git merge --no-ff feat/defect-catalog -m "Merge Project A — defect catalog admin (deployed 2026-05-13)"
git push origin main

# Cleanup (опционально):
git branch -d feat/defect-catalog
git push origin --delete feat/defect-catalog
```

**ВАЖНО:** prod уже работает на этом коде. Merge — это git hygiene; не требует re-deploy. Только убедиться что main = prod.

### §5.4 Шаг 3 — Cosmetic green-rules decision (юзер)

После §5.2 юзер видит реальный bucket distribution. Если 0 green продолжает быть проблемой:

Option A: на /profiles/{id}/feature-rules переключить cosmetic rules (display.glass_broken, case.back_broken, display.stains_stripes) с `green` на `ignore`. Это сразу даст non-zero green count (лоты без critical defect перестанут падать в grey из-за косметики).

Option B: оставить — grey = «нужен ручной разбор» работает; green просто остаётся редким сигналом для урgent TG.

Brainstorm с юзером если непонятно.

### §5.5 Шаг 4 — Project B priority decision

После Project A merged — следующий вопрос: когда начинать Project B?

Project B = «Признаки» UI на profile-edit + kanban-card читает из catalog (вместо текущего flat-системы). Это требует:
- Добавить `device_node_id` FK к `SearchProfile`
- Резолвер `resolve_applicable_defects(profile.device_node_id)` → dict feature_key → severity
- Переписать profile-edit form Tab «Признаки» чтобы рендерить applicable defects из catalog
- Переписать compute_bucket чтобы читать severity из catalog (или поддерживать оба пути backward-compat)
- Kanban card «Признаки» block — то же

Spec нужен. Brainstorm 30-60 мин. Реализация ~similar scale что Project A.

### §5.6 Что НЕ делать без подтверждения

- Force-push в main / feat/defect-catalog
- Дропать новые таблицы (feature_nodes / device_nodes / device_feature_bindings)
- Rebuild image только для одного сервиса (§6 — нужны все Python-services вместе)
- Удалить `app/services/defect_catalog/` или `app/web/defects.py` (Project A core)

---

## §6. Известные грабли (актуально 2026-05-13)

### Новые из Project A deploy

- ❌ **Alembic в старом контейнере не видит новый migration файл.** После sync source — сначала `docker compose up -d --force-recreate` всех 7 сервисов, ПОТОМ `alembic upgrade head`. Если запустишь до recreate — `alembic current` вернёт старый head, `upgrade head` — no-op. (Произошло в этой сессии.)
- ❌ **`asyncpg.connection.close()` → `RuntimeError: Event loop is closed`** при запуске seed/diag скриптов через docker exec. **Это known §6 quirk, не fatal — данные коммитятся ДО shutdown.** Проверять реальный state через отдельный asyncpg query.
- ❌ **Создание `app/web/routers/` директории shadow'ит существующий `app/web/routers.py`** → ImportError на `from app.web.routers import router as web_router`. **НЕ создавай routers/ под существующий routers.py.** Новые роутеры — siblings типа `app/web/defects.py`.

### Из Phase 2.1 deploy (sticky)

- ❌ **`docker compose build avito-monitor` НЕ обновляет образы worker/scheduler/messenger-bot/telegram-bot/health-checker/avito-mcp** — у каждого свой image SHA, хоть build context общий. Надо `docker compose build` для ВСЕХ Python-сервисов вместе.
- ❌ **pg_dump 16 vs server 17.6** — host pg-client несовместим с Cloud Supabase 17. Use `docker run --rm postgres:17 pg_dump ...`.
- ❌ **Cloud Supabase pooler search_path пустой** — `psql` запросы требуют `SET search_path=public` ИЛИ schema-qualified `public.table_name`. SQLAlchemy/asyncpg в коде работает потому что queries автоматически используют public (default). Если будешь дебажить через psql напрямую — добавляй `--set=search_path=public` или `public.<table>`.
- ❌ **DATABASE_URL preprocessing для pg_dump/psql** — у нас `postgresql+asyncpg://...?ssl=require&prepared_statement_cache_size=0`. Для libpq tools конвертация: `s|postgresql+asyncpg://|postgresql://|; s/[?&]prepared_statement_cache_size=0//; s/[?&]ssl=require/?sslmode=require/`.
- ❌ **pgbouncer/Supavisor transaction-mode + asyncpg prepared statements** = `DuplicatePreparedStatementError`. При raw asyncpg connect — `statement_cache_size=0` обязательно. SQLAlchemy code работает потому что `prepared_statement_cache_size=0` уже в DATABASE_URL.
- ❌ **`pytest_plugins` в non-top-level conftest deprecated** — pytest 8+ блокирует. Define fixtures прямо в conftest.

### Из общей prod-эксплуатации

- ❌ **Никогда не пересобирай только один service** (повтор) — shared image, нужны все consumers.
- ❌ **JWT-сессии могут стать server-side-зомби** — manual refresh launch Avito-app 60 сек.
- ❌ **TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`** через import.
- ❌ **Не deploy'ить через rsync с Windows** — нет в системе. Use `tar + ssh tar -xf`.
- ❌ **SQLite не поддерживает JSONB + `pg_insert.on_conflict_do_update`** — для тестов в `tests/defect_features/conftest.py` dialect-aware UPSERT (`_is_postgres(session)` check). Тот же паттерн используется в `app/services/defect_catalog/repository.py` через `_now_expr(session)` helper.
- ❌ **Hardcoded `datetime('now')` в UPDATE statements** — SQLite-only syntax, на Postgres `function datetime(unknown) does not exist`. Use dialect-aware helper.

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md + auto-memory (особенно project_phase_2_1_shipped.md
и memory про Project A когда сохранён).

Состояние:
- main: Phase 2.0 + 2.1 + F1/F5/parser-tune/bucket-relax merged + deployed.
- feat/defect-catalog: Project A defect-catalog admin tool готов и
  deployed на prod (alembic 0017, /defects live, 8+3+6 seed rows),
  НО НЕ merged в main.

Юзер должен сделать manual UI smoke на /defects (см. §4.2 checklist в
CONTINUE.md). После smoke OK — merge feat/defect-catalog в main.

Дальше:
- §5.4 — cosmetic green-rules decision (юзер переключает в ignore?)
- §5.5 — Project B priority (Признаки UI читает из catalog)
- §5.6 — backlog (CQ refactors / Project C auto-gen prompts /
  refresh-flow push gap / price-tiered criteria / Phase B dialogs)

Production:
- VPS 81.200.119.132 (ssh root@, key auth)
- Cloud Supabase Frankfurt drwgozasaypgphkxyizt
- Alembic head 0017_defect_catalog
- https://avitosystem.duckdns.org/defects (новое!)

ОЧЕНЬ ВАЖНО при code-deploy: docker compose build для ВСЕХ Python-
сервисов сразу + ВСЕГДА recreate ДО alembic upgrade (alembic в старом
контейнере не видит новый migration файл).
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
- `DOCS/superpowers/plans/2026-05-13-unified-criteria-phase-2.1.md` — план 14 tasks (выполнен)
- `DOCS/superpowers/specs/2026-05-13-defect-catalog-design.md` — **NEW** spec Project A
- `DOCS/superpowers/plans/2026-05-13-defect-catalog-impl.md` — **NEW** план Project A (34 tasks, выполнен)
- `DOCS/REFERENCE/README.md` — карта production (обновлена 2026-05-13)
- `DOCS/DECISIONS.md` — ADR-001..011

---

## §10. Phase 2.1 + Project A deploy log (для архива)

```
== Phase 2.1 deploy (предыдущая сессия) ==
2026-05-13 07:42 UTC  pg_dump (2.0M) via docker postgres:17
2026-05-13 07:48 UTC  docker compose build для всех 7 Python-сервисов
2026-05-13 07:48 UTC  docker compose up -d --force-recreate всех
2026-05-13 07:49 UTC  alembic upgrade head: 0015 → 0016_unified_criteria
2026-05-13 07:50 UTC  V2 mapping --apply: 5 inserts
2026-05-13 07:54 UTC  Hotfix 4af53c4 (template tolerates bare-array repaired_components)

== Эта сессия — Phase 2.1 hotfixes ==
2026-05-13 12:xx UTC  F1 prompt fix deployed (extract_price_signal.md STRICT JSON)
2026-05-13 12:xx UTC  Parser-tune deployed (6 section prompts с negation-as-ok)
2026-05-13 12:xx UTC  Backfill #3: red 5→14 (+9 confirmed defects)
2026-05-13 12:xx UTC  Bucket relax deployed (unknown ≈ ok)
2026-05-13 12:xx UTC  F5 test fix + merge Phase 2.0+2.1 → main + push

== Project A defect-catalog ==
2026-05-13 13-15 UTC  Brainstorming + spec + plan committed
2026-05-13 15-16 UTC  Subagent-driven impl: 34 tasks, 30 commits, 33 new tests
2026-05-13 ~16:10 UTC docker compose build + recreate всех 7
2026-05-13 ~16:11 UTC alembic upgrade head: 0016 → 0017_defect_catalog
2026-05-13 ~16:13 UTC seed_defect_catalog: 8 features + 3 devices + 6 bindings
2026-05-13 ~16:14 UTC /defects smoke 200/303 OK, branch pushed to origin
```
