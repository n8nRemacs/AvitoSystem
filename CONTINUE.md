# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md` (ADR-011 — autosearch sync). Pool — в `DOCS/superpowers/specs/2026-04-28-account-pool-design.md`.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito.

**Дата последнего обновления:** 2026-04-29. Реализована **Account Pool** — 26 коммитов на ветке `feat/account-pool` (worktree `c:/Projects/Sync/AvitoSystem-account-pool/`). Pool готов архитектурно и закодирован полностью; осталась физика (USB passthrough) и E2E-проверка.

**Состояние ветки:** работа в worktree `feat/account-pool`, основной `main` остаётся production-ready с предыдущей autosearch-sync работой. Merge → main делается после T13 + T23.

### Карта ключевых артефактов

| Файл | Что |
|---|---|
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Полный spec: state machine, DB schema, error matrix, testing |
| `DOCS/superpowers/plans/2026-04-28-account-pool.md` | Implementation plan, 24 task'а в 12 фазах |
| `DOCS/REFERENCE/` | 5 файлов / 1583 строки справочника по Avito API + auth + Android setup + reverse-engineering |
| `supabase/migrations/007_avito_accounts_pool.sql` | Schema applied на homelab Supabase |
| `avito-monitor/alembic/versions/20260429_*owner_account.py` | Migration 0005 applied |

### Что в pool сделано (26 коммитов)

| Слой | Что |
|---|---|
| **Schema (Supabase)** | `avito_accounts` table: state machine (active/cooldown/needs_refresh/waiting_refresh/dead), cooldown ratchet, multi-phone (`phone_serial`, `android_user_id`), `last_403_body` capture. `avito_sessions.account_id` FK. |
| **Schema (avito-monitor)** | `search_profiles.owner_account_id` UUID (cross-DB, no FK). Все 7 active профилей привязаны к Clone account. |
| **xapi accounts router** | 6 endpoints: `GET /accounts`, `POST /poll-claim` (atomic CAS LRU), `POST /{id}/report` (state transitions + ratchet), `GET /{id}/session-for-sync`, `POST /{id}/refresh-cycle` (ADB switch + cmd), `PATCH /{id}/state`. |
| **xapi sessions** | Account-scoped deactivation (`POST /sessions` теперь по `account_id`, не по `tenant_id`). Auto-resolve+create account по `avito_user_id`. `waiting_refresh→active` transition. |
| **xapi session_reader** | Pool-aware `load_session_for_account` (async). Legacy `load_active_session` остался sync для backward-compat. |
| **xapi subscriptions** | `?account_id=` query param поддерживается. Если есть → `load_session_for_account`. Если нет → legacy fallback. |
| **xapi DeviceSwitcher** | Multi-phone wrapper над ADB. Per-phone `asyncio.Lock` (параллельный switch на разных телефонах). `device_switcher` singleton. |
| **xapi storage helper** | `QueryBuilder.is_(col, None)` + `order(..., nullsfirst=True)` для CAS-предиката с partial index. |
| **monitor AccountPool** | Тонкий HTTP-клиент: `claim_for_poll`/`report`/`claim_for_sync`/`list_*_accounts`/`trigger_refresh_cycle`/`patch_state`. |
| **monitor pool factory** | `services/account_pool_factory.py` singleton — используется и polling'ом, и UI. |
| **monitor polling** | `fetch_with_pool` retry (403/401 → другой acc, 5xx → тот же + sleep). `poll_profile` **переподключён** на pool через factory. |
| **monitor autosearch_sync** | Per-account loop: каждый active acc pull'ит свои `/5/subscriptions`, skip cooldown, `owner_account_id` set on upsert. |
| **monitor health_checker tick** | `account_tick_iteration`: cooldown_expired → `trigger_refresh_cycle`, waiting_refresh > 5 мин → `dead` + TG-alert, active+expiry<3мин → proactive refresh. Idempotent TG-alert на consecutive >= 5. |
| **monitor health_checker scheduler** | `account_loop` запускается параллельной asyncio-task'ой каждые 30 с в `__main__.py`. TG через `send_alert()`. |
| **monitor UI** | `/settings/accounts` read-only таблица: nickname, Android-user, phone, state badge (active/cooldown/needs_refresh/waiting_refresh/dead), cooldown_until, last_polled, consecutive, last_403 expandable. |

### Состояние БД на homelab Supabase

```
avito_accounts:
  Clone   | uuid=42c179db-18b1-40b2-9af2-274c52824ab1
          | avito_user_id=157920214, android_user_id=10, phone_serial=110139ce
          | state=active, last_session_at='2026-04-29 08:00:15'

avito_sessions: 6 rows total (1 active linked to Clone, 5 inactive legacy unbound)
search_profiles: 7 active rows, все owner_account_id=Clone
```

