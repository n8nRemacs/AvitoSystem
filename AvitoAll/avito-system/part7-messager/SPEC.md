# Part 7: Messenger (Полнофункциональный Avito Messenger)

## Обзор

Серверный клиент Avito Messenger с двумя транспортами: **WebSocket JSON-RPC 2.0** (real-time) и **HTTP REST API** (batch-операции). Получает токены из Backend API (Part 1), поддерживает постоянное подключение, принимает и отправляет сообщения, управляет чатами.

**Стек:** Python 3.11+ / asyncio / curl_cffi / websockets
**Папка:** `part7-messager/`
**Работает на:** сервере (Homelab или VPS)

## Отличие от Part 3 (Worker)

| | Part 3: Worker | Part 7: Messenger |
|--|---------------|-------------------|
| Назначение | Поиск товаров + AI-анализ | Полноценный мессенджер |
| Сообщения | Только авто-приветствие | Полный диалог (отправка, приём, история) |
| WebSocket | Нет (только HTTP) | Постоянное подключение, real-time |
| Чаты | Создание чата по itemId | Все операции: список, история, создание, чтение |
| Медиа | Нет | Изображения, голосовые, видео, файлы |
| Уведомления | Через Part 4 (Telegram) | Собственные push-events + callback в Backend |
| Телефония | Нет | История звонков + скачивание записей |

## Архитектура

```
                    Backend API (Part 1)
                    ┌─────────────┐
                    │  GET /session│ ← токены от Part 5/6
                    │  POST /dialogs│
                    │  POST /messages│
                    └──────┬──────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Part 7: Messenger                         │
│                                                              │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  messenger.py   │    │  ws_client.py                │    │
│  │  (Главный цикл) │───▶│  WebSocket JSON-RPC          │    │
│  │                  │    │  wss://socket.avito.ru       │    │
│  │                  │    │  • Real-time сообщения       │    │
│  │                  │    │  • Push events               │    │
│  │                  │    │  • Typing, read, ping        │    │
│  │                  │    └──────────────────────────────┘    │
│  │                  │                                        │
│  │                  │    ┌──────────────────────────────┐    │
│  │                  │───▶│  http_client.py              │    │
│  │                  │    │  HTTP REST API               │    │
│  │                  │    │  app.avito.ru/api/1/messenger│    │
│  │                  │    │  • Batch: каналы, сообщения  │    │
│  │                  │    │  • Отправка сообщений        │    │
│  │                  │    │  • Пагинация                 │    │
│  │                  │    └──────────────────────────────┘    │
│  │                  │                                        │
│  │                  │    ┌──────────────────────────────┐    │
│  │                  │───▶│  call_tracker.py             │    │
│  │                  │    │  IP Telephony                │    │
│  │                  │    │  /web/1/calltracking-pro     │    │
│  │                  │    │  • История звонков           │    │
│  │                  │    │  • Скачивание записей        │    │
│  │                  │    └──────────────────────────────┘    │
│  └─────────────────┘                                        │
│                                                              │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  event_handler  │    │  backend_client.py           │    │
│  │  .py            │    │  HTTP к Backend API (Part 1) │    │
│  │  Обработка      │───▶│  • Синхронизация диалогов    │    │
│  │  push events    │    │  • Сохранение сообщений      │    │
│  │  от Avito WS    │    │  • Получение токенов         │    │
│  └─────────────────┘    └──────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
   Avito Servers                Backend (Part 1)
   socket.avito.ru              localhost:8080
   app.avito.ru
   www.avito.ru
```

## Структура проекта

```
part7-messager/
├── SPEC.md
├── API.md
├── TESTING.md
├── requirements.txt
├── .env.example
└── src/
    ├── messenger.py          # Точка входа, главный цикл
    ├── config.py             # Настройки из .env
    ├── ws_client.py          # WebSocket JSON-RPC клиент
    ├── http_client.py        # HTTP REST клиент (app.avito.ru)
    ├── call_tracker.py       # IP-телефония (история + записи)
    ├── event_handler.py      # Обработчик push events от WebSocket
    ├── backend_client.py     # HTTP клиент к Backend API (Part 1)
    ├── session_manager.py    # Управление токенами + auto-refresh
    └── models.py             # Pydantic-модели (Channel, Message, etc.)
```

## .env.example

```env
# Backend API (Part 1)
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026

# WebSocket
WS_PING_INTERVAL=30
WS_RECONNECT_DELAY=5
WS_MAX_RECONNECT_ATTEMPTS=10

# HTTP API
HTTP_REQUEST_DELAY=2
HTTP_BACKOFF_ON_429=30

# Call Tracking (опционально)
CALL_TRACKING_ENABLED=false
CALL_RECORDING_DIR=./recordings

# Logging
LOG_LEVEL=INFO
```

