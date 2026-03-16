# Part 3: Worker (Avito Monitor) — Описание и API

## Назначение

Фоновый процесс, который выполняет основную работу системы:
- Мониторит Avito по заданным поисковым запросам
- Фильтрует зарезервированные товары
- Проводит AI-анализ найденных товаров
- Отправляет автоприветствия продавцам при положительном вердикте
- Сохраняет результаты в Backend

## Функционал

1. **Получение конфигурации** — токены, поиски, AI-правила от Backend
2. **Поиск на Avito** — HTTP-запросы к мобильному API Avito
3. **Дедупликация** — фильтрация уже виденных товаров
4. **Проверка резервации** — запрос карточки товара, проверка статуса
5. **AI-анализ** — отправка на OpenRouter, получение вердикта
6. **Автоприветствие** — создание чата и отправка сообщения через WebSocket Avito
7. **Сохранение результатов** — POST товаров и диалогов на Backend

---

## Что получает

### От Backend API

| Endpoint | Что получает | Когда |
|----------|-------------|-------|
| `GET /api/v1/session` | Токены авторизации Avito | Каждый цикл |
| `GET /api/v1/searches?enabled=true` | Активные поиски | Каждый цикл |
| `GET /api/v1/rules?enabled=true` | AI-правила (красные флаги) | Каждый цикл |

**Формат токенов (session):**
```json
{
  "session_token": "eyJhbGciOiJIUzUxMi...",
  "fingerprint": "A2.a541fb18def1032c...",
  "device_id": "a8d7b75625458809",
  "remote_device_id": "kSCwY4Kj4HUfwZHG...",
  "user_hash": "9b82afc1ab1e2419...",
  "user_id": 157920214,
  "expires_at": 1770104756
}
```

**Формат поиска (search):**
```json
{
  "id": 1,
  "query": "iPhone 12 Pro",
  "price_min": 10000,
  "price_max": 25000,
  "delivery": true,
  "location_id": 621540
}
```

**Формат правила (rule):**
```json
{
  "id": 1,
  "text": "iCloud Lock / Activation Lock — пропустить",
  "enabled": true
}
```

### От Avito API

| Endpoint | Что получает | Описание |
|----------|-------------|----------|
| `GET /api/11/items` | Список товаров | Поисковая выдача |
| `GET /api/19/items/{id}` | Карточка товара | Детали + статус резервации |

**Формат ответа поиска Avito:**
```json
{
  "status": "ok",
  "result": {
    "items": [
      {
        "type": "item",
        "value": {
          "id": "7867391303",
          "title": "iPhone 12 Pro, 128 ГБ",
          "price": {"current": "15 000 ₽"},
          "galleryItems": [{"value": {"678x678": "https://..."}}],
          "isDeliveryAvailable": true,
          "sellerInfo": {"userKey": "abc123"},
          "freeForm": [...]
        }
      }
    ]
  }
}
```

### От OpenRouter API

| Endpoint | Что получает |
|----------|-------------|
| `POST /api/v1/chat/completions` | AI-анализ товара |

**Формат ответа OpenRouter:**
```json
{
  "choices": [{
    "message": {
      "content": "{\"verdict\": \"OK\", \"score\": 8, \"summary\": \"Хорошее состояние\", \"defects\": []}"
    }
  }]
}
```

### От Avito Messenger (WebSocket)

| Метод JSON-RPC | Что получает |
|----------------|-------------|
| `avito.chatCreateByItemId.v2` | channel_id созданного чата |
| `avito.sendTextMessage.v2` | Подтверждение отправки |

---

## Что отправляет

### На Backend API

| Endpoint | Что отправляет | Когда |
|----------|---------------|-------|
| `POST /api/v1/items` | Найденный товар с AI-анализом | После анализа каждого товара |
| `PATCH /api/v1/items/{id}` | `{greeted: true, channel_id}` | После отправки приветствия |
| `POST /api/v1/dialogs` | Созданный диалог | После отправки приветствия |

**Формат товара для сохранения:**
```json
{
  "id": "7867391303",
  "title": "iPhone 12 Pro, 128 ГБ",
  "price": 15000,
  "location": "Москва",
  "url": "https://www.avito.ru/7867391303",
  "image_urls": ["https://..."],
  "delivery": true,
  "seller_id": "abc123",
  "reserved": false,
  "description": "Отличное состояние, полный комплект...",
  "ai_verdict": "OK",
  "ai_score": 8,
  "ai_summary": "Хорошее состояние, без видимых дефектов",
  "ai_defects": [],
  "search_id": 1,
  "greeted": false,
  "channel_id": null
}
```

**Формат диалога:**
```json
{
  "channel_id": "ch_123456",
  "item_id": "7867391303",
  "item_title": "iPhone 12 Pro, 128 ГБ",
  "item_price": 15000,
  "seller_name": "Александр",
  "our_message": "Здравствуйте! Интересует ваш iPhone...",
  "search_query": "iPhone 12 Pro"
}
```

### На Avito API

| Endpoint | Что отправляет |
|----------|---------------|
| `GET /api/11/items` | Параметры поиска |

**Параметры поиска:**
```
query=iPhone 12 Pro
locationId=621540
priceMin=10000
priceMax=25000
withDelivery=true
page=1
limit=30
key=af0deccbgcgidddjgnvljitntccdduijhdinfgjgfjir
```