Main account (banned user 0 token) **создастся автоматически** когда APK Main сделает POST /sessions (после restore вручную).

### Что осталось до production deploy

| Task | Что | Кто |
|---|---|---|
| **T13** | USB passthrough OnePlus 8T → homelab LXC: подключить кабель, добавить `lxc.cgroup2.devices.allow: c 189:* rwm` + bind-mount `/dev/bus/usb`, `apt-get install android-tools-adb` в контейнере, `adb start-server`, проверить `adb devices` показывает `110139ce  device`. | ты + я (физика на твоей стороне, я ssh-команды) |
| **T23** | E2E force-tests на staging: force 403 → switch на 2-й acc, force cooldown_expired → refresh-cycle через ADB → новая сессия → state=active, force waiting_refresh > 5 мин → dead + TG-alert, ADB unplug → ADB-alert, reboot worker → recovery. | ты + я |
| **Merge** | `git merge feat/account-pool → main`, redeploy xapi + monitor | я |

---

## 2. Известные ограничения V1.5

| # | Ограничение | Severity | План |
|---|---|---|---|
| 1 | `avito_device_commands` schema (migration 006) per-tenant, не per-device. Когда pool из >1 APK на одном tenant'е — теоретически race на long-poll, может перехватить «не та» APK. **Mitigation:** `device_switcher.switch_to(target_user)` ДО создания cmd → нужный APK в foreground first long-poll'ит. `target_device_id`+`target_account_id` уже embedded в `payload` (V1.5 APK update сможет фильтровать). | Theoretical, V1 single-phone не страдает | V1.5: migration 008 ADD COLUMN `device_id` + APK update |
| 2 | `account_tick.account_loop` читает `expires_at` для proactive refresh из `avito_accounts`, но колонки там нет (она в `avito_sessions`). Proactive refresh за 3 мин до expiry **не срабатывает**. Reactive (401 → expires_at=NOW в session) и post-cooldown refresh работают. | Medium | V1.5: расширить `GET /accounts` чтобы JOIN'ить `avito_sessions.expires_at` или передать в `list_all_accounts` response |
| 3 | AvitoSessionManager APK не фильтрует команды по `target_device_id` из payload. В pool из 2 APK команда может уйти не той. **Mitigation:** device_switcher.switch_to + tcp/long-poll natural ordering. | Low | V1.5: APK update с filter |
| 4 | Pool=1 пока, потому что Main token banned (см. § 3). Round-robin фактически not yet exercised. | Operational | T23: Main re-login → APK POST /sessions → pool=2 |

---

## 3. Operational заметки

* **Avito anti-fraud per-account** — эмпирически подтверждено (юзер с того же IP но другого устройства/аккаунта работал). Защита: pool аккаунтов + cooldown ratchet 20→40→80→160→24ч.
* **`/5/subscriptions` отдаёт title/description, без structured params**. Точные search params — через `/2/subscriptions/{filter_id}` → `result.deepLink`.
* **System Clone в OnePlus 8T:** `pm list users` → 0 + 10. Apps ставить через `pm install-existing --user 10`. NotificationListener в неактивном user может тормозиться Android Doze — `device_switcher.switch_to` + 8 сек warm-up решает (см. spec §3.D11).
* **Magisk root grant per-UID, per-user**: UID = `userId * 100000 + appId`. `magisk --sqlite "INSERT OR REPLACE INTO policies (uid, ...) VALUES (1010296, ...)"`.
* **AvitoSessionManager НЕ читает SharedPreferences самостоятельно при старте** — триггерится push'ом. Workaround: `python scripts/register_clone_session.py` (читает /data/user/N/... через root + POST /api/v1/sessions).
* **TG проксирование через Xray** — `TELEGRAM_PROXY_URL=http://host.docker.internal:10808`, `aiohttp-socks==0.11.0`.
* **Refresh flow** (с pool): health_checker замечает cooldown_expired → `pool.trigger_refresh_cycle(acc_id)` → xapi `POST /accounts/{id}/refresh-cycle` → `device_switcher.switch_to` + 8 сек warm-up → INSERT command в `avito_device_commands` → APK long-poll'ит → APK триггерит Avito-app → новый JWT в SharedPrefs → APK POST /api/v1/sessions → xapi resolves account → `state=active`.

---

## 4. Что делать дальше

**Сейчас (V1 ready-to-deploy):**

1. **T13** — физический USB-кабель + LXC config (≈30 мин с тобой ssh-командами)
2. **T23** — E2E checklist из spec'а §6.4 / plan'а Phase 12 Task 23
3. **Merge** `feat/account-pool` → `main`, deploy

**После deploy (V1.5+):**

