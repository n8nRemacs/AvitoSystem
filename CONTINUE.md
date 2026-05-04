# CONTINUE — Быстрый рестарт сессии

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md`. Pool — в `DOCS/superpowers/specs/2026-04-28-account-pool-design.md`. Server migration — `DOCS/superpowers/plans/2026-05-02-server-migration.md` + `ops/migration-2026-05-02/README.md`.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, работа продолжится.

---

## 1. Где мы сейчас

**Production stack — 2026-05-04:**

| Что | Где |
|---|---|
| **VPS** (xapi + monitor + Caddy + Redis) | `81.200.119.132` (Beget RU, 1c/2GB/15GB Ubuntu 24.04, Docker 29) |
| **Public URL** | `https://avitosystem.duckdns.org` (Let's Encrypt, auto-renew) |
| **БД** | Supabase Cloud `drwgozasaypgphkxyizt` (Frankfurt, eu-central-1) |
| **Phone** | OnePlus 8T (serial `110139ce`), USB подключен к Windows ПК юзера; APK в user_0 + user_10 указывает на VPS |
| **Homelab** | xapi+monitor контейнеры **остановлены** (rollback path: `ssh homelab; cd /mnt/projects/repos/AvitoSystem/avito-{xapi,monitor}; docker compose start`) |

### Что закрыто (server migration, ветка `feat/server-migration`, 14 коммитов)

| Phase | Что |
|---|---|
| 1+2 | Schema (supabase/migrations 001-008 + alembic head) + data (1395 rows) на Cloud. Audit_log конфликт решён переименованием xapi-таблицы → `audit_log_xapi`. |
| 3 | xapi refactor — удалены `device_switcher`, `/refresh-cycle`, `/devices/me/commands`. 177 тестов pass. |
| 4 | monitor refactor — `account_tick.py` теперь one-stale TG alerts, не proactive refresh. 5/5 новых тестов + 239 broader pass. |
| 5+6 | Deploy artifacts (`ops/server/`) + первый deploy на VPS. 4 сервиса Up. xapi отдаёт Cloud данные через REST. |
| 7 | APK repoint — prefs обоих юзеров отредактированы через ADB+Magisk root. user_0 уже шлёт GET 200 OK на VPS. |
| 8 | Cutover — homelab xapi+monitor stopped. |

### Pool state на момент cutover

```
avito_accounts:
  Clone (42c179db…)            | user_10 phone_serial=110139ce | state=dead
  auto-157920214 (b5cbf28b…)   | user_0  no phone_serial       | state=cooldown
```

Оба сейчас неактивны — возобновятся когда Avito-app в каждом Android-user будет открыт юзером и refreshнёт JWT, APK поймает push → POST /sessions → state=active.

---

## 2. Manual refresh model — как теперь работает

1. **Юзер вручную:** утром открыть Avito-app в user_0, вечером в user_10 (или по необходимости когда expires_at близко к now).
2. **Avito-app сам решает refresh** (по своей внутренней логике near-expiry).
3. **APK ловит push через NotificationListener** → читает SharedPrefs (root через Magisk) → `POST https://avitosystem.duckdns.org/api/v1/sessions` с новым session_token.
4. **xapi:** `resolve_or_create_account(payload.u, payload.device_id)` → деактивирует старую active session → INSERT новую → если account.state=`waiting_refresh` (legacy) → `active`.
5. **monitor health-checker (account_tick):** раз в 30 сек проверяет accounts. Если `expires_at < NOW` — one-shot TG alert (idempotent на переход fresh→stale). Если все аккаунты stale → critical alert «Polling DOWN».

---

## 3. V1.5 backlog (по приоритету)

| # | Задача | Severity | Часы | Что |
|---|---|---|---|---|
| 1 | **Ротация секретов** (засветились в чате 2026-05-04) | high | 0.3 | Root-пароль VPS, Supabase service_role JWT (Reset JWT), Supabase Secret API key (`sb_secret_*`). После — обновить `/opt/avito-system/.env`. |
| 2 | **Avito-MCP — определиться** | medium | 0.5 | На homelab был standalone `avito-mcp-homelab` (host networking, ходил на localhost:8080). После cutover — сломан. Sidecar `avito-mcp` есть в monitor compose (port 9000), но Caddyfile его наружу не маршрутизирует. Решить: используется ли вообще? Если да — добавить `/mcp/*` route в Caddy + обновить APK `mcp_url`. |
| 3 | **Зарегистрировать второй Avito-аккаунт** для реального pool=2 | high | 0.5 + регистрация | Schema готова (`UNIQUE(avito_user_id, last_device_id)`). Нужен второй номер телефона. |
| 4 | **TG bot inbound через прокси** | low | 0.3 | `aiogram` падает на `aiohttp-socks` если он не установлен. Outbound alerts через прямой `httpx` работают. |
| 5 | **Captcha/IP-ban detection** | medium | 2-3 | `last_403_body` capture есть, парсера нет. |
| 6 | **Reboot recovery alert** | low | 0.5 | После reboot OnePlus FBE требует разблокировки каждого user отдельно. Detect через health_checker. |

---

## 4. Что делать дальше

**Soak-режим (текущий):**

