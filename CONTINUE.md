# CONTINUE — Быстрый рестарт сессии

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md`. Production VPS state — раздел 1. Следующая большая задача — раздел 4. Backlog — раздел 3. Команды на проверку — раздел 5.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, работа продолжится с того же места.

---

## 1. Production state — 2026-05-05 (Phase A V2 LLM pipeline shipped)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU, **2c/4GB**/15GB Ubuntu 24.04 + 2GB swap, Docker 29). 13 контейнеров: caddy, avito-xapi, avito-monitor, avito-mcp, redis, scheduler, health-checker, telegram-bot + **5×worker (`worker-1..8`)**. Upgraded с 1c/2GB после OOM на 2026-05-05. |
| **Public URL** | `https://avitosystem.duckdns.org` (Let's Encrypt cert auto-renew, DuckDNS cron-update token в `/usr/local/bin/duckdns-update.sh`) |
| **БД** | Supabase Cloud `drwgozasaypgphkxyizt` (Frankfurt, eu-central-1). `DATABASE_URL` pooler 6543 + `prepared_statement_cache_size=0` через `connect_args` (URL query string не работает в современной SQLAlchemy — фикс в `app/db/base.py:50` + `alembic/env.py:53`). `SUPABASE_KEY` = `sb_secret_*`. |
| **Phone** | OnePlus 8T (`110139ce`), USB к Windows ПК. APK `com.avitobridge.sessionmanager` в user_0+user_10. **На 2026-05-05** Avito-app в user_0 залогинен под другим Avito user (`431483569`), не старый Clone (`157920214`). |
| **Homelab** | закрыт физически. Rollback на homelab невозможен. |
| **UI логин** | `owner` / `Avito2026Soak`, `remacs` / `31415926` (admin). |

### Branch state — main current

После 2026-05-05 Phase A deploy: `feat/server-migration` смержена в `main` (commit `6ca0295`) и pushed на `origin/main`. **Production деплоится из main rsync'ом** (`/opt/avito-system/repo/` — НЕ git). Workflow rsync: `cd avito-monitor && tar -czf - --exclude __pycache__ --exclude .git . | ssh root@81.200.119.132 'cd /opt/avito-system/repo/avito-monitor && tar -xzf -'`.

### Pool state на момент закрытия сессии (2026-05-05 ~10:00 UTC)

```
avito_accounts:
  Clone                 (42c179db…)  user_10   state=dead       (exp 2026-05-01 18:27)
  auto-157920214        (b5cbf28b…)  user_0    state=cooldown   (exp 2026-05-05 11:32)
  auto-431483569 NEW    (14acfef4…)  user_0    state=cooldown   (exp 2026-05-05 15:08)  ← свежий, но в cooldown
```

**Live polling сейчас не работает.** Все 7 search_profiles имеют `owner_account_id=42c179db` (Clone, dead) потому что были импортированы через `autosearch_sync` от Clone-аккаунта. При попытке fetch через нового `431483569` Avito возвращает **403** на `/subscriptions/261149389/items` — autosearch принадлежит старому Clone, не новому юзеру.