## Компоненты

### config.py

```python
class Config:
    backend_url: str
    backend_api_key: str
    ws_ping_interval: int = 30          # секунд
    ws_reconnect_delay: int = 5         # секунд
    ws_max_reconnect: int = 10
    http_request_delay: float = 2.0     # секунд между запросами
    http_backoff_on_429: int = 30       # секунд при rate limit
    call_tracking_enabled: bool = False
    call_recording_dir: str = "./recordings"
    log_level: str = "INFO"
```

### models.py

```python
@dataclass
class SessionData:
    session_token: str          # JWT (HS512)
    fingerprint: str            # Заголовок "f"
    device_id: str
    remote_device_id: str
    user_hash: str              # Для WebSocket URL
    user_id: int                # Из JWT payload
    cookies: dict               # 1f_uid, u, v, _avisc
    expires_at: int             # Unix timestamp

@dataclass
class Channel:
    id: str                     # "u2i-xxx"
    type: int
    is_read: bool
    unread_count: int
    users: list[ChannelUser]
    last_message: Message | None
    item: ItemContext | None     # Связанное объявление
    sorting_timestamp: int

@dataclass
class Message:
    id: str
    channel_id: str
    author_id: str
    text: str | None
    type: str                   # text, image, voice, location, file
    created_at: int
    is_read: bool
    is_deleted: bool
    body: dict                  # Полное тело (для медиа)

@dataclass
class CallRecord:
    id: int
    caller: str
    receiver: str
    duration: str
    has_record: bool
    is_spam: bool
    create_time: str            # ISO 8601
    item_id: int | None
    item_title: str | None
```

### session_manager.py

Управляет токенами: получает из Backend, следит за exp, запрашивает refresh.

```python
class SessionManager:
    def __init__(self, backend_client: BackendClient)

    async def get_session(self) -> SessionData
    # Возвращает текущую сессию
    # Если exp < 1 час → запрашивает свежую из Backend

    async def refresh_if_needed(self) -> bool
    # Проверяет время до истечения
    # Если < 1 час → GET /api/v1/session → обновляет локально

    def build_headers(self) -> dict
    # Собирает все заголовки для Avito API:
    # Cookie, X-Session, X-DeviceId, X-RemoteDeviceId, f,
    # X-App, X-Platform, X-AppVersion, User-Agent, Content-Type

    def build_ws_url(self) -> str
    # wss://socket.avito.ru/socket?use_seq=true&app_name=android
    #   &id_version=v2&my_hash_id={user_hash}
```

**Заголовки для Avito API:**
```
Cookie: sessid={JWT}; 1f_uid={uuid}; u={u_cookie}; v={timestamp}
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

### ws_client.py

WebSocket JSON-RPC 2.0 клиент с auto-reconnect.

```python
class AvitoWebSocket:
    def __init__(self, session_manager: SessionManager)

    async def connect(self) -> dict
    # 1. Получить сессию из SessionManager
    # 2. Построить URL с id_version=v2 и my_hash_id
    # 3. curl_cffi Session(impersonate="chrome120")
    # 4. ws_connect(url, headers)
    # 5. Получить session init → вернуть {userId, serverTime, seq}

    async def disconnect(self)

    async def send_rpc(self, method: str, params: dict) -> dict
    # Отправить JSON-RPC запрос, ожидать ответ по id

    async def recv(self) -> dict | None
    # Получить следующее сообщение/event

    async def ping(self)
    # Отправить {"method": "ping", "params": {}}

    # === Методы-обёртки ===

    async def get_chats(self, limit=30, offset=None) -> list[Channel]
    # avito.getChats.v5

    async def get_chat_by_id(self, channel_id: str) -> Channel
    # avito.getChatById.v3

    async def get_history(self, channel_id: str, limit=100, offset_id=None) -> list[Message]
    # messenger.history.v2

    async def send_message(self, channel_id: str, text: str) -> dict
    # avito.sendTextMessage.v2 (randomId = uuid4)

    async def send_typing(self, channel_id: str, user_hash: str)
    # messenger.sendTyping.v2

    async def read_chats(self, channel_ids: list[str])
    # messenger.readChats.v1

    async def get_unread_count(self) -> int
    # messenger.getUnreadCount.v1

    async def create_chat_by_item(self, item_id: str) -> Channel
    # avito.chatCreateByItemId.v2

    async def create_chat_by_user(self, user_hash: str) -> Channel
    # messenger.chatCreateByUserId.v2

    async def get_users(self, channel_id: str, user_ids: list[str]) -> list
    # messenger.getUsers.v2

    async def get_settings(self) -> dict
    # messenger.getSettings.v2

    async def get_quick_replies(self) -> list
    # messenger.quickReplies.v1

    async def get_suggestions(self, channel_id: str, last_msg_id: str) -> list
    # suggest.getMessages

    async def get_body_images(self, channel_id: str) -> list
    # avito.getBodyImages
