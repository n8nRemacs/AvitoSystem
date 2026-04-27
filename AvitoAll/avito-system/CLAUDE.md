# avito-system — Старая архитектура (7 частей)

**Назначение:** Полное ТЗ системы мониторинга Avito для скупки товаров: поиск → AI-анализ → автоматическое приветствие продавца. Только документация, без реализации.

**Статус:** archive — ТЗ написано, код не реализован. Заменяется текущим V1.

**Стек/технологии:** FastAPI, SQLite, Vue 3, Python, aiogram 3, Kotlin (Android), Docker, curl_cffi, WebSocket.

## Что внутри

| Папка/файл | Что это |
|------------|---------|
| `part1-backend/` | Backend API (FastAPI :8080) — хранение поисков, токенов, результатов |
| `part2-frontend/` | Web-панель (Vue 3 :3000) — управление поисками и правилами |
| `part3-worker/` | Worker: мониторинг Avito + AI-анализ + автоприветствие |
| `part4-telegram/` | Telegram-бот (aiogram 3) — уведомления и команды |
| `part5-token-bridge/` | Извлечение токенов из Redroid (Docker Android) |
| `part6-Android-token/` | Извлечение токенов с рут-телефона (Kotlin APK) |
| `part7-messager/` | Полнофункциональный Avito Messenger (WS + HTTP, 20 методов) |
| `contracts/` | JSON-схемы (session, search, item, rule) + API Reference |
| `avito-redroid/` | Dockerfile + скрипты для Redroid: маскировка build.prop, генерация fingerprint |
| `DATABASE.md` | Структура SQLite БД |
| `ASSEMBLY.md` | Инструкция по сборке и запуску всей системы |
| `docker-compose.yml` | Production оркестрация всех 7 частей |

## Архитектура (кратко)

```
Token (part5 или part6) → Backend API (part1) ← Worker (part3) → AI анализ → авто-сообщение
                                    ↓
                    Frontend (part2) + Telegram (part4) + Messenger (part7)
```

Backend — центральная шина. Все части общаются только через него.

## Что полезно для V1

- **`contracts/`** — JSON-схемы session/search/item/rule: готовые модели данных для V1.
- **`part3-worker/SPEC.md`** — детальный алгоритм воркера: параметры поиска Avito API, логика дедупликации, AI-вердикты (OK/RISK/SKIP), rate limit. **Главный reference для V1 worker.**
- **`avito-redroid/scripts/`** — генераторы `build_prop_gen.py`, `fingerprint_gen.py`, `device_profile_gen.py` — утилиты для создания уникальных device-профилей.
- **`part7-messager/SPEC.md`** — 20 методов Avito Messenger API, включая IP-телефонию и пагинацию до 3000+ чатов.
- **`DATABASE.md`** — схема БД с индексами, можно взять как основу.

## Что НЕ использовать

Кода нет ни в одной папке — только SPEC.md, API.md, TESTING.md. Это чистое ТЗ, не запускаемый проект. Не пытаться запустить docker-compose — там нет реальных сервисов.

## Ссылки

- Корень: `../CLAUDE.md`
- Текущий проект V1: `../../avito-xapi/`
