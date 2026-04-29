# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком, потом проверь сервисы по §2, потом выбери действие из §4. Архитектурные решения — в `DOCS/DECISIONS.md` (ADR-011 — поворот на autosearch sync через мобильный API подписок).
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, и работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito + ценовой разведки.

**Дата последнего обновления:** 2026-04-28 (вечер). Большая сессия — реализована autosearch-sync (ADR-011), реверс мобильного API подписок, поднят второй Avito-аккаунт через System Clone, изменён scheduler на round-robin.

### ⚠ Текущее состояние Avito-сессий

```
                          ┌─ status в БД ──┬─ source ─────┬─ примечание ─────────────────┐
session A (user 0)        │ is_active=false│ manual       │ banned Avito anti-fraud утром │
session B (user 10 clone) │ is_active=true │ android      │ свежая, polling идёт через неё│
```

* **Бан session A** случился из-за burst в первый sync (14 запросов на /N/subscriptions за 5 сек).
* **System Clone (user 10)** настроен на OnePlus 8T — отдельный Avito-аккаунт (profile_id 157920214). На уровне Avito anti-fraud это **другое устройство** (другой device_id), **другой аккаунт** (другой user_id). Polling работает через его токен.
* **Critical mobile API insight:** любой Avito-токен может опрашивать **любой** subscription/{filter_id} — Avito не привязывает access к создателю автопоиска. То есть для polling pool можно ротировать любые токены, sync списка `/5/subscriptions` — только под аккаунтом-владельцем.

### Что задеплоено и работает

| Слой | Что | Статус |
|---|---|---|
| **xapi** (avito-xapi) | `routers/subscriptions.py` с тремя GET-эндпойнтами: `/api/v1/subscriptions` (list), `/api/v1/subscriptions/{id}/search-params` (parsed dict), `/api/v1/subscriptions/{id}/items` (proxy на /11/items с params_extra). Rate-limit понижен до **1 RPS, burst 3**. | ✅ |
| **DB миграция 0004** | `search_profiles.{avito_autosearch_id, import_source, archived_at, last_synced_at, search_params}` + новая таблица `user_listing_blacklist(user_id, listing_id, reason)`. | ✅ применена |
| **avito-monitor service** | `AutosearchSyncService` (pull → upsert → soft-archive → wipe pending/viewed); 2с между autosearch'ами в синке. | ✅ |
| **Polling** | Routing `if profile.import_source==autosearch_sync → fetch_subscription_items(filter_id) else legacy URL`. Pre-fetch user_listing_blacklist → skip rejected. | ✅ |
| **Reject button** | Insert в `user_listing_blacklist`; Undo lifts blacklist. | ✅ |
| **UI** | «🔄 Синхронизировать» на /search-profiles → POST /search-profiles/sync с flash; раздел «🗄 Архив»; форма карточки скрывает поле URL для autosearch_sync (синтетический URL `avito://subscription/{id}`); lightbox на 8-фото галерее в /listings (Esc/← →); фото в TG match-уведомлениях через `send_media_group` (до 10 фото) + текст с кнопками отдельным сообщением. | ✅ |
| **Scheduler** | `app/tasks/scheduler.py` round-robin per user: за tick — максимум 1 enqueue per user, gap 60–120 s jitter между poll'ями одного юзера, выбирается least-recently-polled из due. | ✅ применён, **worker перезагружен** для подхвата кода |
| **System Clone (user 10) на OnePlus** | Avito-app + AvitoSessionManager установлены через `pm install-existing --user 10`; Magisk grant добавлен через `magisk --sqlite "INSERT INTO policies VALUES (1010296, ...)"`; NotificationListener access выставлен через `settings --user 10 put secure enabled_notification_listeners`. Юзер залогинен **вторым** Avito-аккаунтом. | ✅ |
| **Session B зарегистрирована в БД** | Через `c:/Users/EloNout/AppData/Local/Temp/register_clone_session.py` — читает SharedPreferences `/data/user/10/com.avito.android/shared_prefs/com.avito.android_preferences.xml`, парсит и POST на `/api/v1/sessions`. xapi автодеактивирует прежнюю сессию. | ✅ |

### Реальные данные после deploy

`scheduler.tick` после рестарта worker'а делает round-robin:
```
checked=7  eligible_users=1  enqueued=1  skipped_gap=0   ← gap не пройден ещё
checked=7  eligible_users=1  enqueued=1  skipped_gap=0   ← через 60-120с
...
```
Первый автоматический run после re-activation: **7 профилей × 35 items** на каждый, classify уже распределяет по condition_class (working / broken_screen / parts_only / blocked_account / broken_other). Никаких чайников — search_params Avito выдают точную выдачу.

