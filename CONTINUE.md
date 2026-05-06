# CONTINUE — Быстрый рестарт сессии

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md` (особенно ADR-008/010/011). Production state — раздел 1. Что заблокировано прямо сейчас — раздел 1.5. Следующая большая задача — раздел 4. Команды на проверку — раздел 5.
>
> **Если ты — пользователь:** скопируй промпт-стартер из раздела 8 в новую сессию, или просто открой Claude Code в `c:/Projects/Sync/AvitoSystem/` — этот файл подгружается через `init`.

---

## 1. Production state — 2026-05-06 (Phase A V2 LLM pipeline shipped, Phase B blocked)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU, **2c/4GB**/15GB Ubuntu 24.04 + 2GB swap, Docker 29). 13 контейнеров: caddy, avito-xapi, avito-monitor, avito-mcp, redis, scheduler, health-checker, telegram-bot + **5×worker** (`worker-1, 4, 5, 6, 7, 8` — нумерация после force-recreate). Upgraded с 1c/2GB после OOM 2026-05-05. |
| **Public URL** | `https://avitosystem.duckdns.org` (Caddy + Let's Encrypt cert auto-renew, DuckDNS cron-update token в `/usr/local/bin/duckdns-update.sh`) |
| **БД** | Cloud Supabase `drwgozasaypgphkxyizt` (Frankfurt, eu-central-1). `DATABASE_URL` pooler 6543. Критично: `prepared_statement_cache_size=0` через `connect_args` — URL query string не работает в SQLAlchemy 2.x (фикс в `app/db/base.py:50` + `alembic/env.py:53`). `SUPABASE_KEY = sb_secret_*`. |
| **Phone** | OnePlus 8T (`110139ce`), USB к Windows ПК. APK `com.avitobridge.sessionmanager` в user_0+user_10. На 2026-05-05 Avito-app в user_0 залогинен под другим Avito user (`431483569`), не старый Clone (`157920214`). |
| **Homelab** | закрыт физически. Rollback невозможен. |
| **UI логин** | `owner` / `Avito2026Soak`, `remacs` / `31415926` (admin). |
| **Branch state** | `main` ahead origin/main = 0 (всё push'нуто на 2026-05-05). HEAD = `cfeb99c` («switch V2 default to per_criterion»). Ветка `feat/server-migration` смержена в main коммитом `6ca0295`. |
| **Deploy mechanism** | rsync с локальной машины: `cd avito-monitor && tar -czf - --exclude __pycache__ --exclude .git . \| ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'`. Затем `ssh root@VPS 'cd /opt/avito-system && docker compose build <svc> && docker compose up -d --force-recreate --no-deps <svc>'`. Production-репо НЕ git. |

### 1.5. Что заблокировано прямо сейчас

**Live polling не работает.** Все 7 search_profiles имеют `owner_account_id=42c179db` (Clone, state=dead, exp 2026-05-01) — autosearch_sync импортировал их под этим аккаунтом. Pool пустой:

```
nickname              | android_user_id | state    | expires_at             | live?
Clone (42c179db)      | user_10         | dead     | 2026-05-01 18:27 UTC   | -3д+
auto-157920214 (b5cb) | user_0          | cooldown | 2026-05-05 11:32 UTC   | exp
auto-431483569 (14ac) | user_0          | cooldown | 2026-05-05 15:08 UTC   | exp
```

При попытке fetch через нового `431483569` Avito возвращает **403** на `/subscriptions/261149389/items` — autosearch принадлежит старому Clone, не новому юзеру.

**Чтобы оживить:**
1. **Юзер открывает Avito-app в user_0 под `157920214`** (старый аккаунт Clone). Avito-app сам решит refresh near-expiry → APK NotificationListener поймает push → POST `/api/v1/sessions` → `b5cbf28b` перейдёт в `state=active`.
2. **Для user_10** (Clone) — открыть и его, тогда полноценный pool=2.

После этого Phase B соак запускается автоматически (один профиль `iPhone 12 Pro` уже включил V2: `notification_settings.llm_pipeline_v2=true`).

---

## 2. Manual refresh model + reliability scenarios

### Refresh flow

1. Юзер вручную открывает Avito-app в нужном android-юзере.
2. Avito-app сам решает refresh (по своей внутренней логике near-expiry).
3. APK ловит push через NotificationListener → читает Avito-app SharedPrefs (root через Magisk) → `POST https://avitosystem.duckdns.org/api/v1/sessions` с новым session_token + device_id + fingerprint.
4. xapi: `resolve_or_create_account(payload.u, payload.device_id)` → деактивирует старую active session → INSERT новую.
5. monitor health-checker (account_tick): раз в 30 сек проверяет accounts. Если `expires_at < NOW` → one-shot TG-alert.

### Health-checker scenarios (после `92079da` + `a5d566a`)

Каждые 5 минут health-checker гоняет 8 сценариев. После 3 fail подряд шлёт TG-alert с **конкретным временем/числом**, не абстрактным «скоро»:

| Letter | Title | Reason формат |
|---|---|---|
| **A** | JWT-токен | «протухнет в HH:MM +TZ (через Xч Yм)» |
| **B** | Ротация JWT-токена | «последняя ротация Xч назад в HH:MM +TZ» |
| **C** | Мессенджер Avito (доступность) | «endpoint /url → HTTP {code}» |
| **D** | Мессенджер Avito (latency) | «{ms} ms > budget {budget} ms» |
| **E** | Real-time мессенджер (SSE) | «connect {ms}ms, second event {ms}ms» |
| **F** | POST в мессенджер Avito | «endpoint /url → HTTP {code} {error}» |
| **G** | DISABLED in prod (`RELIABILITY_DISABLED_SCENARIOS=G`, messenger-bot не deployed) | — |
| **I** | Push с phone | «последний push HH:MM +TZ (≈Xч назад)» |

При recovery — `✅ Восстановлено: <title> (X) — <fresh_for>`. Каждый scenario пишет `details["reason"]` (FAIL) и `details["fresh_for"]` (PASS). Файлы: `app/services/health_checker/alerts.py:77-134` (titles) + `scenarios/{a..f,i}_*.py` (numbers).

---

## 3. Backlog (по приоритету)

| # | Задача | Severity | Часы |
|---|---|---|---|
| **1** | Pool warm-up — открыть Avito-app в user_0 под `157920214`, опционально user_10 | **критично** | 0.1 (manual) |
| **2** | Ротация засветившихся секретов | high | 0.3 |
|   | • Root-пароль VPS `Mi31415926pSss!` — `passwd` под root |   |   |
|   | • Supabase legacy service_role JWT — Dashboard → Settings → API → «Reset JWT secret» |   |   |
|   | • Supabase Secret API key `sb_secret_*` — Revoke, новый, обновить `/opt/avito-system/.env` |   |   |
|   | • Avito-MCP auth token `7235ad5be6...4f2222` — opt'l |   |   |
|   | • UI пароли `Avito2026Soak`/`31415926` — `python -m scripts.create_admin <user> <new_pw>` |   |   |
| 3 | Зарегистрировать второй Avito-аккаунт для real pool=2 | high | 0.5 + reg |
| 4 | Avito-MCP в Claude Code — `claude mcp add --transport sse avito https://avitosystem.duckdns.org/mcp/sse --header "Authorization: Bearer 7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222"` (4 tools) | low | 0.1 |
| 5 | TG bot inbound через прокси | low | 0.3 |
| 6 | Captcha/IP-ban detection | medium | 2-3 |
| 7 | Reboot recovery alert (FBE PIN unlock detector) | low | 0.5 |
| 8 | Phase C migration — apply `0009_drop_legacy_v2_artifacts` ПОСЛЕ Phase B соака | medium | 0.2 |

---

## 4. Следующая большая задача — Phase B соак V2 LLM pipeline

**State:** Phase A V2 LLM pipeline shipped 2026-05-05 (план `C:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md`). Двухступенчатый ADR-010 заменён на **single-stage flag-based evaluation с 3 корзинами**:

- **GREEN** = все criteria green ≥ confidence_threshold (0.7) → TG-нотификация если `in_alert_zone`
- **GREY** = unknown / низкий confidence → видно в `/listings` с серым chip, без алерта
- **RED** = любой criterion red ≥ threshold → auto-INSERT в `user_listing_blacklist` reason=`auto_red:<key>` (ADR-011 reuse, varchar(96) после миграции 0008)

**Default стратегия — `per_criterion`** (с 2026-05-05 коммит `cfeb99c`). Per_listing остался как fallback. Hot-switch: `UPDATE search_profiles SET evaluate_strategy='per_listing' WHERE id=...`. Cache гранулярный per-criterion → переключение НЕ инвалидирует.

### Что задеплоено в Phase A

- Миграции 0006/0007/0008 применены. 0009 (Phase C — destructive) написана, **НЕ применена**.
- 13 templates в `criteria_templates` (8 criterion + 2 info_llm + 3 info_api), seeded из `app/data/criteria_templates.yaml`.
- 7 legacy профилей auto-конвертированы в `profile_criteria` (5-6 rows на каждый, derived из `allowed_conditions`).
- `LLMAnalyzer.evaluate_listing(...)` + 3 prompts: `evaluate_listing_batch.md`, `evaluate_criterion.md`, `extract_info.md`.
- TaskIQ task `evaluate_listing` в `app/tasks/analysis.py`. Polling routes на v2 если `notification_settings.llm_pipeline_v2=true` (env override `LLM_PIPELINE=v2`).
- UI редактор criteria в `/search-profiles/<id>/edit` — раздел «V2 пайплайн»: chips library + params-формы для memory_gte/title_matches_model + custom rows.
- `/listings` — bucket badge на карточках + filter chips «Все / Зелёная / Серая / Красная» + query param `?bucket=`.
- Health-checker scenarios A-I с конкретными deadlines.
- pgbouncer fix через `connect_args` в base.py + alembic env.py.

### Phase B шаги (когда оживёт polling)

1. **Smoke test live polling**: `iPhone 12 Pro` уже на `evaluate_strategy=per_criterion`. Дождаться poll_profile → один listing → 5 LLM-вызовов → bucket → notification (если green+alert_zone).
2. **Соак 3-4 дня**. Метрики через `bash ops/v2-soak-metrics.sh` на VPS — выводит:
   - Bucket distribution per profile (24h)
   - LLM cost per type (24h, total + per 1k listings + avg latency)
   - Auto-red blacklist rate (24h, по criterion)
   - Polling success rate (1h)
   - Pool state right now
3. **Прогноз бюджета** (per_criterion с 5-8 criteria): initial backfill ~3K лотов = $1-2 разово; daily 150 лотов = $0.075/день ≈ $2.25/мес. Лимит `OPENROUTER_DAILY_USD_LIMIT=$20` → запас ×200.
4. **Если качество плохое** в `per_criterion` — hot-switch на `per_listing` через UPDATE; cache reuse, ничего не теряется.
5. **Phase C** после signoff соака: `docker compose exec avito-monitor alembic upgrade head` (применит 0009 — drop legacy `custom_criteria` + `allowed_conditions` + старые ProcessingStatus values + legacy task функции).

---

## 5. Команды на проверку production stack

```bash
# Containers
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose ps'

# Public smoke
curl -s https://avitosystem.duckdns.org/health
curl -sH "X-Api-Key: test_dev_key_123" https://avitosystem.duckdns.org/api/v1/accounts | python3 -m json.tool

# V2 soak metrics (one-shot, читает .env на VPS)
ssh root@81.200.119.132 'bash /opt/avito-system/v2-soak-metrics.sh'

# Pool state direct SQL
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql 'postgresql://postgres.drwgozasaypgphkxyizt@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require' -c \"SELECT a.nickname,a.state,s.expires_at FROM avito_accounts a LEFT JOIN avito_sessions s ON s.account_id=a.id AND s.is_active;\""

# Логи
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose logs --tail=50 avito-monitor'
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose logs --tail=50 worker'
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose logs --tail=50 health-checker'

# Health-checker manual
ssh root@81.200.119.132 'docker exec avito-system-health-checker-1 curl -s -X POST http://localhost:9100/run-all | python3 -m json.tool'

# Trigger immediate poll for a profile (uuid)
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "import asyncio; from app.tasks.polling import poll_profile; asyncio.run(poll_profile.kiq(\"<uuid>\"))"'

# Trigger immediate evaluate_listing on existing listing
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "import asyncio; from app.tasks.analysis import evaluate_listing; asyncio.run(evaluate_listing.kiq(\"<listing_uuid>\", \"<profile_uuid>\"))"'

# adb через USB к Windows ПК
adb devices
adb shell 'su -c "cat /data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml"' \
  | grep -E "server_url|api_key|expires_at|mcp_url"
adb shell am switch-user 10                # переключить на user_10
adb shell am switch-user 0                 # вернуться в Main

# Avito-app SharedPrefs (где session_token реально живёт)
adb shell 'su -mm -c cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml' \
  | grep -E '"u"|"exp"|device_id'

# Reset cooldown на аккаунте (force pool re-attempt)
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql 'postgresql://...' -c \"UPDATE avito_accounts SET state='active', cooldown_until=NULL, consecutive_cooldowns=0 WHERE id='<uuid>'\""

# Hot-switch стратегии профиля
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql 'postgresql://...' -c \"UPDATE search_profiles SET evaluate_strategy='per_listing' WHERE name='iPhone 12 Pro'\""
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `C:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md` | План V2 LLM pipeline (Phase A done, Phase B/C предстоят) |
| `DOCS/V1_EXECUTION_PLAN.md` | 8 блоков V1 — блок 4 заменён V2 пайплайном |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главный ТЗ V1.2 |
| `DOCS/DECISIONS.md` | ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 (двухступенчатый — заменён V2 в 2026-05-05), ADR-011 autosearch sync + auto_red blacklist |
| `DOCS/superpowers/plans/2026-05-02-server-migration.md` | Server migration plan (выполнен) |
| `ops/migration-2026-05-02/README.md` | Audit data migration |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Deploy artifacts production |
| `ops/v2-soak-metrics.sh` | Phase B observability one-shot dump |
| `DOCS/REFERENCE/01-avito-api.md` | Avito endpoints + headers + structured params |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow (manual model post-2026-05-02), pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk grants, ADB, NotificationListener |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi workflow |
| `DOCS/avito_api_snapshots/` | JSON-снимки Avito API (categories, fields, brands) |

---

## 7. Где секреты

* **Глобальные старые:** `c:/Projects/Sync/CLAUDE.md` — homelab Supabase. Cloud-проект (`drwgozasaypgphkxyizt`) **НЕ** задокументирован, секреты на VPS в `/opt/avito-system/.env`.
* **VPS** `/opt/avito-system/.env` (chmod 600 root):
  - `DATABASE_URL` (asyncpg pooler 6543, query string + `connect_args` в коде)
  - `SUPABASE_URL=https://drwgozasaypgphkxyizt.supabase.co`
  - `SUPABASE_KEY=sb_secret_*`
  - `AVITO_XAPI_API_KEY=test_dev_key_123` (plaintext; hash в `avito_api_keys`)
  - `AVITO_MCP_AUTH_TOKEN=7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222`
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`
  - `OPENROUTER_API_KEY` (ротирован 2026-04-29)
  - `OPENROUTER_DAILY_USD_LIMIT=20` (поднят 2026-05-05)
  - `DOMAIN=avitosystem.duckdns.org`
  - `RELIABILITY_DISABLED_SCENARIOS=G`
* **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (per-user в `/data/user/{0|10}/...`). Ключи: `server_url`, `api_key`, `mcp_url`, `mcp_auth_token`, `auto_launch_avito` (false), `auto_sync` (true).
* **Avito-app session:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml` — `session`, `refresh_token`, `device_id`, `remote_device_id`, `profile_id`. На 2026-05-05 user_0 залогинен под `431483569`, user_10 — без логина (только crash reports).
* **DuckDNS:** token `688fa99d-efaa-41d7-9c42-824569926b8f` в `/usr/local/bin/duckdns-update.sh` на VPS.
* **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 8. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/. Phase A V2 LLM pipeline shipped 2026-05-05,
ветка main pushed. Production: VPS 81.200.119.132 (2c/4GB) +
https://avitosystem.duckdns.org + Cloud Supabase Frankfurt.
13 контейнеров: caddy, xapi, monitor, mcp, redis, scheduler, health-checker,
telegram-bot + 5×worker. Default V2 strategy = per_criterion (~$0.07/1k лотов).

UI логин: owner / Avito2026Soak (или remacs / 31415926).

Прочитай CONTINUE.md (раздел 1.5 — что заблокировано, раздел 4 — Phase B соак).

Pool сейчас drained: все 7 профилей owned by Clone (dead). Чтобы оживить
polling — открыть Avito-app в user_0 на phone под Avito user_id=157920214.

После warm-up — Phase B соак 3-4 дня (метрики через `ssh VPS 'bash
/opt/avito-system/v2-soak-metrics.sh'`), потом Phase C migration apply.
```

---

## TL;DR для следующей сессии

1. **Phase A V2 LLM pipeline shipped** 2026-05-05, main pushed (`cfeb99c`). 3 новые таблицы (criteria_templates / profile_criteria / profile_listing_evaluations), 13 templates seeded, 7 профилей конвертированы.
2. **Default strategy = per_criterion** (granular cache, $0.07-0.50/1k лотов, ~$2/мес daily). Hot-switch на per_listing через `UPDATE search_profiles SET evaluate_strategy='per_listing'`.
3. **Phase B заблокирован** — pool drained, нужен Avito-app login под `157920214` в user_0. Backlog #1.
4. **Phase B соак** запустится автоматом когда оживёт polling — `iPhone 12 Pro` уже на V2. Метрики через `ops/v2-soak-metrics.sh`.
5. **Phase C migration** (0009 — drop legacy custom_criteria/allowed_conditions, удаление `analyze_listing`/`match_listing`) написана, **НЕ применена**. Apply после signoff соака.
6. **Health-checker scenarios A-I** теперь показывают конкретные deadlines/numbers, не «скоро».
7. **Backlog #2 — ротация секретов** (всё засветилось в чате 2026-05-04..05).
