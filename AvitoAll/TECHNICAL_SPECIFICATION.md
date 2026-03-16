# Avito Bridge System - Техническая спецификация

**Версия:** 2.0
**Дата:** 2026-01-14
**Статус:** В разработке

---

## 1. Обзор системы

### 1.1 Цель

Система **Avito Bridge** обеспечивает интеграцию мессенджера Avito с внешними платформами (Telegram) через:
- Автоматический захват сессии с rooted Android устройства
- Серверный клиент для Avito WebSocket API
- Telegram бот для пересылки сообщений

### 1.2 Текущая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    ANDROID DEVICE (Rooted)                       │
│                                                                   │
│   ┌─────────────────┐         ┌────────────────────────────┐    │
│   │   Avito App     │◄───────►│  AvitoSessionManager App   │    │
│   │   (Official)    │  reads  │  (com.avitobridge)         │    │
│   │                 │  prefs  │                            │    │
│   │  • Авторизован  │         │  • Root (libsu)            │    │
│   │  • Обновляет JWT│         │  • Foreground Service      │    │
│   │  • 24h lifetime │         │  • Auto-launch Avito       │    │
│   └─────────────────┘         │  • Notifications           │    │
│                               └──────────────┬─────────────┘    │
└──────────────────────────────────────────────┼──────────────────┘
                                               │ POST /api/v1/sessions
                                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          SERVER (VPS)                            │
│                                                                   │
│  ┌───────────────────┐    ┌───────────────────────────────────┐ │
│  │ avito_session_    │    │  avito_telegram_bot_v2.py         │ │
│  │ server.py (:8080) │───►│  (systemd: avito-bridge)          │ │
│  │                   │    │                                    │ │
│  │ • Receives session│    │  • WebSocket: socket.avito.ru     │ │
│  │ • Saves JSON file │    │  • HTTP API: app.avito.ru         │ │
│  │ • Restarts MCP    │    │  • Telegram Bot API               │ │
│  └───────────────────┘    └───────────────────────────────────┘ │
│                                        │                         │
│                                        ▼                         │
│                              ┌─────────────────┐                │
│                              │  Telegram User  │                │
│                              │  (Your phone)   │                │
│                              └─────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Компоненты системы

### 2.1 Android App - AvitoSessionManager

**Назначение:** Захват и синхронизация сессии Avito

**Технологии:**
- Kotlin, Android SDK 26+
- libsu (root access)
- OkHttp, Gson
- Foreground Service

**Ключевые функции:**

| Функция | Описание |
|---------|----------|
| Session Reader | Чтение SharedPrefs Avito через `su -c cat` |
| Monitor Service | Периодическая проверка токена |
| Auto-launch | Запуск Avito при истечении токена |
| Notifications | Уведомления при истечении |
| Server Sync | POST сессии на сервер |
| MCP Control | Статус и перезапуск MCP бота |

**Путь к данным:**
```
/data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Извлекаемые данные:**
```kotlin
data class SessionData(
    val sessionToken: String,     // JWT, 24h lifetime
    val refreshToken: String?,    // Для обновления (требует fingerprint)
    val fingerprint: String,      // Заголовок 'f', ~400 chars
    val deviceId: String,         // X-DeviceId, 16 hex
    val remoteDeviceId: String?,  // X-RemoteDeviceId
    val userId: Long?,            // User ID из JWT
    val userHash: String?,        // Для WebSocket подключения
    val expiresAt: Long,          // Unix timestamp
    val cookies: Map<String, String>
)
```

### 2.2 Session Server

**Файл:** `avito_session_server.py`
**Порт:** 8080

**Endpoints:**

| Method | Path | Описание |
|--------|------|----------|
| GET | `/health` | Health check |
| GET | `/status` | Статус сессии (expires_at, hours_left) |
| GET | `/api/v1/full-status` | Полный статус (session + MCP) |
| POST | `/api/v1/sessions` | Принять сессию от Android app |
| GET | `/api/v1/mcp/status` | Статус MCP бота |
| POST | `/api/v1/mcp/restart` | Перезапуск MCP бота |

**Авторизация:**
- Header: `X-Device-Key: avito_sync_key_2026`

**При получении сессии:**
1. Валидация данных
2. Сохранение в `avito_session_new.json`
3. `systemctl restart avito-bridge`

### 2.3 MCP - Telegram Bot

**Файл:** `avito_telegram_bot_v2.py`
**Systemd:** `avito-bridge.service`

**Функции:**
- WebSocket подключение к `wss://socket.avito.ru/socket`
- Получение входящих сообщений Avito
- Пересылка в Telegram чат
- Отправка ответов из Telegram в Avito
- Auto-reconnect, watchdog

**Telegram команды:**

| Команда | Описание |
|---------|----------|
| `/chats` | Список чатов Avito |
| `/select N` | Выбрать чат по номеру |
| `/history` | История сообщений |
| `/status` | Статус подключения |
| `/help` | Справка |

**Workflow:**
```
Avito User → Avito WS → MCP Bot → Telegram Bot API → Your Telegram
Your Telegram → MCP Bot → Avito HTTP API → Avito User
```

---

## 3. Avito API Reference

### 3.1 Обязательные заголовки

```http
User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)
X-App: avito
X-Platform: android
X-AppVersion: 215.1
X-DeviceId: a8d7b75625458809
X-RemoteDeviceId: kSCwY4Kj4HUf...android
X-Session: eyJhbGciOiJIUzUxMiIs...
X-Date: 1768295320
f: A2.a541fb18def1032c...
Cookie: sessid=<JWT>; 1f_uid=...; u=...; v=...
```

