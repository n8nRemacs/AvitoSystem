# AvitoSystem

**Назначение:** Персональная система мониторинга Avito и ценовой разведки. Автоматический поиск объявлений по URL Avito с LLM-классификацией и фильтрацией + рыночная аналитика + Telegram-уведомления. Управление через веб-дашборд.

**Статус:** V1.2 — ТЗ финализировано после полного исследования Avito API, начинается реализация в новом монорепо `avito-monitor/`. Существующие подпроекты (`avito-xapi`, `AvitoBayer`) — рабочая база для переноса компонентов.

---

## 🚀 При старте новой сессии — прочитай в этом порядке

1. **`DOCS/V1_EXECUTION_PLAN.md`** — компактный план реализации (8 блоков, что делать, что проверять)
2. **`DOCS/TZ_Avito_Monitor_V1.md`** (версия 1.2) — основное ТЗ
3. **`DOCS/DECISIONS.md`** — 10 ADR с обоснованиями ключевых решений (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM)
4. **`DOCS/RU_PROXY_SETUP.md`** — обязательный SOCKS5-туннель к homelab для запросов к Avito (без него 429)
5. **`DOCS/avito_api_snapshots/README.md`** — полученные данные API (категории, поля, XML-каталоги брендов/моделей)

**Глобальные секреты** (Supabase URL, JWT, SSH-алиасы) — в `c:\Projects\Sync\CLAUDE.md`.
**Avito Official API credentials** — в `c:\Projects\Sync\AvitoSystem\.env` (gitignored).

---

## Карта подпроектов

| Папка | Что это | Статус | Порт |
|---|---|---|---|
| `avito-xapi/` | FastAPI-шлюз к мобильному API Avito (curl-cffi, JWT auth, WS) | working | 8080 |
| `AvitoBayer/` | Прототип: FastMCP + scheduler + LLM-оценка + Telegram | working prototype | 8132 |
| `tenant-auth/` | Сервис аутентификации тенантов (FastAPI + JWT + OTP провайдеры) | WIP | 8090 |
| `avito-frontend/` | Vue 3 SPA (Pinia + Tailwind + Naive UI) | not_used_in_v1 | 3000 |
| `avito-farm-agent/` | Python+JS агент для Android (Frida, перехват токенов) | prototype | — |
| `supabase/migrations/` | SQL-миграции исходной схемы (не Alembic) | working | — |
| `AvitoAll/` | Результаты реверс-исследования Avito API (скрипты, сессии) | archive/research | — |
| `DOCS/` | Вся документация: ТЗ, API-спека, архитектура, деплой | актуальна | — |

**Docker Compose (корень):** три сервиса — xapi:8080, tenant-auth:8090, frontend:3000.

---

## Главные сущности (V1.2)

- **SearchProfile** — профиль мониторинга. Хранит **URL поиска Avito** (юзер копирует из веб-UI), плюс overlay (region_slug, search/alert вилки, sort, delivery), плюс LLM-критерии и расписание. Без таксономии и динамических форм фильтров (см. ADR-001).
- **Listing** — объявление с `condition_class` (working / blocked_icloud / broken_screen / ...), статусом обработки, ценой и историей изменений.
- **ProfileRun / ProfileMarketStats** — агрегаты прогонов и рыночная статистика (clean-медиана, тренды, distribution состояний).
- **LLMAnalysis** — кеш результатов LLM по типам: `condition` (классификация состояния), `match` (соответствие критериям), `compare` (price intelligence).
- **Notification** — уведомление с типами: new_listing, price_drop, market_trend_*, historical_low, supply_surge, condition_mix_change, и др.

---

## Что в V1.2 (новый модуль `avito-monitor/`)

Стек ТЗ: FastAPI + HTMX-дашборд + SQLAlchemy 2.0 async + Alembic + TaskIQ/Redis + aiogram Telegram-бот + avito-mcp (4 V1-tools). **Не** SPA. Переиспользует код из `avito-xapi/src/workers/` (curl_cffi, rate_limiter) и подходы из `AvitoBayer/`.

**Двойная вилка** (ADR-008): search-вилка широкая, alert-вилка узкая. Двухступенчатый LLM (ADR-010): дешёвый classify состояния на всех лотах, дорогой match только на alert-зоне с подходящим состоянием. Это даёт корректную статистику рынка без искажений от мусорных лотов.

**НЕ входит в V1:** автоответчик в мессенджере, квалифицирующие вопросы, биллинг, autoload своих объявлений (V2), platform messenger через официальный API.

---

## Конвенции

- Все Python-сервисы: FastAPI + Pydantic v2 + структура `src/`
- Авторизация в xapi — через `X-Api-Key` header (хэш SHA-256 в Supabase)
- JWT (user JWT в tenant-auth) — HS256, секрет из `CLAUDE.md` глобального
- Supabase self-hosted (213.108.170.194:8000) — используется в AvitoBayer и xapi
- `AvitoAll/` — не трогать, разбирается отдельным агентом

---

## Связано с ТЗ V1

`DOCS/TZ_Avito_Monitor_V1.md` — главный документ. Разделы 3.1–3.4 описывают архитектуру потоков данных, раздел 4 — функциональные требования, раздел 2 — технологический стек.
