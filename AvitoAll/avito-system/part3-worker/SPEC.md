# Part 3: Avito Monitor Worker

## Обзор

Фоновый процесс, который мониторит Avito по заданным поискам, фильтрует зарезервированные, запускает AI-анализ и отправляет автоприветствия.

**Стек:** Python 3.11+ / asyncio / curl_cffi / aiohttp / OpenRouter
**Папка:** `part3-worker/`

## Структура файлов

```
part3-worker/
├── SPEC.md
├── requirements.txt
├── .env.example
└── src/
    ├── worker.py              # Точка входа, главный цикл
    ├── config.py              # Настройки из .env
    ├── backend_client.py      # HTTP-клиент к Backend API
    ├── avito_api.py           # Клиент к Avito API (поиск, карточка)
    ├── avito_messenger.py     # WebSocket клиент мессенджера Avito
    ├── analyzer.py            # AI-анализ через OpenRouter
    ├── auto_message.py        # Автоприветствие продавцу
    └── tracker.py             # Дедупликация (локальный SQLite)
```

## .env.example

```env
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-sonnet-4
CHECK_INTERVAL=60
MESSAGE_RATE_LIMIT=30
AUTO_GREET=true
```

## Главный цикл (worker.py)

```
При запуске:
  1. Получить токены с Backend API
  2. Получить список активных поисков
  3. Получить AI-правила

Цикл (каждые CHECK_INTERVAL секунд):
  1. Обновить токены если нужно (проверить exp)
  2. Обновить список поисков и правил
  3. Для каждого активного поиска:
     a. GET /api/11/items (Avito API)
     b. filter_new() — дедупликация
     c. Для каждого нового товара:
        - Запросить карточку товара
        - Если зарезервирован → пропустить
        - AI-анализ (описание + фото + правила)
        - Сохранить результат → POST /api/v1/items (Backend)
        - Если OK и AUTO_GREET:
          → create_chat + send_message (Avito Messenger)
          → POST /api/v1/dialogs (Backend)
  4. Очистка старых записей (>7 дней)
```

## Компоненты

### backend_client.py — HTTP к Backend API

```python
class BackendClient:
    def __init__(self, url: str, api_key: str)

    async def get_session(self) -> dict          # GET /api/v1/session
    async def get_searches(self) -> list[dict]   # GET /api/v1/searches?enabled=true
    async def get_rules(self) -> list[dict]      # GET /api/v1/rules?enabled=true
    async def save_item(self, item: dict)        # POST /api/v1/items
    async def save_dialog(self, dialog: dict)    # POST /api/v1/dialogs
```

### avito_api.py — Клиент Avito HTTP API

Перенос логики из существующего `avito_search_client.py` с изменениями:
- Токены получает из BackendClient, а не из файла
- Добавить метод `get_item_card(item_id)` — запрос карточки товара
- Добавить проверку поля резервации

```python
class AvitoApi:
    def __init__(self, session: dict)

    def update_session(self, session: dict)       # Обновить токены
    def search(self, query, price_min, price_max, delivery, location_id) -> list[Item]
    def get_item_card(self, item_id: str) -> ItemCard | None
    def is_reserved(self, item_card: dict) -> bool
```

**Avito API endpoints:**
- Поиск: `GET https://app.avito.ru/api/11/items`
- Карточка: `GET https://app.avito.ru/api/{version}/items/{item_id}` (endpoint уточняется через Frida)
- Обязательные заголовки:
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
- Rate limiting: 2с между запросами, backoff на 429

**Параметры поиска:**
```
query = строка из Search
locationId = 621540 (Вся Россия)
priceMin / priceMax = из Search
withDelivery = true/false из Search
key = af0deccbgcgidddjgnvljitntccdduijhdinfgjgfjir
limit = 30
page = 1
```

### avito_messenger.py — WebSocket мессенджер

Перенос из существующего кода. WebSocket JSON-RPC 2.0.

```python
class AvitoMessenger:
    def __init__(self, session: dict)

    async def connect()
    async def disconnect()
    async def create_chat_by_item(item_id: str) -> str | None  # → channel_id
    async def send_message(channel_id: str, text: str) -> bool
```

**URL:** `wss://socket.avito.ru/messenger?seq=0&id_version=v2&my_hash_id={user_hash}`

### analyzer.py — AI-анализ

```python
class Analyzer:
    def __init__(self, api_key: str, model: str)

    async def analyze(
        title: str,
        description: str,
        image_urls: list[str],
        rules: list[str]       # Тексты активных правил из Backend
    ) -> AnalysisResult
```

**AnalysisResult:**
```python
@dataclass
class AnalysisResult:
    verdict: str       # OK | RISK | SKIP
    score: int         # 1-10
    summary: str       # Краткое описание
    defects: list[str] # Найденные дефекты
```

**System prompt включает:**
- Базовые инструкции анализа
- Все активные rules из Backend API (красные флаги)

### auto_message.py — Автоприветствие

```python
class AutoMessenger:
    def __init__(self, messenger: AvitoMessenger, rate_limit: int = 30)

    async def send_greeting(item_id: str, template: str) -> str | None  # → channel_id
```

- Rate limit: `MESSAGE_RATE_LIMIT` секунд между сообщениями
- Проверка дубликатов через Backend API (item.greeted)

### tracker.py — Дедупликация

Локальный SQLite для отслеживания уже виденных товаров.

```python
class Tracker:
    def __init__(self, db_path: str = "tracker.db")

    def filter_new(self, query: str, items: list) -> list
    def cleanup(self, max_age_days: int = 7)
```

## БЛОКЕР: Endpoint карточки товара

Для определения статуса "Товар зарезервирован" нужно:
1. Перехватить через Frida запрос при открытии объявления в Avito
2. Определить endpoint и поле со статусом
3. Реализовать `get_item_card()` и `is_reserved()`

**До этого:** метод `is_reserved()` возвращает `False` (заглушка).

## Зависимости (requirements.txt)

```
curl_cffi>=0.7.0
aiohttp>=3.9.0
openai>=1.0.0
python-dotenv>=1.0.0
```

## Запуск

```bash
cd part3-worker
pip install -r requirements.txt
cp .env.example .env
python src/worker.py
```
