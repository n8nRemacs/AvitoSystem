# Part 7: Messenger — План тестирования

## Инструменты

- **pytest** + **pytest-asyncio** — async unit-тесты
- **unittest.mock / AsyncMock** — мок WebSocket, HTTP
- **aioresponses** — мок HTTP-запросов к Avito API
- **pytest-cov** — покрытие кода

## Структура тестов

```
part7-messager/
└── tests/
    ├── conftest.py                   # Фикстуры: mock session, WS, HTTP
    ├── test_ws_client.py             # WebSocket JSON-RPC клиент
    ├── test_http_client.py           # HTTP REST клиент
    ├── test_event_handler.py         # Обработка push events
    ├── test_session_manager.py       # Управление токенами
    ├── test_backend_client.py        # HTTP к Backend API
    ├── test_call_tracker.py          # IP-телефония
    ├── test_models.py                # Pydantic-модели
    ├── test_messenger.py             # Главный цикл
    └── fixtures/
        ├── session_data.json         # Тестовая сессия
        ├── ws_session_init.json      # Ответ WebSocket session
        ├── ws_message_push.json      # Push event: Message
        ├── ws_typing_push.json       # Push event: ChatTyping
        ├── channels_response.json    # HTTP getChannels ответ
        ├── messages_response.json    # HTTP getUserVisibleMessages ответ
        └── calls_response.json       # Call tracking history ответ
```

## Фикстуры

### session_data.json
```json
{
  "session_token": "eyJhbGciOiJIUzUxMiJ9.eyJleHAiOjk5OTk5OTk5OTksInUiOjEyMzQ1NiwiZCI6InRlc3QiLCJoIjoiaGFzaCIsInBsIjoiYW5kcm9pZCJ9.sig",
  "fingerprint": "A2.test_fingerprint_hex",
  "device_id": "test_device_001",
  "remote_device_id": "test_remote_device",
  "user_hash": "4c48533419806d790635e8565693e5c2",
  "user_id": 123456,
  "cookies": {"1f_uid": "test-uid", "u": "test-u", "v": "123"},
  "expires_at": 9999999999
}
```

### ws_session_init.json
```json
{
  "id": 1,
  "type": "session",
  "value": {
    "userId": 123456,
    "serverTime": 1768223980574,
    "seq": "100"
  }
}
```

### ws_message_push.json
```json
{
  "seq": "101",
  "id": 3,
  "type": "Message",
  "type_v2": "messenger.Message",
  "value": {
    "id": "msg_test_001",
    "body": {"text": "Тестовое сообщение", "randomId": "uuid-test"},
    "channelId": "u2i-test_channel",
    "type": "text",
    "created": 1768300000000,
    "isDeleted": false,
    "isRead": false,
    "fromUid": "sender_hash",
    "uid": "receiver_hash"
  }
}
```

## Unit-тесты

### test_models.py

| Тест | Ожидание |
|------|----------|
| SessionData из валидного JSON | Все поля заполнены |
| SessionData — build_headers() | 9 заголовков, Cookie содержит sessid |
| SessionData — build_ws_url() | URL содержит id_version=v2 и my_hash_id |
| Channel из ответа getChats | id, users, lastMessage корректны |
| Message из HTTP ответа | Текст из body.text.text |
| Message из WS push | Текст из body.text |
| CallRecord из ответа history | Все поля, включая item |
| Channel ID формат | Начинается с "u2i-" |

### test_ws_client.py

| Тест | Ожидание |
|------|----------|
| `connect()` — успех | Получает session init (userId, seq) |
| `connect()` — URL содержит id_version=v2 | Параметр в URL |
| `connect()` — URL содержит my_hash_id | user_hash в URL |
| `connect()` — использует impersonate="chrome120" | curl_cffi сессия |
| `send_rpc()` — корректный JSON-RPC формат | id auto-increment, jsonrpc="2.0" |
| `get_chats()` | Метод avito.getChats.v5, limit=30 |
| `get_chats()` с пагинацией | offsetTimestamp передаётся |
| `get_chat_by_id()` | Метод avito.getChatById.v3 |
| `get_history()` | Метод messenger.history.v2, limit=100 |
| `get_history()` с пагинацией | offsetMessageId передаётся |
| `send_message()` | Метод avito.sendTextMessage.v2, randomId=UUID |
| `send_message()` — randomId уникален | Каждый вызов — новый UUID |
| `send_typing()` | Метод messenger.sendTyping.v2 |
| `read_chats()` | Метод messenger.readChats.v1, channelIds массив |
| `get_unread_count()` | Метод messenger.getUnreadCount.v1 |
| `create_chat_by_item()` | Метод avito.chatCreateByItemId.v2 |
| `create_chat_by_user()` | Метод messenger.chatCreateByUserId.v2 |
| `ping()` | Метод ping, params={} |
| Ошибка -32043 (Forbidden) | Логирование, переподключение |
| Ошибка -32601 (Method not found) | Логирование |
| ConnectionClosed | Auto-reconnect |
| Timeout на recv | Не crash, продолжает |

### test_http_client.py

| Тест | Ожидание |
|------|----------|
| `get_channels()` — category=1 | НЕ category=0 |
| `get_channels()` — парсинг ответа | Список Channel объектов |
| `get_channels()` — пагинация по sortingTimestamp | Корректный offsetTimestamp |
| `get_all_channels()` — hasMore=true | Продолжает пагинацию |
| `get_all_channels()` — hasMore=false | Останавливается |
| `get_messages()` — текст в body.text.text | Двойная вложенность парсится |
| `send_message()` — idempotencyKey | UUID v4 в запросе |
| `read_chats()` | channelIds массив |
| Ответ 500 | Result.failure, логирование |
| Ответ 401 | Trigger session refresh |
| Ответ 429 | Backoff 30 сек, retry |
| Delay между запросами | ≥ 2 сек (config.http_request_delay) |
| Заголовки содержат fingerprint | Заголовок "f" присутствует |
| Заголовки содержат все cookies | Cookie строка полная |
| impersonate="chrome120" | curl_cffi сессия |