1. Открой Avito-app в user_0 и user_10 на phone — APK подтянет токены и POSTит на VPS. Проверка: `ssh root@81.200.119.132 'docker logs avito-system-avito-xapi-1 --since=5m 2>&1 | grep "POST.*sessions"'`.
2. Раз в день: `ssh root@81.200.119.132 'docker logs avito-system-avito-monitor-1 --since=24h | grep -E "fetch_with_pool|cooldown|403|alert"'`.
3. UI: `https://avitosystem.duckdns.org/` (через VPN или CORS-allowed origin).

**Параллельно если хочется:**

* Backlog #1 — ротация секретов (15 мин)
* Backlog #2 — решить судьбу avito-MCP
* Backlog #3 — второй Avito-аккаунт
* **Avito-сервис core**: LLM-анализ листингов, ценовая разведка, market_stats — следующая большая задача после server migration. См. `DOCS/V1_EXECUTION_PLAN.md` блоки 5-8.

---

## 5. Команды на проверку production stack

```bash
# Health
curl -s https://avitosystem.duckdns.org/health
curl -sk -H "X-Api-Key: test_dev_key_123" https://avitosystem.duckdns.org/api/v1/accounts | python3 -m json.tool

# Pool через xapi
ssh root@81.200.119.132 'curl -sH "X-Api-Key: test_dev_key_123" http://avito-xapi:8080/api/v1/accounts | python3 -m json.tool' \
  || ssh root@81.200.119.132 'docker exec avito-system-avito-monitor-1 curl -sH "X-Api-Key: test_dev_key_123" http://avito-xapi:8080/api/v1/accounts'

# Force refresh-cycle — НЕТ. Manual refresh: открыть Avito-app на phone.

# adb через USB к Windows ПК юзера
adb devices
adb shell 'su -c "cat /data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml"' \
  | grep -E "server_url|api_key|expires_at"

# Cloud Supabase
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql 'postgresql://postgres.drwgozasaypgphkxyizt@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require' -c \"SELECT id,nickname,state,expires_at FROM avito_accounts a LEFT JOIN avito_sessions s ON s.account_id=a.id AND s.is_active;\""

# Логи
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml logs --tail=100 avito-monitor'
ssh root@81.200.119.132 'docker compose -f /opt/avito-system/docker-compose.yml logs --tail=100 avito-xapi'

# Rollback на homelab (если что-то совсем не работает)
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-xapi && docker compose start'
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose start'
# и переключить APK обратно через adb sed на homelab URL
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/superpowers/plans/2026-05-02-server-migration.md` | Server migration plan: 8 phases от schema migration до cutover |
| `ops/migration-2026-05-02/README.md` | Audit trail: какие таблицы мигрированы, сколько rows, нюансы |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Deploy artifacts |
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Pool design (актуально, кроме refresh-cycle секций — заменено manual model) |
| `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md` | Refresh Hardening (исторический, до Server Migration) |
| `DOCS/REFERENCE/01-avito-api.md` | Все endpoints (mobile + official), headers, structured params |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow (manual model), pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk, ADB, NL, USB passthrough |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi workflow |
| `DOCS/DECISIONS.md` | ADRs (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM, ADR-011 autosearch sync) |

---

## 7. Где секреты

* **Глобальные:** `c:/Projects/Sync/CLAUDE.md` — старые homelab credentials. Cloud-проект (`drwgozasaypgphkxyizt`) — там НЕ задокументирован, на VPS в `/opt/avito-system/.env`.
* **VPS:** `/opt/avito-system/.env` (chmod 600 root). Содержит `DATABASE_URL` (asyncpg pooler), `SUPABASE_URL`, `SUPABASE_KEY` (sb_secret_*), `AVITO_XAPI_API_KEY=test_dev_key_123` (plaintext), TG token, OPENROUTER_API_KEY.
* **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/` (per-user в `/data/user/{0|10}/...`). Поля: `server_url`, `api_key`, `mcp_url`, `mcp_auth_token`.
* **Avito session storage:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml` — ключи: `session`, `refresh_token`, `device_id`, `remote_device_id`, `profile_id`.
* **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 8. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/. Server migration shipped 2026-05-04
(ветка feat/server-migration, 14 коммитов). Production: VPS 81.200.119.132,
Cloud Supabase Frankfurt, manual refresh model. Прочитай CONTINUE.md
(текущий статус) + DOCS/REFERENCE/. Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Хочу [Backlog #N / soak-debugging / Avito-сервис LLM analysis / ...]
```

---

**TL;DR для следующей сессии:**

1. Server Migration **выполнен** 2026-05-04. Production на VPS + Cloud Supabase, homelab остановлен, APK repointed.
2. Manual refresh model: юзер открывает Avito-app → APK POSTит токен → polling резюмируется.
3. Pool сейчас неактивен (Clone=dead, auto=cooldown) — нужно открыть Avito-app в обоих юзерах для warm-up.
4. **Backlog #1 (ротация засветившихся секретов) — high priority.**
5. Ветка `feat/server-migration` НЕ замержена в main — ждёт user'ское решение.
6. Следующая большая работа — **Avito-сервис core**: LLM analysis листингов, price intelligence, market stats.
