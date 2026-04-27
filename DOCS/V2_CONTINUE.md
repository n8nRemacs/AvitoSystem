# V2 Continue — снапшот для рестарта сессии

> **Если ты Claude и видишь это первым:** прочитай этот файл целиком, потом проверь сервисы по §3, потом действуй по §6.
> **Если ты пользователь:** скопируй файл в новую сессию Claude — работа продолжится.

**Дата снапшота:** 2026-04-27 ~06:05 UTC
**Где живёт код:** `c:/Projects/Sync/AvitoSystem/` (Windows-пути; Docker контейнеры внутри)

---

## 1. Что работает сейчас (production)

### avito-monitor стэк (dev-машина, Docker Desktop)

| Сервис | Порт | Роль | Up |
|---|---|---|---|
| `app` | 8000 | FastAPI дашборд + `/reliability` страница + `/api/v1/health/full` | ✅ |
| `db` | 5432 | Postgres 16 (16 таблиц: V1 + 5 V2-reliability) | ✅ |
| `redis` | 6379 | резерв под TaskIQ V1 | ✅ |
| `avito-mcp` | 9000 | FastMCP-сервер с 4 tools (search, listing, images, health) | ✅ |
| `health-checker` | 9100 | 7 сценариев A-G каждые 5 мин + русские TG-алерты | ✅ |
| `activity-simulator` | 9101 | имитация юзера (10-22 MSK 5-15 actions/h) | ✅ |
| `messenger-bot` | 9102 | SSE listener + dedup + whitelist + rate-limit | ✅ работает, но **gap-резильентность отсутствует** |

### homelab (213.108.170.194) сервисы

| Сервис | Порт | Роль |
|---|---|---|
| `avito-xapi-xapi-1` | 8080 | xapi — gateway к Avito mobile API (curl_cffi Chrome120, WS к `wss://socket.avito.ru`) |
| `avito-mcp-homelab` | 9000 | дублёр avito-mcp на homelab (для APK с телефона) |
| Supabase self-hosted | 8000, 5433 | PostgreSQL + REST для xapi (`avito_sessions`, `tenants`, `avito_api_keys`, etc.) |

### Phone (OnePlus 8T, 192.168.31.143)

- **Avito client** (`com.avito.android`) — установлен, юзер залогинен, JWT в SharedPrefs обновляется при использовании
- **AvitoSessionManager APK** (`com.avitobridge.sessionmanager`) — Magisk root grant выдан (uid 10296 policy=2/ALLOW), читает SharedPrefs через `su -mm -c cat`, шлёт `POST /api/v1/sessions` на xapi. UI — три зелёных карты (Server Status, avito-mcp, Device Session)

### SSH-туннели (с dev-машины к homelab)

```bash
ssh -D 127.0.0.1:1081 -N -f homelab            # SOCKS5 для запросов к Avito с зарубежного IP
ssh -L 127.0.0.1:8080:localhost:8080 -N -f homelab  # xapi доступен локально как localhost:8080
```

Оба нужны на dev-машине, проверяй после рестарта.

---

## 2. Что сделано (V2.0 Reliability + V1 fixes)

### V2.0 Messenger Reliability Stack — 9/9 этапов завершены

См. `DOCS/V2_MESSENGER_RELIABILITY_TZ.md` — полное ТЗ.

| Этап | Артефакт |
|---|---|
| 1 | xapi WS reliability: tuple-fix recv(), `RECONNECT_MAX_ATTEMPTS=999_999`, token refresh callback из БД при reconnect, seq resume через `?seq=`. `apparmor:unconfined` security_opt. `--loop asyncio` (uvloop падает в LXC) |
| 2 | 5 БД-таблиц: `health_checks`, `messenger_chats`, `messenger_messages`, `chat_dialog_state`, `activity_log` |
| 3 | health-checker сервис, сценарии A/B/C/D через xapi REST |
| 4 | `SseClient` async ctx manager, сценарии E/F |
| 5 | activity-simulator: getChats 60% / getUnreadCount 20% / getListing 10% / openRandomChat+markRead 10% |
| 6 | messenger-bot: SSE listener → handler с dedup (`chat_dialog_state`), whitelist по `is_my_listing` (default-allow на uncertainty), rate-limit (60/h глобально, 1/min на канал), kill-switch `MESSENGER_BOT_ENABLED`, scenario G |
| 7 | `/reliability` UI page + `/api/v1/health/full` JSON |
| 8 | TG alerts на русском: 🚨 «Сбой проверки», ✅ «Сценарий восстановлен», 📊 «Сводка надёжности», 🧪 «Тест Telegram-алертов». Бот `@Avitisystem_bot`, токен `8703595821:AAGt0Xi3tNBscmyfa_-9yUy9PMQ8KcrsXNA`, chat_id `6416413182` |
| 9 | Soak-итерации: scenario E фикс (any post-connected event, budget 60s), scenario F фикс (`/typing` → `/read`, Avito убрал typing endpoint) |

