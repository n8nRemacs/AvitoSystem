# Avito Messenger API v2

## Обзор

Avito Messenger использует **WebSocket JSON-RPC 2.0** протокол для real-time коммуникации.

## WebSocket Connection

### Endpoint
```
wss://socket.avito.ru/socket?use_seq=true&app_name=android&...
```

### Headers
```
Cookie: sessid=<JWT_TOKEN>
X-Session: <JWT_TOKEN>
X-DeviceId: <DEVICE_UUID>
X-App: avito
X-Platform: android
X-AppVersion: 215.1
```

### Инициализация сессии

После подключения сервер отвечает:
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

---

## JSON-RPC Методы

### 1. Получение списка чатов

**Метод:** `avito.getChats.v5`

```json
{
  "id": 5,
  "jsonrpc": "2.0",
  "method": "avito.getChats.v5",
  "params": {
    "limit": 30,
    "filters": {
      "excludeTags": ["p", "s"]
    }
  }
}
```

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| limit | int | Количество чатов (макс 30) |
| offsetTimestamp | int | Пагинация - timestamp последнего чата |
| filters.tags | array | Показать только с тегами: "p" (покупки), "s" (продажи) |
| filters.excludeTags | array | Исключить теги |

---

### 2. Получение чата по ID

**Метод:** `avito.getChatById.v3`

```json
{
  "id": 10,
  "jsonrpc": "2.0",
  "method": "avito.getChatById.v3",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw"
  }
}
```

---

### 3. Получение истории сообщений

**Метод:** `messenger.history.v2`

```json
{
  "id": 15,
  "jsonrpc": "2.0",
  "method": "messenger.history.v2",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw",
    "limit": 100
  }
}
```

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| channelId | string | ID канала/чата |
| limit | int | Количество сообщений |
| offsetMessageId | string | Для пагинации - ID последнего сообщения |

---

### 4. Отправка текстового сообщения

**Метод:** `avito.sendTextMessage.v2`

```json
{
  "id": 37,
  "jsonrpc": "2.0",
  "method": "avito.sendTextMessage.v2",
  "params": {
    "channelId": "u2i-zwvj~9_pEgzdJ8XtWCWK4Q",
    "randomId": "adc96106-9bd2-450e-b968-db5cedc9b584",
    "text": "Текст сообщения",
    "initActionTimestamp": 1768224468487
  }
}
```

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| channelId | string | ID канала |
| randomId | string | UUID для дедупликации |
| text | string | Текст сообщения |
| initActionTimestamp | int | Timestamp начала набора |

---

### 5. Отправка индикатора набора

**Метод:** `messenger.sendTyping.v2`

```json
{
  "id": 25,
  "jsonrpc": "2.0",
  "method": "messenger.sendTyping.v2",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw",
    "userId": "4c48533419806d790635e8565693e5c2"
  }
}
```

---

### 6. Пометка чатов как прочитанных

**Метод:** `messenger.readChats.v1`

```json
{
  "id": 50,
  "jsonrpc": "2.0",
  "method": "messenger.readChats.v1",
  "params": {
    "channelIds": ["u2i-PJIRB81Ps9iX81CSTNUgPw"]
  }
}
```

---

### 7. Получение счётчика непрочитанных

**Метод:** `messenger.getUnreadCount.v1`

```json
{
  "id": 8,
  "jsonrpc": "2.0",
  "method": "messenger.getUnreadCount.v1",
  "params": {}
}
```

---

### 8. Быстрые ответы

**Метод:** `messenger.quickReplies.v1`

```json
{
  "id": 12,
  "jsonrpc": "2.0",
  "method": "messenger.quickReplies.v1",
  "params": {}
}
```

---

### 9. Подсказки сообщений

**Метод:** `suggest.getMessages`

```json
{
  "id": 38,
  "jsonrpc": "2.0",
  "method": "suggest.getMessages",
  "params": {
    "channelId": "u2i-zwvj~9_pEgzdJ8XtWCWK4Q",
    "actualLastMessageId": "5c3405114ffbbc8dc5c50143a37e3aab"
  }
}
```

---

### 10. Настройки мессенджера

**Метод:** `messenger.getSettings.v2`

```json
{
  "id": 7,
  "jsonrpc": "2.0",
  "method": "messenger.getSettings.v2",
  "params": {
    "fields": ["promt_autoreplies_url"]
  }
}
```

---

### 11. Время последних действий

**Метод:** `messenger.getLastActionTimes.v2`

```json
{
  "id": 20,
  "jsonrpc": "2.0",
  "method": "messenger.getLastActionTimes.v2",
  "params": {
    "channelIds": ["u2i-PJIRB81Ps9iX81CSTNUgPw"]
  }
}
```

---

### 12. Изображения объявления

**Метод:** `avito.getBodyImages`

```json
{
  "id": 30,
  "jsonrpc": "2.0",
  "method": "avito.getBodyImages",
  "params": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw"
  }
}
```

---

### 13. Ping/Keep-alive

**Метод:** `ping`

```json
{
  "id": 100,
  "jsonrpc": "2.0",
  "method": "ping",
  "params": {}
}
```

---

## Channel ID Format

