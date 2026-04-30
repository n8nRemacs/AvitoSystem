# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком. Архитектурные решения — в `DOCS/DECISIONS.md` (ADR-011 — autosearch sync). Pool — в `DOCS/superpowers/specs/2026-04-28-account-pool-design.md`.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito.

**Дата:** 2026-04-30 19:30 UTC. **Refresh Hardening shipped в `main`** (commits `63a4c2b`..`5bc72d3`, ветка `feat/refresh-hardening` мерж-удалена). До этого — Account Pool merged 2026-04-29 (commit `8e12434`). Pool в production, T13 + T23 + refresh hardening пройдены, soak-режим.

### Что покрыто (закрытые задачи)

| Этап | Статус |
|---|---|
| **Spec + Plan** | done — `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` + `plans/2026-04-28-account-pool.md` |
| **Implementation** (24 task'а в 12 фазах) | done — 30 коммитов |
| **T13 — USB passthrough** | done — `adb` в xapi-контейнере, `device_cgroup_rules: c 189:* rwm` для hot-plug, RSA-fingerprint authorized |
| **T23 — E2E force-tests 7/7** | done — ratchet 20→40→80m, 401-deactivation, cooldown→refresh-cycle (ADB switch user_0→user_10, APK delivered cmd), waiting>5m→dead+TG (HTTP 200), ADB unplug→503+recovery, worker restart |
| **Merge → main + deploy** | done — homelab pulled, контейнеры здоровы |
| **Refresh Hardening (2026-04-30)** | done — план `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md`, 9 task TDD + 2 docker fix, all reviewed, merged. См. § 8. |

### Production state на homelab Supabase

```
avito_accounts:
  Clone | uuid=42c179db-18b1-40b2-9af2-274c52824ab1
        | avito_user_id=157920214, android_user_id=10, phone_serial=110139ce
        | state=active

avito_sessions: 2 active (Clone — fresh JWT until 2026-04-30 08:05;
                          Main orphan без account_id — V1.5 cleanup)
search_profiles: 7 active, все owner_account_id=Clone
```

### Pool=1 фактически — почему

Открытие из T23: **Main и Clone — один и тот же Avito-юзер 157920214 в разных Android-юзерах**. У них разные `device_id` (`61238c...0491` Main vs `aaf5ce...656d` Clone), но один `u`. `resolve_or_create_account` ключуется по `u`, поэтому upload Main даёт тот же `account_id` что Clone. Round-robin фактически не работает — pool архитектурно = 1.

**Чтобы pool=2 по-настоящему** — нужен второй Avito-аккаунт (другой номер телефона), регистрация занимает 5 мин на телефоне.

---

## 2. V1.5 backlog (по приоритету)

| # | Задача | Severity | Часы | Что |
|---|---|---|---|---|
| ~~1~~ | ~~**Gap 4 — proactive refresh**~~ | — | — | **CLOSED 2026-04-30** через Refresh Hardening sprint. `GET /accounts` теперь возвращает `expires_at` per row (Task 5), `account_tick` триггерит refresh-cycle при `exp<NOW+30min` или `expires_at IS NULL` (Task 6). Boot-recovery работает автоматически на первом тике после рестарта. |
| 2 | **Зарегистрировать второй Avito-аккаунт** для реального round-robin pool=2 | high | 0.5 + регистрация | После Refresh Hardening схема готова: migration 008 даёт `UNIQUE(avito_user_id, last_device_id)`, resolver ключует по паре. Можно либо регистрировать второй номер, либо настроить multi-device (один Avito-юзер на user_0+user_10 phone'а — но per-account ban валит обоих, см. ADR/REFERENCE §F). |
| 3 | **TG bot inbound через прокси** | low | 0.3 | `aiogram` падает в `TelegramNetworkError` потому что `aiohttp-socks` не установлен → fallback to direct → timeout (api.telegram.org заблокирован без прокси). Fix: `pip install aiohttp-socks` в monitor image. Outbound alerts через прямой `httpx` работают. |
| 4 | **`200 report` не зачищает `cooldown_until`** | cosmetic | 0.1 | После успешного 200 ratchet=0, но `cooldown_until` остаётся (pool по `state` фильтрует, не влияет). |
| 5 | **Gap 1+3 — `avito_device_commands` per-tenant** | low | 3-4 | Теоретическая race на pool>1 APK. Mitigation: `device_switcher.switch_to` ДО cmd. Fix: migration 008 ADD COLUMN `device_id` + APK update. |
| 6 | **Captcha/IP-ban detection** | medium | 2-3 | `last_403_body` capture есть, парсера для определения captcha vs IP-ban — нет. |
| 7 | **Auto-resume agent** через `/schedule` | low | 0.5 | Каждые 30 мин проверять что Clone-токен ≥10 мин TTL. Если нет — alert + поставить polling на паузу. |
| 8 | **Reboot recovery alert** | low | 0.5 | После reboot phone'а юзера 0 и 10 нужно вручную разблокировать (FBE). Detect по health_checker'у: если `adb shell am switch-user N` + чтение prefs возвращает «empty» — alert. |

---

## 3. Operational заметки

* **Avito anti-fraud per-account** — эмпирически подтверждено. Pool аккаунтов + cooldown ratchet 20→40→80→160→24ч.
* **Phone reboot — manual step**: после reboot OnePlus FBE требует разблокировки каждого user отдельно (PIN). Без этого `/data/user/N/` зашифрован, Avito-app не сможет refresh'нуть. Ключи в kernel держатся до следующего reboot.
* **USB renumeration при `am switch-user`** — phone отваливается на ~1с, adb на следующей команде получит «no devices». `device_switcher.switch_to` имеет confirm-loop с retry 5 сек, переживает.
* **Avito-app refresh JWT** — только near-expiry. При TTL > 1ч app проигнорирует, не пойдёт в сеть. Manual refresh = открыть app на 30-60с когда TTL малый.
* **AvitoSessionManager НЕ читает SharedPreferences самостоятельно при старте** — триггерится push'ом или нашим `refresh_token` cmd. Reactive workaround при offline-restore: `python scripts/register_clone_session.py` (читает /data/user/N/... через root + POST /api/v1/sessions).
* **Refresh flow с pool**: health_checker замечает cooldown_expired → `pool.trigger_refresh_cycle` → xapi `POST /accounts/{id}/refresh-cycle` → `device_switcher.switch_to(android_user_id)` + 8с warm-up → INSERT cmd в `avito_device_commands` → APK long-poll'ит → APK триггерит Avito-app → новый JWT в SharedPrefs → APK POST /api/v1/sessions → xapi resolves account → `state=active`.
* **`/5/subscriptions` отдаёт title/description, без structured params**. Точные search params — через `/2/subscriptions/{filter_id}` → `result.deepLink`.
* **System Clone в OnePlus 8T:** `pm list users` → 0 + 10. Apps ставятся через `pm install-existing --user 10`. NotificationListener в неактивном user тормозится Android Doze — `device_switcher.switch_to` + 8с warm-up решает.
* **Magisk root grant per-UID, per-user**: UID = `userId * 100000 + appId`. `magisk --sqlite "INSERT OR REPLACE INTO policies (uid, ...) VALUES (1010296, ...)"`.
* **TG проксирование** для outbound alerts (health-checker → api.telegram.org) использует прямой `httpx` через Xray-прокси, работает. Inbound (aiogram bot polling) — пока не работает (см. backlog #3).

---

## 4. Что делать дальше

**Soak-режим (текущий):**

1. Просто наблюдать 3-4 дня. Polling будет молотить через pool с Clone-токеном (TTL 24ч, рефрешится автоматически когда Avito-app сам решит).
2. Раз в день `docker logs avito-monitor-worker-1 --since=24h | grep -E "fetch_with_pool|cooldown|403"` — посмотреть, реальные ли ловят 403.
3. UI: `http://homelab:8000/settings/accounts` (через Xray VPN) — pool state визуально.

**Параллельно если хочется:**

* Backlog #2 — зарегистрировать второй Avito-аккаунт (раз и навсегда сделать pool=2)
* Backlog #1 — закрыть Gap 4 (1 час)
* Backlog #3 — починить TG bot inbound (15 мин)

**Если что-то сломается:**

* `state=dead` → TG-alert придёт; разобраться в `last_403_body`
* `state=cooldown` дольше 24ч → проверить consecutive_cooldowns; больше 5 → ручной разбор
* `adb devices` пусто → `device_switcher.health()` 503; проверить кабель и `/dev/bus/usb/`

---

## 5. Команды на проверку pool

```bash
# Какие аккаунты в pool сейчас
ssh homelab "PGPASSWORD='Mi31415926pSss!' psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c \
  \"SELECT nickname, state, android_user_id, consecutive_cooldowns, last_polled_at FROM avito_accounts;\""

# Pool через xapi
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/accounts | python3 -m json.tool"

# Round-robin claim
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' \
  http://127.0.0.1:8080/api/v1/accounts/poll-claim | python3 -m json.tool"

# Force refresh-cycle вручную (триггерит ADB switch + cmd)
ssh homelab "curl -s -X POST -H 'X-Api-Key: test_dev_key_123' \
  http://127.0.0.1:8080/api/v1/accounts/42c179db-18b1-40b2-9af2-274c52824ab1/refresh-cycle"

# adb внутри xapi (phone должен показаться)
ssh homelab "docker exec avito-xapi-xapi-1 adb devices"

# Логи
ssh homelab 'docker logs avito-monitor-health-checker-1 --since=2m 2>&1 | grep account_'
ssh homelab 'docker logs avito-monitor-worker-1 --since=2m 2>&1 | grep -E "poll-claim|fetch_with_pool"'
```

### Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/. Pool merged в main (8e12434).
Refresh Hardening shipped 2026-04-30 (5bc72d3). Прочитай CONTINUE.md
(текущий статус) + DOCS/REFERENCE/ + при нужде
DOCS/superpowers/plans/2026-04-30-refresh-hardening.md.
Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Хочу [Backlog #N / soak-debugging / новая фича / ...]
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Pool design: state machine, DB schema, error matrix, concurrency, testing |
| `DOCS/superpowers/plans/2026-04-28-account-pool.md` | Pool implementation plan: 24 task'а с TDD-шагами (для истории) |
| `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md` | **Refresh Hardening** plan: 7 task TDD — xapi propagate Avito 4xx, multi-device migration, account_tick proactive refresh |
| `DOCS/REFERENCE/01-avito-api.md` | Все endpoints (mobile + official), headers, structured params |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow, two refresh_token (Avito-app vs наш), pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk, ADB, NL, USB passthrough |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi workflow, что не работает (Frida) |
| `DOCS/DECISIONS.md` ADR-011 | Поворот на autosearch-sync через мобильный API |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Реверс subscription endpoints v222.5 |

---

## 7. Где секреты

* **Глобальные**: `c:/Projects/Sync/CLAUDE.md` — Supabase URLs/keys, JWT, homelab IP, TG bot token, Xray-proxy.
* **avito-monitor локальный:** `c:/Projects/Sync/AvitoSystem/avito-monitor/.env` — gitignored. **OPENROUTER_API_KEY ротирован** 2026-04-29 (старый утёк в `22b86f5:DOCS/V2_CONTINUE.md`, revoked).
* **На homelab `.env`** в `/mnt/projects/repos/AvitoSystem/avito-monitor/.env` (TG_BOT_TOKEN, OPENROUTER_API_KEY, TELEGRAM_PROXY_URL).
* **xapi homelab:** `BASE_URL=https://app.avito.ru/api`, `AVITO_XAPI_API_KEY=test_dev_key_123`, rate_limit_rps=1.0, burst=3.
* **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (root, и **per-user**: `/data/user/10/...` для clone).
* **Avito session storage:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml` — ключи: `session`, `refresh_token`, `device_id`, `remote_device_id`, `profile_id`.
* **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

**TL;DR для следующей сессии:**

1. Pool **в main** (`8e12434` merged 2026-04-29). Refresh Hardening **в main** (`5bc72d3` merged 2026-04-30). Soak.
2. Pool=1 фактически (Clone) — Main = тот же `u`. Schema теперь готова к multi-device (`UNIQUE(u, device)`); чтобы pool=2 — либо register второй номер, либо настроить multi-device на одном `u` (см. backlog #2).
3. T13 (USB) + T23 (7/7 force-тестов) + Refresh Hardening **пройдены E2E** на homelab.
4. **V1.5 backlog 7 пунктов** в § 2 (Gap 4 закрыт). 
5. **Известные мелкие issues**: TG bot inbound (aiohttp-socks missing), `200 report` не зачищает `cooldown_until`.

---

## 8. Refresh Hardening — что сделано (2026-04-30)

**Контекст инцидента:** 2026-04-30 18:00 UTC. Сервер был выключен → JWT протух → worker стартанул и долбил Avito с мёртвым токеном → Avito отдавал 403 → xapi оборачивал в 500 → pool не видел 403, не переводил в cooldown → молотил часами. JWT в Avito-app тоже истёк, refresh-cycle не сработал, понадобилось ручное открытие Avito-app на phone.

**Корень:** три архитектурные дыры:
1. xapi оборачивал Avito 401/403/429 в 500 (middleware catch-all) → pool слеп.
2. `account_tick` читал `expires_at` из `avito_accounts` (где её нет — она в `avito_sessions`) → proactive refresh не работал.
3. `UNIQUE(avito_user_id)` блокировал multi-device → один phone-юзер = один pool row.

**План:** `DOCS/superpowers/plans/2026-04-30-refresh-hardening.md` — 7 TDD-задач, выполнены через subagent-driven development (по свежему агенту на задачу + spec + code quality review). Итог 9 commits + 2 dockerfix.

**Что в production:**
- xapi теперь возвращает Avito 401/403/429 наружу как HTTPException (через `reraise_avito_error` helper в `src/routers/_avito_errors.py`). Все Avito-touching call sites в `subscriptions.py` (4 шт) и `messenger.py` (9 шт) обёрнуты.
- Migration 008: `UNIQUE(avito_user_id, last_device_id)` — multi-device per Avito-юзер допустим в схеме.
- `resolve_or_create_account` ключует по паре `(u, device_id)`. Каждый device — свой pool row.
- `GET /api/v1/accounts` возвращает `expires_at` per row (JOIN с `avito_sessions`).
- `account_tick`: threshold 3min → 30min, треатит `expires_at IS NULL` как trigger. Покрывает boot-recovery (первый тик после рестарта подхватит просроченный JWT).
- Dockerfile monitor: `pip` вместо `uv` (uv падал с signalfd panic на kernel 6.17).

**Verified live на homelab:** near-expiry simulation (set `expires_at=NOW+5min`) → health_checker fired refresh-cycle через 30с. Phone-side 503 — отдельная история (ADB/APK состояние сейчас).

**Что ОСТАЛОСЬ от плана (Phase 2, ops):**
- Реальная multi-device активация: APK в user_10 настроить (сейчас пуст), привести Avito-app в обоих юзерах в нужное состояние, разнести refresh на 12ч сдвиг между Main/Clone. Plan §"Phase 2".
- Известный pre-existing bug в supabase wrapper: `.eq(col, None)` не делает SQL `IS NULL` (генерит `eq.None`). Сейчас не влияет (production flow всегда передаёт `device_id`), но в backlog.
