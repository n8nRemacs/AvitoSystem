# Part 6: Android Token — Описание и API

## Назначение

Android-приложение для рутованного смартфона. Извлекает токены авторизации Avito из SharedPreferences через root-доступ, мониторит время жизни JWT и синхронизирует на Backend API.

## Функционал

1. **Чтение SharedPreferences** — через `su -c cat` (libsu) читает XML с токенами
2. **Парсинг JWT** — декодирует токен для получения `exp` (время истечения)
3. **Мониторинг истечения** — Foreground Service проверяет каждые 30 минут
4. **Обновление токена** — запускает Avito через Intent для автоматического refresh
5. **Синхронизация** — отправляет токены на Backend API
6. **Уведомления** — Android notifications + Telegram (опционально)
7. **Автозапуск** — BootReceiver запускает сервис при загрузке устройства

---

## Что получает

### От Avito (SharedPreferences через root)

**Пути к файлу (по приоритету):**
```
/data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
/data/user_de/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Формат XML:**
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzAxMDQ3NTYsImlhdCI6MTc3MDAxODM1NiwidSI6MTU3OTIwMjE0LCJwIjoyODEwOTU5OSwicyI6ImRkMWNlNGE0Y2NmYjRiYjZiYjI0Mzk1YTk1NDZjYWRlLjE3NzAwMTgzNTYiLCJoIjoiTkRaa01UYzVOamxqWlRGaVpXWmlNamN5TmpFNFkyUTFPVGt5T1RkbE1qRmhNelEyTUdJMU9EcFpWR2hyVGpKSk0wNVVXWGxPVkZFeFQwUm5kMDlSIiwiZCI6ImE4ZDdiNzU2MjU0NTg4MDkiLCJwbCI6ImFuZHJvaWQiLCJleHRyYSI6bnVsbH0.8gO0spmKfHoHN2i0Vbf908_QMrPFmUUkl_WUhzlNPPSJvxyGBxpbNyvM4AHmX-nbuuyYzhMM_O_GBTQ-FTaCYA</string>
    <string name="fpx">A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700...</string>
    <string name="refresh_token">5c5b31d4b70e997ac188ad7723b395b4</string>
    <string name="device_id">a8d7b75625458809</string>
    <string name="remote_device_id">kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM...</string>
    <string name="user_hash">9b82afc1ab1e2419981f7a9d9d2b6af9</string>
</map>
```

**Маппинг XML → SessionData:**

| XML name | SessionData field | Fallback names | Обязательное |
|----------|-------------------|----------------|:------------:|
| `session` | `sessionToken` | `token` | ✅ |
| `fpx` | `fingerprint` | `f`, `fingerprint` | ✅ |
| `fpx_calc_time` | `fingerprintCalcTime` | — | ❌ |
| `refresh_token` | `refreshToken` | — | ❌ |
| `device_id` | `deviceId` | — | ❌ |
| `remote_device_id` | `remoteDeviceId` | — | ❌ |
| `user_hash` | `userHash` | — | ❌ |
| `visitor_id` | `visitorId` | — | ❌ |
| `1f_uid` | `cookies["1f_uid"]` | — | ❌ |
| `u_cookie` | `cookies["u"]` | — | ❌ |
| `v_cookie` | `cookies["v"]` | — | ❌ |

**JWT payload (из `session`):**
```json
{
  "exp": 1770104756,
  "iat": 1770018356,
  "u": 157920214,
  "p": 28109599,
  "s": "dd1ce4a4ccfb4bb6bb24395a9546cade.1770018356",
  "h": "NDZkMTc5NjljZTFiZWZiMjcyNjE4Y2Q1OTkyOTdlMjFhMzQ2MGI1OD...",
  "d": "a8d7b75625458809",
  "pl": "android",
  "extra": null
}
```

---

## Что отправляет

### 1. POST /api/v1/sessions — Синхронизация токенов

**Когда:** при изменении токена, по расписанию, после refresh

**Заголовки:**
```
Content-Type: application/json
X-Device-Key: {API_KEY}
```

**Тело запроса:**
```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "5c5b31d4b70e997ac188ad7723b395b4",
  "fingerprint": "A2.a541fb18def1032c46e8ce9356bf78870fa9c764...",
  "device_id": "a8d7b75625458809",
  "remote_device_id": "kSCwY4Kj4HUfwZHG...",
  "user_id": 157920214,
  "user_hash": "9b82afc1ab1e2419981f7a9d9d2b6af9",
  "expires_at": 1770104756,
  "cookies": {
    "1f_uid": "...",
    "u": "...",
    "v": "..."
  },
  "synced_at": 1770018400
}
```

**Ответ 200:**
```json
{
  "success": true,
  "expires_at": 1770104756,
  "hours_left": 12.5
}
```

### 2. GET /health — Проверка доступности Backend

**Ответ 200:**
```json
{ "status": "ok" }
```

### 3. GET /api/v1/full-status — Полный статус сервера

**Заголовки:**
```
X-Device-Key: {API_KEY}
```

**Ответ 200:**
```json
{
  "server": {
    "status": "running",
    "timestamp": 1770018400
  },
  "session": {
    "exists": true,
    "expires_at": 1770104756,
    "hours_left": 12.5,
    "is_valid": true,
    "updated_at": 1770018356,
    "token_preview": "eyJhbG...первые 20 символов"
  },
  "mcp": {
    "service": "avito-mcp-bot",
    "is_running": true,
    "status": "connected"
  }
}
```

### 4. POST /api/v1/mcp/restart — Перезапуск MCP бота

**Заголовки:**
```
X-Device-Key: {API_KEY}
```

**Ответ 200:**
```json
{ "success": true, "message": "MCP service restarted" }
```