Ещё пример раннего run'а (до рестарта worker'а — старый scheduler enqueue'ил 7 разом):
```
iPhone 12 Pro     | success | seen=35 | new=2  | queued_for_analysis=2
iPhone 13         | success | seen=35 | new=4  | queued=5
iPhone 12 Pro Max | success | seen=35 | new=1  | queued=1
iPhone 14         | success | seen=35 | new=1  | queued=1
Телефоны          | success | seen=35 | new=0  | queued=0
```

### Что НЕ сделано в этой сессии (TODO)

**Tasks #10–#15** в задачнике — все pending:

| # | Что |
|---|---|
| #10 | Captcha detection + TG-notify + pause |
| #11 | Avito IP-ban detection + proxy failover |
| #12 | IP rotation pool for Avito API |
| #13 | Multi-account pool with round-robin (xapi account-aware, AccountPool service) |
| #14 | V1.5: 2nd Avito account via OnePlus Parallel/Clone — на устройстве сделано, **backend для round-robin между токенами не реализован** (xapi всё ещё берёт `MAX(created_at) WHERE is_active=true` — то есть всегда **последнюю** активную сессию, не RR) |
| #15 | Exponential backoff on Avito 403 ban |

**Главный архитектурный долг — #13/#14:** сейчас xapi.session_reader всегда возвращает **одну** active session (последнюю по created_at). Чтобы реально использовать pool из двух токенов, нужно:
1. DB миграция 0005: `avito_accounts(id, tenant_id, nickname, state, last_used_at, daily_quota_used)` + `avito_sessions.account_id` FK
2. xapi `BaseAvitoClient(account_id)` + новый `load_session_for_account(id)`
3. avito-monitor `AccountPool` — round-robin LRU + per-account 60–120 s gap + on-403 mark and skip
4. Передача `account_id` из poll_profile в xapi-client

Оценка: ~3-4 часа. Сейчас pool работает де-факто как pool-of-1 (clone token), потому что user 0 token deactivated после ban'а.

---

## 2. Что сделать сразу при возврате

```bash
# 1. Sync homelab жив?
ssh homelab 'echo OK'

# 2. Стек поднят?
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose ps --format "table {{.Service}}\t{{.Status}}"'

# 3. xapi живой и Avito ему отвечает?
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' -o /dev/null -w '%{http_code}\n' \
  'http://127.0.0.1:8080/api/v1/search/items?query=iphone&per_page=1'"
# 200 = clone-токен работает. 500 = Avito banned и его, см. §4 «восстановление».

# 4. Round-robin scheduler действительно ставит по 1?
ssh homelab 'docker logs avito-monitor-worker-1 --since=5m 2>&1 | grep "scheduler.tick" | tail -10'
# Ожидаешь: enqueued=1 (НЕ 7) и skipped_gap иногда=1 между tick'ами

# 5. Profile_runs за последний час
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"SELECT pr.started_at, sp.name, pr.status, pr.listings_seen, pr.listings_new \
  FROM profile_runs pr JOIN search_profiles sp ON sp.id=pr.profile_id \
  WHERE pr.started_at > NOW() - INTERVAL '1 hour' ORDER BY pr.started_at DESC LIMIT 10;\""

# 6. Активные сессии
ssh homelab "docker exec supabase-db psql -U postgres -d postgres -c \
  \"SELECT id, device_id, source, is_active, EXTRACT(EPOCH FROM (NOW()-created_at))/60 as min_old, expires_at \
  FROM avito_sessions ORDER BY created_at DESC LIMIT 5;\""
# Ожидаешь: 1 active (clone, source=android) + старые is_active=false (включая banned user 0)
```

---

## 3. Operational заметки

### Сегодняшние ключевые insights

