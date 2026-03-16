# Part 7: Messenger — API Reference

## Транспорты

Part 7 использует **три API** для коммуникации с Avito:

| API | URL | Протокол | Назначение |
|-----|-----|----------|------------|
| WebSocket | `wss://socket.avito.ru/socket` | JSON-RPC 2.0 | Real-time: приём/отправка сообщений |
| HTTP REST | `https://app.avito.ru/api/1/messenger/*` | REST JSON | Batch: списки каналов, история |
| Call Tracking | `https://www.avito.ru/web/1/calltracking-pro/*` | REST JSON | Телефония: звонки, записи |

---

## Аутентификация

### Заголовки для всех запросов (HTTP + WebSocket)

```
Cookie: sessid={JWT}; 1f_uid={1f_uid}; u={u_cookie}; v={v_cookie}
X-Session: {JWT}
X-DeviceId: {device_id}
X-RemoteDeviceId: {remote_device_id}
f: {fingerprint}
X-App: avito
X-Platform: android
X-AppVersion: 215.1
User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)
Content-Type: application/json
```

### Откуда берутся данные

| Поле | Источник | Пример |
|------|----------|--------|
| JWT | `GET /api/v1/session` → `session_token` | `eyJhbGciOiJIUzUxMi...` |
| fingerprint | `GET /api/v1/session` → `fingerprint` | `A2.a541fb18def1...` |
| device_id | `GET /api/v1/session` → `device_id` | `a8d7b75625458809` |
| remote_device_id | `GET /api/v1/session` → `remote_device_id` | `kSCwY4Kj4HU...` |
| user_hash | `GET /api/v1/session` → `user_hash` | `4c485334198...` (32 hex) |
| user_id | JWT payload → `u` | `157920214` |
| cookies | `GET /api/v1/session` → `cookies` | `{1f_uid, u, v}` |

### TLS Fingerprint

**Обязательно:** `curl_cffi` с `impersonate="chrome120"`.

```python
from curl_cffi import requests as curl_requests
session = curl_requests.Session(impersonate="chrome120")
```

Без TLS-имперсонации Avito блокирует запросы.

---

## WebSocket JSON-RPC API

### Подключение

**URL (КРИТИЧНО — все параметры обязательны):**
```
wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}
```

Без `id_version=v2` и `my_hash_id` — методы возвращают `Forbidden (-32043)`.

**Инициализация (сервер → клиент):**
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

### Формат запроса

```json
{
  "id": <auto_increment>,
  "jsonrpc": "2.0",
  "method": "<method_name>",
  "params": { ... }
}
```

### Формат ответа (успех)

```json
{
  "jsonrpc": "2.0",
  "result": { ... },
  "id": <request_id>
}
```

