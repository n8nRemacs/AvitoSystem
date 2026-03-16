# Avito SmartFree - TODO

## Статусы
- 🔴 Критично - блокирует запуск
- 🟡 Важно - нужно для production
- 🟢 Улучшение - можно отложить
- ⚪ Техдолг - рефакторинг/тесты

---

## 🔴 Критично

### [ ] SMS интеграция для регистрации
**Файл:** `token-farm/registration.py` (создать)

Сейчас регистрация аккаунтов требует ручного ввода SMS кода. Нужна автоматизация.

**Варианты:**
1. **SMS-activate API** - автоматическая покупка номеров
   ```python
   # Пример интеграции
   async def get_sms_code(phone: str) -> str:
       async with httpx.AsyncClient() as client:
           resp = await client.get(
               "https://api.sms-activate.org/stubs/handler_api.php",
               params={"api_key": API_KEY, "action": "getStatus", "id": order_id}
           )
           return parse_code(resp.text)
   ```

2. **Webhook + Telegram** - уведомление админу, ручной ввод
   ```python
   # В telegram_bot.py
   @router.message(Command("code"))
   async def enter_code(message: Message, state: FSMContext):
       code = message.text.split()[1]
       await complete_registration(code)
   ```

**Оценка:** 4-8 часов

---

### [ ] Тестирование Redroid на ARM
**Файл:** `token-farm/docker-compose.yml`

Redroid не запускается на x86. Нужно протестировать на реальном ARM сервере.

**Шаги:**
1. Заказать Hetzner CAX11 (€4/мес) или Oracle Ampere (бесплатно)
2. Установить kernel modules:
   ```bash
   modprobe binder_linux devices="binder,hwbinder,vndbinder"
   modprobe ashmem_linux
   ```
3. Запустить `docker-compose up`
4. Проверить ADB подключение: `adb connect localhost:5555`
5. Установить Avito APK: `adb install avito.apk`

**Оценка:** 2-4 часа

---

### [ ] Интеграция AvitoClient ↔ TelegramBot
**Файлы:** `mcp-server/mcp_manager.py`, `mcp-server/telegram_bot.py`

Сейчас компоненты работают изолированно. Нужно связать:

1. **Получение чатов в боте:**
   ```python
   # telegram_bot.py
   async def show_chats_callback(callback: CallbackQuery):
       # Получить клиент из pool
       client = mcp_manager.get_client_for_user(callback.from_user.id)
       channels = await client.get_channels()
       # Отобразить в inline keyboard
   ```

2. **Отправка сообщений:**
   ```python
   # telegram_bot.py
   @router.message(F.text)
   async def forward_to_avito(message: Message):
       client = mcp_manager.get_client_for_user(message.from_user.id)
       await client.send_message(channel_id, message.text)
   ```

3. **Получение уведомлений:**
   ```python
   # mcp_manager.py - в on_message callback
   async def handle_avito_message(account_id, msg):
       tg_users = await get_telegram_users_for_account(account_id)
       for user in tg_users:
           await bot.send_message(user.telegram_id, format_message(msg))
   ```

**Оценка:** 4-6 часов

---

## 🟡 Важно

### [ ] Proxy Manager
**Файл:** `token-farm/proxy_manager.py` (создать)

```python
class ProxyManager:
    """Управление пулом прокси"""

    async def get_proxy(self, proxy_type: str = "mobile") -> Optional[Proxy]:
        """Получить здоровый прокси"""

    async def mark_failed(self, proxy_id: UUID) -> None:
        """Пометить прокси как неработающий"""

    async def health_check_all(self) -> None:
        """Проверить все прокси"""

    async def rotate(self) -> Proxy:
        """Получить следующий прокси из ротации"""
```

**Оценка:** 3-4 часа

---

### [ ] Полный Registration Flow
**Файлы:** `token-farm/registration.py`, `token-farm/farm_manager.py`

Автоматизация:
1. Выбрать свободный контейнер
2. Очистить данные Avito: `adb shell pm clear com.avito.android`
3. Установить SharedPreferences с device_id
4. Запустить Avito
5. Ввести номер телефона (UI Automator)
6. Получить SMS код
7. Ввести код
8. Извлечь session_token и fingerprint из SharedPreferences
9. Сохранить в БД

**Оценка:** 8-16 часов

---

### [ ] Мониторинг (Prometheus + Grafana)
**Файлы:** `deploy/prometheus.yml`, `deploy/grafana/`

Метрики:
- `avito_connections_total` - количество WebSocket соединений
- `avito_messages_sent_total` - отправленные сообщения
- `avito_messages_received_total` - полученные сообщения
- `token_refresh_total` - обновления токенов
- `token_refresh_errors_total` - ошибки обновления

```python
# В avito_client.py
from prometheus_client import Counter, Gauge

CONNECTIONS = Gauge('avito_connections', 'Active connections')
MESSAGES_SENT = Counter('avito_messages_sent', 'Messages sent')

class AvitoClient:
    async def start(self):
        CONNECTIONS.inc()

    async def stop(self):
        CONNECTIONS.dec()

    async def send_message(self, ...):
        MESSAGES_SENT.inc()
```

**Оценка:** 4-6 часов

---

### [ ] Логирование (structlog)
**Файл:** `shared/logging.py` (создать)