| Опция | Часов |
|---|---|
| Решить Gap 2 — proactive refresh: extend `GET /accounts` чтобы возвращать `expires_at` через JOIN | 1 |
| Решить Gap 1+3 — migration 008 ADD `device_id` в `avito_device_commands` + APK update для filter'а | 3-4 |
| Captcha/IP-ban detection (#11) | 2-3 |
| Третий аккаунт через ещё один System Clone | 30 мин |
| 2-й физический OnePlus | $200-300 + 1 ч setup (схема готова, multi-phone supported by design) |
| Auto-resume agent: `/schedule` каждые 30 мин проверяет clone-токен → пауза + alert | 30 мин |

---

## 5. Команды для проверки pool

```bash
# Какие аккаунты в pool сейчас
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"SELECT nickname, state, android_user_id, phone_serial, consecutive_cooldowns, last_polled_at FROM avito_accounts;\""

# Pool через xapi (всё доступно)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts | python3 -m json.tool"

# Round-robin claim (что сейчас отдаст pool)
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:8080/api/v1/accounts/poll-claim | python3 -m json.tool"

# Force test 403-cooldown через report endpoint
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{\"status_code\":403,\"body_excerpt\":\"<firewall>test</firewall>\"}' \
  http://127.0.0.1:8080/api/v1/accounts/42c179db-18b1-40b2-9af2-274c52824ab1/report"

# UI pool state
# Открой http://homelab:8000/settings/accounts в браузере (через VPN)

# Force refresh-cycle вручную (триггерит ADB switch + cmd)
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' \
  http://127.0.0.1:8080/api/v1/accounts/42c179db-18b1-40b2-9af2-274c52824ab1/refresh-cycle"

# Логи account_loop (health_checker tick)
ssh homelab 'docker logs avito-monitor-health-checker-1 --since=2m 2>&1 | grep account_'

# Логи polling (pool-aware fetch)
ssh homelab 'docker logs avito-monitor-worker-1 --since=2m 2>&1 | grep -E "poll-claim|fetch_with_pool|pool drained"'
```

### Промпт-стартер для нового блока

```
Проект: c:/Projects/Sync/AvitoSystem/ (worktree feat/account-pool в c:/Projects/Sync/AvitoSystem-account-pool/)
Прочитай: CONTINUE.md (текущий статус) + DOCS/REFERENCE/ + DOCS/superpowers/specs/2026-04-28-account-pool-design.md.
Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Хочу [T13 USB passthrough / T23 E2E / merge / V1.5 fix Gap 2 / …].
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Pool design: state machine, DB schema, error matrix, concurrency, testing |
| `DOCS/superpowers/plans/2026-04-28-account-pool.md` | Pool implementation plan: 24 task'а с TDD-шагами |
| `DOCS/REFERENCE/01-avito-api.md` | Все endpoints (mobile + official), headers, structured params |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow, two refresh_token (Avito-app vs наш), pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk, ADB, NL, USB passthrough |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi workflow, что не работает (Frida) |
| `DOCS/DECISIONS.md` ADR-011 | Поворот на autosearch-sync через мобильный API |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Реверс subscription endpoints v222.5 |
| `DOCS/V1_BLOCKS_TZ.md` | Per-block ТЗ |

---

## 7. Где секреты

* **Глобальные**: `c:/Projects/Sync/CLAUDE.md` — Supabase URLs/keys, JWT, homelab IP, TG bot token, Xray-proxy.
* **avito-monitor локальный конфиг:** `c:/Projects/Sync/AvitoSystem/avito-monitor/.env` — gitignored.
* **На homelab `.env`** в `/mnt/projects/repos/AvitoSystem/avito-monitor/.env` (TG_BOT_TOKEN, OPENROUTER_API_KEY, TELEGRAM_PROXY_URL).
* **xapi homelab:** `BASE_URL=https://app.avito.ru/api`, `AVITO_XAPI_API_KEY=test_dev_key_123`, rate_limit_rps=1.0, burst=3.
* **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (root, и **per-user**: `/data/user/10/...` для clone).
* **Avito session storage:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml` — ключи: `session`, `refresh_token`, `device_id`, `remote_device_id`, `profile_id`.
* **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

**TL;DR для следующей сессии:**

1. Pool **полностью закодирован** (26 commits на `feat/account-pool`). Все тесты зелёные (174 xapi + 243 monitor, modulo 2 pre-existing failures).
2. **Что осталось до deploy**: T13 (USB physical setup) + T23 (E2E) → merge в main.
3. Pool=1 фактически (Clone), потому что Main token banned. Restore Main = APK POST /sessions → xapi auto-create avito_accounts row → pool=2.
4. **Известные V1.5 issues**: proactive refresh не срабатывает (Gap 4 — нужно extend GET /accounts), device_commands per-tenant (теоретическая race, mitigated через device_switcher).