### Формат ответа (ошибка)

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32043,
    "message": "Forbidden"
  },
  "id": <request_id>
}
```

---

### Методы

#### 1. avito.getChats.v5 — Список чатов

```json
{
  "method": "avito.getChats.v5",
  "params": {
    "limit": 30,
    "offsetTimestamp": null,
    "filters": {
      "excludeTags": ["p", "s"]
    }
  }
}
```

| Параметр | Тип | Описание |
|----------|-----|----------|
| `limit` | int | Макс 30 |
| `offsetTimestamp` | int\|null | Пагинация: `sortingTimestamp` последнего чата |
| `filters.tags` | string[] | Только: `"p"` (покупки), `"s"` (продажи) |
| `filters.excludeTags` | string[] | Исключить теги |

#### 2. avito.getChatById.v3 — Чат по ID

```json
{
  "method": "avito.getChatById.v3",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw"
  }
}
```

#### 3. messenger.history.v2 — История сообщений

```json
{
  "method": "messenger.history.v2",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw",
    "limit": 100,
    "offsetMessageId": null
  }
}
```

| Параметр | Тип | Описание |
|----------|-----|----------|
| `channelId` | string | ID канала |
| `limit` | int | Макс 100 |
| `offsetMessageId` | string\|null | Пагинация по ID сообщения |

#### 4. avito.sendTextMessage.v2 — Отправка текста

```json
{
  "method": "avito.sendTextMessage.v2",
  "params": {
    "channelId": "u2i-xxx",
    "randomId": "adc96106-9bd2-450e-b968-db5cedc9b584",
    "text": "Здравствуйте!",
    "templates": [],
    "quoteMessageId": null,
    "chunkIndex": null,
    "xHash": null,
    "initActionTimestamp": 1768224468487
  }
}
```

| Параметр | Тип | Обязательный | Описание |
|----------|-----|:------------:|----------|
| `channelId` | string | ✅ | ID канала |
| `randomId` | string | ✅ | UUID v4 для дедупликации |
| `text` | string | ✅ | Текст сообщения |
| `initActionTimestamp` | int | ❌ | Timestamp начала набора |
| `quoteMessageId` | string | ❌ | ID цитируемого сообщения |
| `templates` | array | ❌ | Шаблоны |
| `chunkIndex` | int | ❌ | Порядок в chunk |
| `xHash` | string | ❌ | Хеш операции |

#### 5. avito.sendImageMessage.v2 — Отправка изображения

```json
{
  "method": "avito.sendImageMessage.v2",
  "params": {
    "channelId": "u2i-xxx",
    "randomId": "uuid",
    "imageId": "50523524262.75f34c304e68433e918a20d6cc9c3250",
    "quoteMessageId": null,
    "chunkIndex": null
  }
}
```

#### 6. messenger.sendVoice — Голосовое сообщение

```json
{
  "method": "messenger.sendVoice",
  "params": {
    "channelId": "u2i-xxx",
    "fileId": "file_uuid",
    "voiceId": "voice_uuid",
    "randomId": "uuid",
    "quoteMessageId": null,
    "chunkIndex": null
  }
}
```

#### 7. messenger.sendVideo.v2 — Видео

```json
{
  "method": "messenger.sendVideo.v2",
  "params": {
    "channelId": "u2i-xxx",
    "fileId": "file_uuid",
    "videoId": "video_uuid",
    "randomId": "uuid",
    "quoteMessageId": null,
    "chunkIndex": null
  }
}
```

#### 8. avito.chatCreateByItemId.v2 — Создать чат по объявлению

```json
{
  "method": "avito.chatCreateByItemId.v2",
  "params": {
    "itemId": "123456789",
    "source": null,
    "extra": null,
    "xHash": null
  }
}
```

#### 9. messenger.chatCreateByUserId.v2 — Создать чат с пользователем

```json
{
  "method": "messenger.chatCreateByUserId.v2",
  "params": {
    "opponentId": "user_hash"
  }
}
```

#### 10. messenger.sendTyping.v2 — Индикатор набора

```json
{
  "method": "messenger.sendTyping.v2",
  "params": {
    "channelId": "u2i-xxx",
    "userId": "4c48533419806d790635e8565693e5c2",
    "initActionTimestamp": 1768225500619
  }
}
```

#### 11. messenger.readChats.v1 — Пометить прочитанным

```json
{
  "method": "messenger.readChats.v1",
  "params": {
    "channelIds": ["u2i-xxx", "u2i-yyy"]
  }
}
```

#### 12. messenger.readChat — Прочитать до сообщения

```json
{
  "method": "messenger.readChat",
  "params": {
    "channelId": "u2i-xxx",
    "lastMessageTime": 1704067200000
  }
}
```

#### 13. messenger.getUnreadCount.v1 — Счётчик непрочитанных

```json
{
  "method": "messenger.getUnreadCount.v1",
  "params": {}
}
```

#### 14. messenger.getUsers.v2 — Информация о пользователях

```json
{
  "method": "messenger.getUsers.v2",
  "params": {
    "channelId": "u2i-xxx",
    "userIds": ["user_hash1", "user_hash2"]
  }
}
```

#### 15. messenger.getSettings.v2 — Настройки

```json
{
  "method": "messenger.getSettings.v2",
  "params": {
    "fields": ["promt_autoreplies_url"]
  }
}
```

#### 16. messenger.quickReplies.v1 — Быстрые ответы

```json
{
  "method": "messenger.quickReplies.v1",
  "params": {}
}
```

#### 17. suggest.getMessages — Подсказки

```json
{
  "method": "suggest.getMessages",
  "params": {
    "channelId": "u2i-xxx",
    "actualLastMessageId": "5c3405114ffbbc8dc5c50143a37e3aab"
  }
}
```

#### 18. messenger.getLastActionTimes.v2 — Время последних действий

```json
{
  "method": "messenger.getLastActionTimes.v2",
  "params": {
    "channelIds": ["u2i-xxx"]
  }
}
```

#### 19. avito.getBodyImages — Изображения объявления

```json
{
  "method": "avito.getBodyImages",
  "params": {
    "channelId": "u2i-xxx"
  }
}
```

#### 20. ping — Keep-alive

```json
{
  "method": "ping",
  "params": {}
}
```

Отправлять каждые 30 секунд.

---

## Push Events (Server → Client)

### Message — Новое сообщение

```json
{
  "seq": "9269",
  "id": 3,
  "type": "Message",
  "type_v2": "messenger.Message",
  "value": {
    "id": "8550e1ed03edab7afdd44d657b7f1c13",
    "body": {
      "randomId": "js:09bd0f3e-61b1-464b-a575-e56a9af8b68b",
      "text": "Текст сообщения"
    },
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw",
    "type": "text",
    "created": 17682255249711911,
    "isDeleted": false,
    "isRead": false,
    "isSpam": false,
    "chatType": "u2i",
    "uid": "4c48533419806d790635e8565693e5c2",
    "fromUid": "b5b928d9b300d15526cf829b93962213",
    "initActionTimestamp": 1768225524440
  }
}
```

**Типы body по type:**

| type | Поля body | Пример |
|------|-----------|--------|
| `text` | `text`, `randomId` | `{"text": "Привет!", "randomId": "uuid"}` |
| `image` | `imageId`, `randomId` | `{"imageId": "50523524262.75f34c304e68", "randomId": "uuid"}` |
| `voice` | `voiceId`, `randomId` | `{"voiceId": "0571ea17-b177-4331", "randomId": "uuid"}` |
| `location` | `lat, lon, kind, title, text` | `{"lat": 46.36, "lon": 48.05, "kind": "house"}` |
| `file` | `fileId, name, sizeBytes` | `{"fileId": "uuid", "name": "file.xls", "sizeBytes": 1856512}` |

### ChatTyping — Индикатор набора

```json
{
  "id": 2,
  "type": "ChatTyping",
  "value": {
    "channelId": "u2i-xxx",
    "fromUid": "b5b928d9b300d15526cf829b93962213",
    "initActionTimestamp": 1768225500619
  }
}
```

### ChatRead — Чат прочитан

```json
{
  "type": "ChatRead",
  "value": {
    "channelId": "u2i-xxx"
  }
}
```

### ChannelUpdate — Обновление канала

```json
{
  "type": "ChannelUpdate",
  "value": {
    "channelId": "u2i-xxx",
    "updated": 17682255249711911
  }
}
```

### MessageDelete — Удаление сообщения

```json
{
  "type": "MessageDelete",
  "value": {
    "channelId": "u2i-xxx",
    "messageId": "8550e1ed03edab7afdd44d657b7f1c13"
  }
}
```

---

## HTTP REST API

Base URL: `https://app.avito.ru`

