# V2 Messenger — Reliability Stack

**Дата:** 2026-04-26
**Статус:** в работе, итеративный
**Цель:** end-to-end надёжная цепочка для V2-мессенджера через **mobile reverse API** (xapi). Соединение к Avito держим **2-3+ дня без потерь сообщений**, всё наблюдаемо, авто-тестируется и алертится.

---

## 1. Что входит, что не входит

### Входит (V2.0 — этот ТЗ)
- Persistent WS-канал к `wss://socket.avito.ru/socket` с auto-reconnect, token refresh, seq resume
- Авто-проверка цепочки токена (телефон → APK → xapi → БД)
- Activity simulator (естественный фон трафика чтобы не выглядеть ботом)
- Messenger-bot **с одним шаблонным ответом** на новый чат (логика цепочки — позже, V2.1)
- Health-check сценарии A-G + UI status board
- Telegram-alerts на 3 fail подряд

### НЕ входит (V2.1+, отдельные ТЗ)
- Цепочка квалификационных вопросов
- LLM-ответы и динамические шаблоны
- Inbox для ручного перехвата в дашборде
- Handoff в TG с контекстом «тёплый лид»
- Avito Official OAuth2 API (тут только mobile reverse)

---

## 2. Архитектура (5 слоёв)

```
┌─ L1: TOKEN PIPELINE ─────────────────────────────────────────┐
│ AvitoSessionManager APK → xapi POST /sessions → avito_sessions│
│ Token Verifier (NEW): cron-job в health-checker              │
└──────────────────────────────────────────────────────────────┘
              ↓
┌─ L2: CONNECTION KEEPER ──────────────────────────────────────┐
│ xapi WsManager ←─ WS ─→ Avito                                │
│  + 3 правки: infinite reconnect, token refresh, seq resume   │
│ WS Health Monitor: ping через WS getUnreadCount каждые 60с   │
└──────────────────────────────────────────────────────────────┘
              ↓
┌─ L3: ACTIVITY SIMULATOR ─────────────────────────────────────┐
│ Сервис activity-simulator: 10-22 MSK 5-15 actions/h          │
│  Микс: getChats 60% / getUnreadCount 20% / getListing 10% /  │
│        openRandomChat+markRead 10%                           │
│  НЕ шлёт исходящих                                           │
└──────────────────────────────────────────────────────────────┘
              ↓
┌─ L4: AUTO-TEST SUITE ────────────────────────────────────────┐
│ A. Token freshness (TTL > 4h)                                │
│ B. Token rotation (≥1 свежий за 24ч)                         │
│ C. WS connection alive                                        │
│ D. WS round-trip getUnreadCount < 5s                          │
│ E. Real-time push (self-send POST → SSE event < 10s)         │
│ F. HTTP messenger send round-trip                             │
│ G. Bot template + dedup (двойной trigger → 1 reply)          │
└──────────────────────────────────────────────────────────────┘
              ↓
┌─ L5: OBSERVABILITY + ALERTS ─────────────────────────────────┐
│ /reliability page: status board + 24h timeline + Run Now     │
│ JSON /api/v1/health/full для APK + внешнего consume          │
│ TG: 3 fail → 🚨, recovery → ✅, daily summary 9:00 MSK       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Принятые архитектурные решения

| Решение | Выбор | Альтернативы |
|---|---|---|
| Транспорт | Mobile reverse через xapi (использует готовый `AvitoWsClient`) | Avito Official OAuth2 — V3+ |
| Где живёт UI | Страница `/reliability` в существующем avito-monitor дашборде | Отдельный сервис, расширение APK UI |
| Activity-simulator | Средний режим (10-22 MSK) | Минимум, максимум-параноидальный |
| Messenger-bot | Отдельный контейнер `messenger-bot` | Внутри `app` |
| Сценарий E (push) | Self-send: бот шлёт себе через POST, ждёт собственный event в SSE | Второй аккаунт (когда появится — переключим) |

---

## 4. БД-миграция (5 новых таблиц в avito-monitor)

### `health_checks`
```sql
id BIGSERIAL PK
ts TIMESTAMPTZ NOT NULL DEFAULT now()
scenario TEXT NOT NULL          -- 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G'
status TEXT NOT NULL            -- 'pass' | 'fail' | 'skip'
latency_ms INT
details JSONB                   -- error msg, измеренные значения
INDEX (scenario, ts DESC)
```

### `messenger_chats`
```sql
id TEXT PK                       -- channel_id с avito (u2i-...)
contact_id TEXT
contact_name TEXT
item_id BIGINT                   -- объявление
is_my_listing BOOLEAN            -- true только если listing наш (whitelist)
created_at TIMESTAMPTZ
last_message_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
raw JSONB
INDEX (last_message_at DESC)
```

### `messenger_messages`
```sql
id TEXT PK                       -- message_id с avito
channel_id TEXT REFERENCES messenger_chats(id) ON DELETE CASCADE
direction TEXT                   -- 'in' | 'out'
author_id TEXT
text TEXT
type TEXT                        -- 'text' | 'image' | 'voice' | 'system'
created_at TIMESTAMPTZ
raw JSONB
INDEX (channel_id, created_at)
```

### `chat_dialog_state`
```sql
channel_id TEXT PK REFERENCES messenger_chats(id) ON DELETE CASCADE
state TEXT NOT NULL              -- V2.0: только 'replied_with_template' | 'no_action'
                                 -- V2.1+: 'qualifying' | 'qualified' | 'cold' | 'handoff' | 'closed'
