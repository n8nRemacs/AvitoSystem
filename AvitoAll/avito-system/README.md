# Avito System — Автоматический мониторинг и скупка товаров на Avito

## Что это

Система автоматического мониторинга объявлений на Avito для поиска выгодных предложений по электронике. Ищет товары по заданным критериям (модель, цена, доставка), анализирует их через AI на дефекты и красные флаги, фильтрует зарезервированные, и автоматически отправляет приветствие продавцу при положительном вердикте. Полнофункциональный мессенджер позволяет вести диалоги с продавцами в реальном времени.

## Как это работает

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│   1. ТОКЕНЫ                              2. УПРАВЛЕНИЕ                 │
│                                                                        │
│   Redroid (Android Docker)               Веб-панель (:3000)           │
│   ├── Avito APK + авторизация            ├── Добавить поиск            │
│   ├── Token Bridge извлекает             │   "iPhone 12 Pro"           │
│   └── POST /api/v1/sessions             │   10 000 — 25 000 ₽        │
│              │                           ├── Настроить AI-правила      │
│   Android-телефон (root)                 └── Смотреть результаты       │
│   ├── AvitoSessionManager APK                                          │
│   ├── Читает токены через su             ┌─────────────────────────┐   │
│   └── POST /api/v1/sessions             │ 5. МЕССЕНДЖЕР            │   │
│              │                           │                          │   │
│              ▼                           │ WebSocket + HTTP REST    │   │
│   Backend API (:8080)  ◄────────────────│ wss://socket.avito.ru   │   │
│   Хранит: токены, поиски,               │ ├── Real-time сообщения  │   │
│   правила, результаты,                  │ ├── Чаты, история        │   │
│   диалоги, сообщения                    │ ├── Typing, медиа        │   │
│              │                           │ └── IP-телефония         │   │
│              ▼                           └─────────────────────────┘   │
│   3. МОНИТОРИНГ                                                        │
│                                                                        │
│   Worker (фоновый процесс, каждые 60 сек)                             │
│   ├── Ищет на Avito API (/api/11/items)                               │
│   ├── Фильтрует зарезервированные                                     │
│   ├── AI-анализ (OpenRouter / Claude):                                │
│   │   ├── iCloud Lock? → SKIP                                        │
│   │   ├── Разбит экран? → SKIP                                       │
│   │   ├── Подозрительная цена? → RISK                                │
│   │   └── Всё ок? → OK (8/10) → авто-приветствие через Messenger     │
│   └── Результат → Backend → Telegram уведомление                     │
│                                                                        │
│   4. УВЕДОМЛЕНИЯ                                                       │
│                                                                        │
│   Telegram Bot                                                         │
│   ├── ✅ iPhone 12 Pro 128GB — 15 000 ₽  AI: 8/10                    │
│   ├── ⚠️ iPhone 12 Pro 64GB — 6 000 ₽   Подозрительная цена         │
│   └── Быстрые команды: /add, /list, /status                          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## Из чего состоит

Система разбита на 7 независимых частей. Каждая живёт в своей папке, имеет своё ТЗ (`SPEC.md`), API-описание (`API.md`), план тестов (`TESTING.md`), и общается с остальными только через HTTP API.

| # | Часть | Папка | Что делает | Стек |
|---|-------|-------|------------|------|
| 1 | **Backend API** | `part1-backend/` | Центральное хранилище и REST API | FastAPI + SQLite |
| 2 | **Web Panel** | `part2-frontend/` | Управление поисками, правилами, результаты | Vue 3 + Vite |
| 3 | **Worker** | `part3-worker/` | Мониторинг Avito, AI-анализ, автосообщения | Python + curl_cffi + OpenRouter |
| 4 | **Telegram Bot** | `part4-telegram/` | Уведомления и быстрые команды | aiogram 3 |
| 5 | **Token Bridge** | `part5-token-bridge/` | Извлечение токенов из Redroid (Docker) | Python + docker exec |
| 6 | **Android Token** | `part6-Android-token/` | Извлечение токенов с рутованного телефона | Kotlin + libsu |
| 7 | **Messenger** | `part7-messager/` | Полнофункциональный Avito Messenger | Python + curl_cffi + WebSocket |

## Источники токенов (Part 5 vs Part 6)

Part 5 и Part 6 — взаимозаменяемы. Оба отправляют токены на один Backend API.

| | Part 5: Token Bridge | Part 6: Android Token |
|--|---------------------|----------------------|
| Платформа | Сервер + Redroid (Docker) | Рутованный смартфон |
| Чтение токенов | `docker exec cat` | `su -c cat` (libsu) |
| Обновление | `am start` через docker | `startActivity()` нативно |
| Интерфейс | Логи в stdout | Android UI + Notifications + Telegram |
| Автозапуск | systemd | BootReceiver + Foreground Service |

Можно использовать оба одновременно (разные аккаунты Avito).

## Messenger (Part 7)

Полнофункциональный клиент Avito Messenger с двумя транспортами:

- **WebSocket JSON-RPC** — real-time: приём/отправка сообщений, typing, push events
- **HTTP REST** — batch: списки каналов, история, пагинация (до 3000+ чатов)
- **IP-телефония** — история звонков + скачивание записей

20 методов: текст, изображения, голосовые, видео, файлы, создание чатов, typing, read.

## AI-анализ

Каждое новое объявление проходит анализ через LLM (Claude Sonnet via OpenRouter):

**Вердикты:**
- **OK** (score 7-10) → уведомление + авто-приветствие через Messenger
- **RISK** (score 4-6) → уведомление с предупреждением
- **SKIP** (score 1-3) → тихо пропускается

## Быстрый старт

```bash
# 1. Клонировать
git clone <repo> avito-system && cd avito-system

# 2. Настроить .env в каждой части (см. ASSEMBLY.md)

# 3. Запустить всё
docker compose up -d

# 4. Настроить источник токенов:
#    Вариант A: Redroid (Part 5) — установить Avito APK, авторизоваться
#    Вариант B: Android (Part 6) — установить APK на рутованный телефон

# 5. Открыть веб-панель: http://localhost:3000
#    Добавить поиск → система начнёт мониторинг
```

Подробная инструкция: [ASSEMBLY.md](./ASSEMBLY.md)

## Документация

| Файл | Описание |
|------|----------|
| [ASSEMBLY.md](./ASSEMBLY.md) | Инструкция по сборке и запуску |
| [DATABASE.md](./DATABASE.md) | Структура базы данных |
| [TESTING.md](./TESTING.md) | Мастер-план тестирования |
| `partN-*/SPEC.md` | ТЗ каждой части |
| `partN-*/API.md` | API-описание каждой части |
| `partN-*/TESTING.md` | План тестов каждой части |

## Разработка

Части разрабатываются **параллельно** без конфликтов:

```bash
Терминал 1: cd part1-backend      && python src/server.py     # :8080 (ПЕРВЫМ!)
Терминал 2: cd part2-frontend     && npm run dev               # :3000
Терминал 3: cd part3-worker       && python src/worker.py
Терминал 4: cd part4-telegram     && python src/bot.py
Терминал 5: cd part5-token-bridge && python src/bridge.py      # Redroid
Терминал 6: cd part7-messager     && python src/messenger.py   # Messenger
```

Part 6 (Android Token) — отдельное APK-приложение, собирается через `./gradlew assembleRelease`.
