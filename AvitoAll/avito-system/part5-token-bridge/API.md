# Part 5: Token Bridge — Описание и API

## Назначение

Скрипт, работающий на сервере рядом с Redroid-контейнером. Извлекает токены авторизации Avito из SharedPreferences приложения и синхронизирует их на Backend API.

## Функционал

1. **Чтение SharedPreferences** — через `docker exec` читает XML-файл с токенами
2. **Парсинг JWT** — декодирует токен для получения `exp` (время истечения)
3. **Мониторинг истечения** — следит за временем жизни токена
4. **Обновление токена** — запускает Avito для автоматического refresh
5. **Синхронизация** — отправляет токены на Backend API

---

## Что получает

### От Redroid (SharedPreferences)

**Путь к файлу:**
```
/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Формат XML:**
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzAxMDQ3NTYsImlhdCI6MTc3MDAxODM1NiwidSI6MTU3OTIwMjE0LCJwIjoyODEwOTU5OSwicyI6ImRkMWNlNGE0Y2NmYjRiYjZiYjI0Mzk1YTk1NDZjYWRlLjE3NzAwMTgzNTYiLCJoIjoiTkRaa01UYzVOamxqWlRGaVpXWmlNamN5TmpFNFkyUTFPVGt5T1RkbE1qRmhNelEyTUdJMU9EcFpWR2hyVGpKSk0wNVVXWGxPVkZFeFQwUm5kMDlSIiwiZCI6ImE4ZDdiNzU2MjU0NTg4MDkiLCJwbCI6ImFuZHJvaWQiLCJleHRyYSI6bnVsbH0.8gO0spmKfHoHN2i0Vbf908_QMrPFmUUkl_WUhzlNPPSJvxyGBxpbNyvM4AHmX-nbuuyYzhMM_O_GBTQ-FTaCYA</string>
    <string name="fpx">A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc1745e3d2e24cbb87ae5689497c9bce22cdcd798f306ccdf536c876453ee72d819c926bde786618ec0c59d92fb046d297a84e69ad1f83cce8f28c4ca35981c98db2ea6cdb77dd8407a7a35deff88841c7e7969e6fc652179ab038927803f09bddd850e1322ce88c639b4</string>
    <string name="refresh_token">5c5b31d4b70e997ac188ad7723b395b4</string>
    <string name="device_id">a8d7b75625458809</string>
    <string name="remote_device_id">kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android</string>
    <string name="user_hash">9b82afc1ab1e2419981f7a9d9d2b6af9</string>
</map>
```

**Mapping XML → SessionData:**

| XML name | SessionData field | Fallback names |
|----------|-------------------|----------------|
| `session` | `session_token` | `token` |
| `fpx` | `fingerprint` | `f`, `fingerprint` |
| `refresh_token` | `refresh_token` | — |
| `device_id` | `device_id` | — |
| `remote_device_id` | `remote_device_id` | — |
| `user_hash` | `user_hash` | — |

**user_id и expires_at** извлекаются из JWT payload:

```json
{
  "exp": 1770104756,
  "iat": 1770018356,
  "u": 157920214,
  "p": 28109599,
  "s": "dd1ce4a4ccfb4bb6bb24395a9546cade.1770018356",
  "h": "NDZkMTc5NjljZTFiZWZiMjcyNjE4Y2Q1OTkyOTdlMjFhMzQ2MGI1ODpZVGhrTjJKTTBOVVdYbE9WRkV4T0RnZDB=",
  "d": "a8d7b75625458809",
  "pl": "android",
  "extra": null
}
```

---

## Что отправляет

### На Backend API

| Endpoint | Что отправляет | Когда |
|----------|---------------|-------|
| `POST /api/v1/sessions` | Токены авторизации | При изменении токена / по расписанию |

**Формат запроса:**
```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "5c5b31d4b70e997ac188ad7723b395b4",
  "fingerprint": "A2.a541fb18def1032c46e8ce9356bf78870fa9c764...",
  "device_id": "a8d7b75625458809",
  "remote_device_id": "kSCwY4Kj4HUfwZHG...",
  "user_hash": "9b82afc1ab1e2419981f7a9d9d2b6af9",
  "user_id": 157920214,
  "expires_at": 1770104756,
  "cookies": {}
}
```

**HTTP-заголовки:**
```
Content-Type: application/json
X-Api-Key: avito_sync_key_2026
```

**Ответ 200:**
```json
{
  "success": true,
  "expires_at": 1770104756,
  "hours_left": 12.5
}
```

### На Redroid (через docker exec)

| Команда | Когда |
|---------|-------|
| `docker exec redroid cat /data/.../preferences.xml` | Чтение токенов |
| `docker exec redroid am start -n com.avito.android/.MainActivity` | Запуск Avito для refresh |

---

## Главный цикл

