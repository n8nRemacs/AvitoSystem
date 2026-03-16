# Инструкция по сборке — Avito System

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- Git
- Android Studio / Gradle (для Part 6)

## Структура проекта

```
avito-system/
├── part1-backend/          # Backend API (FastAPI :8080)
├── part2-frontend/         # Web Panel (Vue 3 :3000)
├── part3-worker/           # Avito Monitor Worker
├── part4-telegram/         # Telegram Bot
├── part5-token-bridge/     # Redroid Token Bridge (Docker)
├── part6-Android-token/    # Android Token Refresher (APK)
├── part7-messager/         # Avito Messenger (WebSocket + HTTP)
├── contracts/              # JSON-схемы API (общий контракт)
├── docker-compose.yml      # Production: серверные компоненты
├── ASSEMBLY.md             # Эта инструкция
├── DATABASE.md             # Структура БД
├── README.md               # Обзор проекта
└── TESTING.md              # Мастер-план тестирования
```

## 1. Клонирование

```bash
git clone <repo> avito-system
cd avito-system
```

## 2. Настройка переменных окружения

Скопировать `.env.example` → `.env` в каждой части и заполнить:

```bash
# Общий API-ключ (одинаковый везде)
API_KEY=<придумать_свой_ключ>

# Part 1: Backend
cd part1-backend && cp .env.example .env
# Отредактировать: API_KEY, DATABASE_URL

# Part 2: Frontend
cd ../part2-frontend && cp .env.example .env
# Отредактировать: VITE_API_URL, VITE_API_KEY

# Part 3: Worker
cd ../part3-worker && cp .env.example .env
# Отредактировать: BACKEND_URL, BACKEND_API_KEY, OPENROUTER_API_KEY

# Part 4: Telegram
cd ../part4-telegram && cp .env.example .env
# Отредактировать: TELEGRAM_TOKEN, TELEGRAM_ALLOWED_USERS, BACKEND_URL, BACKEND_API_KEY

# Part 5: Token Bridge
cd ../part5-token-bridge && cp .env.example .env
# Отредактировать: BACKEND_URL, BACKEND_API_KEY, REDROID_CONTAINER

# Part 7: Messenger
cd ../part7-messager && cp .env.example .env
# Отредактировать: BACKEND_URL, BACKEND_API_KEY
```

**Part 6 (Android):** настраивается через UI приложения (Settings → Server URL, API Key).

## 3. Установка зависимостей

```bash
# Backend
cd part1-backend && pip install -r requirements.txt

# Frontend
cd ../part2-frontend && npm install

# Worker
cd ../part3-worker && pip install -r requirements.txt

# Telegram
cd ../part4-telegram && pip install -r requirements.txt

# Token Bridge
cd ../part5-token-bridge && pip install -r requirements.txt

# Messenger
cd ../part7-messager && pip install -r requirements.txt

# Android Token (отдельная сборка)
cd ../part6-Android-token && ./gradlew assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

## 4. Порядок запуска (Development)

**Порядок важен!** Backend первым, остальные — в любом порядке.

```bash
# Терминал 1 — Backend API (ПЕРВЫМ!)
cd part1-backend && python src/server.py
# → http://0.0.0.0:8080

# Терминал 2 — Frontend
cd part2-frontend && npm run dev
# → http://localhost:3000

# Терминал 3 — Worker
cd part3-worker && python src/worker.py

# Терминал 4 — Telegram Bot
cd part4-telegram && python src/bot.py

# Терминал 5 — Token Bridge (на сервере с Redroid)
cd part5-token-bridge && python src/bridge.py

# Терминал 6 — Messenger
cd part7-messager && python src/messenger.py
```

**Part 6:** устанавливается на рутованный Android-телефон отдельно.

## 5. Production (Docker Compose)

```bash
docker compose up -d
```

Это запустит:
- `backend` (:8080)
- `frontend` (:3000)
- `worker`
- `telegram`
- `redroid` (:5555 ADB, :5900 VNC)
- `token-bridge`
- `messenger`

**Part 6 (Android Token)** не входит в Docker — это APK для физического телефона.

## 6. Проверка работоспособности

### Backend
```bash
curl http://localhost:8080/health
# {"status": "ok", "timestamp": ...}
```

### Frontend
Открыть `http://localhost:3000` — должна загрузиться веб-панель.

### Token Bridge / Android Token
```bash
curl http://localhost:8080/api/v1/session -H "X-Api-Key: <ключ>"
# Должен вернуть токены (или 404 если ещё не синхронизированы)
```

### Worker
```bash
# Development — stdout
# Docker
docker compose logs -f worker
```

### Messenger
```bash
# Development — stdout (Connected: userId=..., seq=...)
# Docker
docker compose logs -f messenger
```

### Telegram
Отправить `/status` боту — должен ответить статистикой.

## 7. Настройка источников токенов

### Вариант A: Redroid (Part 5) — серверный

1. Запустить Redroid:
   ```bash
   cd part5-token-bridge
   docker compose -f docker-compose.redroid.yml up -d
   ```

2. Подключиться через scrcpy или VNC:
   ```bash
   scrcpy --tcpip=localhost:5555
   # или VNC на порт 5900
   ```

3. Установить Avito APK:
   ```bash
   adb connect localhost:5555
   adb install avito.apk
   ```

4. Авторизоваться в Avito (вручную, SMS)

5. Открыть вкладку "Сообщения" (обязательно!)

6. Запустить Token Bridge:
   ```bash
   python src/bridge.py
   ```

### Вариант B: Android-телефон (Part 6)

1. Собрать APK: `cd part6-Android-token && ./gradlew assembleRelease`
2. Установить на рутованный телефон: `adb install app-release.apk`
3. Открыть AvitoSessionManager → Settings → указать Server URL и API Key
4. Нажать "Read Session" → проверить что токен читается
5. Нажать "Start Service" → запустить фоновый мониторинг

### Проверка синхронизации
```bash
curl http://localhost:8080/api/v1/session -H "X-Api-Key: <ключ>"
# Должен вернуть JSON с session_token, fingerprint, expires_at
```

## 8. Матрица зависимостей

```
                  Зависит от →
                  backend  frontend  worker  telegram  bridge  android  messenger  redroid
backend             -        -        -        -        -       -         -         -
frontend          ✅        -        -        -        -       -         -         -
worker            ✅        -        -        -        -       -         -         -
telegram          ✅        -        -        -        -       -         -         -
bridge            ✅        -        -        -        -       -         -        ✅
android           ✅        -        -        -        -       -         -         -
messenger         ✅        -        -        -        -       -         -         -
```

**Backend не зависит ни от кого** — запускается первым.
Все остальные зависят **только от Backend**.
**Bridge** дополнительно зависит от **Redroid**.
**Android Token** — standalone APK, зависит от Backend только для синхронизации.
**Части не зависят друг от друга** — можно разрабатывать параллельно.

## 9. Обновление

При обновлении одной части — остальные не затрагиваются:

```bash
# Обновить только backend
cd part1-backend && git pull && pip install -r requirements.txt

# Обновить только frontend
cd part2-frontend && git pull && npm install && npm run build

# Обновить только messenger
cd part7-messager && git pull && pip install -r requirements.txt

# Обновить Android Token
cd part6-Android-token && ./gradlew assembleRelease
# Переустановить APK на телефон
```
