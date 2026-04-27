# avito-xapi / src / workers

**Назначение:** Всё взаимодействие с Avito — HTTP REST, WebSocket JSON-RPC, управление сессиями, парсинг токенов, rate limiting. Ядро шлюза.

**Статус:** working. Ключевая папка для V1.

---

## Файлы

- `base_client.py` — `BaseAvitoClient`: curl_cffi Session с Chrome120 fingerprint, сборка 12+ обязательных заголовков Avito (UA, X-Session, X-DeviceId, fingerprint, Cookie, X-Date…), TokenBucket rate limiter
- `http_client.py` — `AvitoHttpClient(BaseAvitoClient)`: все HTTP REST методы (getChannels, getUserVisibleMessages, sendMessage, поиск, звонки). Методы `async` по сигнатуре, внутри **синхронный** curl_cffi — намеренно
- `ws_client.py` — `AvitoWsClient`: WebSocket JSON-RPC 2.0 к `wss://socket.avito.ru/socket`. Синхронный recv в фоновом треде, пинг каждые 25с, reconnect до 5 попыток
- `ws_manager.py` — `WsManager` (singleton): per-tenant TenantConnection, fan-out событий WS → SSE подписчикам через `asyncio.Queue` + `loop.call_soon_threadsafe()`
- `session_reader.py` — `SessionData` dataclass + `load_active_session(tenant_id)`: читает активную сессию из Supabase `avito_sessions`
- `token_monitor.py` — генерация алертов по TTL JWT токена (expired / critical <10мин / warning <30мин)
- `jwt_parser.py` — парсинг Avito JWT (HS512, без верификации), извлечение `user_id`, `exp`, вычисление `time_left()`
- `rate_limiter.py` — `TokenBucket`: async `wait_and_acquire()`, настраивается через `settings.rate_limit_rps` / `rate_limit_burst`
- `browser_auth.py` — Playwright headless Chromium для авторизации в Avito через реальный браузер. Скриншоты стримятся на фронт через WS. После логина — извлечение cookies+токенов в Supabase

---

## Критически важно

- **Не заменять** `curl_cffi` на `httpx` / `aiohttp` — Avito блокирует запросы с неправильным TLS fingerprint через QRATOR
- `ws_manager` инициализируется один раз в `lifespan()` с event loop. Не создавать второй экземпляр
- `session_reader` читает из Supabase синхронно через кастомный httpx QueryBuilder
- Avito JWT живёт ровно **24 часа** (HS512). `token_monitor` даёт warning за 30мин, critical за 10мин

---

## Связано с ТЗ V1

Раздел 4.3 — avito_client / avito-mcp. Методы из `http_client.py` (search, get_listing) — прямые кандидаты в MCP tools `avito_search` и `avito_get_listing`.
