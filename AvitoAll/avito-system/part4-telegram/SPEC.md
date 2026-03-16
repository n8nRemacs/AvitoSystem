# Part 4: Telegram Bot

## Обзор

Telegram-бот для уведомлений о найденных товарах и быстрого управления.

**Стек:** Python 3.11+ / aiogram 3
**Папка:** `part4-telegram/`

## Структура файлов

```
part4-telegram/
├── SPEC.md
├── requirements.txt
├── .env.example
└── src/
    ├── bot.py                # Точка входа
    ├── config.py             # Настройки из .env
    ├── backend_client.py     # HTTP-клиент к Backend API
    ├── handlers.py           # Обработчики команд
    └── notifier.py           # Фоновый цикл уведомлений
```

## .env.example

```env
TELEGRAM_TOKEN=123456:ABC-DEF
TELEGRAM_ALLOWED_USERS=123456789,987654321
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026
NOTIFY_INTERVAL=30
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие + помощь |
| `/add <query> [мин-макс] [доставка]` | Добавить поиск |
| `/list` | Список активных поисков |
| `/remove <id>` | Удалить поиск |
| `/status` | Статус: токены, статистика |
| `/stop` | Выкл все поиски |

### Парсинг `/add`

```
/add iPhone 12 Pro 10000-25000 доставка
     ──────────── ──────────── ────────
      query        price range  delivery flag
```

- Последнее слово "доставка" → `delivery=true`
- Паттерн `\d+-\d+` → `price_min, price_max`
- Остальное → `query`

Отправляет `POST /api/v1/searches` на Backend.

## Уведомления (notifier.py)

Фоновый цикл, каждые `NOTIFY_INTERVAL` секунд:

1. `GET /api/v1/items/new?since=<last_check>` — новые товары
2. Для каждого товара с вердиктом:
   - **OK** → зелёное уведомление с фото, ценой, ссылкой, AI-summary
   - **RISK** → жёлтое предупреждение с дефектами
   - **SKIP** → не отправляем

### Формат уведомления

```
✅ iPhone 12 Pro 128GB — 15 000 ₽
📍 Москва | С доставкой
🤖 AI: 8/10 — Хорошее состояние, без дефектов
💬 Приветствие отправлено

🔗 https://www.avito.ru/7867391303
```

```
⚠️ iPhone 12 Pro 128GB — 8 000 ₽
📍 Саратов | С доставкой
🤖 AI: 4/10 — Подозрительно низкая цена
⛔ Дефекты: Нет фото экрана, мало информации

🔗 https://www.avito.ru/7867391304
```

## backend_client.py

Аналогичный `part3-worker/src/backend_client.py`:

```python
class BackendClient:
    def __init__(self, url: str, api_key: str)

    async def get_searches(self) -> list
    async def create_search(self, data: dict) -> dict
    async def delete_search(self, id: int) -> bool
    async def get_new_items(self, since: str) -> list
    async def get_stats(self) -> dict
```

## Контроль доступа

- `TELEGRAM_ALLOWED_USERS` — список user_id через запятую
- Пустой = доступ всем
- Все handler'ы проверяют доступ

## Зависимости (requirements.txt)

```
aiogram>=3.4.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
```

## Запуск

```bash
cd part4-telegram
pip install -r requirements.txt
cp .env.example .env
python src/bot.py
```
