# Avito SmartFree

Полностью серверное SaaS решение для интеграции Avito Messenger с Telegram на 1000+ клиентов без физических устройств.

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         TOKEN FARM                               │
│                    (ARM Server - Hetzner/Oracle)                 │
│                                                                  │
│   Redroid Containers (Android эмуляторы)                        │
│   ├── Генерация fingerprint                                     │
│   ├── Обновление JWT токенов (каждые 20ч)                       │
│   ├── Регистрация новых аккаунтов                               │
│   └── API для MCP серверов                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MCP SERVER                                │
│                    (VPS - распределённые)                        │
│                                                                  │
│   Один Telegram бот на всех клиентов                            │
│   ├── WebSocket к Avito (1000 соединений)                       │
│   ├── Telegram Bot API                                          │
│   ├── Пересылка сообщений Avito ↔ Telegram                      │
│   └── Auto-reconnect, health monitoring                         │
└─────────────────────────────────────────────────────────────────┘
```

## Структура проекта

```
Avito_smartFree/
├── shared/                        # Общие модули
│   ├── __init__.py
│   ├── models.py                  # SQLAlchemy модели (PostgreSQL)
│   ├── config.py                  # Конфигурация из ENV
│   ├── database.py                # Async PostgreSQL
│   └── utils.py                   # JWT парсер, утилиты
│
├── token-farm/                    # ARM Server компоненты
│   ├── docker-compose.yml         # Redroid контейнеры
│   ├── farm_manager.py            # Оркестратор контейнеров
│   ├── account_sync.py            # Синхронизация аккаунтов
│   ├── registration.py            # Регистрация через прокси
│   ├── api_server.py              # FastAPI REST API
│   ├── proxy_manager.py           # Управление прокси
│   └── requirements.txt
│
├── mcp-server/                    # MCP Server компоненты
│   ├── mcp_manager.py             # Multi-account менеджер
│   ├── avito_client.py            # Avito WebSocket/HTTP клиент
│   ├── telegram_bot.py            # aiogram 3.x бот
│   ├── message_router.py          # Роутинг сообщений
│   └── requirements.txt
│
├── deploy/                        # Деплой
│   ├── docker-compose.farm.yml
│   ├── docker-compose.mcp.yml
│   ├── setup_farm.sh
│   └── nginx.conf
│
└── README.md
```

## План реализации

### Фаза 1: Shared модули ✅
- [x] `shared/models.py` - PostgreSQL модели
- [x] `shared/config.py` - конфигурация
- [x] `shared/database.py` - async PostgreSQL
- [x] `shared/utils.py` - утилиты

### Фаза 2: Token Farm ✅
- [x] `docker-compose.yml` - Redroid контейнеры
- [x] `farm_manager.py` - управление контейнерами
- [x] `api_server.py` - FastAPI сервер
- [ ] `registration.py` - авто-регистрация (в разработке)
- [ ] `proxy_manager.py` - прокси ротация (в разработке)

### Фаза 3: MCP Server ✅
- [x] `avito_client.py` - WebSocket + HTTP клиент
- [x] `telegram_bot.py` - aiogram бот
- [x] `mcp_manager.py` - multi-account manager

### Фаза 4: Деплой ✅
- [x] Docker Compose файлы
- [x] Systemd сервисы (в setup скриптах)
- [x] Nginx конфигурация
- [ ] Мониторинг (опционально)

## Быстрый старт

### 1. Установка зависимостей

```bash
# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Установить зависимости
pip install -r shared/requirements.txt
pip install -r mcp-server/requirements.txt
```

### 2. Настройка PostgreSQL

```bash
# Docker
docker run -d \
  --name avito-postgres \
  -e POSTGRES_USER=avito \
  -e POSTGRES_PASSWORD=avito \
  -e POSTGRES_DB=avito_smartfree \
  -p 5432:5432 \
  postgres:15
```

### 3. Конфигурация

```bash
# Скопировать пример конфигурации
cp .env.example .env

# Отредактировать .env
nano .env
```

### 4. Запуск MCP Server

```bash
cd mcp-server
python mcp_manager.py
```

### 5. Запуск Token Farm (на ARM сервере)

```bash
cd token-farm
docker-compose up -d
python api_server.py
```

## API Endpoints

### Token Farm API (порт 8000)

| Method | Path | Описание |
|--------|------|----------|
| GET | `/health` | Health check |
| GET | `/accounts` | Список аккаунтов |
| POST | `/accounts` | Создать аккаунт (регистрация) |
| GET | `/accounts/{id}` | Информация об аккаунте |
| GET | `/accounts/{id}/session` | Получить текущую сессию |
| POST | `/accounts/{id}/refresh` | Принудительно обновить токен |
| DELETE | `/accounts/{id}` | Удалить аккаунт |
| GET | `/containers` | Статус контейнеров |

### Telegram Bot команды

| Команда | Описание |
|---------|----------|
| `/start` | Начать работу |
| `/link <phone>` | Привязать аккаунт Avito |
| `/chats` | Список чатов Avito |
| `/select <N>` | Выбрать чат по номеру |
| `/history` | История сообщений |
| `/status` | Статус аккаунта и подключения |
| `/help` | Справка |

## Расчёт ресурсов

### На 1000 клиентов

| Компонент | Спецификация | Цена/мес |
|-----------|--------------|----------|
| Token Farm | Hetzner CAX41 (16 ARM, 32GB) | €30 |
| MCP Server | 4× Hetzner CX22 (2 vCPU, 4GB) | €16 |
| PostgreSQL | Включен в MCP сервер | €0 |
| Mobile Proxy | Для регистрации | €50-80 |
| **Итого** | | **~€100/мес** |

### Масштабирование

| Клиентов | Token Farm | MCP Servers | RAM Total |
|----------|------------|-------------|-----------|
| 1000 | 1× CAX41 | 4× CX22 | 48 GB |
| 5000 | 2× CAX41 | 15× CX22 | 124 GB |
| 10000 | 5× CAX41 | 35× CX22 | 300 GB |

## Переменные окружения

```bash
# Database
DATABASE_URL=postgresql+asyncpg://avito:avito@localhost:5432/avito_smartfree

# Token Farm
FARM_HOST=0.0.0.0
FARM_PORT=8000
FARM_API_KEY=your_secret_key

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ADMIN_IDS=123456789,987654321

# Avito
AVITO_WS_URL=wss://socket.avito.ru/socket
AVITO_API_URL=https://app.avito.ru

# Proxy
PROXY_URL=http://user:pass@proxy:port

# Logging
LOG_LEVEL=INFO
```

## Лицензия

Приватный проект. Все права защищены.

---

*Версия: 1.0*
*Создано: 2026-01-14*