```

**TLS Fingerprint:**
```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session(impersonate="chrome120")
ws = session.ws_connect(url, headers=headers)
```

**Критично:** Без `impersonate="chrome120"` Avito блокирует подключение.

**Критично:** URL должен содержать `id_version=v2` и `my_hash_id={user_hash}`, иначе методы возвращают `Forbidden (-32043)`.

### http_client.py

HTTP REST клиент для batch-операций (когда WebSocket избыточен).

```python
class AvitoHttpClient:
    def __init__(self, session_manager: SessionManager)

    # Все запросы через curl_cffi с impersonate="chrome120"

    async def get_channels(self, limit=30, offset=None) -> list[Channel]
    # POST /api/1/messenger/getChannels
    # category=1 (НЕ 0 — вернёт 500!)

    async def get_all_channels(self) -> list[Channel]
    # Пагинация по sortingTimestamp до hasMore=false

    async def get_channel_by_id(self, channel_id: str) -> Channel
    # POST /api/1/messenger/getChannelById

    async def get_messages(self, channel_id: str, limit=50) -> list[Message]
    # POST /api/1/messenger/getUserVisibleMessages
    # ВАЖНО: текст в body.text.text (вложенный)

    async def send_message(self, channel_id: str, text: str) -> Message
    # POST /api/1/messenger/sendTextMessage
    # idempotencyKey = uuid4

    async def read_chats(self, channel_ids: list[str])
    # POST /api/1/messenger/readChats
```

**Различие форматов ответов:**

| Поле | HTTP REST | WebSocket Push |
|------|-----------|----------------|
| Текст сообщения | `body.text.text` | `body.text` |
| ID автора | `authorId` | `fromUid` |
| Timestamp | `createdAt` | `created` |

### call_tracker.py

IP-телефония — история звонков и записи разговоров.

```python
class CallTracker:
    def __init__(self, session_manager: SessionManager)

    # Использует browser cookie (sessid), без fingerprint

    async def get_call_history(self, date_from: str, date_to: str,
                                limit=50, offset=0) -> list[CallRecord]
    # POST /web/1/calltracking-pro/history

    async def get_all_calls(self, date_from: str, date_to: str) -> list[CallRecord]
    # Пагинация по offset до offset >= total

    async def download_recording(self, call_id: int, output_dir: str) -> str | None
    # GET /web/1/calltracking-pro/audio?historyId={call_id}
    # Сохраняет в {output_dir}/{call_id}.mp3
    # Возвращает путь или None если нет записи
```

### event_handler.py

Обработчик push-events от WebSocket.

```python
class EventHandler:
    def __init__(self, backend_client: BackendClient)

    async def handle(self, event: dict)
    # Роутер по event["type"]:

    async def on_message(self, value: dict)
    # type: "Message" / "messenger.Message"
    # → Сохранить в Backend (POST /api/v1/messages)
    # → Callback (для Telegram бота / Worker)

    async def on_typing(self, value: dict)
    # type: "ChatTyping"
    # → Логирование

    async def on_chat_read(self, value: dict)
    # type: "ChatRead"
    # → Обновить статус в Backend

    async def on_channel_update(self, value: dict)
    # type: "ChannelUpdate"
    # → Обновить канал в Backend

    async def on_message_delete(self, value: dict)
    # type: "MessageDelete"
    # → Пометить удалённым в Backend

    async def on_presence(self, value: dict)
    # type: "Presence"
    # → Логирование онлайн-статуса
```

**Push event types:**

| type | type_v2 | Описание |
|------|---------|----------|
| `session` | — | Инициализация сессии (после connect) |
| `Message` | `messenger.Message` | Новое сообщение |
| `ChatTyping` | — | Собеседник печатает |
| `ChatRead` | — | Чат прочитан |
| `ChannelUpdate` | — | Обновление канала |
| `MessageDelete` | — | Сообщение удалено |
| `Presence` | — | Онлайн-статус |

### backend_client.py

HTTP-клиент к Backend API (Part 1).

```python
class BackendClient:
    def __init__(self, url: str, api_key: str)

    async def get_session(self) -> SessionData
    # GET /api/v1/session

    async def save_dialog(self, dialog: dict) -> bool
    # POST /api/v1/dialogs

    async def update_dialog(self, dialog_id: str, data: dict) -> bool
    # PUT /api/v1/dialogs/{id}

    async def save_message(self, message: dict) -> bool
    # POST /api/v1/messages

    async def get_new_items(self, since: int) -> list
    # GET /api/v1/items/new?since={timestamp}
    # Для auto-greet: новые товары с verdict=OK