**HTTP-заголовки (обязательные):**
```
X-Session: {session_token}
Cookie: sessid={session_token}
X-DeviceId: {device_id}
X-RemoteDeviceId: {remote_device_id}
f: {fingerprint}
X-App: avito
X-Platform: android
X-AppVersion: 216.0
User-Agent: AVITO 216.0 (OnePlus LE2115; Android 14; ru)
```

### На OpenRouter API

| Endpoint | Что отправляет |
|----------|---------------|
| `POST /api/v1/chat/completions` | Запрос на анализ |

**Запрос на анализ:**
```json
{
  "model": "anthropic/claude-sonnet-4",
  "messages": [
    {
      "role": "system",
      "content": "Ты анализируешь объявления о продаже телефонов...\n\nКрасные флаги:\n- iCloud Lock...\n- Разбит экран...\n..."
    },
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Название: iPhone 12 Pro, 128 ГБ\nЦена: 15000 ₽\nОписание: ..."},
        {"type": "image_url", "image_url": {"url": "https://..."}},
        {"type": "image_url", "image_url": {"url": "https://..."}}
      ]
    }
  ],
  "response_format": {"type": "json_object"}
}
```

### На Avito Messenger (WebSocket)

**Создание чата:**
```json
{
  "jsonrpc": "2.0",
  "method": "avito.chatCreateByItemId.v2",
  "params": {
    "itemId": "7867391303",
    "source": "item",
    "extra": {},
    "xHash": null
  },
  "id": "req_1_abc123"
}
```

**Отправка сообщения:**
```json
{
  "jsonrpc": "2.0",
  "method": "avito.sendTextMessage.v2",
  "params": {
    "channelId": "ch_123456",
    "text": "Здравствуйте! Интересует ваш iPhone 12 Pro...",
    "randomId": "uuid-random",
    "templates": [],
    "quoteMessageId": null,
    "chunkIndex": null,
    "xHash": null,
    "initActionTimestamp": 1770062500000
  },
  "id": "req_2_def456"
}
```

---

## Главный цикл

```
┌─────────────────────────────────────────────────────────────┐
│ ЗАПУСК                                                      │
│ 1. Загрузить конфигурацию из .env                          │
│ 2. Инициализировать BackendClient, AvitoApi, Analyzer      │
│ 3. Подключиться к Avito Messenger (WebSocket)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ЦИКЛ (каждые 60 секунд)                                     │
│                                                             │
│ 1. GET /api/v1/session → токены                            │
│    └─ Если 404: логировать, пропустить цикл                │
│    └─ Проверить exp: если < now+3600 → warning             │
│                                                             │
│ 2. GET /api/v1/searches?enabled=true → поиски              │
│    └─ Если пусто: ничего не делать                         │
│                                                             │
│ 3. GET /api/v1/rules?enabled=true → правила               │
│                                                             │
│ 4. Для каждого поиска:                                      │
│    │                                                        │
│    ├─ 4.1 Avito API: search(query, price, delivery, loc)   │
│    │      └─ Rate limit: 2 сек между запросами             │
│    │      └─ Backoff на 429: 5, 10, 20, 60 сек             │
│    │                                                        │
│    ├─ 4.2 Дедупликация: filter_new(query, items)           │
│    │      └─ Сравнение с tracker.db                        │
│    │                                                        │
│    └─ 4.3 Для каждого нового товара:                       │
│           │                                                 │
│           ├─ 4.3.1 Avito API: get_item_card(id)            │
│           │        └─ Проверить reserved → если true: skip │
│           │                                                 │
│           ├─ 4.3.2 OpenRouter: analyze(title, desc, imgs)  │
│           │        └─ Включить rules в system prompt       │
│           │        └─ Получить verdict, score, defects     │
│           │                                                 │
│           ├─ 4.3.3 Backend: POST /api/v1/items             │
│           │        └─ Сохранить товар с AI-результатом     │
│           │                                                 │
│           └─ 4.3.4 Если verdict == OK и AUTO_GREET:        │
│                    │                                        │
│                    ├─ Messenger: create_chat(item_id)       │
│                    ├─ Messenger: send_message(channel, msg) │
│                    ├─ Backend: PATCH item {greeted, ch_id} │
│                    └─ Backend: POST /api/v1/dialogs        │
│                                                             │
│ 5. Очистка tracker.db (записи старше 7 дней)               │
│                                                             │
│ 6. Ожидание: CHECK_INTERVAL секунд                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Переменные окружения (.env)

```env
# Backend
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026

# OpenRouter (AI)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-sonnet-4

# Worker settings
CHECK_INTERVAL=60
MESSAGE_RATE_LIMIT=30
AUTO_GREET=true
GREETING_TEMPLATE=Здравствуйте! Интересует ваш {title}. Товар в наличии? Готов к быстрой сделке через Авито Доставку.
```

---

## Что возвращает (результат работы)

Worker не имеет собственного API. Результат его работы:

1. **Товары в Backend** — с полным AI-анализом (verdict, score, summary, defects)
2. **Диалоги в Backend** — созданные чаты с продавцами
3. **Сообщения в Avito** — приветствия продавцам
4. **Записи в tracker.db** — для дедупликации
5. **Логи** — stdout/stderr с прогрессом и ошибками
