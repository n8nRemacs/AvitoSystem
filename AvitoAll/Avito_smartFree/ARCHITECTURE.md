# Avito SmartFree - Техническая документация

## Оглавление
1. [Обзор проекта](#обзор-проекта)
2. [Проблема и решение](#проблема-и-решение)
3. [Архитектура системы](#архитектура-системы)
4. [Avito API - Reverse Engineering](#avito-api---reverse-engineering)
5. [Компоненты системы](#компоненты-системы)
6. [База данных](#база-данных)
7. [Безопасность и антифрод](#безопасность-и-антифрод)
8. [Деплой и масштабирование](#деплой-и-масштабирование)
9. [Известные ограничения](#известные-ограничения)
10. [TODO](#todo)

---

## Обзор проекта

**Avito SmartFree** - это SaaS платформа для интеграции Avito Messenger с Telegram. Позволяет пользователям получать уведомления о новых сообщениях Avito в Telegram и отвечать на них прямо из Telegram.

### Ключевые особенности:
- **Без физических устройств** - используются Android эмуляторы (Redroid) на ARM серверах
- **Масштабируемость** - архитектура рассчитана на 1000+ клиентов
- **Один Telegram бот** - все клиенты работают через единый бот
- **Автоматическое обновление токенов** - токены Avito живут 24 часа, система обновляет их автоматически

### Целевая аудитория:
- Продавцы на Avito, которым нужно быстро отвечать на сообщения
- Бизнесы с множеством объявлений
- Те, кто не хочет постоянно держать приложение Avito открытым

---

## Проблема и решение

### Проблема
Avito не предоставляет официального API для мессенджера. Единственный способ работать с сообщениями - через мобильное приложение. Это создаёт проблемы:
1. Нужно постоянно держать телефон под рукой
2. Нельзя автоматизировать ответы
3. Нельзя интегрировать с другими системами (CRM, Telegram)

### Решение
Мы реверс-инженерили Android-приложение Avito и выяснили:

1. **Авторизация**: Avito использует JWT токены со сроком жизни 24 часа
2. **WebSocket**: Реальное время достигается через WebSocket на `wss://socket.avito.ru/socket`
3. **Fingerprint**: Заголовок `f` содержит зашифрованный fingerprint устройства, генерируемый нативной библиотекой
4. **Защита**: Avito проверяет fingerprint, device_id, User-Agent и другие параметры

### Ключевое открытие
Fingerprint (`f` header) генерируется один раз при установке приложения и сохраняется в SharedPreferences. Его можно **извлечь с реального устройства** или **сгенерировать в эмуляторе** и использовать на сервере без самого устройства.

---

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              КЛИЕНТЫ                                     │
│                         (Telegram пользователи)                          │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ Telegram Bot API
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MCP SERVER                                     │
│                        (VPS - Hetzner CX22)                              │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │  Telegram Bot    │  │  Avito Client    │  │   MCP Manager    │       │
│  │  (aiogram 3.x)   │◄─┤  Pool            │◄─┤                  │       │
│  │                  │  │  (WebSocket x N) │  │  Orchestrator    │       │
│  └──────────────────┘  └────────┬─────────┘  └──────────────────┘       │
│                                 │                                        │
│                                 │ WebSocket (wss://socket.avito.ru)      │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            AVITO                                         │
│                     (Серверы Авито)                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ REST API (регистрация, refresh)
                                  │
┌─────────────────────────────────┴───────────────────────────────────────┐
│                          TOKEN FARM                                      │
│                    (ARM Server - Hetzner CAX41)                          │
│                                                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │  Redroid 1  │ │  Redroid 2  │ │  Redroid 3  │ │  Redroid N  │        │
│  │  (Android)  │ │  (Android)  │ │  (Android)  │ │  (Android)  │        │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                    Farm Manager                               │       │
│  │  - Управление контейнерами                                    │       │
│  │  - Генерация fingerprint                                      │       │
│  │  - Обновление JWT токенов                                     │       │
│  │  - Регистрация аккаунтов                                      │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                    FastAPI Server                             │       │
│  │  POST /accounts - создать аккаунт                             │       │
│  │  GET  /accounts/{id}/session - получить токен                 │       │
│  │  POST /accounts/{id}/refresh - обновить токен                 │       │
│  └──────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL                                      │
│                                                                          │
│  accounts     - аккаунты Avito (phone, device_id, fingerprint)          │
│  sessions     - JWT токены (session_token, expires_at)                   │
│  telegram_users - связь Telegram ↔ Avito                                 │
│  messages     - кэш сообщений                                            │
│  proxies      - пул прокси                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Почему два сервера?

1. **Token Farm (ARM)**:
   - Redroid работает ТОЛЬКО на ARM архитектуре
   - Требует привилегированный режим Docker
   - Ресурсоёмкий (каждый контейнер ~2-4GB RAM)
   - Используется редко (раз в 20 часов на аккаунт)

2. **MCP Server (любой VPS)**:
   - Держит WebSocket соединения 24/7
   - Telegram бот polling
   - Лёгкий (можно запустить на дешёвом VPS)
   - Горизонтально масштабируется

---

## Avito API - Reverse Engineering

### Авторизация

Avito использует JWT токены. Структура:

```
Header: { "alg": "HS256", "typ": "JWT" }
Payload: {
  "exp": 1736899200,      // Expiration (Unix timestamp)
  "iat": 1736812800,      // Issued at
  "u": 123456789,         // User ID
  "p": 987654321,         // Profile ID
  "s": "abc123...",       // Session hash
  "d": "device_id_hex",   // Device ID
  "pl": "android"         // Platform
}
```

**Время жизни**: 24 часа (86400 секунд)

### Заголовки запросов

```http
User-Agent: AVITO 215.1 (Samsung SM-G998B; Android 12; ru)
X-App: avito
X-Platform: android
X-AppVersion: 215.1
X-DeviceId: a1b2c3d4e5f6g7h8
X-Session: eyJhbGciOiJIUzI1NiIs...
X-Date: 1736812800
f: base64_encoded_fingerprint
Cookie: sessid=eyJhbGciOiJIUzI1NiIs...
```

### Fingerprint (заголовок `f`)

Самый важный элемент защиты. Генерируется нативной библиотекой `libavito.so`:

```
f = base64(encrypt({
  "device_id": "...",
  "android_id": "...",
  "build_fingerprint": "samsung/...",
  "imei": "...",
  "sensors": [...],
  "installed_apps": [...],
  "timestamp": ...
}))
```

**Важно**: Fingerprint привязан к device_id. Нельзя использовать fingerprint от одного устройства с device_id от другого.

### WebSocket API

**URL**: `wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}`

**Формат сообщений** (JSON):

```javascript
// Ping (клиент → сервер)
{ "t": "ping", "ts": 1736812800000 }

// Pong (сервер → клиент)
{ "t": "pong", "ts": 1736812800000 }

// Новое сообщение (сервер → клиент)
{
  "t": "message",
  "payload": {
    "message": {
      "id": "msg_123",
      "channelId": "ch_456",
      "authorId": 789,
      "body": {
        "text": { "text": "Привет!" }
      },
      "created": 1736812800
    }
  }
}

// Typing indicator (клиент → сервер)
{ "t": "typing", "payload": { "channelId": "ch_456" } }
```

### HTTP API

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/1/messenger/getChannels` | GET | Список чатов |
| `/api/1/messenger/getMessages` | GET | Сообщения чата |
| `/api/1/messenger/sendMessage` | POST | Отправить сообщение |
| `/api/1/messenger/markRead` | POST | Отметить прочитанным |
| `/api/1/users/self` | GET | Информация о пользователе |

---

## Компоненты системы

### 1. Shared (`shared/`)

Общие модули, используемые и Token Farm, и MCP Server.

#### `models.py`
SQLAlchemy ORM модели:
- `Account` - аккаунт Avito (phone, device_id, fingerprint, status)
- `Session` - JWT токен (session_token, expires_at, is_active)
- `TelegramUser` - пользователь Telegram (telegram_id, account_id, selected_channel_id)
- `Proxy` - прокси для регистрации
- `Message` - кэш сообщений

#### `database.py`
Async PostgreSQL через SQLAlchemy 2.0:
- `Database` класс с context manager для сессий
- Repository классы для CRUD операций
- Глобальный инстанс через `get_db()`

#### `utils.py`
Утилиты:
- `parse_jwt()` - парсинг JWT без валидации подписи
- `generate_device_id()` - генерация device_id (16 hex chars)
- `generate_imei()` - генерация валидного IMEI с Luhn checksum
- `build_avito_headers()` - формирование заголовков для API
- `RateLimiter` - ограничение частоты запросов

#### `config.py`
Pydantic Settings из ENV переменных.

### 2. Token Farm (`token-farm/`)

#### `api_server.py`
FastAPI REST API:
- `POST /accounts` - создать аккаунт, запустить регистрацию
- `GET /accounts` - список аккаунтов
- `GET /accounts/{id}/session` - получить активную сессию
- `POST /accounts/{id}/refresh` - запросить обновление токена
- `GET /health` - health check
- `GET /containers` - статус Redroid контейнеров

#### `farm_manager.py`
Оркестратор Redroid контейнеров:
- `FarmManager` - управляет пулом контейнеров
- `ContainerInfo` - состояние контейнера (idle/busy/error)
- `ADBController` - взаимодействие с Android через ADB
- Автоматическое обновление токенов (проверка каждые 30 минут)

#### `docker-compose.yml`
5 Redroid контейнеров с разными fingerprints устройств:
- Samsung Galaxy S21 Ultra
- Samsung Galaxy A52
- Google Pixel 6
- Samsung Galaxy S21
- Xiaomi POCO F3

### 3. MCP Server (`mcp-server/`)

#### `avito_client.py`
Клиент для Avito:
- `AvitoClient` - WebSocket + HTTP клиент для одного аккаунта
- `AvitoClientPool` - пул клиентов для множества аккаунтов
- Auto-reconnect с exponential backoff
- Rate limiting (30 запросов/минуту)

#### `telegram_bot.py`
Telegram бот на aiogram 3.x:
- `/start` - начало работы
- `/link` - привязка аккаунта по номеру телефона
- `/chats` - список чатов Avito (inline keyboard)
- `/status` - статус подключения
- Пересылка текстовых сообщений в выбранный чат

#### `mcp_manager.py`
Главный оркестратор:
- Загружает активные аккаунты при старте
- Создаёт WebSocket соединения для каждого
- Роутит сообщения Avito → Telegram и обратно
- Координирует обновление токенов с Token Farm

---

## База данных

### Схема

```sql
-- Аккаунты Avito
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    phone VARCHAR(20) UNIQUE NOT NULL,
    user_id BIGINT,
    user_hash VARCHAR(64),
    device_id VARCHAR(32) NOT NULL,
    remote_device_id TEXT,
    fingerprint TEXT,                    -- Важно! Заголовок 'f'
    device_model VARCHAR(100),
    android_version VARCHAR(10),
    status VARCHAR(20) DEFAULT 'pending', -- pending/active/expired/blocked
    error_message TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Сессии (JWT токены)
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    session_token TEXT NOT NULL,         -- JWT токен
    refresh_token VARCHAR(64),
    expires_at TIMESTAMP NOT NULL,       -- Когда истекает
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP
);

-- Пользователи Telegram
CREATE TABLE telegram_users (
    id UUID PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    account_id UUID REFERENCES accounts(id),  -- Привязанный аккаунт
    selected_channel_id VARCHAR(100),         -- Текущий выбранный чат
    notifications_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP
);

-- Прокси
CREATE TABLE proxies (
    id UUID PRIMARY KEY,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    username VARCHAR(100),
    password VARCHAR(100),
    proxy_type VARCHAR(20),              -- mobile/residential/datacenter
    is_active BOOLEAN DEFAULT TRUE,
    is_healthy BOOLEAN DEFAULT TRUE
);

-- Кэш сообщений
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    avito_message_id VARCHAR(100) UNIQUE,
    channel_id VARCHAR(100),
    account_id UUID REFERENCES accounts(id),
    author_id VARCHAR(100),
    text TEXT,
    is_incoming BOOLEAN,
    telegram_message_id BIGINT,
    avito_created_at TIMESTAMP,
    created_at TIMESTAMP
);
```

### Индексы

```sql
CREATE INDEX idx_accounts_status ON accounts(status);
CREATE INDEX idx_accounts_phone ON accounts(phone);
CREATE INDEX idx_sessions_active_expires ON sessions(is_active, expires_at);
CREATE INDEX idx_telegram_users_tg_id ON telegram_users(telegram_id);
CREATE INDEX idx_messages_channel ON messages(channel_id, avito_created_at);
```

---

## Безопасность и антифрод

### Что проверяет Avito

1. **Device ID** - должен быть уникальным и постоянным
2. **Fingerprint** - должен соответствовать device_id
3. **User-Agent** - должен содержать версию приложения и модель устройства
4. **IP адрес** - при регистрации проверяется тип (mobile/residential/datacenter)
5. **Поведение** - частота запросов, паттерны использования

### Наши меры

1. **Уникальные fingerprints** - каждый аккаунт получает уникальный fingerprint из Redroid
2. **Реалистичные устройства** - эмулируем реальные модели Samsung/Xiaomi/Google
3. **Mobile прокси** - для регистрации используем мобильные прокси (важно!)
4. **Rate limiting** - ограничение 30 запросов/минуту
5. **Постоянные device_id** - не меняем device_id после создания

### Рекомендации

- Для регистрации ОБЯЗАТЕЛЬНО использовать мобильные прокси
- Не превышать 50 сообщений/час с одного аккаунта
- Не делать массовые действия (рассылки)
- При бане менять fingerprint И device_id

---

## Деплой и масштабирование

### Минимальная конфигурация (100 клиентов)

| Компонент | Сервер | Цена |
|-----------|--------|------|
| Token Farm | Oracle Ampere (4 ARM, 24GB) | Бесплатно |
| MCP Server | Hetzner CX22 (2 vCPU, 4GB) | €4/мес |
| **Итого** | | **€4/мес** |

### Рекомендуемая конфигурация (1000 клиентов)

| Компонент | Сервер | Цена |
|-----------|--------|------|
| Token Farm | Hetzner CAX41 (16 ARM, 32GB) | €30/мес |
| MCP Server | 4× Hetzner CX22 | €16/мес |
| Mobile Proxy | 5-10 прокси | €50-80/мес |
| **Итого** | | **~€100/мес** |

### Горизонтальное масштабирование

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   MCP Server 1  │ │   MCP Server 2  │ │   MCP Server N  │
│   (accounts     │ │   (accounts     │ │   (accounts     │
│    1-250)       │ │    251-500)     │ │    ...)         │
└─────────────────┘ └─────────────────┘ └─────────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (shared)      │
                    └─────────────────┘
```

Каждый MCP Server обслуживает ~250 WebSocket соединений.

---

## Известные ограничения

1. **Redroid только на ARM** - Token Farm должен быть на ARM сервере
2. **Fingerprint истекает** - при обновлении Avito может потребоваться новый fingerprint
3. **SMS верификация** - регистрация требует SMS код (нужна интеграция с SMS сервисом или ручной ввод)
4. **Лимиты Avito** - при активном использовании возможны временные баны
5. **Один аккаунт на пользователя** - текущая архитектура поддерживает 1 аккаунт на Telegram пользователя

---

## TODO

### Критично (блокирует запуск)

- [ ] **SMS интеграция** - подключить SMS сервис для автоматической регистрации
  - Варианты: SMS-activate, 5sim, GetSMS
  - Или: webhook для ручного ввода кода через Telegram

- [ ] **Тестирование на реальном ARM сервере** - проверить работу Redroid
  - Заказать Hetzner CAX или Oracle Ampere
  - Проверить kernel modules (binder_linux, ashmem_linux)

- [ ] **Интеграция AvitoClient с TelegramBot** - сейчас компоненты изолированы
  - Добавить callback в mcp_manager для получения чатов
  - Реализовать реальную отправку сообщений

### Важно (нужно для production)

- [ ] **Proxy Manager** - ротация прокси для регистрации
  - Хранение прокси в БД
  - Health check прокси
  - Автоматическая ротация при ошибках

- [ ] **Registration Flow** - полный цикл регистрации аккаунта
  - Запуск Avito в контейнере
  - Автоматизация ввода номера телефона
  - Ожидание и ввод SMS кода
  - Извлечение токена и fingerprint

- [ ] **Мониторинг и алерты**
  - Prometheus метрики
  - Grafana дашборды
  - Alertmanager для уведомлений

- [ ] **Логирование**
  - Structlog для JSON логов
  - Централизованный сбор (Loki/ELK)

### Улучшения

- [ ] **Поддержка изображений** - отправка/получение фото
- [ ] **Голосовые сообщения** - конвертация voice в текст
- [ ] **Автоответчик** - шаблоны ответов
- [ ] **Статистика** - количество сообщений, время ответа
- [ ] **Мультиаккаунт** - несколько Avito аккаунтов на одного Telegram пользователя
- [ ] **Web Admin Panel** - управление аккаунтами через веб-интерфейс
- [ ] **Backup/Restore** - автоматический бэкап БД

### Техдолг

- [ ] **Unit тесты** - pytest для всех модулей
- [ ] **Integration тесты** - тесты с моками Avito API
- [ ] **CI/CD** - GitHub Actions для автодеплоя
- [ ] **Type hints** - 100% покрытие типами
- [ ] **Documentation** - Sphinx/MkDocs документация

---

## Быстрый старт для разработки

```bash
# 1. Клонировать репозиторий
cd C:\Users\User\Documents\Revers\APK\Avito_smartFree

# 2. Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Установить зависимости
pip install -r shared/requirements.txt
pip install -r mcp-server/requirements.txt

# 4. Запустить PostgreSQL
docker run -d --name avito-postgres \
  -e POSTGRES_USER=avito \
  -e POSTGRES_PASSWORD=avito \
  -e POSTGRES_DB=avito_smartfree \
  -p 5432:5432 \
  postgres:15

# 5. Настроить окружение
cp .env.example .env
# Отредактировать .env, добавить TELEGRAM_BOT_TOKEN

# 6. Запустить MCP Server
cd mcp-server
python mcp_manager.py
```

---

*Последнее обновление: 2026-01-14*
*Версия документации: 1.0*
