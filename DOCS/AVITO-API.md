# Avito API Reference

Полное описание реверс-инженерного API Avito. Все данные получены через Frida-перехват трафика мобильного приложения и анализ OkHttp interceptors.

**Статус:** Актуально на февраль 2026. Версия приложения 215.1 / 216.0.

---

## Содержание

1. [Блок 1: Аутентификация и токены](#блок-1-аутентификация-и-токены)
2. [Блок 2: HTTP-заголовки и TLS](#блок-2-http-заголовки-и-tls)
3. [Блок 3: Messenger HTTP REST API](#блок-3-messenger-http-rest-api)
4. [Блок 4: Messenger WebSocket JSON-RPC](#блок-4-messenger-websocket-json-rpc)
5. [Блок 5: Поиск и объявления](#блок-5-поиск-и-объявления)
6. [Блок 6: IP-телефония (Call Tracking)](#блок-6-ip-телефония-call-tracking)
7. [Блок 7: Анти-бот защита (QRATOR)](#блок-7-анти-бот-защита-qrator)
8. [Блок 8: Извлечение токенов (Root/Redroid)](#блок-8-извлечение-токенов-rootredroid)

---

## Блок 1: Аутентификация и токены

### JWT Session Token

**Алгоритм:** HS512
**Время жизни:** ровно 24 часа
**Хранение:** SharedPreferences ключ `session`

**Payload:**
```json
{
  "exp": 1770104756,       // Expiration (iat + 86400)
  "iat": 1770018356,       // Issued at
  "u": 157920214,          // User ID
  "p": 28109599,           // Profile ID
  "s": "dd1ce4a4ccfb4bb6bb24395a9546cade.1770018356",  // Session hash
  "h": "NDZkMTc5NjljZTFi...",  // Hash (base64)
  "d": "a8d7b75625458809", // Device ID (= X-DeviceId)
  "pl": "android",         // Platform
  "extra": null
}
```

**Декодирование (без проверки подписи):**
```python
import base64, json

def parse_jwt(token: str) -> dict:
    parts = token.split('.')
    payload = parts[1]
    payload += '=' * (4 - len(payload) % 4)  # fix padding
    return json.loads(base64.urlsafe_b64decode(payload))
```

### Refresh Token

- Формат: 32-символьная hex-строка (напр. `5c5b31d4b70e997ac188ad7723b395b4`)
- Хранение: SharedPreferences ключ `refresh_token`
- Обновление: происходит автоматически при запуске Avito, когда текущий JWT близок к истечению

### Fingerprint (заголовок `f`)

- Формат: `A2.{256+ hex символов}`
- Хранение: SharedPreferences ключ `fpx`
- Генерация: нативная библиотека `com.avito.security.libfp.FingerprintService` (VM-обфускация)
- **Невозможно сгенерировать программно** — только извлечь с рутованного устройства или через Frida
- Собирает: CPU info, Build.FINGERPRINT, Android ID, MAC-адреса
- Серверная валидация: формат и content проверяются

### Полная структура сессии

```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "5c5b31d4b70e997ac188ad7723b395b4",
  "session_data": {
    "device_id": "a8d7b75625458809",
    "fingerprint": "A2.a541fb18def1032c46e8ce9356bf78870fa9c764...",
    "remote_device_id": "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBc...android",
    "user_hash": "4c48533419806d790635e8565693e5c2",
    "user_id": 157920214,
    "cookies": {
      "1f_uid": "uuid",
      "u": "string",
      "v": "timestamp",
      "_avisc": "base64"
    }
  }
}
```

### Endpoint авторизации (для справки)

```
POST https://app.avito.ru/api/11/auth
Content-Type: application/x-www-form-urlencoded

login=+7XXXXXXXXXX&password=xxxxx&token=<firebase>&isSandbox=false&fid=<tracker_uid>
```

**Ответ (успех):**
```json
{
  "result": {
    "phash": "add7f675e4dd83c86e25df4b51ff713f",
    "refreshToken": "fd74bc392447ed35a52d6546d0e4034e",
    "session": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
    "signature": "afafafafafafafafafafafafafafafaf",
    "user": {
      "id": 427999413,
      "name": "mips",
      "phone": "+7***725-37-77",
      "userHashId": "17fa67c42a7531c898da1c4284ccfed4",
      "type": {"code": "private", "title": "Частное лицо"}
    }
  },
  "status": "ok"
}
```

**SMS верификация (TFA):**
```
POST https://app.avito.ru/api/2/tfa/auth
Content-Type: application/x-www-form-urlencoded

code=123456&flow=sms&fid=<tracker_uid>
```

**Visitor Generate:**
```
POST https://app.avito.ru/api/1/visitorGenerate
→ {"result": {"visitor": "kSCwY4Kj4HUfwZHG...android"}, "status": "ok"}
```

> **ВНИМАНИЕ:** Endpoint авторизации защищён QRATOR и требует firebase token. Мы НЕ используем его — вместо этого извлекаем токены из SharedPreferences.

---

## Блок 2: HTTP-заголовки и TLS

### Обязательные заголовки (все запросы к app.avito.ru)

```
User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)
X-Session: {JWT_TOKEN}
X-DeviceId: {device_id}                    # 16 hex chars
X-RemoteDeviceId: {remote_device_id}        # base64 строка
f: {fingerprint}                            # A2.{hex} ~400 chars
X-App: avito
X-Platform: android
X-AppVersion: 215.1
Content-Type: application/json
Cookie: sessid={JWT}; 1f_uid={uuid}; u={u_cookie}; v={timestamp}
```

### Дополнительные заголовки (присутствуют в оригинальном трафике)

```
X-Date: {unix_timestamp_seconds}
X-Geo: {lat};{lng};{accuracy};{timestamp}   # опционально
X-Supported-Features: helpcenter-form-46049
Accept-Encoding: zstd;q=1.0, gzip;q=0.8
AT-v: 1
Schema-Check: 0
```

### Откуда берутся данные

| Заголовок | Источник | Пример |
|-----------|----------|--------|
| JWT | SharedPreferences → `session` | `eyJhbGciOiJIUzUxMi...` |
| fingerprint | SharedPreferences → `fpx` | `A2.a541fb18def1...` |
| device_id | SharedPreferences → `device_id` | `a8d7b75625458809` |
| remote_device_id | SharedPreferences → `remote_device_id` | `kSCwY4Kj4HUf...` |
| user_hash | SharedPreferences → `user_hash` | `4c485334198...` (32 hex) |
| cookies | SharedPreferences → `1f_uid`, `u_cookie`, `v_cookie` | см. структуру сессии |

### TLS Impersonation

**Обязательно** использовать `curl_cffi` с `impersonate="chrome120"`:

```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session(impersonate="chrome120")
resp = session.post(url, headers=headers, json=payload)
```

Без TLS-имперсонации QRATOR блокирует запросы (определяет по JA3/JA3S fingerprint).

### Построение Cookie строки

```python
def build_cookie(session_data: dict) -> str:
    jwt = session_data["session_token"]
    cookies = session_data["cookies"]
    parts = [f"sessid={jwt}"]
    for key, value in cookies.items():
        parts.append(f"{key}={value}")
    return "; ".join(parts)
```

---

## Блок 3: Messenger HTTP REST API

**Base URL:** `https://app.avito.ru`
**Авторизация:** полный набор заголовков (см. Блок 2)
**Rate limit:** ~2 секунды между запросами, 429 → backoff 30 секунд

### 3.1 Получение списка каналов (чатов)

```
POST /api/1/messenger/getChannels
```

**Запрос:**
```json
{
  "category": 1,
  "filters": {},
  "limit": 30,
  "offsetTimestamp": null
}
```

| Параметр | Тип | Описание |
|----------|-----|----------|
| category | int | **1** = все каналы (РАБОТАЕТ). **0** = ошибка 500! **6** = избранные |
| limit | int | Макс 30 |
| offsetTimestamp | int/null | Пагинация: `sortingTimestamp` последнего канала |

**Ответ:**
```json
{
  "success": {
    "channels": [
      {
        "id": "u2i-gFdm0fc~KmiXS21tNQV_~g",
        "type": 2,
        "isRead": true,
        "unreadCount": 0,
        "users": [
          {"name": "Артём", "id": "68066a9daa4df0b3741fd41dff16e09a"},
          {"name": "РемАкс", "id": "4c48533419806d790635e8565693e5c2"}
        ],
        "lastMessage": {
          "body": {"text": {"text": "Договорились"}},
          "direction": 1,
          "type": 1
        },
        "context": {
          "item": {"title": "iPhone 12"}
        },
        "sortingTimestamp": 1768300000000
      }
    ],
    "hasMore": true
  }
}
```

**Пагинация:**
```
Page 1: offsetTimestamp = null
Page 2: offsetTimestamp = channels[-1].sortingTimestamp
...пока hasMore = false
```

Протестировано: корректно работает на ~3000 каналах.

### 3.2 Получение сообщений канала

```
POST /api/1/messenger/getUserVisibleMessages
```

**Запрос:**
```json
{
  "channelId": "u2i-xxx",
  "limit": 50,
  "before": null,
  "after": null
}
```

**Ответ:**
```json
{
  "success": {
    "messages": [
      {
        "id": "12f70ec959e9ff2975f6135e9ef251a5",
        "authorId": "4c48533419806d790635e8565693e5c2",
        "body": {
          "idempotencyKey": "uuid",
          "text": {"text": "Привет!"}
        },
        "channelId": "u2i-xxx",
        "createdAt": 1768299248468329563,
        "type": "text",
        "isFirstMessage": false
      }
    ]
  }
}
```

> **ВАЖНО:** Текст сообщения в HTTP REST — `body.text.text` (двойная вложенность). В WebSocket push — `body.text` (одинарная).

### 3.3 Отправка текстового сообщения

```
POST /api/1/messenger/sendTextMessage
```

**Запрос:**
```json
{
  "channelId": "u2i-xxx",
  "text": "Здравствуйте!",
  "idempotencyKey": "uuid-v4"
}
```

**Ответ:**
```json
{
  "success": {
    "message": {
      "id": "message_hash",
      "authorId": "user_hash",
      "body": {"text": {"text": "Здравствуйте!"}},
      "channelId": "u2i-xxx",
      "createdAt": 1768299248468329563
    }
  }
}
```

### 3.4 Получение канала по ID

```
POST /api/1/messenger/getChannelById
```

**Запрос:**
```json
{
  "category": 0,
  "channelId": "u2i-xxx"
}
```

### 3.5 Пометить каналы прочитанными

```
POST /api/1/messenger/readChats
```

**Запрос:**
```json
{
  "channelIds": ["u2i-xxx", "u2i-yyy"]
}
```

### Различие форматов HTTP REST vs WebSocket Push

| Поле | HTTP REST | WebSocket Push |
|------|-----------|----------------|
| Текст сообщения | `body.text.text` | `body.text` |
| ID автора | `authorId` | `fromUid` |
| Timestamp | `createdAt` | `created` |
| ID ключа | `idempotencyKey` | `randomId` |

---

## Блок 4: Messenger WebSocket JSON-RPC

### Подключение

**URL (все параметры ОБЯЗАТЕЛЬНЫ):**
```
wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}
```

> **КРИТИЧНО:** Без `id_version=v2` и `my_hash_id` — методы возвращают `Forbidden (-32043)`.

**TLS:** curl_cffi с `impersonate="chrome120"`

```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session(impersonate="chrome120")
ws = session.ws_connect(ws_url, headers=headers)
```

**Заголовки:** те же что и для HTTP REST (см. Блок 2)

### Инициализация сессии (сервер → клиент, первое сообщение)

```json
{
  "id": 1,
  "type": "session",
  "value": {
    "userId": 157920214,
    "serverTime": 1768223980574,
    "seq": "9233"
  }
}
```

### Формат JSON-RPC запроса

```json
{
  "id": <auto_increment>,
  "jsonrpc": "2.0",
  "method": "<method_name>",
  "params": { ... }
}
```

### Формат JSON-RPC ответа

**Успех:**
```json
{"jsonrpc": "2.0", "result": { ... }, "id": <request_id>}
```

**Ошибка:**
```json
{"jsonrpc": "2.0", "error": {"code": -32043, "message": "Forbidden"}, "id": <request_id>}
```

### 4.1 Методы — Каналы и чаты

#### avito.getChats.v5 — Список чатов

```json
{
  "method": "avito.getChats.v5",
  "params": {
    "limit": 30,
    "offsetTimestamp": null,
    "filters": {"excludeTags": ["p", "s"]}
  }
}
```

| Параметр | Тип | Описание |
|----------|-----|----------|
| limit | int | Макс 30 |
| offsetTimestamp | int/null | Пагинация по sortingTimestamp |
| filters.tags | string[] | Только: "p" (покупки), "s" (продажи) |
| filters.excludeTags | string[] | Исключить теги |

#### avito.getChatById.v3 — Чат по ID

```json
{"method": "avito.getChatById.v3", "params": {"channelId": "u2i-xxx"}}
```

#### avito.chatCreateByItemId.v2 — Создать чат по объявлению

```json
{
  "method": "avito.chatCreateByItemId.v2",
  "params": {"itemId": "123456789", "source": null, "extra": null, "xHash": null}
}
```

#### messenger.chatCreateByUserId.v2 — Создать чат с пользователем

```json
{"method": "messenger.chatCreateByUserId.v2", "params": {"opponentId": "user_hash"}}
```

### 4.2 Методы — Сообщения

#### messenger.history.v2 — История сообщений

```json
{
  "method": "messenger.history.v2",
  "params": {"channelId": "u2i-xxx", "limit": 100, "offsetMessageId": null}
}
```

#### avito.sendTextMessage.v2 — Отправка текста

```json
{
  "method": "avito.sendTextMessage.v2",
  "params": {
    "channelId": "u2i-xxx",
    "randomId": "uuid-v4",
    "text": "Текст сообщения",
    "templates": [],
    "quoteMessageId": null,
    "chunkIndex": null,
    "xHash": null,
    "initActionTimestamp": 1768224468487
  }
}
```

#### avito.sendImageMessage.v2 — Отправка изображения

```json
{
  "method": "avito.sendImageMessage.v2",
  "params": {"channelId": "u2i-xxx", "randomId": "uuid", "imageId": "50523524262.75f34c304e68"}
}
```

#### messenger.sendVoice — Голосовое сообщение

```json
{
  "method": "messenger.sendVoice",
  "params": {"channelId": "u2i-xxx", "fileId": "uuid", "voiceId": "uuid", "randomId": "uuid"}
}
```

#### messenger.sendVideo.v2 — Видео

```json
{
  "method": "messenger.sendVideo.v2",
  "params": {"channelId": "u2i-xxx", "fileId": "uuid", "videoId": "uuid", "randomId": "uuid"}
}
```

### 4.3 Методы — Статус и действия

#### messenger.sendTyping.v2 — Индикатор набора

```json
{"method": "messenger.sendTyping.v2", "params": {"channelId": "u2i-xxx", "userId": "user_hash"}}
```

#### messenger.readChats.v1 — Пометить прочитанным

```json
{"method": "messenger.readChats.v1", "params": {"channelIds": ["u2i-xxx"]}}
```

#### messenger.readChat — Прочитать до сообщения

```json
{"method": "messenger.readChat", "params": {"channelId": "u2i-xxx", "lastMessageTime": 1704067200000}}
```

#### messenger.getUnreadCount.v1 — Счётчик непрочитанных

```json
{"method": "messenger.getUnreadCount.v1", "params": {}}
```

### 4.4 Методы — Информация

#### messenger.getUsers.v2 — Информация о пользователях

```json
{"method": "messenger.getUsers.v2", "params": {"channelId": "u2i-xxx", "userIds": ["hash1", "hash2"]}}
```

#### messenger.getSettings.v2 — Настройки

```json
{"method": "messenger.getSettings.v2", "params": {"fields": ["promt_autoreplies_url"]}}
```

#### messenger.quickReplies.v1 — Быстрые ответы

```json
{"method": "messenger.quickReplies.v1", "params": {}}
```

#### suggest.getMessages — Подсказки

```json
{"method": "suggest.getMessages", "params": {"channelId": "u2i-xxx", "actualLastMessageId": "msg_id"}}
```

#### messenger.getLastActionTimes.v2 — Время последних действий

```json
{"method": "messenger.getLastActionTimes.v2", "params": {"channelIds": ["u2i-xxx"]}}
```

#### avito.getBodyImages — Изображения объявления в чате

```json
{"method": "avito.getBodyImages", "params": {"channelId": "u2i-xxx"}}
```

### 4.5 Ping (keepalive)

Отправлять каждые 25-30 секунд:

```json
{"method": "ping", "params": {}}
```

### 4.6 Push Events (сервер → клиент)

#### Message — Новое сообщение

```json
{
  "seq": "9269",
  "id": 3,
  "type": "Message",
  "type_v2": "messenger.Message",
  "value": {
    "id": "8550e1ed03edab7afdd44d657b7f1c13",
    "body": {"randomId": "uuid", "text": "Текст сообщения"},
    "channelId": "u2i-xxx",
    "type": "text",
    "created": 17682255249711911,
    "isDeleted": false,
    "isRead": false,
    "chatType": "u2i",
    "uid": "4c48533419806d790635e8565693e5c2",
    "fromUid": "b5b928d9b300d15526cf829b93962213"
  }
}
```

**Типы body по type:**

| type | Поля body | Пример |
|------|-----------|--------|
| text | `text`, `randomId` | `{"text": "Привет!", "randomId": "uuid"}` |
| image | `imageId`, `randomId` | `{"imageId": "50523524262.75f34c304e68", "randomId": "uuid"}` |
| voice | `voiceId`, `randomId` | `{"voiceId": "uuid", "randomId": "uuid"}` |
| location | `lat, lon, kind, title, text` | `{"lat": 46.36, "lon": 48.05, "kind": "house"}` |
| file | `fileId, name, sizeBytes` | `{"fileId": "uuid", "name": "file.xls", "sizeBytes": 1856512}` |

#### ChatTyping — Набирает сообщение

```json
{"type": "ChatTyping", "value": {"channelId": "u2i-xxx", "fromUid": "user_hash"}}
```

#### ChatRead — Чат прочитан

```json
{"type": "ChatRead", "value": {"channelId": "u2i-xxx"}}
```

#### ChannelUpdate — Обновление канала

```json
{"type": "ChannelUpdate", "value": {"channelId": "u2i-xxx", "updated": 17682255249711911}}
```

#### MessageDelete — Удаление сообщения

```json
{"type": "MessageDelete", "value": {"channelId": "u2i-xxx", "messageId": "msg_id"}}
```

---

## Блок 5: Поиск и объявления

**Base URL:** `https://app.avito.ru`
**Авторизация:** полный набор заголовков (см. Блок 2)

### 5.1 Поиск товаров

```
GET /api/11/items
```

**Параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| query | string | Поисковый запрос ("iPhone 12 Pro") |
| locationId | int | ID региона (621540 = вся Россия, 637640 = Москва) |
| priceMin | int | Минимальная цена |
| priceMax | int | Максимальная цена |
| withDelivery | bool | Только с Авито Доставкой |
| key | string | API ключ: `af0deccbgcgidddjgnvljitntccdduijhdinfgjgfjir` |
| limit | int | Кол-во результатов (макс 30) |
| page | int | Номер страницы |

**Ответ:**
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

### 5.2 Карточка товара

```
GET /api/19/items/{item_id}
```

> **БЛОКЕР:** Точный endpoint карточки товара не подтверждён. Необходимо перехватить через Frida запрос при открытии объявления. Пока используется заглушка.

**Ключевые поля для проверки:**
- Статус "зарезервирован" (`reserved`)
- Полное описание (`description`)
- Все фотографии (`images`)
- Информация о продавце (`seller`)

---

## Блок 6: IP-телефония (Call Tracking)

**Base URL:** `https://www.avito.ru`
**Авторизация:** только cookie `sessid` (БЕЗ fingerprint `f`)

### 6.1 История звонков

```
POST /web/1/calltracking-pro/history
```

**Запрос:**
```json
{
  "dateFrom": "2025-01-01",
  "dateTo": "2026-02-06",
  "limit": 50,
  "offset": 0,
  "sortingField": "createTime",
  "sortingDirection": "desc",
  "newOrRepeated": "all",
  "receivedOrMissed": "all",
  "showSpam": true,
  "itemFilters": {}
}
```

**Ответ:**
```json
{
  "result": {
    "items": [
      {
        "id": 1108478743,
        "caller": "+7 927 576-67-88",
        "receiver": "+7 917 170-80-77",
        "duration": "0:42",
        "waitingTime": "0:05",
        "hasRecord": true,
        "isNew": false,
        "isSpamTagged": false,
        "isCallback": false,
        "createTime": "2026-01-13T13:06:26+03:00",
        "item": {"id": 123456, "title": "iPhone 12"}
      }
    ],
    "total": 150
  },
  "status": "success"
}
```

**Пагинация:** `offset += limit` пока `offset < total`

### 6.2 Скачивание записи разговора

```
GET /web/1/calltracking-pro/audio?historyId={call_id}
```

Возвращает аудио-файл (MP3).

---

## Блок 7: Анти-бот защита (QRATOR)

### Что детектируется

1. **TLS Fingerprint (JA3/JA3S)** — отпечаток TLS handshake. OkHttp имеет отличный от curl fingerprint
2. **HTTP/2 Fingerprint** — порядок и параметры HTTP/2 фреймов
3. **Порядок заголовков** — все required headers должны быть
4. **Паттерны запросов** — timing, частота, порядок

### Симптомы блокировки

- HTTP 400: `"Пожалуйста, используйте приложение или авторизуйтесь через avito.ru"`
- Временная блокировка аккаунта

### Решение

- `curl_cffi` с `impersonate="chrome120"` — проходит QRATOR для messenger и search API
- Все обязательные заголовки должны быть (особенно `f`, `X-DeviceId`, `X-Session`)
- Соблюдать rate limit: ~2 сек между запросами
- При 429: backoff 30 секунд

### Что НЕ работает

- `requests` / `aiohttp` — блокируется по TLS fingerprint
- `curl_cffi` с `impersonate="okhttp4_android_13"` — частично работает
- Endpoint авторизации (`POST /api/11/auth`) — дополнительная защита, не обходится

### OkHttp Interceptors Chain (из jadx)

```
1. session_refresh.h      — управление сессией
2. captcha.interceptor.g  — обработка капчи
3. interceptor.Z0         — User-Agent
4. interceptor.g0         — основные заголовки (X-DeviceId, X-Session, f, и т.д.)
5. zstd.j                 — zstd сжатие
6. interceptor.x          — certificate pinning
7. interceptor.D          — X-Date заголовок
```

---

## Блок 8: Извлечение токенов (Root/Redroid)

### SharedPreferences — источник всех токенов

**Пути файла (по приоритету):**
```
1. /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
2. /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
3. /data/user_de/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Дополнительные файлы (альтернативные):**
```
4. /data/data/com.avito.android/shared_prefs/avito_auth_v2.xml
5. /data/data/com.avito.android/shared_prefs/auth_prefs.xml
6. /data/data/com.avito.android/shared_prefs/secure_prefs.xml
```

### Формат XML

```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMi...</string>
    <string name="fpx">A2.a541fb18def1032c46e8ce9...</string>
    <string name="refresh_token">5c5b31d4b70e997ac188ad7723b395b4</string>
    <string name="device_id">a8d7b75625458809</string>
    <string name="remote_device_id">kSCwY4Kj4HUfwZHG...</string>
    <string name="user_hash">9b82afc1ab1e2419981f7a9d9d2b6af9</string>
    <long name="fpx_calc_time" value="1768297821046" />
</map>
```

### Маппинг XML → Поля сессии

| XML name | Поле сессии | Fallback names | Обязательное |
|----------|-------------|----------------|:------------:|
| `session` | session_token | `token` | да |
| `fpx` | fingerprint | `f`, `fingerprint` | да |
| `refresh_token` | refresh_token | — | нет |
| `device_id` | device_id | — | нет |
| `remote_device_id` | remote_device_id | — | нет |
| `user_hash` | user_hash | — | нет |
| `1f_uid` | cookies["1f_uid"] | — | нет |
| `u_cookie` | cookies["u"] | — | нет |
| `v_cookie` | cookies["v"] | — | нет |

### Чтение через Redroid (Docker)

```bash
docker exec redroid cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

### Чтение через рутованный Android

```bash
# Magisk mount master
su -mm -c cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml

# Стандартный su
su -c cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

### Обновление токена

Avito автоматически обновляет JWT при запуске приложения (если токен близок к истечению).

```bash
# Запуск Avito в Redroid
docker exec redroid am start -n com.avito.android/.MainActivity

# Запуск Avito на Android
adb shell am start -n com.avito.android/.MainActivity
```

**Алгоритм обновления:**
```
1. Проверить exp JWT → вычислить hours_left
2. Если hours_left > 2ч → ничего не делать
3. Если 0 < hours_left < 2ч:
   a. Запустить Avito (am start)
   b. Ждать 30 секунд (приложение инициализируется, обновляет токен)
   c. Перечитать SharedPreferences
   d. Если exp изменился → токен обновлён → синхронизировать
4. Если hours_left <= 0 (истёк):
   a. Запустить Avito
   b. Ждать 60 секунд
   c. Перечитать SharedPreferences
   d. Если обновился → sync. Если нет → ошибка.
```

---

## Коды ошибок

| Код | Сообщение | Причина | Решение |
|-----|-----------|---------|---------|
| -32043 | Forbidden | Нет `id_version=v2` / `my_hash_id` в WS URL | Добавить параметры |
| -32601 | Method not found | Неверное имя/версия метода | Проверить документацию |
| 500 | Internal error | `category=0` в getChannels | Использовать `category=1` |
| 401 | Unauthorized | JWT истёк | Обновить токен |
| 429 | Too many requests | Rate limit | Backoff 30 секунд |
| 400 | QRATOR block | Неверный TLS fingerprint / заголовки | curl_cffi + chrome120 |

---

## Формат Channel ID

```
u2i-{base64_encoded_id}
```

Пример: `u2i-PJIRB81Ps9iX81CSTNUgPw`

- `u2i` = user-to-item (чат по объявлению)

---

## Ключевые особенности (ловушки)

1. **category=0 → 500.** Всегда использовать `category=1`
2. **Текст сообщений в разных API.** HTTP: `body.text.text`. WS push: `body.text`
3. **WS URL без параметров → Forbidden.** Обязательно `id_version=v2` + `my_hash_id`
4. **TLS без impersonate → блок.** Только curl_cffi с chrome120
5. **Fingerprint нельзя генерировать.** Только извлечь из SharedPreferences
6. **Timestamps в миллисекундах** (Unix epoch * 1000)
7. **randomId / idempotencyKey = UUID v4** для дедупликации
8. **Ping каждые 25 сек** чтобы WS не закрылся