```python
import structlog

def setup_logging():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

logger = structlog.get_logger()

# Использование
logger.info("message_sent",
    channel_id=channel_id,
    user_id=user_id,
    text_length=len(text)
)
```

**Оценка:** 2-3 часа

---

## 🟢 Улучшения

### [ ] Поддержка изображений
**Файлы:** `mcp-server/avito_client.py`, `mcp-server/telegram_bot.py`

```python
# avito_client.py
async def send_image(self, channel_id: str, image_data: bytes) -> str:
    # 1. Upload image to Avito
    # 2. Send message with image_id

# telegram_bot.py
@router.message(F.photo)
async def forward_photo(message: Message):
    photo = message.photo[-1]  # Largest size
    file = await bot.get_file(photo.file_id)
    image_data = await bot.download_file(file.file_path)
    await client.send_image(channel_id, image_data)
```

**Оценка:** 4-6 часов

---

### [ ] Голосовые сообщения
**Файлы:** `mcp-server/avito_client.py`, `mcp-server/telegram_bot.py`

Варианты:
1. Просто пересылать как аудио
2. Конвертировать в текст (Whisper API)

**Оценка:** 4-8 часов

---

### [ ] Автоответчик
**Файлы:** `mcp-server/auto_responder.py` (создать)

```python
class AutoResponder:
    templates = {
        "greeting": "Здравствуйте! Товар в наличии. Что вас интересует?",
        "price": "Цена указана в объявлении. Торг возможен при самовывозе.",
        "busy": "Сейчас не могу ответить, напишу позже."
    }

    async def check_and_respond(self, message: AvitoMessage) -> Optional[str]:
        # Анализ входящего сообщения
        # Автоматический ответ если подходит шаблон
```

**Оценка:** 4-6 часов

---

### [ ] Статистика
**Файлы:** `shared/models.py`, `mcp-server/stats.py` (создать)

Новая таблица:
```sql
CREATE TABLE stats (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    date DATE,
    messages_sent INT DEFAULT 0,
    messages_received INT DEFAULT 0,
    avg_response_time_seconds FLOAT,
    active_chats INT DEFAULT 0
);
```

**Оценка:** 3-4 часа

---

### [ ] Мультиаккаунт
**Файлы:** `shared/models.py`, `mcp-server/telegram_bot.py`

Изменения:
1. TelegramUser может иметь несколько account_id (many-to-many)
2. Команда `/accounts` - список привязанных аккаунтов
3. Команда `/switch` - переключение между аккаунтами

**Оценка:** 4-6 часов

---

### [ ] Web Admin Panel
**Файлы:** `admin/` (создать директорию)

Опции:
1. FastAPI + Jinja2 (простой)
2. React/Vue SPA (современный)
3. Streamlit (быстрый прототип)

Функции:
- Список аккаунтов
- Добавление/удаление аккаунтов
- Просмотр логов
- Статистика
- Управление прокси

**Оценка:** 16-24 часа

---

## ⚪ Техдолг

### [ ] Unit тесты
**Файлы:** `tests/` (создать)

```python
# tests/test_utils.py
import pytest
from shared.utils import parse_jwt, normalize_phone

def test_parse_jwt_valid():
    token = "eyJhbGci..."
    payload = parse_jwt(token)
    assert payload.user_id == 123456

def test_normalize_phone():
    assert normalize_phone("89991234567") == "+79991234567"
    assert normalize_phone("+7 999 123-45-67") == "+79991234567"
```

**Оценка:** 8-12 часов

---

### [ ] Integration тесты
**Файлы:** `tests/integration/`

```python
# tests/integration/test_avito_client.py
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_websocket_connect():
    mock_ws = AsyncMock()
    client = AvitoClient(session=mock_session)
    # ...
```

**Оценка:** 8-12 часов

---

### [ ] CI/CD (GitHub Actions)
**Файл:** `.github/workflows/ci.yml`

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r shared/requirements.txt
      - run: pip install pytest pytest-asyncio
      - run: pytest tests/

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - run: ssh deploy@server 'cd /opt/avito && git pull && docker-compose up -d'
```

**Оценка:** 2-4 часа

---

### [ ] Type hints 100%
**Все файлы**

Добавить mypy в CI:
```yaml
- run: pip install mypy
- run: mypy shared/ mcp-server/ token-farm/ --strict
```

**Оценка:** 4-6 часов

---

### [ ] Документация (MkDocs)
**Файлы:** `docs/`, `mkdocs.yml`

```yaml
# mkdocs.yml
site_name: Avito SmartFree
theme: material
nav:
  - Home: index.md
  - Architecture: architecture.md
  - API Reference: api.md
  - Deployment: deployment.md
```

**Оценка:** 4-6 часов

---

## Приоритет выполнения

### Этап 1: MVP (1-2 недели)
1. 🔴 Тестирование Redroid на ARM
2. 🔴 Интеграция AvitoClient ↔ TelegramBot
3. 🔴 SMS интеграция (хотя бы webhook)

### Этап 2: Production Ready (2-3 недели)
4. 🟡 Proxy Manager
5. 🟡 Полный Registration Flow
6. 🟡 Логирование
7. 🟡 Мониторинг

### Этап 3: Улучшения (ongoing)
8. 🟢 Поддержка изображений
9. 🟢 Статистика
10. 🟢 Web Admin Panel

### Параллельно
11. ⚪ Unit тесты
12. ⚪ CI/CD

---

*Последнее обновление: 2026-01-14*