```

### messenger.py (Главный цикл)

```python
async def main():
    config = Config.from_env()
    backend = BackendClient(config.backend_url, config.backend_api_key)
    session_mgr = SessionManager(backend)
    ws = AvitoWebSocket(session_mgr)
    http = AvitoHttpClient(session_mgr)
    events = EventHandler(backend)
    calls = CallTracker(session_mgr) if config.call_tracking_enabled else None

    # 1. Подключиться к WebSocket
    session_info = await ws.connect()
    log.info(f"Connected: userId={session_info['userId']}, seq={session_info['seq']}")

    # 2. Запустить параллельные задачи
    await asyncio.gather(
        ws_listener(ws, events),       # Слушать push events
        ping_loop(ws),                 # Keepalive каждые 30 сек
        session_refresh_loop(session_mgr, ws),  # Проверка токена каждые 15 мин
    )

async def ws_listener(ws, events):
    """Бесконечный цикл приёма push events."""
    while True:
        try:
            event = await ws.recv()
            if event:
                await events.handle(event)
        except ConnectionClosed:
            log.warning("WebSocket disconnected, reconnecting...")
            await ws.connect()

async def ping_loop(ws):
    """Keepalive каждые WS_PING_INTERVAL секунд."""
    while True:
        await asyncio.sleep(config.ws_ping_interval)
        await ws.ping()

async def session_refresh_loop(session_mgr, ws):
    """Проверка токена каждые 15 минут, reconnect при обновлении."""
    while True:
        await asyncio.sleep(900)
        refreshed = await session_mgr.refresh_if_needed()
        if refreshed:
            log.info("Session refreshed, reconnecting WebSocket...")
            await ws.disconnect()
            await ws.connect()
```

## Типы сообщений

### Отправка

| Тип | Метод (WS) | Метод (HTTP) | Параметры |
|-----|-----------|-------------|-----------|
| Текст | `avito.sendTextMessage.v2` | `POST /sendTextMessage` | channelId, text, randomId |
| Изображение | `avito.sendImageMessage.v2` | — | channelId, imageId, randomId |
| Голосовое | `messenger.sendVoice` | — | channelId, fileId, voiceId, randomId |
| Видео | `messenger.sendVideo.v2` | — | channelId, fileId, videoId, randomId |

### Приём (push events)

| body.type | Поля | Описание |
|-----------|------|----------|
| `text` | `text` | Текстовое сообщение |
| `image` | `imageId` | Картинка (`itemId.hash`) |
| `voice` | `voiceId` | Голосовое (UUID) |
| `location` | `lat, lon, title, kind, text` | Геолокация |
| `file` | `fileId, name, sizeBytes` | Файл |

## Rate Limiting

| API | Лимит | Действие при 429 |
|-----|-------|-----------------|
| HTTP REST | 2 сек между запросами | Backoff 30 сек |
| WebSocket RPC | Нет жёсткого лимита | — |
| Отправка сообщений | ~30 в час (практический) | Пауза |

## Обработка ошибок

| Код | Сообщение | Причина | Действие |
|-----|-----------|---------|----------|
| `-32043` | Forbidden | Нет `id_version=v2` / `my_hash_id` в URL | Исправить URL |
| `-32601` | Method not found | Неверное имя метода | Проверить версию |
| `500` | Internal error | `category=0` в HTTP getChannels | Использовать `category=1` |
| `401` | Unauthorized | Токен истёк | Refresh из Backend |

## Зависимости (requirements.txt)

```
curl_cffi>=0.6.0
aiohttp>=3.9.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

## Запуск

```bash
cd part7-messager
pip install -r requirements.txt
cp .env.example .env
# Убедиться что Backend (Part 1) запущен и токены доступны
python src/messenger.py
```

## Интеграция с другими частями

```
Part 5/6 (Token sources) ──▶ Part 1 (Backend) ──▶ Part 7 (Messenger)
                                                        │
Part 3 (Worker) ──── verdict=OK ──▶ Part 7 ────────────┤ Отправка приветствий
                                                        │
Part 4 (Telegram) ◀──── push events ───────────────────┘ Уведомления о сообщениях
```

- **Part 1** → предоставляет токены через `GET /api/v1/session`
- **Part 3** → может вызвать Part 7 для отправки авто-приветствий
- **Part 4** → получает уведомления о новых сообщениях через Backend
- **Part 5/6** → поставляют свежие токены в Backend