bot_replied_at TIMESTAMPTZ
bot_reply_message_id TEXT
last_qualified_lead_score INT    -- задел для V2.1
notes JSONB
updated_at TIMESTAMPTZ DEFAULT now()
```

### `activity_log`
```sql
id BIGSERIAL PK
ts TIMESTAMPTZ NOT NULL DEFAULT now()
source TEXT                      -- 'simulator' | 'bot' | 'health_checker' | 'manual'
action TEXT                      -- 'getChats' | 'getUnreadCount' | 'sendMessage' | ...
target TEXT                      -- channel_id / item_id если есть
status TEXT                      -- 'ok' | 'error' | 'rate_limited'
latency_ms INT
details JSONB
INDEX (ts DESC), INDEX (source, ts DESC)
```

---

## 5. xapi reliability-фиксы (Этап 1)

Файл `avito-xapi/src/workers/ws_client.py`:

1. **Reconnect.** `RECONNECT_MAX_ATTEMPTS = 999_999` (де-факто infinite). Capped backoff остаётся 30 сек.
2. **Token refresh при reconnect.** Перед каждым повторным `connect()` перезагружать `session_data = load_active_session(tenant_id)`. Если новой нет → ждать 60 сек и повторять (без счётчика).
3. **Seq resume.** При `connect()` добавлять `?seq={self._seq}` к WS_URL если `_seq > 0`. Avito пришлёт пропущенные события.

---

## 6. Конфигурация (.env)

```env
# --- V2 Messenger Reliability ---
RELIABILITY_ENABLED=true
HEALTH_CHECK_INTERVAL_SEC=300
WS_RECONNECT_DELAY_MAX_SEC=30
WS_PING_INTERVAL_SEC=60

# Activity simulator
ACTIVITY_SIM_ENABLED=true
ACTIVITY_SIM_TIMEZONE=Europe/Moscow
ACTIVITY_SIM_WORKHOURS_START=10
ACTIVITY_SIM_WORKHOURS_END=22
ACTIVITY_SIM_ACTIONS_PER_HOUR_WORK=10
ACTIVITY_SIM_ACTIONS_PER_HOUR_OFF=2

# Messenger bot
MESSENGER_BOT_ENABLED=true
MESSENGER_BOT_TEMPLATE="Здравствуйте! Минуту, сейчас подключится оператор и ответит."
MESSENGER_BOT_RATE_LIMIT_PER_HOUR=60
MESSENGER_BOT_PER_CHANNEL_COOLDOWN_SEC=60
MESSENGER_BOT_WHITELIST_OWN_LISTINGS_ONLY=true

# Telegram alerts (лайт)
RELIABILITY_TG_ALERT_ENABLED=true
RELIABILITY_TG_ALERT_FAIL_THRESHOLD=3
RELIABILITY_TG_ALERT_DAILY_SUMMARY_HOUR=9
```

---

## 7. 9 этапов разработки

См. трекер задач #4–#12. Каждый этап завершается demo-проверкой и коммитом. После Этапа 8 запуск всего стека на 72-96 ч (Этап 9), сбор логов, итерация.

---

## 8. Критерии «стабильности» (когда говорим «готово»)

Soak 72 ч с метриками:
- WS uptime ≥ 99.5%
- Token TTL никогда < 1ч (== APK всегда успевает)
- Round-trip getUnreadCount p95 < 1500 мс
- Auto-bot dedup: 0 двойных ответов
- Activity simulator: ≥ 80 actions/день в рабочие часы, ноль 5xx ошибок
- Telegram alerts отработали хотя бы 1 искусственный fail (manually inject)
- Все 7 сценариев A-G в зелёном на дашборде ≥ 95% времени

После — V2.0 закрыт, начинаем V2.1 (логика цепочки).