### V1 fixes по ходу

| Что | Артефакт |
|---|---|
| Block 1 (avito-mcp) | 4 V1-tools, scaffolding в `avito_mcp/`, тесты, MCP-конфиг для Claude Code |
| **Task #3 — xapi search normalizer** ✅ переделан: search feed теперь имеет форму `result.items[].value.{id,title,price.current,galleryItems,uri,...}` вместо старой плоской. Detail на `/api/19/items/{id}` тоже исправлен. Реальные данные текут (35 iPhones по запросу, цены 10-13к в нужном диапазоне). 106 тестов pass |

### Сервисы, БД, секреты

```bash
# OpenRouter (V1 Block 3+):
OPENROUTER_API_KEY=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  # $8.41 used, без лимита

# avito-xapi auth:
X-Api-Key: test_dev_key_123  # tenant c0000000-0000-0000-0000-000000000001, toolkit с features ["avito.sessions","avito.messenger","avito.search","avito.calls","avito.farm"]

# avito-mcp auth (Bearer):
AVITO_MCP_AUTH_TOKEN=dev-mcp-token-change-me

# Avito session (БД homelab Supabase, таблица avito_sessions):
# обновляется AvitoSessionManager APK с телефона, TTL ~24h, source='manual' от APK
```

---

## 3. Quick health check (после рестарта Claude-сессии)

```bash
# 1. Туннели — после засыпания ноута часто умирают
ssh -L 127.0.0.1:8080:localhost:8080 -N -f homelab
ssh -D 127.0.0.1:1081 -N -f homelab
curl -s http://localhost:8080/health  # → {"status":"ok","version":"0.1.0"}

# 2. avito-monitor стек
cd c:/Projects/Sync/AvitoSystem/avito-monitor && docker compose ps

# 3. Все 7 сценариев зелёные?
curl -s -X POST http://127.0.0.1:9100/run-all | python -c "import sys,json; r=json.load(sys.stdin); [print(x['scenario'],x['status'],x.get('latency_ms'),'ms') for x in r['results']]"

# 4. /reliability дашборд (auth cookie через owner/block0test)
curl -s -c /tmp/c.txt -d "username=owner&password=block0test" http://127.0.0.1:8000/login
curl -s -b /tmp/c.txt http://127.0.0.1:8000/api/v1/health/full | python -m json.tool | head -30
```

---

## 4. Известные проблемы (вскрылись в soak)

### Критическое: bot пропускает реальные сообщения при разрывах SSE

**Симптом:** покупатель написал в чат `u2i-~AyuR1xA7zmtpIKN01uUfw` 2026-04-27 05:55, бот не среагировал. В логах `messenger-bot.sse.broken` — 14 раз за 8 часов работы. В 05:55:32 случился разрыв, сообщение пришло в 05:55-05:56.

**Root cause:** Avito не делает backfill пропущенных push-events. SSE-стрим bot↔xapi разрывается → window наружу выпадает.

**Зафиксированные таймстампы разрывов SSE (UTC 2026-04-27):** 05:55:32, 05:58:40, 05:58:41, 05:59:43, 05:59:44, 06:01:42, 06:01:43, ещё ~7 раньше.

**В то же время бот СРАБОТАЛ** на чате `u2i-iFvvBZ3TGrsQbIg9IKoOaA` в 05:31:18 — отправил шаблон, dedup'ил последующие events. То есть пайплайн рабочий, проблема только в gap-resilience.

### Мелкие

- `User ID: -` в APK UI и в `avito_sessions.user_id` (NULL) — xapi не вытаскивает `u` claim из JWT. Поправить в `xapi/src/routers/sessions.py`.
- `D` сценарий иногда borderline (~1500-2000ms) под parallel-load run-all. Не критично, threshold 2000ms даёт запас.

---

## 5. Открытые задачи (трекер)

