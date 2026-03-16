# Part 5: Token Bridge (Redroid → Backend)

## Обзор

Скрипт, работающий на сервере рядом с Redroid-контейнером. Извлекает токены Avito из SharedPreferences и синхронизирует на Backend API.

**Стек:** Python 3.11+ / ADB / XML-парсинг
**Папка:** `part5-token-bridge/`
**Работает на:** сервере с Docker/Redroid

## Структура файлов

```
part5-token-bridge/
├── SPEC.md
├── requirements.txt
├── .env.example
├── docker-compose.redroid.yml     # Redroid контейнер
└── src/
    ├── bridge.py                  # Точка входа, цикл мониторинга
    ├── config.py                  # Настройки из .env
    ├── session_reader.py          # Чтение SharedPrefs через ADB/docker exec
    ├── jwt_parser.py              # Парсинг JWT (exp, user_id)
    └── backend_client.py          # HTTP-клиент к Backend API
```

## .env.example

```env
BACKEND_URL=http://localhost:8080
BACKEND_API_KEY=avito_sync_key_2026
REDROID_CONTAINER=redroid
CHECK_INTERVAL=1800
AVITO_PACKAGE=com.avito.android
```

## Архитектура

```
Redroid контейнер
  └── /data/data/com.avito.android/shared_prefs/
      └── com.avito.android_preferences.xml
          ├── session (JWT)
          ├── fpx (fingerprint)
          ├── refresh_token
          ├── device_id
          └── ...
              │
              │ docker exec / adb shell
              ▼
      bridge.py (session_reader.py)
          │ парсинг XML → SessionData
          │ парсинг JWT → exp, user_id
          ▼
      POST /api/v1/sessions → Backend API
```

## Главный цикл (bridge.py)

```
При запуске:
  1. Проверить доступность Redroid контейнера
  2. Прочитать текущую сессию
  3. Отправить на Backend

Цикл (каждые CHECK_INTERVAL секунд = 30 минут):
  1. Прочитать сессию из SharedPrefs
  2. Проверить exp из JWT
  3. Если exp изменился (токен обновился) → синхронизировать на Backend
  4. Если до exp < 2 часов:
     - Запустить Avito через ADB: am start com.avito.android
     - Подождать 30 сек (Avito обновит токен автоматически)
     - Перечитать и синхронизировать
  5. Если токен истёк:
     - Запустить Avito
     - Подождать 60 сек
     - Перечитать
     - Если обновился → синхронизировать
     - Если нет → логировать ошибку
```

## Компоненты

### session_reader.py

```python
class SessionReader:
    def __init__(self, container: str, package: str)

    def read_session(self) -> SessionData | None
```

**Чтение через docker exec:**
```bash
docker exec {container} cat /data/data/{package}/shared_prefs/{package}_preferences.xml
```

**Парсинг XML:**
- Ищет `<string name="session">` → session_token (JWT)
- Ищет `<string name="fpx">` → fingerprint
- Ищет `<string name="refresh_token">` → refresh_token
- Ищет `<string name="device_id">` → device_id
- Fallback имена: `token`, `f`, `fingerprint`

**Пути SharedPreferences (по приоритету):**
1. `/data/data/{package}/shared_prefs/{package}_preferences.xml`
2. `/data/user/0/{package}/shared_prefs/{package}_preferences.xml`
3. `/data/user_de/0/{package}/shared_prefs/{package}_preferences.xml`

### jwt_parser.py

```python
def parse_jwt(token: str) -> dict:
    """Декодирует JWT payload без верификации подписи."""
    # Возвращает: {exp, iat, u (user_id), d (device_id), pl (platform), ...}

def get_expiry(token: str) -> int | None:
    """Возвращает exp timestamp из JWT."""

def hours_until_expiry(token: str) -> float:
    """Часов до истечения (отрицательное = уже истёк)."""
```

### backend_client.py

```python
class BackendClient:
    def __init__(self, url: str, api_key: str)

    def sync_session(self, session: SessionData) -> bool
        # POST /api/v1/sessions
```

## docker-compose.redroid.yml

```yaml
version: '3.8'
services:
  redroid:
    image: redroid/redroid:13.0.0-latest
    container_name: redroid
    privileged: true
    ports:
      - "5555:5555"   # ADB
      - "5900:5900"   # VNC
    volumes:
      - redroid_data:/data
    environment:
      - REDROID_WIDTH=1080
      - REDROID_HEIGHT=2400
      - REDROID_DPI=420
      - REDROID_GPU_MODE=auto
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G

volumes:
  redroid_data:
```

## Первоначальная настройка (ручная)

1. Запустить Redroid: `docker compose -f docker-compose.redroid.yml up -d`
2. Подождать загрузки: `adb connect localhost:5555`
3. Установить Avito APK: `adb install avito.apk`
4. Открыть Avito через scrcpy/VNC
5. Авторизоваться по SMS
6. Открыть вкладку "Сообщения" (активирует сохранение токенов)
7. Запустить bridge.py — начнёт мониторинг

## Обновление токенов

Avito автоматически обновляет JWT при запуске приложения. Bridge:
1. Детектит приближение exp (< 2 часов)
2. Запускает Avito через ADB: `docker exec redroid am start -n com.avito.android/.MainActivity`
3. Ждёт 30-60 сек
4. Перечитывает SharedPrefs — получает новый JWT
5. Отправляет на Backend

## Зависимости (requirements.txt)

```
requests>=2.31.0
python-dotenv>=1.0.0
```

## Запуск

```bash
cd part5-token-bridge
pip install -r requirements.txt
cp .env.example .env
# Убедиться что Redroid запущен
python src/bridge.py
```