### 5. POST /api/v1/devices/ping — Пинг устройства

**Тело запроса:**
```json
{
  "battery_level": 75,
  "avito_app_running": true,
  "last_session_update": 1770018356,
  "timestamp": 1770018400
}
```

**Ответ 200:**
```json
{ "success": true }
```

### 6. Telegram Bot API — Уведомления (опционально)

**URL:** `https://api.telegram.org/bot{botToken}/sendMessage`

**Тело:**
```json
{
  "chat_id": "{chatId}",
  "text": "<b>⏰ Avito Token</b>\nExpires in 1.5 hours\nSync: ✅",
  "parse_mode": "HTML"
}
```

**Типы уведомлений:**
- Истекает скоро: `⏰ Token expiring in X.X hours`
- Истёк: `❌ Token expired! Open Avito manually`
- Синхронизирован: `✅ Token synced (Xh left)`
- Тест: `🔔 Test notification from AvitoSessionManager`

---

## Root-команды к устройству

### Чтение SharedPreferences

**Метод 1 (libsu, Magisk mount master):**
```bash
su -mm -c cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Метод 2 (libsu, стандартный su):**
```bash
su -c cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Метод 3 (Runtime.exec, fallback):**
```kotlin
Runtime.getRuntime().exec(arrayOf("su", "-c", "cat", path))
```

### Запуск Avito для refresh

```kotlin
val intent = packageManager.getLaunchIntentForPackage("com.avito.android")
intent?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
startActivity(intent)
// Ждём 5 секунд, перечитываем SharedPrefs
```

### Проверка Avito

```kotlin
packageManager.getPackageInfo("com.avito.android", 0) // throws if not installed
```

---

## Главный цикл (SessionMonitorService)

```
┌─────────────────────────────────────────────────────────────┐
│ ЗАПУСК СЕРВИСА                                              │
│ 1. Создать Foreground Notification                         │
│ 2. Проверить root (Shell.getShell().isRoot)                │
│ 3. Прочитать текущую сессию                                │
│ 4. Если есть → синхронизировать на Backend                 │
│ 5. Запустить цикл мониторинга                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ЦИКЛ (каждые checkIntervalMinutes = 30 мин)                │
│                                                             │
│ 1. Прочитать сессию из SharedPreferences                   │
│    │                                                        │
│    ├─ su -c cat preferences.xml                            │
│    ├─ Парсинг XML → SessionData                            │
│    └─ Парсинг JWT → exp, userId                            │
│                                                             │
│ 2. Кешировать локально (PrefsManager)                      │
│                                                             │
│ 3. Вычислить hoursUntilExpiry                              │
│    │                                                        │
│    ├─ > syncBeforeExpiryHours (2ч):                        │
│    │   └─ Проверить изменился ли токен (cachedToken)       │
│    │      ├─ Да → sync + обновить notification             │
│    │      └─ Нет → пропустить                              │
│    │                                                        │
│    ├─ 0 < hours < 2 (скоро истечёт):                       │
│    │   └─ Показать WARNING notification                    │
│    │   └─ Если autoLaunchAvito:                            │
│    │      └─ startActivity(Avito)                          │
│    │      └─ delay(5000) // 5 секунд                       │
│    │      └─ Перечитать сессию                             │
│    │      └─ Если exp изменился → sync                     │
│    │   └─ Отправить Telegram (если включен)                │
│    │                                                        │
│    └─ ≤ 0 (истёк):                                         │
│        └─ Показать CRITICAL notification                   │
│        └─ Если autoLaunchAvito:                            │
│           └─ startActivity(Avito)                          │
│           └─ delay(5000)                                   │
│           └─ Перечитать сессию                             │
│           └─ Если обновился → sync                         │
│           └─ Если нет → ERROR notification + Telegram      │
│                                                             │
│ 4. Обновить Foreground Notification                        │
│ 5. delay(checkIntervalMinutes * 60 * 1000)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Настройки (.env / UI Settings)

| Настройка | Default | Описание |
|-----------|---------|----------|
| `serverUrl` | `http://155.212.221.189:8080` | URL Backend API |
| `apiKey` | `avito_sync_key_2026` | Ключ авторизации |
| `checkIntervalMinutes` | `30` | Интервал проверки (мин) |
| `syncBeforeExpiryHours` | `2` | За сколько часов до истечения обновлять |
| `autoSyncEnabled` | `true` | Автоматическая синхронизация |
| `autoLaunchAvito` | `true` | Автозапуск Avito для refresh |
| `notifyOnExpiry` | `true` | Уведомления о истечении |
| `telegramEnabled` | `false` | Telegram-уведомления |
| `telegramBotToken` | — | Токен Telegram бота |
| `telegramChatId` | — | Chat ID для уведомлений |

Настройки хранятся в SharedPreferences приложения (`avito_session_manager`).

---

## Notification Channels

| Channel ID | Importance | Назначение |
|------------|------------|------------|
| `session_monitor` | LOW | Foreground Service статус |

**Foreground Notification:**
- Постоянная, показывает текущий статус
- Action button: "Sync Now"
- Текст: "Token valid (12.5h left)" / "Token expired!"

**Expiry Notification:**
- Priority: HIGH
- Cooldown: 1 час между уведомлениями
- Action: открыть Avito
- Текст: "⏰ Token expiring in 1.5h" / "❌ Token expired!"

---

## Совместимость с Part 5

Part 6 отправляет данные на тот же `POST /api/v1/sessions` что и Part 5.
Backend не различает источник — принимает от любого.

```
Part 5 (Redroid/Docker) ──POST──┐
                                 ├──▶ Backend API /api/v1/sessions
Part 6 (Android Phone)  ──POST──┘
```

Можно использовать одновременно для разных аккаунтов Avito.