### 3.2 Fingerprint (заголовок `f`)

**КРИТИЧЕСКИ ВАЖЕН** - без него QRATOR блокирует запросы.

```
Источник: com.avito.security.libfp (native library с VM-обфускацией)
Формат: A2.<hex_signature> (~400 символов)
Хранение: SharedPreferences ключ "fpx"
```

**Невозможно сгенерировать программно** - только извлечь с устройства.

### 3.3 JWT Token

```json
{
  "exp": 1768379484,       // Expiration (iat + 24h)
  "iat": 1768293084,       // Issued at
  "u": 157920214,          // User ID
  "p": 28109599,           // Profile ID
  "s": "409e1bc2...17682", // Session hash
  "d": "a8d7b75625458809", // Device ID
  "pl": "android"          // Platform
}
```

**Время жизни: ровно 24 часа**

### 3.4 Messenger HTTP API

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/1/messenger/getChannels` | POST | Список чатов |
| `/api/1/messenger/getUserVisibleMessages` | POST | Сообщения чата |
| `/api/1/messenger/sendTextMessage` | POST | Отправка сообщения |
| `/api/1/messenger/markAsRead` | POST | Пометить прочитанным |

### 3.5 WebSocket API

**URL:** `wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}`

**Инициализация:**
```json
{"type": "session", "value": {"userId": 157920214, "serverTime": 1768298094000}}
```

**Ping (каждые 25 сек):**
```json
{"id": 999, "jsonrpc": "2.0", "method": "ping", "params": {}}
```

**Входящее сообщение:**
```json
{
  "type": "Message",
  "value": {
    "id": "msg-456",
    "channelId": "u2i-abc123xyz",
    "fromUid": "hash456",
    "body": {"text": {"text": "Привет!"}},
    "created": 1768295000000
  }
}
```

---

## 4. Настройка и деплой

### 4.1 Android App

```bash
# Сборка
cd AvitoSessionManager
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
gradlew.bat assembleDebug

# Установка
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 4.2 Server

```bash
# Session Server
python3 avito_session_server.py &

# MCP Bot (systemd)
sudo cp avito-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable avito-bridge
sudo systemctl start avito-bridge
```

### 4.3 Systemd Service

```ini
# /etc/systemd/system/avito-bridge.service
[Unit]
Description=Avito Telegram Bridge
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/avito
ExecStart=/usr/bin/python3 /root/avito/avito_telegram_bot_v2.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 5. Безопасность

### 5.1 Критические данные

| Данные | Хранение | Защита |
|--------|----------|--------|
| JWT Token | JSON файл на сервере | Файловые права 600 |
| Fingerprint | JSON файл на сервере | Не передавать третьим лицам |
| Telegram Bot Token | Переменная окружения | Не коммитить в git |
| API Key | Код приложения | Использовать env vars |

### 5.2 Ограничения

- **Fingerprint невозможно подделать** - защита от ботов
- **QRATOR блокирует** нестандартные TLS fingerprints
- **Rate limits** на API Avito (не документированы)

---

## 6. Troubleshooting

### 6.1 Android App

| Проблема | Решение |
|----------|---------|
| No root access | Проверить Magisk, предоставить права |
| Failed to read session | Avito не авторизован, открыть вручную |
| Sync failed | Проверить сеть и URL сервера |

### 6.2 MCP Bot

| Проблема | Решение |
|----------|---------|
| WebSocket disconnect | Проверить токен, перезапустить |
| 403 Forbidden | Истёк токен или fingerprint |
| No messages | Проверить user_hash в WS URL |

### 6.3 Логи

```bash
# MCP Bot
journalctl -u avito-bridge -f

# Session Server
tail -f /var/log/avito-session.log
```

---

## 7. Файлы проекта

```
APK/Avito/
├── AvitoSessionManager/          # Android приложение
│   ├── app/src/main/java/com/avitobridge/
│   │   ├── App.kt
│   │   ├── data/
│   │   │   ├── PrefsManager.kt
│   │   │   ├── SessionData.kt
│   │   │   ├── AvitoSessionReader.kt
│   │   │   └── ServerApi.kt
│   │   ├── service/
│   │   │   ├── SessionMonitorService.kt
│   │   │   └── BootReceiver.kt
│   │   └── ui/
│   │       └── MainActivity.kt
│   └── README.md
├── avito_session_server.py       # HTTP сервер для приёма сессий
├── avito_telegram_bot_v2.py      # MCP - Telegram бот
├── avito_session_new.json        # Текущая сессия
├── avito-bridge.service          # Systemd unit
├── ssl_simple.js                 # Frida SSL bypass (для отладки)
├── frida_avito_hooks.js          # Frida hooks (для отладки)
└── TECHNICAL_SPECIFICATION.md    # Этот файл
```

---

## 8. TODO / Roadmap

### Реализовано
- [x] Android app для захвата сессии
- [x] Foreground service с мониторингом
- [x] Auto-launch Avito при истечении
- [x] Уведомления при истечении токена
- [x] HTTP сервер для приёма сессий
- [x] MCP Telegram бот
- [x] WebSocket подключение к Avito
- [x] Пересылка сообщений Avito → Telegram
- [x] Отправка ответов Telegram → Avito

### В планах
- [ ] Поддержка нескольких аккаунтов
- [ ] Отправка изображений
- [ ] Web UI для управления
- [ ] Автоматический refresh токена (требует решение fingerprint)
- [ ] Push уведомления на iOS/Android клиент

---

*Документ обновлён: 2026-01-14*
