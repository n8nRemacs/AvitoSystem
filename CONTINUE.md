# CONTINUE — Быстрый рестарт сессии

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md`. Production VPS state — раздел 1. Следующая большая задача — раздел 4. Backlog — раздел 3. Команды на проверку — раздел 5.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, работа продолжится с того же места.

---

## 1. Production state — 2026-05-04

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU, 1c/2GB/15GB Ubuntu 24.04, Docker 29). 9 контейнеров: caddy, avito-xapi, avito-monitor (web UI), avito-mcp, redis, worker, scheduler, health-checker, telegram-bot |
| **Public URL** | `https://avitosystem.duckdns.org` (Let's Encrypt cert auto-renew, DuckDNS cron-update token в `/usr/local/bin/duckdns-update.sh`) |
| **БД** | Supabase Cloud `drwgozasaypgphkxyizt` (Frankfurt, eu-central-1). `DATABASE_URL` use pooler 6543 + `?prepared_statement_cache_size=0` (asyncpg+pgbouncer fix). `SUPABASE_KEY` — `sb_secret_*` для xapi REST. |
| **Phone** | OnePlus 8T (`110139ce`), USB к Windows ПК. APK `com.avitobridge.sessionmanager` в user_0+user_10, оба видят VPS. Magisk policies для UID 10296+1010296 = Allow, multiuser_mode=1. Notification listener granted в обоих юзерах. |
| **Homelab** | xapi+monitor контейнеры **остановлены**. Rollback: `ssh homelab; cd /mnt/projects/repos/AvitoSystem/avito-{xapi,monitor}; docker compose start`. |

### Branch state

`feat/server-migration` — **20 коммитов** поверх main (см. `git log main..HEAD`). НЕ замержена в main, ждёт user-decision.

### Pool state на момент закрытия сессии

```
avito_accounts:
  Clone (42c179db…)            user_10  state=dead
  auto-157920214 (b5cbf28b…)   user_0   state=cooldown
```

Pool неактивен — Avito-app в обоих юзерах не делал refresh JWT (текущий токен экспирится 2026-05-05 ~08:25 UTC, ещё свежий). Polling возобновится автоматически когда:
- Avito-app сам решит refresh near-expiry → APK поймает push → POST `/api/v1/sessions` на VPS → state=active.
- Либо юзер вручную откроет Avito-app в каждом android-юзере на 60-90 сек.

Health-checker мониторит, шлёт TG-alerts (см. раздел про alerting ниже).

---

## 2. Manual refresh model — как работает

1. **Юзер вручную:** утром открыть Avito-app в user_0 (Main), вечером в user_10 (Clone), или просто когда expires_at близко к now.
2. **Avito-app сам решает refresh** (по своей внутренней логике near-expiry).
3. **APK ловит push через NotificationListener** → читает Avito-app SharedPrefs (root через Magisk) → `POST https://avitosystem.duckdns.org/api/v1/sessions` с новым session_token + device_id + fingerprint.
4. **xapi:** `resolve_or_create_account(payload.u, payload.device_id)` → деактивирует старую active session → INSERT новую.
5. **monitor health-checker (account_tick):** раз в 30 сек проверяет accounts. Если `expires_at < NOW` — one-shot TG-alert. Если все аккаунты stale → critical alert «Polling DOWN».

### V2 reliability scenarios (другой таймер health-checker)

Параллельно с account_tick запускается loop из 8 сценариев (A-G + I) каждые 5 минут. Каждый проверяет конкретный аспект инфраструктуры. После 3 fail подряд шлёт TG-alert в формате:

```
🚨 <человекочитаемый title>  (<буква>)
<technical reason>, 3 fail подряд, последний HH:MM:SS +TZ.

Возможные причины:
• ...
```

При recovery (один pass) — `✅ Восстановлено: <title> (X)`.

Сценарии:
- A — JWT-токен скоро протухнет
- B — Ротации JWT не было >24ч
- C — Мессенджер Avito временно недоступен
- D — Мессенджер Avito медленный или упал
- E — Real-time мессенджер не работает (SSE bridge)
- F — POST в мессенджер Avito не проходит
- G — отключён в production (`RELIABILITY_DISABLED_SCENARIOS=G`, messenger-bot не deployed)
- I — Push-уведомления с phone не приходят

Описания и список причин — `avito-monitor/app/services/health_checker/alerts.py:73` (SCENARIO_DESCRIPTIONS). Чтобы переформулировать — менять там, scp на VPS, `docker compose up -d --build health-checker`.

---

## 3. Backlog (по приоритету)