```
┌─────────────────────────────────────────────────────────────┐
│ ЗАПУСК                                                      │
│ 1. Загрузить конфигурацию из .env                          │
│ 2. Проверить доступность Redroid контейнера                │
│ 3. Прочитать текущую сессию                                │
│ 4. Если есть → синхронизировать на Backend                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ЦИКЛ (каждые CHECK_INTERVAL секунд = 30 минут)              │
│                                                             │
│ 1. Прочитать сессию из SharedPreferences                   │
│    │                                                        │
│    ├─ docker exec cat preferences.xml                      │
│    ├─ Парсинг XML → SessionData                            │
│    └─ Парсинг JWT → exp, user_id                           │
│                                                             │
│ 2. Вычислить hours_until_expiry                            │
│    │                                                        │
│    ├─ Если > 2 часов:                                      │
│    │   └─ Проверить изменился ли токен                     │
│    │      └─ Если да → синхронизировать                    │
│    │      └─ Если нет → пропустить                         │
│    │                                                        │
│    ├─ Если 0 < hours < 2 (скоро истечёт):                  │
│    │   └─ Запустить Avito: am start ...                    │
│    │   └─ Подождать 30 секунд                              │
│    │   └─ Перечитать сессию                                │
│    │   └─ Если exp изменился → синхронизировать            │
│    │                                                        │
│    └─ Если ≤ 0 (истёк):                                    │
│        └─ Запустить Avito                                  │
│        └─ Подождать 60 секунд                              │
│        └─ Перечитать сессию                                │
│        └─ Если exp обновился → синхронизировать            │
│        └─ Если нет → ОШИБКА в логи                         │
│                                                             │
│ 3. Ожидание: CHECK_INTERVAL секунд                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Команды к Redroid

### Чтение SharedPreferences

```bash
docker exec redroid cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Альтернативные пути (fallback):**
```bash
/data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
/data/user_de/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

### Запуск Avito для refresh

```bash
docker exec redroid am start -n com.avito.android/.MainActivity
```

Avito при запуске автоматически проверяет токен и обновляет его если близок к истечению.

### Проверка статуса Avito

```bash
docker exec redroid pidof com.avito.android
```

---

## Парсинг JWT

JWT состоит из 3 частей, разделённых точкой:
```
HEADER.PAYLOAD.SIGNATURE
```

**Декодирование payload:**
```python
import base64
import json

def parse_jwt(token: str) -> dict:
    parts = token.split('.')
    if len(parts) < 2:
        return None

    payload = parts[1]
    # Fix base64 padding
    payload += '=' * (4 - len(payload) % 4)

    decoded = base64.urlsafe_b64decode(payload)
    return json.loads(decoded)

# Пример:
claims = parse_jwt(session_token)
exp = claims['exp']        # 1770104756
user_id = claims['u']      # 157920214
```

---

## Переменные окружения (.env)

```env
# Backend
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026

# Redroid
REDROID_CONTAINER=redroid
AVITO_PACKAGE=com.avito.android

# Timing
CHECK_INTERVAL=1800
```

| Переменная | Default | Описание |
|------------|---------|----------|
| `BACKEND_URL` | — | URL Backend API |
| `BACKEND_API_KEY` | — | API-ключ для авторизации |
| `REDROID_CONTAINER` | `redroid` | Имя Docker-контейнера |
| `AVITO_PACKAGE` | `com.avito.android` | Package name Avito |
| `CHECK_INTERVAL` | `1800` | Интервал проверки (сек) = 30 мин |

---

## Что возвращает (результат работы)

1. **Токены на Backend** — через `POST /api/v1/sessions`
2. **Логи** — stdout с событиями:
   - `[INFO] Session read: exp=1770104756, hours_left=12.5`
   - `[INFO] Token unchanged, skipping sync`
   - `[WARN] Token expires in 1.5h, launching Avito...`
   - `[INFO] Token refreshed! New exp=1770191156`
   - `[ERROR] Token expired and Avito failed to refresh`

---

## Первоначальная настройка

**Один раз (вручную):**

1. Запустить Redroid:
   ```bash
   docker compose -f docker-compose.redroid.yml up -d
   ```

2. Подключиться через scrcpy:
   ```bash
   adb connect localhost:5555
   scrcpy
   ```

3. Установить Avito APK:
   ```bash
   adb install avito.apk
   ```

4. Открыть Avito, авторизоваться по SMS

5. **Обязательно:** открыть вкладку "Сообщения"
   - Это активирует сохранение токенов в SharedPreferences

6. Запустить Token Bridge:
   ```bash
   python src/bridge.py
   ```

7. Проверить синхронизацию:
   ```bash
   curl http://localhost:8080/api/v1/session -H "X-Api-Key: <key>"
   ```

---

## Логика обновления токена

```
Токен живёт 24 часа.

Проверка каждые 30 минут:
├─ > 2 часов осталось → ничего не делать (или sync если токен новый)
├─ 0-2 часа осталось → запустить Avito, дождаться refresh, синхронизировать
└─ Истёк → запустить Avito, подождать дольше, попробовать синхронизировать

Avito автоматически обновляет токен при запуске приложения,
если он близок к истечению или уже истёк.

После запуска Avito:
├─ Ждём 30-60 сек (приложение инициализируется, делает refresh)
├─ Перечитываем SharedPreferences
├─ Если exp изменился → токен обновился → синхронизируем
└─ Если exp не изменился → проблема, логируем ошибку
```