Формат ID канала: `u2i-<BASE64_ENCODED_ID>`

Например: `u2i-PJIRB81Ps9iX81CSTNUgPw`

---

## Теги чатов

| Тег | Описание |
|-----|----------|
| p | Покупки (purchase) |
| s | Продажи (sale) |

---

## Аутентификация

### JWT Token Structure

Session token - JWT с алгоритмом HS512:

```json
{
  "exp": 1768310379,
  "iat": 1768223979,
  "u": 157920214,
  "p": 28109599,
  "s": "f404f1a23a88b3fd7d95adebbf6edb9f.1768223979",
  "h": "BASE64_HASH",
  "d": "a8d7b75625458809",
  "pl": "android",
  "extra": null
}
```

**Поля:**
| Поле | Описание |
|------|----------|
| u | User ID |
| d | Device ID |
| pl | Platform (android/ios/web) |
| s | Session hash |
| exp | Expiration timestamp |
| iat | Issued at timestamp |

---

## Необходимые данные для клиента

1. **sessid** - JWT session token
2. **user_id** - ID пользователя
3. **user_hash** - Hash пользователя (для typing)
4. **device_id** - UUID устройства
5. **refresh_token** - Для обновления сессии

---

## Push События WebSocket (Server -> Client)

Сервер отправляет push-события через WebSocket. У них нет `id` в JSON-RPC формате.

### Message - Новое сообщение

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
    "delivered": 17682255249711911,
    "chatType": "u2i",
    "channel": {
      "updated": 17682255249711911
    },
    "uid": "4c48533419806d790635e8565693e5c2",
    "fromUid": "b5b928d9b300d15526cf829b93962213",
    "initActionTimestamp": 1768225524440
  }
}
```

**Поля value:**
| Поле | Описание |
|------|----------|
| id | ID сообщения |
| body.text | Текст (для type=text) |
| body.imageId | ID картинки (для type=image) |
| body.voiceId | ID голосового (для type=voice) |
| body.randomId | UUID для дедупликации |
| channelId | ID канала/чата |
| type | Тип: text, image, voice |
| created | Timestamp создания |
| isRead | Прочитано ли |
| fromUid | Hash отправителя |
| uid | Твой user hash |
| chatType | u2i (user to item) |

**Типы сообщений:**
| type | body поля | Описание |
|------|-----------|----------|
| text | text | Текстовое сообщение |
| image | imageId | Картинка (формат: itemId.hash) |
| voice | voiceId | Голосовое сообщение (UUID) |
| location | lat, lon, title, kind, text | Геолокация |
| file | fileId, name, sizeBytes | Прикреплённый файл |

**Примеры body для разных типов:**

```json
// text
{"text": "Привет!", "randomId": "uuid"}

// image
{"imageId": "50523524262.75f34c304e68433e918a20d6cc9c3250", "randomId": "uuid"}

// voice
{"voiceId": "0571ea17-b177-4331-8208-b37edecb6cb4", "randomId": "uuid"}

// location
{"lat": 46.36, "lon": 48.05, "kind": "house", "title": "Астрахань", "text": "Адрес"}

// file
{"fileId": "d809e7d2-f511-4b69-beb1-4ff40f12dbcb", "name": "file.xls", "sizeBytes": 1856512}
```

---

### ChatTyping - Индикатор набора

```json
{
  "id": 2,
  "type": "ChatTyping",
  "type_v2": "",
  "value": {
    "channelId": "u2i-PJIRB81Ps9iX81CSTNUgPw",
    "initActionTimestamp": 1768225500619,
    "uid": "4c48533419806d790635e8565693e5c2",
    "fromUid": "b5b928d9b300d15526cf829b93962213"
  }
}
```

---

### Session - Инициализация сессии

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

---

### Другие типы событий

- `ChatRead` - Чат прочитан
- `ChannelUpdate` - Обновление канала
- `MessageDelete` - Удаление сообщения
- `Presence` - Онлайн статус

---

## Пример Python клиента

```python
import websocket
import json
import uuid

class AvitoMessenger:
    def __init__(self, sessid, device_id):
        self.sessid = sessid
        self.device_id = device_id
        self.request_id = 0

    def connect(self):
        ws_url = f"wss://socket.avito.ru/socket?use_seq=true&app_name=android"
        headers = {
            "Cookie": f"sessid={self.sessid}",
            "X-Session": self.sessid,
            "X-DeviceId": self.device_id
        }
        self.ws = websocket.WebSocket()
        self.ws.connect(ws_url, header=headers)

    def send_rpc(self, method, params=None):
        self.request_id += 1
        msg = {
            "id": self.request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        self.ws.send(json.dumps(msg))
        return self.ws.recv()

    def get_chats(self, limit=30):
        return self.send_rpc("avito.getChats.v5", {
            "limit": limit,
            "filters": {"excludeTags": ["p", "s"]}
        })

    def send_message(self, channel_id, text):
        return self.send_rpc("avito.sendTextMessage.v2", {
            "channelId": channel_id,
            "randomId": str(uuid.uuid4()),
            "text": text,
            "initActionTimestamp": int(time.time() * 1000)
        })
```