| # | Статус | Что |
|---|---|---|
| #14 | pending | **Catchup on reconnect** для bot — после SSE reconnect дёрнуть GET /messenger/channels, синтезировать `new_message` events для пропущенных |
| #15 | pending | V1 Block 3 — LLM Analyzer (OpenRouter classify_condition / match_criteria / compare_to_reference + cache + budget) |
| #16 | **новая** | **Notification Interception на APK** — см. §6 ниже |
| — | pending | Сценарий H в health-checker — bot coverage check (есть unread без нашего outgoing/state → FAIL) |
| — | pending | V1 Block 4 worker (теперь разблокирован после Task #3) |
| — | pending | V1 Block 5/6/7/8 (TG bot, stats charts, price intel, deploy) |

---

## 6. ТЗ — Notification Interception (новая идея, приоритет высокий)

### Зачем

Avito Android-клиент получает FCM push-уведомления о новых сообщениях, звонках, уведомлениях системы — даже когда приложение в фоне или закрыто. Эти push рендерятся в Notification shade. Мы можем **читать их в реальном времени** через `NotificationListenerService` — это надёжный канал, **не зависит от WS** к Avito.

Это **третий канал** для получения новых сообщений (плюс к WS push и REST polling), и самый устойчивый — Google FCM сам делает retry/backfill, мы просто слушатели.

### Архитектура

```
Avito server  ──FCM push──>  com.avito.android (на телефоне)
                                    │
                                    ▼ (Android Notification API)
              ┌────────── NotificationListenerService ──────┐
              │ class AvitoNotificationListener              │
              │   onNotificationPosted(sbn) {                │
              │     if (sbn.packageName == "com.avito.android") {  │
              │       parse(sbn.notification.extras)          │
              │       POST /api/v1/notifications  ──────────┐ │
              │     }                                        │ │
              │   }                                          │ │
              └──────────────────────────────────────────────┘ │
                                                                │
                                ┌───────────────────────────────┘
                                ▼
                          xapi (homelab :8080)
                          /api/v1/notifications endpoint (новый)
                            │
                            ├── persist в новую таблицу avito_notifications
                            └── broadcast в WsManager queue
                                  │
                                  ▼
                            messenger-bot (SSE)
                            handle_event(synthetic new_message)
```

### Шаги реализации

#### Phase 1: APK — NotificationListenerService

В `AvitoSessionManager` APK:

1. **Permission в Manifest:**
   ```xml
   <service
       android:name=".service.AvitoNotificationListener"
       android:label="Avito Notification Listener"
       android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE"
       android:exported="true">
       <intent-filter>
           <action android:name="android.service.notification.NotificationListenerService" />
       </intent-filter>
   </service>
   ```

2. **Service** `app/src/main/java/com/avitobridge/service/AvitoNotificationListener.kt`:
   - `extends NotificationListenerService`
   - В `onNotificationPosted(sbn: StatusBarNotification)`:
     - Фильтр `sbn.packageName == "com.avito.android"`
     - Парсинг `sbn.notification.extras`:
       - `Notification.EXTRA_TITLE` — обычно имя отправителя ("Иван") или название уведомления
       - `Notification.EXTRA_TEXT` — preview сообщения
       - `Notification.EXTRA_BIG_TEXT` — полный текст если есть
       - `Notification.EXTRA_SUB_TEXT` — channel id или контекст
       - `sbn.tag`, `sbn.id` — Avito может класть туда channel_id
     - POST на xapi `http://192.168.31.97:8080/api/v1/notifications` с payload:
       ```json
       {
         "source": "android_notification",
         "received_at": "<iso>",
         "package_name": "com.avito.android",
         "notification_id": <int>,
         "tag": "<string>",
         "title": "<string>",
         "text": "<string>",
         "big_text": "<string>",
         "sub_text": "<string>",
         "extras_raw": {<...>}  // полный JSON для дебага
       }
       ```
     - Заголовок `X-Device-Key: test_dev_key_123` (тот же что у sync токена)

3. **UI**:
   - В MainActivity добавить блок «Notification Listener»:
     - Status: granted / not granted (через `NotificationManagerCompat.getEnabledListenerPackages()`)
     - Кнопка «Grant access» → открывает `Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`
     - Last forwarded: timestamp последнего успешного POST
     - Total today: счётчик
     - Test button: создать локальный test notification → проверить что forward сработал

4. **In-memory dedup**: ring buffer (last 100 notifications) для обхода дублей если Android повторно postит то же самое.

#### Phase 2: xapi — `/api/v1/notifications` endpoint

В `avito-xapi/src/routers/`:

1. **Новый router** `notifications.py`:
   - `POST /api/v1/notifications` — принимает JSON, валидирует (Pydantic), сохраняет в новую таблицу `avito_notifications`, **broadcasts через WsManager** в SSE-очередь.
   - Auth: `X-Device-Key` / `X-Api-Key` (стандартный для нашего tenant).
   - Не блокирует ответ — broadcast и persist делаем в background task, response 201 сразу.

2. **БД-миграция** на homelab Supabase:
   ```sql
   CREATE TABLE avito_notifications (
       id BIGSERIAL PRIMARY KEY,
       tenant_id UUID NOT NULL REFERENCES tenants(id),
       received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       source TEXT,          -- 'android_notification'
       title TEXT, text TEXT, big_text TEXT, sub_text TEXT,
       notification_id INT, tag TEXT,
       extras JSONB,
       processed BOOLEAN DEFAULT false,
       INDEX (tenant_id, received_at DESC)
   );
   ```

3. **WsManager broadcast**: после persist — формируем event:
   ```python
   {
       "event": "notification_intercepted",
       "tenant_id": ctx.tenant.id,
       "timestamp": "<iso>",
       "payload": {"title": ..., "text": ..., "tag": ...}
   }
   ```
   и `conn.broadcast(event)` через тот же WsManager. SSE подписчики (наш messenger-bot) получают.

#### Phase 3: messenger-bot — handle `notification_intercepted`

В `app/services/messenger_bot/handler.py`:

- Расширить `handle_event` — принимать `event_name == "notification_intercepted"` так же как `new_message`
- Маппинг: `title` → contact_name (примерно), `text` → message body, `tag` → channel_id (если Avito туда кладёт)
- **Если channel_id извлёкся** — обработать как обычный `new_message` event (dedup, whitelist, send template)
- **Если channel_id не извлёкся** — записать в `activity_log` для дебага, не отвечать (мы не знаем куда)

Параллельно: bot может **запрашивать xapi `GET /messenger/channels?limit=10`** чтобы найти свежий канал по совпадению title/text — fallback если tag не информативен. Но это P2.

#### Phase 4: scenario I — Notification Listener health

Новый сценарий в health-checker:
- Проверяет что **за последние X часов** были intercepted notifications (как индикатор что Android Service жив + API endpoint работает)
- Или дёргает endpoint `GET /api/v1/notifications/stats` который xapi выставит — последний таймстамп
- PASS если стабильный поток или хотя бы 1 за 12 часов
- FAIL если тишина

### Когда полезно

- WS-разрыв в bot↔xapi → notification всё равно прилетит на телефон → bot обработает
- Avito WS pushes ненадёжен (как мы только что выяснили) → notifications надёжнее
- В будущем — реакции на звонки, уведомления о товарах, фильтрах поиска и т.д. (более широкий канал)

### Подводные камни

1. **Notification listener** требует ручного grant'а в Settings (один раз).
2. **Notification text может быть обрезан** (Android urлчает summary, full text доступен только если приложение разрешает `BIG_TEXT_STYLE`). Проверить как Avito форматирует.
3. **Авито может объединять несколько сообщений в одно уведомление** (group summary). Парсить по тегу/id.
4. **Магазин Google Play может отвергнуть APK** с NotificationListener без dialog disclosure — нам не критично, мы sideload.
5. **Дубли** — если Avito переотправляет уведомление (например при чтении), мы должны не зацикливаться. Dedup в самом APK (ring buffer) + dedup в bot (уже есть через `chat_dialog_state`).

### Время

- Phase 1 (APK): 2-3 часа
- Phase 2 (xapi endpoint + БД-миграция): 1-1.5 часа
- Phase 3 (bot handler): 30-60 мин
- Phase 4 (scenario I): 30-60 мин
- Тестирование (попросить покупателя написать → проверить что прилетел notification → bot ответил): 30 мин

**Итого:** ~5-7 часов. Можно дробить.

---

## 7. Задачи в трекере (актуальный список)

```
#1  ✅ Fix APK auto-sync
#2  ✅ Block 1 — avito-mcp scaffolding
#3  ✅ Fix xapi search normalizer
#4-#11 ✅ V2-Reliability Этапы 1-8
#12 ✅ V2-Reliability Этап 9 — soak (выявил проблему §4)
#13 ✅ APK UI cleanup
#14 ⏳ Catchup on reconnect для bot
#15 ⏳ V1 Block 3 — LLM Analyzer
#16 ⏳ Notification Interception (новый, см. §6)
```

---

## 8. Финальное решение по архитектуре (зафиксировано)

После обсуждения вариантов A/B/C (phone vs Redroid vs combined) выбран **этапный путь**:

### Сейчас (V2.1) — Phone NotificationListener + REST catchup

- Только физический OnePlus 8T (192.168.31.143) перехватывает FCM-уведомления
- `NotificationListenerService` в AvitoSessionManager → POST на xapi `/api/v1/notifications`
- Дополнительно — Task #14 (catchup-on-reconnect для bot)
- **Без Redroid в этой фазе**

### Потом (V2.2) — мониторим soak ~3-5 дней

- Если Phone-канал стабилен — Redroid не нужен, готово
- Если Phone-канал даёт сбои (батарея/Wi-Fi/перезагрузки) → переходим к Phase 2

### V2.2 (если надо) — добавляем Redroid в strict-mutex с phone

**Архитектура (зафиксирована, к реализации только если phone-only оказался ненадёжен):**

State-machine с двумя состояниями: «phone primary» / «redroid primary». Только один клиент Avito **онлайн в моменте** (другой — `am force-stop` + iptables drop сетки для `com.avito.android`).

Handoff каждые ~20-22ч или по health-fail:
1. Active делает финальный sync JWT в xapi DB
2. Active → standby (force-stop, network block)
3. Передача через xapi `POST /api/v1/devices/handoff`
4. Promote: standby читает свежий JWT из DB → подменяет SharedPrefs → unblock network → стартует Avito-app → регистрирует FCM, открывает WS
5. Symmetric reverse

Что нужно:
- В `AvitoSessionManager` новые intent-handler'ы `STANDBY` / `PROMOTE`
- В xapi state-machine endpoint `POST /api/v1/devices/handoff`
- Сценарий H в health-checker — следит за primary lifetime, инициирует handoff
- Anti-detect стек на Redroid: Magisk + Shamiko + Zygisk DenyList + build.prop spoof OnePlus 8T + PlayIntegrityFix

**Время:** 1-2 недели. Не делается сейчас, только если phone-only не справится.

**Риски V2.2:** ~30% шанс что Avito детектит «частые FCM-swap = ненадёжный аккаунт» и попросит SMS-подтверждение. Если так — пересматриваем подход.

### V2.3+ (потенциал) — дополнительные каналы

- Web-сессия через Selenium/Playwright как 4-й канал (если совсем deep redundancy)
- Reverse refresh_token flow в xapi (чтобы phone был только seed-источник, JWT обновлялся без UI Avito) — посмотреть `AvitoAll/Avito_Redroid_Token/`, `AvitoAll/API_AUTH.md` на предмет существующего reversa

---

## 9. Что делать в новой сессии — старт-промпт

```
Прочитай c:/Projects/Sync/AvitoSystem/DOCS/V2_CONTINUE.md целиком — это
снапшот после длинной сессии работы над V2 Messenger Reliability.

Проверь сервисы по §3 (туннели после засыпания ноута часто падают).
Если что-то красное — почини.

Дальше — реализуем §6 «Notification Interception, Phase 1 — Phone only»:
1. APK: NotificationListenerService для com.avito.android, POST на xapi
2. xapi: новый router /api/v1/notifications, БД-таблица avito_notifications,
   broadcast в SSE
3. Bot: handle_event на event_name=notification_intercepted
4. Сценарий I в health-checker

Параллельно (независимо) можно делать:
- Task #14 Catchup on reconnect (~1.5ч)
- Task #15 V1 Block 3 LLM Analyzer (~6-8ч, нужен для Block 4)

Redroid (V2.2) — пока НЕ делаем. Сначала смотрим как phone справится в soak.

Алерты в TG @Avitisystem_bot — на русском. Общение со мной — на русском.
```

**Приоритет 1:** #16 Phase 1 (phone NotificationListener) — ~5-7ч
**Приоритет 2:** #14 Catchup on reconnect — ~1.5ч (сразу после #16, чтобы bot был bullet-proof)
**Приоритет 3:** #15 V1 Block 3 LLM — параллельно, разблокирует Block 4

После завершения этих трёх — начинается V1 Block 4 worker pipeline (актуальный продукт мониторинга).