| # | Задача | Severity | Часы |
|---|---|---|---|
| 1 | **Ротация секретов** (засветились в чате 2026-05-04) | high | 0.3 |
|   | • Root-пароль VPS `Mi31415926pSss!` — `passwd` под root |   |   |
|   | • Supabase legacy service_role JWT — Dashboard → Settings → API → «Reset JWT secret» |   |   |
|   | • Supabase Secret API key `sb_secret_JWTeco7Y5...` — Revoke, создать новый, обновить `/opt/avito-system/.env` |   |   |
|   | • Avito-MCP auth token `7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222` — opt'l rotate |   |   |
| 2 | **Зарегистрировать второй Avito-аккаунт** для реального pool=2 | high | 0.5 + регистрация |
| 3 | **Pool warm-up** — открыть Avito-app в user_0+user_10 на phone (manual one-time, после первой refresh цикл устаканится) | high | 0.1 |
| 4 | **Avito-MCP в Claude Code** — добавить через `claude mcp add --transport sse avito https://avitosystem.duckdns.org/mcp/sse --header "Authorization: Bearer 7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222"`. Tools: `avito_fetch_search_page`, `avito_get_listing`, `avito_get_listing_images`, `avito_health_check`. | low | 0.1 |
| 5 | **TG bot inbound через прокси** | low | 0.3 |
| 6 | **Captcha/IP-ban detection** | medium | 2-3 |
| 7 | **Reboot recovery alert** (FBE PIN unlock detector) | low | 0.5 |
| 8 | **Merge `feat/server-migration` → main** + cleanup | medium | 0.2 |

---

## 4. Следующая большая задача — LLM разбор парсинга объявлений

**Цель:** настроить core monitoring loop — search profile parses Avito search URL → fetches listings via xapi → LLM classifies condition (`working`/`blocked_icloud`/`broken_screen`/...) → LLM matches alert criteria → notification.

### Что уже есть (надо проверить)

- **`search_profiles`** на Cloud — 7 rows перенесены с homelab. Проверить через `GET /api/v1/accounts` или Cloud SQL.
- **TaskIQ scheduler + worker** запущены на VPS. Scheduler тикает каждую минуту, worker драинит queues.
- **OPENROUTER_API_KEY** в `.env` (был ротирован 2026-04-29, действующий).
- **`app/services/llm_analyzer.py`** + промпты в `app/prompts/` — это блок 3 V1_EXECUTION_PLAN, скорее всего уже реализован, проверить.
- **`avito_mcp` tools** — могут пригодиться для manual debug Avito-выдачи через Claude.

### Что нужно сделать в этой задаче