**Чтобы оживить polling:**
- Юзеру **залогиниться обратно в Avito-app под `157920214`** (старый Clone). Avito-app сделает refresh JWT, APK push'нет в xapi `/api/v1/sessions`, существующий аккаунт `b5cbf28b` (auto-157920214) перейдёт в `state=active`.
- Альтернативно — **сделать full re-import autosearches для нового юзера** через `/search-profiles/sync` UI button после login. Это **сломает** старые 7 профилей (autosearch_id'ы будут архивированы), но создаст новые под `431483569`.

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
| 1 | **Ротация секретов** (засветились в чате 2026-05-04 + 2026-05-05) | high | 0.3 |
|   | • Root-пароль VPS `Mi31415926pSss!` — `passwd` под root |   |   |
|   | • Supabase legacy service_role JWT — Dashboard → Settings → API → «Reset JWT secret» |   |   |
|   | • Supabase Secret API key `sb_secret_*` — Revoke, создать новый, обновить `/opt/avito-system/.env` |   |   |
|   | • Avito-MCP auth token `7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222` — opt'l rotate |   |   |
|   | • UI пароли `owner` / `Avito2026Soak` и `remacs` / `31415926` — сменить через `python -m scripts.create_admin <user> <new_pw>` |   |   |
| 2 | **Зарегистрировать второй Avito-аккаунт** для реального pool=2 | high | 0.5 + регистрация |
| 3 | **Pool warm-up** — открыть Avito-app в user_0 под `157920214` (старый Clone). Manual, после первой refresh цикл устаканится | **критично** | 0.1 |
| 4 | **Avito-MCP в Claude Code** — `claude mcp add --transport sse avito https://avitosystem.duckdns.org/mcp/sse --header "Authorization: Bearer 7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222"`. Tools: `avito_fetch_search_page`, `avito_get_listing`, `avito_get_listing_images`, `avito_health_check`. | low | 0.1 |
| 5 | **TG bot inbound через прокси** | low | 0.3 |
| 6 | **Captcha/IP-ban detection** | medium | 2-3 |
| 7 | **Reboot recovery alert** (FBE PIN unlock detector) | low | 0.5 |
| 8 | ~~Merge `feat/server-migration` → main~~ — done в `6ca0295` (2026-05-05) |   | done |
| 9 | **Phase C migration** — применить `0009_drop_legacy_v2_artifacts` ПОСЛЕ Phase B соака (3-4 дня) | medium | 0.2 |

---

## 4. Следующая большая задача — Phase B соак V2 LLM pipeline

**State:** Phase A V2 LLM pipeline shipped 2026-05-05 (план в `C:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md`). Двухступенчатый ADR-010 заменён на **single-stage flag-based evaluation с 3 корзинами**:

- **GREEN** = все criteria green ≥ confidence_threshold (0.7) → TG-нотификация если в alert-зоне
- **GREY** = unknown / низкий confidence → видно в `/listings` с серым chip, без алерта
- **RED** = любой criterion red ≥ threshold → auto-INSERT в `user_listing_blacklist` reason=`auto_red:<key>` (ADR-011 reuse)

**Hot-switch** между `per_listing` (1 batch LLM call) и `per_criterion` (N calls) на лету через `UPDATE search_profiles SET evaluate_strategy='per_criterion' WHERE id=...` — cache гранулярный per-criterion, переключение не инвалидирует.

### Что уже задеплоено (Phase A done)

- 3 новые таблицы (`criteria_templates` 13 templates, `profile_criteria` 5-6 rows на каждый из 7 legacy профилей, `profile_listing_evaluations`).
- Колонки: `search_profiles.{evaluate_strategy, confidence_threshold, criteria_set_hash, bucket_routing}`, `profile_listings.{bucket, latest_evaluation_id}`.
- `LLMAnalyzer.evaluate_listing(...)` + 3 prompts (`evaluate_listing_batch.md`, `evaluate_criterion.md`, `extract_info.md`).
- Новый task `evaluate_listing` в `app/tasks/analysis.py`. Polling routes на v2 если `notification_settings.llm_pipeline_v2=true` или env `LLM_PIPELINE=v2`.
- UI редактор criteria в форме профиля (`/search-profiles/<id>/edit` → раздел «V2 пайплайн»): chips library + params-формы для memory_gte/title_matches_model + custom rows.
- Health-checker scenarios A-I — конкретные deadlines в TG-alerts (commit `92079da` + `a5d566a`).
- Bucket badge на карточках в `/listings` (commit `73072c1`).
- Migration `0009_drop_legacy_v2_artifacts` написана но **НЕ применена** — для Phase C после соака.

### Что сделать в Phase B (когда оживёт polling)

1. **Pool warm-up**: открыть Avito-app в user_0 под старым `157920214` (старый Clone аккаунт). APK push'нет refresh JWT в xapi → `b5cbf28b` перейдёт в `state=active` → polling возобновится.
2. **Smoke test live polling**: `iPhone 12 Pro` уже включен V2 (`notification_settings.llm_pipeline_v2=true`). Дождаться один `poll_profile` тик → `evaluate_listing` для каждого нового лота → проверить в БД bucket distribution.
3. **Соак 3-4 дня** в `per_listing` стратегии. Метрики:
   - `SELECT bucket, count(*) FROM profile_listing_evaluations GROUP BY 1`
   - `SELECT type, count(*), sum(cost_usd) FROM llm_analyses WHERE created_at > now()-interval '24h' GROUP BY 1`
   - `SELECT count(*) FROM user_listing_blacklist WHERE reason LIKE 'auto_red:%' AND created_at > now()-interval '24h'` (false-positive watch)
   - Latency end-to-end `polling.success → notification.dispatch_pending` на нескольких лотах
4. **Если качество плохое** в `per_listing` → hot-switch на `per_criterion`: `UPDATE search_profiles SET evaluate_strategy='per_criterion' WHERE id=...`. Cache reuse — лоты не перерасчитываются.
5. **Phase C** после signoff соака: `docker compose exec avito-monitor alembic upgrade head` (применит 0009 — drop legacy ADR-010 columns + tasks). После — tests, smoke, готово.

### Перед стартом следующей сессии

- Прочитать `DOCS/V1_EXECUTION_PLAN.md` (блок 4 уже выполнен — V2 заменил ADR-010).
- Прочитать `DOCS/DECISIONS.md` ADR-008 (двойная вилка) и ADR-010 (про **двухступенчатый — заменён**, остаются термины «clean-метрики» + alert/search вилки).
- Глянуть `git log main --oneline -10` — последние коммиты Phase A.

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