### POST /api/1/messenger/getChannels

```json
{
  "category": 1,
  "filters": {},
  "limit": 30,
  "offsetTimestamp": null
}
```

**ВАЖНО:** `category=0` возвращает 500! Использовать `category=1`.

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
          {"name": "Артём", "id": "68066a9daa4df0b3"},
          {"name": "РемАкс", "id": "4c48533419806d79"}
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
...until hasMore = false
```

### POST /api/1/messenger/getUserVisibleMessages

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
        "id": "12f70ec959e9ff29",
        "authorId": "4c48533419806d79",
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

**ВАЖНО:** Текст в `body.text.text` (двойная вложенность, отличается от WebSocket push).

### POST /api/1/messenger/sendTextMessage

```json
{
  "channelId": "u2i-xxx",
  "text": "Здравствуйте!",
  "idempotencyKey": "uuid-v4"
}
```

### POST /api/1/messenger/getChannelById

```json
{
  "category": 0,
  "channelId": "u2i-xxx"
}
```

### POST /api/1/messenger/readChats

```json
{
  "channelIds": ["u2i-xxx"]
}
```

---

## IP Telephony (Call Tracking)

Base URL: `https://www.avito.ru`
**Auth:** только cookie `sessid` (без fingerprint)

### POST /web/1/calltracking-pro/history

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
  }
}
```

**Пагинация:** `offset += limit` пока `offset < total`.

### GET /web/1/calltracking-pro/audio

```
GET /web/1/calltracking-pro/audio?historyId={call_id}
```

Response: аудио-файл (MP3).

---

## Коды ошибок

| Код | Сообщение | Причина | Решение |
|-----|-----------|---------|---------|
| `-32043` | Forbidden | Нет `id_version=v2` / `my_hash_id` | Добавить в URL |
| `-32601` | Method not found | Неверное имя метода | Проверить версию метода |
| `500` | Internal error | `category=0` в getChannels | Использовать `category=1` |
| `401` | Unauthorized | JWT истёк | Refresh через Backend |
| `429` | Too many requests | Rate limit | Backoff 30 сек |

---

## Channel ID Format

```
u2i-{base64_encoded_id}
```

Пример: `u2i-PJIRB81Ps9iX81CSTNUgPw`

- `u2i` = user-to-item (чат по объявлению)
- После `-` = Base64-encoded уникальный ID

---

## Важные особенности

1. **Текст сообщения в разных API:**
   - HTTP REST: `body.text.text` (двойная вложенность)
   - WebSocket push: `body.text` (одинарная)

2. **`category` в getChannels:**
   - `0` → ошибка 500
   - `1` → все каналы (рабочий вариант)
   - `6` → только избранные

3. **Timestamps:** Все в миллисекундах (Unix epoch).

4. **`randomId`:** UUID v4 для дедупликации отправленных сообщений.

5. **`idempotencyKey`:** UUID v4 для HTTP API (аналог randomId).

6. **Ping:** Отправлять каждые 30 секунд чтобы WebSocket не закрылся.

7. **`seq`:** Sequence number в push events для упорядочивания.
