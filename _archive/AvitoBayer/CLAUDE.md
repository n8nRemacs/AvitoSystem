# AvitoBayer

Автоматизированная система сканирования Avito и управления лидами для покупки iPhone на рефаб.

## Стек

- **Python 3.10+**, FastAPI, Pydantic 2, httpx (SOCKS5), uvicorn
- **MCP server** (mcp[cli]) — 11 инструментов для Claude Code
- **Supabase** (self-hosted, 213.108.170.194:8000) — PostgreSQL 15
- **Vue 3 + Naive UI** — фронтенд-компоненты (AvitoView.vue, ScannedItemsView.vue)

## Структура

```
api.py              — REST API (FastAPI, порт 8132) + lifespan + scheduler
server.py           — MCP server (stdio, 11 tools)
scheduler.py        — Async scan loop (asyncio.Task, без APScheduler)
notifier.py         — Telegram-уведомления (scan summary, leads, price alerts)
xapi_client.py      — HTTP-клиент к avito-xapi (search, messenger, items)
supabase_client.py  — Supabase PostgREST обёртка (все таблицы)
config.py           — Pydantic Settings (.env)
migration_leads.sql — Схема БД (5 таблиц + seed правила)
avitobayer.service  — systemd unit для Homelab
TZ-SCAN-LOOP.md     — Техническое задание (scheduler + notifier + deploy)
```

## Запуск

```bash
# Установка
pip install -r requirements.txt

# MCP-сервер (для Claude Code)
python server.py

# REST API + scheduler
python api.py  # → http://0.0.0.0:8132
```

## База данных

5 таблиц в Supabase (self-hosted):
- `search_processing_rules` — правила обработки (buy/competitors/price_monitor)
- `saved_searches` — сохранённые поиски с URL и привязкой к правилам
- `search_runs` — история запусков (статистика цен, кол-во новых)
- `scanned_items` — просканированные объявления + LLM-оценка (verdict/score/flags)
- `leads` — воронка лидов (new → selected → negotiation → closed)

Миграция: `migration_leads.sql` — применять через psql или Supabase SQL Editor.

## API endpoints

| Группа | Путь | Описание |
|--------|------|----------|
| Health | `GET /health` | Статус сервиса |
| Searches | `/api/searches` | CRUD сохранённых поисков |
| Rules | `/api/rules` | CRUD правил обработки |
| Scanned | `/api/scanned` | Просмотр + обновление статусов |
| Leads | `/api/leads` | CRUD лидов |
| Runs | `GET /api/runs/{search_id}` | История запусков |
| Scheduler | `/api/scheduler/{start,stop,status,run/*}` | Управление планировщиком |
| Telegram | `POST /api/tg/send` | Ручная отправка в TG |

## MCP tools (server.py)

- **Search**: `search_items`, `get_item_details`
- **Messenger**: `get_channels`, `get_messages`, `send_message`, `create_chat_by_item`, `mark_chat_read`, `get_unread_count`
- **Leads**: `create_lead`, `get_leads`, `update_lead`
- **Saved Searches**: `save_search`, `list_searches`, `get_search_details`, `update_search`, `delete_search`, `parse_search_url`
- **Rules**: `list_rules`, `create_rule`, `update_rule`
- **History**: `get_search_history`

## Деплой (Homelab)

```bash
# На сервере 213.108.170.194
cp avitobayer.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now avitobayer
journalctl -u avitobayer -f
```

Порт: **8132** (не 8131 — конфликт с orchestrator-mcp).

## Сеть

- **Avito XApi**: `https://avito.newlcd.ru/api/v1` — поиск, мессенджер, карточки
- **Telegram**: через SOCKS5 `127.0.0.1:1080` (api.telegram.org заблокирован)
- **Claude API** (LLM eval): через тот же SOCKS5 прокси
- **Supabase**: локальный `http://213.108.170.194:8000`

## Конфигурация

Все настройки в `.env` (см. `.env.example`). Ключевые:
- `XAPI_BASE_URL`, `XAPI_API_KEY` — доступ к avito-xapi
- `SUPABASE_URL`, `SUPABASE_KEY` — Supabase self-hosted
- `TG_NOTIFY_*` — Telegram-бот, чат, прокси
- `SCHEDULER_AUTOSTART` — автозапуск сканера при старте API
- `LLM_API_KEY`, `LLM_MODEL` — Claude для оценки объявлений

## Правила работы

1. Scheduler использует `asyncio.Task` + `asyncio.sleep`, не APScheduler
2. Дедупликация по `(item_id, search_id)` в `scanned_items`
3. LLM-вердикты: `ok`, `partial`, `risk`, `skip` (score 0-10)
4. Лиды создаются автоматически при `score >= score_threshold`
5. Интервалы по умолчанию: buy=30мин, competitors=360мин, price_monitor=120мин
6. Не коммить `.env` — содержит ключи и токены
