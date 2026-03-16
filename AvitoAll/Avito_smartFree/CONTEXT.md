# Avito SmartFree - Контекст для AI

> Этот файл содержит краткий контекст проекта для быстрого понимания AI-ассистентом.

## Что это?

SaaS платформа для интеграции **Avito Messenger** с **Telegram**. Пользователи получают уведомления о сообщениях Avito в Telegram и могут отвечать прямо оттуда.

## Почему это сложно?

Avito **не имеет публичного API** для мессенджера. Мы реверс-инженерили мобильное приложение:
- JWT токены живут 24 часа
- WebSocket для real-time сообщений
- Заголовок `f` содержит fingerprint устройства (критично для авторизации)

## Архитектура (2 сервера)

```
Token Farm (ARM) → генерирует токены через Android эмуляторы (Redroid)
       ↓ REST API
MCP Server (VPS) → Telegram бот + WebSocket к Avito
```

## Ключевые файлы

| Файл | Что делает |
|------|------------|
| `shared/models.py` | SQLAlchemy модели (Account, Session, TelegramUser) |
| `shared/utils.py` | JWT парсер, генераторы device_id/IMEI |
| `token-farm/api_server.py` | FastAPI для управления аккаунтами |
| `token-farm/farm_manager.py` | Управление Redroid контейнерами |
| `mcp-server/avito_client.py` | WebSocket/HTTP клиент Avito |
| `mcp-server/telegram_bot.py` | aiogram 3.x бот |
| `mcp-server/mcp_manager.py` | Оркестратор всего |

## Критичные нюансы

1. **Fingerprint (`f` header)** - генерируется нативной библиотекой Avito, привязан к device_id. Без него API отвечает 401.

2. **Redroid только ARM** - эмулятор Android работает только на ARM64 серверах (Hetzner CAX, Oracle Ampere).

3. **Mobile прокси для регистрации** - datacenter IP блокируются при регистрации.

4. **Токены истекают через 24 часа** - нужен auto-refresh.

## База данных (PostgreSQL)

```
accounts (phone, device_id, fingerprint, status)
    ↓
sessions (session_token, expires_at)
    ↓
telegram_users (telegram_id → account_id)
```

## Что НЕ реализовано

- ❌ Автоматическая регистрация (нужен SMS сервис)
- ❌ Реальная интеграция Avito ↔ Telegram (компоненты изолированы)
- ❌ Поддержка изображений/голосовых
- ❌ Мониторинг

## Как запустить (dev)

```bash
# PostgreSQL
docker run -d -e POSTGRES_USER=avito -e POSTGRES_PASSWORD=avito \
  -e POSTGRES_DB=avito_smartfree -p 5432:5432 postgres:15

# Настроить
cp .env.example .env
# Добавить TELEGRAM_BOT_TOKEN

# Запустить
cd mcp-server && python mcp_manager.py
```

## Где смотреть TODO

`TODO.md` - детальный список задач с оценками времени и приоритетами.

## Предыдущие работы

В `C:\Users\User\Documents\Revers\APK\Avito\` лежит предыдущая версия проекта:
- Android приложение для извлечения токенов с рут-телефона
- Frida скрипты для SSL pinning bypass
- Простой Telegram бот (один аккаунт)

Этот проект (SmartFree) - серверная версия для масштабирования на 1000+ клиентов.
