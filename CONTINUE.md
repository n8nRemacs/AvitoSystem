# CONTINUE — следующая сессия

> **Если ты Claude в новой сессии:** прочитай этот файл целиком + `DOCS/REFERENCE/README.md` (общая карта state'а) + `DOCS/superpowers/specs/2026-05-12-defect-checklist-design.md` (rev 1, дизайн всей feature×rules системы — Phase 1 shipped + Phase 2 описана) + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory в `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`. **Главная задача сейчас — soak Phase 1 defect-checklist** (после shipped 2026-05-12). Пока юзер не настроит правила и не запустит backfill — реального трафика на feature pipeline нет.

---

## §1. TL;DR

Defect Checklist Phase 1 **зашиплен в prod 2026-05-12**:

- 2 новые таблицы (`listing_features` UPSERT по `(listing_id, feature_key)`, `profile_feature_rules` UPSERT по `(profile_id, feature_key)`) + миграция `0015_defect_checklist` применена.
- 22 defect-фичи × 6 секций (display/case/locks/sensors/charging/operability) в `app/data/dialog_topics.yaml`, старые 11 ключей переименованы в dotted-формат + 4 удалены.
- LLM-парсер по разделам: `match_avito_parameters` short-circuit для структурированных Avito-полей (iCloud, passcode) → `parse_section_defects` 6 conservative-промптов параллельно через `asyncio.gather`. Cost ≈ $0.0006/лот (Gemini Flash Lite).
- Pure `compute_bucket(features, rules) → (green|grey|red, reason)` — детерминированно по truth-table из spec §8.
- Integration в `analyze_listing`: после `classify_condition` → parser → bucket из rules. Auto-reject pending/viewed лотов с new_bucket=red (с `rejected_reason='auto:<feature_key>'`).
- UI: блок «Признаки» на каждой карточке (kanban + listings), collapsible sidebar (hamburger + localStorage), страница `/profiles/{id}/feature-rules` с 3-state переключателями (🟢/🔴/⊘) + sync bucket recompute с toast counters.
- Backfill: `python -m scripts.backfill_features [--profile <id>]`.

18 commits на main за 2026-05-12 (15 task commits + 2 fixes + 1 hotfix миграции). 37 unit/integration тестов проходят. **Главное что осталось — operator должен (1) выставить правила на профиле iPhone 12 PM через UI, (2) запустить backfill, (3) понаблюдать качество парсера 3-4 дня соака.**

---

## §2. Production state — 2026-05-12 (вечер)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU). 10 контейнеров up. |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt project `drwgozasaypgphkxyizt`. Pooler 6543 + `prepared_statement_cache_size=0`. |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Профили** | `iPhone 12 Pro max 10500-13500` (active, 21 правило выставлено, 120 лотов: 23 accepted / 97 rejected, всё в grey бакете т.к. features ещё не парсились) + `iPhone 13` (**is_active=False**, 0 правил, лоты+evaluations почищены 2026-05-12 после первого test-полла который слил 871 grey-лот). iPhone 13 ждёт unified-criteria редизайна. |
| **HEAD на main** | будет обновлён следующим коммитом (cleanup junk files + iPhone 13 DB cleanup). До этого `79f8aef fix(migration): drop/recreate FKs around topic-key rename`. |
| **Alembic head** | `0015_defect_checklist` (chain: 0013→0014→0015) |
| **Phone** | OnePlus 8T `110139ce`, USB к Windows ПК |
| **V2 reliability autoreply** | **OFF** через `MESSENGER_BOT_ENABLED=false` (соак-таймаут). SSE listener сам жив, seller_dialog ветка работает |

### §2.1 Контейнеры (без изменений с прошлой сессии)

| Сервис | Назначение |
|---|---|
| `caddy` | HTTPS reverse-proxy, ACME |
| `avito-xapi` | FastAPI шлюз к мобильному Avito API (curl_cffi + SOCKS5) |
| `avito-monitor` | Web UI + поиск/мониторинг + defect-feature pipeline |
| `avito-mcp` | FastMCP SSE сервер |
| `worker` | TaskIQ-воркер (polling + LLM analysis + seller_dialog tasks + новый feature pipeline) |
| `scheduler` | TaskIQ-планировщик (cron'ы) |
| `messenger-bot` | SSE listener `/api/v1/messenger/realtime/events` → handler → seller_dialog ветка. V2 reliability ветка отключена через env |
| `telegram-bot` | aiogram long-poll бот для уведомлений |
| `health-checker` | account_tick loop, scenarios A-I |
| `redis` | TaskIQ broker + кэши |

---

## §3. Defect-checklist pipeline — что есть сейчас

### §3.1 Поток данных

```
Polling → listings (existing)
    ↓
analyze_listing → classify_condition (existing, condition_class остаётся для market-stats)
    ↓
analyze_listing_features (NEW):
  1) load profile_feature_rules → active_keys (rule != ignore)
  2) parse_defect_features:
     ├─ match_avito_parameters (Avito iCloud/passcode short-circuit)
     └─ asyncio.gather над parse_section_defects для 6 секций
  3) upsert listing_features rows
  4) compute_bucket(features, rules) → (green|grey|red, reason)
    ↓
write pl.bucket = bucket
auto-reject если bucket=red AND user_action ∈ (None, pending, viewed):
  pl.user_action = 'rejected'
  pl.rejected_reason = f'auto:{reason}'
```

### §3.2 Таблицы

```
listing_features
  id PK, listing_id FK→listings CASCADE, feature_key, state (ok|defect|unknown),
  confidence float NULL, source (avito_parameters|llm|description_kw|seller_dialog),
  evidence text NULL, parsed_at timestamptz.
  UNIQUE(listing_id, feature_key).

profile_feature_rules
  id PK, profile_id FK→search_profiles CASCADE, feature_key, rule (green|red|ignore),
  updated_at timestamptz.
  UNIQUE(profile_id, feature_key).

profile_listings.rejected_reason  (новый column, формат 'auto:<feature>' или 'manual:operator')
```

### §3.3 Таксономия (22 фичи в `app/data/dialog_topics.yaml`)

| section | keys |
|---|---|
| display | replaced, glass_broken, touchscreen_glitch, stains_stripes |
| case | back_broken, midframe_bent, midframe_cracked |
| locks | icloud_linked, passcode_forgotten |
| sensors | face_id, truetone, wifi, sim, bluetooth, other |
| charging | not_charging, wireless_only, unstable |
| operability | boot_loop, reboots, no_boot, apple_loop |

Каждая фича имеет `severity_hint` (red|green|info — дефолт-намёк для оператора в UI) и `opener_phrasing` (для Phase 2 personalised opener).

### §3.4 LLM-вызовы (в `app/services/defect_features/llm_parser.py`)

| Функция | Что делает | Промпт |
|---|---|---|
| `match_avito_parameters` | Dict-driven: iCloud/passcode → state по substring-match. Short-circuit без LLM. | — (pure Python) |
| `parse_section_defects(section, features, …)` | Один LLM-запрос на категорию, conservative — unknown по умолчанию. Возвращает state/confidence/evidence per requested feature. | `app/prompts/parse_section_<section>.md` |
| `parse_defect_features(title, description, parameters, active_keys)` | Orchestrator: match_avito → asyncio.gather над 6 секциями для pending фич → merge. | — (orchestration) |
| `compute_bucket(features, rules)` | Pure: truth-table из spec §8. | — (pure Python, 8 unit-тестов) |

Все через OpenRouter `google/gemini-2.5-flash-lite`, safe fallback (state='unknown' для всех) на ошибке.

### §3.5 UI surface

- **Карточки kanban + listings** — блок «Признаки» в expanded body: 2-column grid по секциям, ✓ зелёная / ⊘ красный круг / ⚪ серый кружок. Hover = evidence tooltip. Фичи с rule=ignore не показываются.
- **Sidebar collapse** — hamburger в topbar, w-60 ↔ w-14, state в localStorage.kpis_sidebar_collapsed.
- **«🛠 Настройки модели»** новый sidebar nav-пункт, активен когда у юзера есть хоть один профиль (резолвится из earliest-created). Открывает `/profiles/{id}/feature-rules`.
- **`/profiles/{id}/feature-rules`** — таблица 22 фич × 3-state переключатель (🟢 green-flag / 🔴 red-flag / ⊘ ignore). Click → PATCH endpoint upsert'ит rule + sync `recompute_buckets_for_profile` (batched 1 SELECT, не N+1) + toast «Бакеты: N зелёных / N серых / N отклонено». Double-click защищён disabled-guard в JS.

---

## §4. Что делать в новой сессии — unified-criteria редизайн (Phase 2 brainstorm в работе)

### §4.0 Текущий статус — pivot к unified criteria

Phase 1 defect-checklist зашиплен 2026-05-12 + правила на iPhone 12 PM выставлены (21 шт). Юзер создал второй профиль **iPhone 13**, и выявились архитектурные проблемы:

1. **Sidebar nav «🛠 Настройки модели» захардкожена на первый профиль** — для iPhone 13 нет UI к feature-rules.
2. **Каша двух LLM-систем:** V2 criteria (`criteria_templates.yaml`, 15 entries, через форму профиля) и Defect features (`dialog_topics.yaml`, 22 entries, через отдельную страницу) **пересекаются по 5+ key'ам** (icloud_locked ↔ locks.icloud_linked, screen_broken ↔ display.glass_broken, etc.). V2 LLM bucket вычисляется, но **не используется** (`profile_listings.bucket` пишется из defect-pipeline).
3. **iPhone 13 при первом polling-проходе слил 871 лот в grey** (нет правил → нет фильтрации). DB почищено 2026-05-12.

**Brainstorm в работе:** ветка `superpowers:brainstorming` начата для unified-criteria дизайна. План на 2 фазы:
- **Phase 2.0 (stop-gap, ~3h):** вынести feature-rules-страницу из глобального sidebar в форму профиля. iPhone 13 получит свой UI. V2 criteria остаются работать «в холостую».
- **Phase 2.1 (unification, отдельный спек):** единая модель — defect / attribute filter / lock / info, миграция V2 → unified, удаление дублей. Юзер выбрал именно этот двухфазный путь.

Brainstorm пауза на этом моменте — после restart сессии можно возобновить с этого state.

### §4.1 Если хочешь продолжить unified-criteria дизайн

Спека пока не написана. Нужно:
1. Пройти clarifying-questions цикл по data model (один тип vs тип-aware), placement UI (форма профиля section vs sub-page vs drawer), deprecation V2 criteria (kill / mapping / coexist).
2. Дизайн в `DOCS/superpowers/specs/2026-05-XX-unified-criteria-design.md`.
3. После approve → writing-plans → 2 фазы.

### §4.2 Если хочешь быстрый stop-gap (Phase 2.0 в одиночку)

Минимальная задача — переместить sidebar nav пункт «🛠 Настройки модели» из глобального layout'a в форму профиля (`/search-profiles/{id}/edit`) как отдельную секцию или вкладку. Эстимейт 2-3h. Тогда iPhone 13 сразу настраивается. V2 criteria остаются в той же форме как сейчас (дубль, но не блокер).

### §4.3 Если хочешь soak Phase 1 на iPhone 12 PM пока

Backfill ещё не запущен — `listing_features` пуст. Чтобы получить реальные данные парсера:
```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm avito-monitor python -m scripts.backfill_features'
```
~$0.0006 × 120 ≈ $0.07. После пробежки увидишь в expanded card body блок «Признаки» с ✓/⊘/⚪. Соак-наблюдения см. §4.4.

### §4.4 Соак-наблюдения (3-4 дня после backfill)

Метрики ручной оценки:
- **Recall парсера** — на ~50 свежих лотах оценить вручную: насколько LLM правильно ловит defect-сигналы? Если recall < 95% по критичным фичам (icloud, broken_glass) — нужен Phase 1.5 keyword fallback.
- **False-positive auto-reject** — сколько iCloud-locked-detected было ложными? Recovery через «↶ Вернуть в новые» в Rejected.
- **LLM cost/день** — на сколько вырос. Если выше $0.05/день — оптимизация.

Команды для дампа state:
```powershell
# Сколько лотов в каждом бакете после backfill
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 python -c "
import asyncio, asyncpg, os
async def m():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\", \"postgresql://\")
    c = await asyncpg.connect(url, statement_cache_size=0)
    rows = await c.fetch(\"SELECT bucket, count(*) FROM profile_listings GROUP BY bucket\")
    for r in rows: print(dict(r))
    auto_rej = await c.fetchval(\"SELECT count(*) FROM profile_listings WHERE rejected_reason LIKE \x27auto:%\x27\")
    print(\"auto-rejected:\", auto_rej)
    await c.close()
asyncio.run(m())"'

# LLM расход за 24ч
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose logs --since=24h worker 2>&1 | grep -iE 'parse_section|llm.cost' | tail -20"
```

### §4.5 Backlog Phase 1 follow-ups (не блокеры)

- **T9-followup: API-killers bypass feature pipeline** — частично исправлено (hotfix `5a1854c` вызывает feature pipeline и в API-killer ветке тоже, отдельной сессией). Если в логах увидим race conditions / двойные upsert'ы — переработать.
- Все остальные code-review findings уже зашиты в commits (`64bde03` repository hardening, `8cac265` taxonomy validators, `9c10f8b` N+1 + double-click fix, `5a1854c` API-killer + stale params).

### §4.6 Что в Phase 2 seller-dialog (категорийный опрос, после soak)

Описано в spec `2026-05-12-defect-checklist-design.md` §10:

1. **Setup-modal → checklist-drawer**: текущий setup-modal Phase B заменяется на slide-out drawer с тоглами на unknown-фичах. Operator может включить тоглы только на тех, что хочет уточнить.
2. **Category-batched survey**: вместо 22 микро-вопросов один человеческий вопрос на категорию. «Вижу что у вас разбито стекло. По остальным моментам уточните: дисплей менялся? полосы/пятна? тачскрин работает?» — ≤ 6 циклов вопрос-ответ. Новые LLM dispatcher'ы `formulate_category_question` + `parse_category_answer`.
3. **Personalised opener**: «Я внимательно прочитал ваше объявление. Понял, что у вас: <список confirmed defects>. Всё верно?» Если confirmed defects = 0 → opener пропускается.
4. **Двойной LLM на каждый inbound**: existing `parse_topic_answer` (targeted) + новый `scan_message_for_features` (broad sweep по всем active features профиля). Продавец проговорился про iCloud в ответе на вопрос про АКБ → recompute_bucket → если стало red → close dialog + TG notify.

Phase 2 ≈ 8h dev + 1-2d soak. Дispatch'нем когда recall парсера Phase 1 ≥ 95%.

---

## §5. Backlog (за пределами defect-checklist)

### §5.1 Seller-dialog (Phase B уже shipped, остальные фазы):

- **Phase C** (drawer вместо modal для setup) — частично перекрывается Phase 2 defect-checklist (там и будет drawer).
- **Phase D**: stages 4-9 (`price_negotiation` → ... → `closed`). Включает «Согласование цены» (operator-driven), polling `items/{id}.price` watch, Avito-delivery tracking.
- **Phase E**: SLA worker `dialog_silence_tick` + 4 оставшихся TG-пинга + sortings/filters в kanban + Phase 2 smart auto-tick.

### §5.2 Известные мелочи (V1.5)

- **AVITO_OWN_USER_ID env** не сконфигурирован → SSE direction грязный.
- **SSE durability / catch-up** — теряет события при reconnect (нет resume-token). Pull-based fallback по active dialog'ам.
- **«Евгений: » prefix в SSE text** — нормализовать.
- **accept→reject race** — worker создаёт dialog даже если operator уже reject'нул.
- **accept→reject→accept resurrection** — второй accept не реанимирует closed dialog (idempotency).
- **`RELIABILITY_DISABLED_SCENARIOS=G`** — scenario G в health-checker раньше скипалась, теперь messenger-bot задеплоен — пора включить probe.
- **docker-compose.yml не в git** — `/opt/avito-system/docker-compose.yml` редактируется напрямую на VPS.
- **V2 reliability whitelist bug** — `whitelist_own_listings_only=True` не отсёк чужой канал в ship-blocker инциденте Phase A. Разобрать при возврате к V2.

---

## §6. Команды для проверки состояния

### §6.1 БД — feature rows + rules + бакеты

```powershell
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 python -c "
import asyncio, asyncpg, os
async def m():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\", \"postgresql://\")
    c = await asyncpg.connect(url, statement_cache_size=0)
    print(\"alembic:\", await c.fetchval(\"SELECT version_num FROM alembic_version\"))
    print(\"listing_features:\", await c.fetchval(\"SELECT count(*) FROM listing_features\"))
    print(\"profile_feature_rules:\", await c.fetchval(\"SELECT count(*) FROM profile_feature_rules\"))
    by_bucket = await c.fetch(\"SELECT bucket, count(*) FROM profile_listings GROUP BY bucket\")
    print(\"buckets:\", [dict(r) for r in by_bucket])
    auto_rej = await c.fetchval(\"SELECT count(*) FROM profile_listings WHERE rejected_reason LIKE \x27auto:%\x27\")
    print(\"auto-rejected:\", auto_rej)
    by_rule = await c.fetch(\"SELECT rule, count(*) FROM profile_feature_rules GROUP BY rule\")
    print(\"rules:\", [dict(r) for r in by_rule])
    await c.close()
asyncio.run(m())"'
```

### §6.2 Worker логи на feature-pipeline

```powershell
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose logs --tail=200 worker 2>&1 | grep -iE 'parse_section|analyze_listing_features|compute_bucket|defect|ERROR' | tail -30"
```

### §6.3 Health check + smoke

```powershell
curl.exe -sS -o NUL -w "kanban -> %{http_code}`n" "https://avitosystem.duckdns.org/listings?tab=in_progress"
curl.exe -sS -o NUL -w "new    -> %{http_code}`n" "https://avitosystem.duckdns.org/listings?tab=new"
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose ps --format 'table {{.Service}}\t{{.Status}}'"
```

### §6.4 Backfill вручную (одного профиля)

```powershell
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm avito-monitor python -m scripts.backfill_features --profile <profile_uuid>'
```

`--dry-run` чтоб только посчитать сколько лотов будут обработаны.

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md, DOCS/REFERENCE/README.md (особенно top entry про
2026-05-12 defect-checklist), и DOCS/superpowers/specs/2026-05-12-defect-
checklist-design.md.

Phase 1 defect-checklist зашиплен в prod 2026-05-12. Pipeline работает,
но profile_feature_rules пуст — пока operator не выставит правила через
UI и не запустит backfill, реальных feature-данных нет. Текущая задача —
soak: проверить точность LLM-парсера на свежих лотах, мониторить
auto-reject rate, ловить regressions. Phase 2 (category-batched survey +
opener + двойной LLM-per-inbound) — после соак.

Production: VPS 81.200.119.132 + Cloud Supabase Frankfurt.
UI https://avitosystem.duckdns.org. HEAD = 79f8aef.
V2 reliability bot выключен (MESSENGER_BOT_ENABLED=false).
```

---

## §8. Что НЕ работает / избежать повторений

- ❌ **Postgres НЕ каскадирует FK при UPDATE по умолчанию.** Если мигрируешь rename ключа в parent table — сначала drop FK, потом UPDATE child + parent, потом recreate FK. Hotfix `79f8aef` в миграции 0015 это исправил.
- ❌ **Docker container НЕ видит изменений в host filesystem** (avito-monitor не монтирует repo как volume) — для миграций нужен `docker compose build avito-monitor` после правки migration file. Затем `docker compose run --rm avito-monitor alembic upgrade head`.
- ❌ **Никогда не пересобирай только один service** через `docker compose build avito-monitor` — shared image. Когда меняешь общий код (`app/services/*`), используй `docker compose build` (без аргументов) + `docker compose up -d --force-recreate <все потребители>`.
- ❌ **`<script>` теги в HTML, инжектируемом через `innerHTML`, НЕ выполняются**. Delegated handlers в parent template.
- ❌ **`templates.TemplateResponse` новая сигнатура**: `(request, name, context)` позиционно.
- ❌ **JWT-сессии могут стать server-side-зомби**: TTL валиден, но Avito ревокнул раньше → 401. Recovery: запустить Avito-app на телефоне на 60 сек.
- ❌ **Avito createItemChannel хочет itemId как int**, не string.
- ❌ **TaskIQ-task'и регистрировать в `app/tasks/broker.py::_register_tasks()`** через import — иначе worker не подхватит.
- ❌ **Card partials НЕ должны линковать на `/listings/{id}`** — этот route не существует.
- ❌ **Не deploy'ить через rsync с Windows** — нет в системе. Использовать `tar + scp + ssh tar -xf`.
- ❌ **PowerShell не имеет grep** — либо grep внутри ssh, либо PowerShell `Select-String`.
- ❌ **SQLite не поддерживает JSONB + `pg_insert.on_conflict_do_update`** — для тестов с in-memory SQLite в `tests/defect_features/conftest.py` используется hand-written CREATE TABLE + dialect-aware UPSERT (`_is_postgres(session)` check в `repository.py`).
- ❌ **Pythonside UUID default + server_default** — на моделях `ListingFeature` и `ProfileFeatureRule` стоит и `default=uuid.uuid4`, и `server_default=text("gen_random_uuid()")`. Это для SQLite test compatibility (SQLite не знает `gen_random_uuid()`). В Postgres prod SQLAlchemy использует Python-side default — функционально эквивалентно.

---

## §9. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`