1. **Smoke test:** есть ли активный search_profile, который тикает; что worker делает — `docker logs avito-system-worker-1`. Если `poll_profile(profile_id)` уже запускается, посмотреть что он fetch'ит.
2. **Проверить блоки 2-3 V1_EXECUTION_PLAN.md (DOCS/V1_EXECUTION_PLAN.md):** что из CRUD/UI search_profiles + LLMAnalyzer уже работает, что нужно доделать.
3. **End-to-end:** взять реальный URL Avito (например, "iPhone 12 Pro Max до 13.5K"), создать profile, дождаться poll_profile → analyze_listing → notification.
4. **Двухступенчатый LLM (ADR-010):** дешёвый classify_condition на всех лотах, дорогой match только на alert-зоне с подходящим состоянием.
5. **Двойная вилка (ADR-008):** search-вилка широкая (±25%), alert-вилка узкая (юзеру важная). Проверить overlay logic.
6. **Pool активность:** для polling нужна `state=active` сессия — делать **после** того как открыли Avito-app (раздел 3 Backlog #3).

### Перед стартом следующей сессии

- Прочитать `DOCS/TZ_Avito_Monitor_V1.md` разделы 4.1 (Search Profiles), 4.4 (LLM), 4.6 (Worker pipeline).
- Прочитать `DOCS/DECISIONS.md` ADR-008, ADR-010.
- Прочитать `DOCS/V1_EXECUTION_PLAN.md` блоки 2-4.
- Понять текущий state кода — `grep -rn "poll_profile\|analyze_listing\|LLMAnalyzer" avito-monitor/app/` чтобы найти что уже есть.

---

## 5. Команды на проверку production stack

```bash
# Health всех 9 контейнеров
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml ps'

# Public smoke
curl -s https://avitosystem.duckdns.org/health
curl -s -H "X-Api-Key: test_dev_key_123" https://avitosystem.duckdns.org/api/v1/accounts | python3 -m json.tool

# Pool state
ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 curl -sH "X-Api-Key: test_dev_key_123" http://avito-xapi:8080/api/v1/accounts | python3 -m json.tool'

# Cloud Supabase прямо
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql 'postgresql://postgres.drwgozasaypgphkxyizt@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require' -c \"SELECT a.nickname,a.state,s.expires_at FROM avito_accounts a LEFT JOIN avito_sessions s ON s.account_id=a.id AND s.is_active;\""

# Логи на VPS
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml logs --tail=50 avito-monitor'
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml logs --tail=50 worker'
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml logs --tail=50 health-checker'

# Health-checker manual trigger
ssh root@81.200.119.132 'docker exec avito-system-health-checker-1 curl -s -X POST http://localhost:9100/run-all | python3 -m json.tool'
ssh root@81.200.119.132 'docker exec avito-system-health-checker-1 curl -s -X POST http://localhost:9100/alerts/test'

# adb через USB к Windows ПК (текущий юзер)
adb devices
adb shell 'su -c "cat /data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml"' \
  | grep -E "server_url|api_key|expires_at|mcp_url"

# Switch android user (для проверки настроек user_10)
adb shell am switch-user 10
adb shell 'su -c "cat /data/user/10/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml"'
adb shell am switch-user 0  # вернуться в Main

# Avito-app SharedPrefs (где session_token реально живёт)
adb shell 'su -mm -c cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml' | grep -E '"u"|"exp"|device_id'

# Rollback на homelab если совсем сломалось
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-xapi && docker compose start'
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose start'
# и в APK поменять server_url обратно на http://213.108.170.194:8080 через adb sed
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/V1_EXECUTION_PLAN.md` | 8 блоков V1 — что делается, что проверяется. Следующий этап — блоки 2-4. |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главный ТЗ V1.2 — search profiles, LLM, worker pipeline, telegram bot. |
| `DOCS/DECISIONS.md` | ADRs (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM, ADR-011 autosearch sync). |
| `DOCS/superpowers/plans/2026-05-02-server-migration.md` | Server migration plan (8 phases, выполнен). |
| `ops/migration-2026-05-02/README.md` | Audit trail data migration: какие таблицы, сколько rows. |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Deploy artifacts production. |
| `DOCS/REFERENCE/01-avito-api.md` | Все Avito endpoints + headers + structured params. |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow (manual model post-2026-05-02), pool state machine. |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk grants, ADB, NotificationListener. |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi workflow. |
| `DOCS/avito_api_snapshots/` | JSON-снимки Avito API (categories, fields, brands). |

---

## 7. Где секреты

* **Глобальные старые:** `c:/Projects/Sync/CLAUDE.md` — homelab Supabase credentials. Cloud-проект (`drwgozasaypgphkxyizt`) — там НЕ задокументирован, секреты на VPS в `/opt/avito-system/.env`.
* **VPS:** `/opt/avito-system/.env` (chmod 600 root). Содержит:
  - `DATABASE_URL` (asyncpg pooler 6543 + `?prepared_statement_cache_size=0`)
  - `SUPABASE_URL=https://drwgozasaypgphkxyizt.supabase.co`
  - `SUPABASE_KEY=sb_secret_*`
  - `AVITO_XAPI_API_KEY=test_dev_key_123` (plaintext; hash в `avito_api_keys` table)
  - `AVITO_MCP_AUTH_TOKEN=7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222`
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`
  - `OPENROUTER_API_KEY` (ротирован 2026-04-29)
  - `DOMAIN=avitosystem.duckdns.org`
  - `RELIABILITY_DISABLED_SCENARIOS=G`
* **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (per-user в `/data/user/{0|10}/...`). Ключи: `server_url`, `api_key`, `mcp_url`, `mcp_auth_token`, `auto_launch_avito` (false), `auto_sync` (true).
* **Avito-app session:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml` — `session`, `refresh_token`, `device_id`, `remote_device_id`, `profile_id`. user_10 currently без логина (только crash reports), readable через `su -mm` fallback из user_0.
* **DuckDNS:** token `688fa99d-efaa-41d7-9c42-824569926b8f` в `/usr/local/bin/duckdns-update.sh` на VPS.
* **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 8. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/. Server migration shipped 2026-05-04 на ветке
feat/server-migration (20 коммитов). Production: VPS 81.200.119.132 +
https://avitosystem.duckdns.org + Cloud Supabase Frankfurt. Manual refresh model.
9 контейнеров на VPS: caddy, xapi, monitor, mcp, redis, worker, scheduler,
health-checker, telegram-bot. Прочитай CONTINUE.md (текущий статус) +
DOCS/V1_EXECUTION_PLAN.md (блоки 2-4 для следующего этапа).

Хочу: настроить LLM-pipeline разбора объявлений (двухступенчатый LLM,
двойная вилка) — следующая большая задача V1 core. Pool warm-up: открой
Avito-app на phone в user_0+user_10 если ещё не сделал.
```

---

**TL;DR для следующей сессии:**

1. Server Migration **выполнен** 2026-05-04. Production на VPS + Cloud Supabase, homelab остановлен, APK repointed, Avito-MCP доступен через Caddy. Все backend services (worker/scheduler/health-checker/telegram-bot) запущены.
2. **Backlog #1 — ротация засветившихся секретов** (high priority): VPS root password, Supabase JWT, Supabase API key, Avito-MCP token.
3. **Backlog #3 — pool warm-up**: открыть Avito-app в user_0+user_10 для естественного refresh. Pool сейчас неактивен.
4. **Health-checker alerts** в новом формате — короткие, без Markdown, без избыточных «проверь токен» когда мы сами знаем что он fresh. Сценарий G отключён (messenger-bot не deployed).
5. Ветка `feat/server-migration` НЕ замержена в main — ждёт user-decision (`Backlog #8`).
6. **Следующий этап** — LLM-pipeline (раздел 4 этого файла + V1_EXECUTION_PLAN.md блоки 2-4).