* **Avito anti-fraud per-account, не per-IP** — мы это эмпирически подтвердили (юзер с того же IP но другого устройства/аккаунта в Avito-app работал нормально, наш банный токен с любого IP не работал). Защита будущего: pool аккаунтов (#13).
* **`/5/subscriptions` отдаёт только title/description, без structured params**. Чтобы получить точные search params нужен ещё один запрос — `/2/subscriptions/{filter_id}`, в `result.deepLink` лежит query-string `?categoryId=84&locationId=621540&params[110617][0]=491590&params[110618][0]=469735&priceMin=…&priceMax=…&sort=…&withDeliveryOnly=1`.
* **Любой Avito-токен может опрашивать любой filter_id** — для polling нужен любой токен из pool, не обязательно создателя autosearch.
* **System Clone в OnePlus** = отдельный Android-user (`pm list users` → 0 + 10). Apps надо ставить отдельно (`pm install-existing --user 10 <pkg>`). NotificationListener в неактивном user может тормозиться Android'ом — рекомендуется раз в день-два открывать clone-пространство на минуту чтобы NL «прогрелся».
* **Magisk root grant per-UID, per-user**: UID = `userId * 100000 + appId`. Для AvitoSessionManager appId=10296 → user 0 UID=10296, user 10 UID=1010296. Команда выдачи:
  ```bash
  magisk --sqlite "INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (1010296, 2, 0, 1, 1)"
  ```
* **AvitoSessionManager НЕ читает SharedPreferences самостоятельно при старте.** Он триггерится push-уведомлением Avito-app о login/refresh. Если push был пропущен (NL access выдан после login) — token не зарегистрируется. Workaround: прямой `cat` SharedPreferences через root + POST на `/api/v1/sessions` (см. `c:/Users/EloNout/AppData/Local/Temp/register_clone_session.py`).
* **xapi `POST /api/v1/sessions` deactivates все прежние active sessions того же tenant'а** (`UPDATE is_active=false WHERE tenant_id=X AND is_active=true`). При regimen с pool это надо **отключить** (или делать INSERT минуя router). Сейчас это нормально потому что мы сознательно сменили активную сессию на clone-токен.
* **TG проксирование через Xray** (для match-нотификаций) — `TELEGRAM_PROXY_URL=http://host.docker.internal:10808`, `aiohttp-socks==0.11.0` нужно установить руками после `docker compose up` — `uv pip install aiohttp-socks` для worker / telegram-bot / health-checker. Не забыть после rebuild.

### Известные хвосты

* **#13/#14 backend для round-robin между токенами** не сделан — pool работает как pool-of-1 (см. §1 хвост).
* **Старая user 0 session может разморозиться** через несколько часов / суток. Когда — нужно вернуть `is_active=true` для соответствующей записи в `avito_sessions` ВРУЧНУЮ (xapi auto-deactivates other so don't rely on auto). До #13 — это просто spare, если clone-токен попадёт в ban.
* **5 health_checker tests сломаны** после Stage 9 (русские строки vs ожидаемые английские) — со прошлой сессии. ~20 мин на починку.
* **Старые 200+ лотов с `class=unknown`** в БД остаются — LLM-кэш по cache_key. Очистятся естественно через cleanup (ADR-009 retention).

---

## 4. Что делать дальше

| Опция | Что | Часов | Приоритет |
|---|---|---|---|
| **A. Backend round-robin pool (#13/#14)** | DB 0005 + AccountPool service + account-aware xapi. После этого pool из 2-х (clone + user 0 когда unbanned) реально шарит нагрузку. | 3-4 | **Высокий** — фундамент защиты от анти-fraud |
| **B. Captcha / IP-ban / 403 detection (#10/#11/#15)** | Distinguish 403-types (capture body первого 403), exponential backoff с pauseUntil, единая TG-нотификация. | 2-3 | Высокий |
| **C. Восстановить user 0 token** | Когда Avito unban'ит — `UPDATE avito_sessions SET is_active=true WHERE id='e6be0b67-…'`. Spare для pool. Без #13 это перезатрёт clone-токен на следующем polling tick'е. **Не делать до #13!** | 5 мин | После #13 |
| **D. Auto-resume agent** | `/schedule` agent каждые 30 мин проверяет clone-токен → если внезапно 403 → пауза профилей + TG-alert. | 30 мин | Низкий |
| **E. UI «Аккаунты Avito» в /settings** | После #13 — список pool-аккаунтов, state, ручной pause. | 30 мин | После #13 |
| **F. Block 8 — Polish + 72h soak (TLS Caddy)** | Финальный V1 блок. | ~6 ч | После A+B |

**Рекомендация на следующий заход:** A (#13 round-robin pool) → B (детекторы 403) → C (вернуть user 0 в pool) → soak.

### Промпт-стартер для нового блока

```
Проект: c:/Projects/Sync/AvitoSystem/avito-monitor/
Прочитай: CONTINUE.md (текущий статус) + DOCS/DECISIONS.md ADR-011 + DOCS/avito_api_snapshots/autosearches/README.md.
Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Хочу [Backend round-robin pool / IP-ban detection / …]. Сначала проверь сервисы (см. §2 CONTINUE.md). Если что-то не up — подними и сообщи.
```

---

## 5. Полезные команды (новые из этой сессии)

```bash
# Проверить какой токен активен сейчас и его TTL
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/sessions/current"

# Список всех autosearches на стороне Avito (через clone token)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/subscriptions" | python3 -m json.tool | head -40

# Получить structured search-params для одного autosearch
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' \
  'http://127.0.0.1:8080/api/v1/subscriptions/264239719/search-params'" | python3 -m json.tool

# Items для одного autosearch (это и есть polling-канал)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' \
  'http://127.0.0.1:8080/api/v1/subscriptions/264239719/items?page=1&per_page=5'"

# Распределение профилей по import_source
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"SELECT import_source, COUNT(*), SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active \
  FROM search_profiles WHERE archived_at IS NULL GROUP BY import_source;\""

# Размер blacklist по reject
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"SELECT COUNT(*), reason FROM user_listing_blacklist GROUP BY reason;\""

# Magisk: список всех root-grants
ADB="C:/Users/EloNout/AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v3.3.4/adb.exe"
$ADB -s 110139ce shell "su -c 'magisk --sqlite \"SELECT * FROM policies\"'"

# Magisk: выдать grant новому UID (например, AvitoSessionManager в новом user)
$ADB -s 110139ce shell "su -c 'magisk --sqlite \"INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (<UID>, 2, 0, 1, 1)\"'"

# NotificationListener access в conkretnom user'е
$ADB -s 110139ce shell "su -c 'settings --user 10 put secure enabled_notification_listeners com.avitobridge.sessionmanager/com.avitobridge.service.AvitoNotificationListener'"

# Зарегистрировать сессию из SharedPreferences user X напрямую
python c:/Users/EloNout/AppData/Local/Temp/register_clone_session.py
# (читает /data/user/10/com.avito.android/shared_prefs/com.avito.android_preferences.xml,
#  парсит, POSTит в xapi /api/v1/sessions; токены не печатает в stdout)

# Принудительный refresh_token через APK (V2.1)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{\"command\":\"refresh_token\",\"payload\":{\"timeout_sec\":90,\"prev_exp\":0},\"issued_by\":\"manual\"}' \
  -X POST http://127.0.0.1:8080/api/v1/devices/me/commands"

# Запустить sync через UI (то же что кнопка «🔄 Синхронизировать»)
# Через docker exec без cookie:
ssh homelab 'docker exec avito-monitor-app-1 python -c "
import asyncio
from app.db.base import get_sessionmaker
from sqlalchemy import select
from app.db.models import User
from app.services.autosearch_sync import sync_autosearches_for_user

async def main():
    async with get_sessionmaker()() as s:
        u = (await s.execute(select(User).limit(1))).scalar_one()
        print(await sync_autosearches_for_user(u.id, session=s))

asyncio.run(main())
"'

# Включить/выключить все autosearch профили разом
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor -c \
  \"UPDATE search_profiles SET is_active=true WHERE import_source='autosearch_sync' AND archived_at IS NULL;\""
```

---

## 6. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/DECISIONS.md` ADR-011 | Поворот на autosearch-sync: re-sync семантика, blacklist, manual_url legacy |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Полный реверс мобильного API: endpoints, request/response, models (SearchSubscription, SearchParams, pu0.d/c) |
| `DOCS/V1_BLOCKS_TZ.md` | Per-block ТЗ. Block 7 done, Block 8 актуален |
| `DOCS/UI_DESIGN_SPEC_V1.md` | UI спека — фон-light, токены |
| `avito-monitor/docker-compose.homelab.yml` | apparmor=unconfined + bind-mount + ports |

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
1. Polling работает через clone-токен (user 10 на OnePlus 8T System Clone). User 0 token banned до восстановления.
2. autosearch-sync залит и работает: из 7 autosearch'ей юзера (iPhone 11/12/12Pro/12ProMax/13/14 + «Телефоны») сервер тянет items через `/2/subscriptions/{id}/items` с точными structured params — никаких чайников.
3. **Главный технический долг**: backend round-robin между токенами (#13/#14). Сейчас pool=1, любой ban toкена → пауза всей системы.
4. После #13 → восстановить user 0 token (он spare) → детекторы 403 (#10/#11/#15) → Block 8 polish.