### test_event_handler.py

| Тест | Ожидание |
|------|----------|
| Event type=Message, type=text | on_message вызван, текст из body.text |
| Event type=Message, type=image | on_message вызван, imageId из body |
| Event type=Message, type=voice | on_message вызван, voiceId из body |
| Event type=Message, type=location | on_message вызван, lat/lon из body |
| Event type=Message, type=file | on_message вызван, fileId/name из body |
| Event type=ChatTyping | on_typing вызван, channelId + fromUid |
| Event type=ChatRead | on_chat_read вызван |
| Event type=ChannelUpdate | on_channel_update вызван |
| Event type=MessageDelete | on_message_delete вызван |
| Event type=Presence | on_presence вызван |
| Event type=session | Пропуск (не ошибка) |
| Неизвестный type | Логирование warning |
| on_message → backend.save_message() | Вызван с корректными данными |
| on_chat_read → backend.update_dialog() | Вызван с корректными данными |
| Backend недоступен | Логирование, не crash |

### test_session_manager.py

| Тест | Ожидание |
|------|----------|
| `get_session()` — первый вызов | Запрос к Backend API |
| `get_session()` — кеш валиден | Без запроса к Backend |
| `get_session()` — exp < 1ч | Запрос свежей сессии из Backend |
| `refresh_if_needed()` — > 1ч | false (не нужен refresh) |
| `refresh_if_needed()` — < 1ч | true, новая сессия получена |
| `build_headers()` — все 9 заголовков | Cookie, X-Session, X-DeviceId, X-RemoteDeviceId, f, X-App, X-Platform, X-AppVersion, User-Agent |
| `build_ws_url()` | Содержит id_version=v2, my_hash_id, use_seq=true |
| Backend недоступен | Exception с понятным сообщением |
| Токен в Backend тоже истёк | Логирование ошибки |

### test_backend_client.py

| Тест | Ожидание |
|------|----------|
| `get_session()` — 200 | SessionData парсится |
| `get_session()` — 500 | Exception |
| `save_dialog()` — 200 | True |
| `save_message()` — 200 | True |
| `update_dialog()` — 200 | True |
| Заголовок X-Api-Key | Присутствует |

### test_call_tracker.py

| Тест | Ожидание |
|------|----------|
| `get_call_history()` — парсинг ответа | Список CallRecord |
| `get_call_history()` — пагинация | offset увеличивается |
| `get_all_calls()` — до total | Все записи |
| `download_recording()` — hasRecord=true | Файл сохранён .mp3 |
| `download_recording()` — hasRecord=false | None |
| Авторизация только cookie sessid | Без fingerprint |

### test_messenger.py (главный цикл)

| Тест | Ожидание |
|------|----------|
| Запуск → connect → session init | Логирование userId, seq |
| ws_listener получает Message | EventHandler.on_message вызван |
| ws_listener — ConnectionClosed | Reconnect |
| ping_loop — каждые 30 сек | ws.ping() вызывается |
| session_refresh_loop — каждые 15 мин | session_mgr.refresh_if_needed() |
| session_refresh_loop — refresh=true | ws.disconnect() + ws.connect() |
| session_refresh_loop — refresh=false | Без reconnect |

## Интеграционные тесты (с реальным Avito)

⚠️ Требуют валидные токены в Backend.

| Тест | Ожидание |
|------|----------|
| WebSocket connect | Session init с userId |
| getChats.v5 | Список каналов (≥1) |
| history.v2 | Список сообщений |
| sendTextMessage.v2 → recv Message | Сообщение отправлено и получено |
| sendTyping.v2 | Нет ошибки |
| readChats.v1 | Нет ошибки |
| HTTP getChannels | Каналы с category=1 |
| HTTP getUserVisibleMessages | body.text.text содержит текст |
| Пагинация каналов (>30) | hasMore + offsetTimestamp работают |
| ping keepalive (5 мин) | Соединение не рвётся |
| Call tracking history | Список звонков (если есть) |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все unit-тесты зелёные | 100% |
| Покрытие ws_client.py | ≥ 85% |
| Покрытие http_client.py | ≥ 85% |
| Покрытие event_handler.py | ≥ 90% |
| Покрытие session_manager.py | ≥ 90% |
| Покрытие models.py | ≥ 95% |
| Нет обращений к реальному Avito в unit-тестах | 0 |

## Метрики

| Метрика | Цель |
|---------|------|
| WebSocket connect | < 3 сек |
| send_rpc() latency | < 500 мс |
| HTTP request latency | < 2 сек |
| Event handling (on_message) | < 50 мс |
| Session refresh | < 2 сек |
| Reconnect time | < 10 сек |
| Memory usage (idle) | < 50 MB |
| Ping interval | 30 сек ± 1 сек |
| Пагинация 3000 каналов | < 5 мин |

## Запуск

```bash
cd part7-messager
pip install pytest pytest-asyncio pytest-cov aioresponses
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Только unit-тесты (быстро, без сети)
```bash
pytest tests/ -v -m "not integration"
```

### Интеграционные (требуют токены)
```bash
BACKEND_URL=http://localhost:8080 BACKEND_API_KEY=avito_sync_key_2026 \
  pytest tests/ -v -m integration
```
