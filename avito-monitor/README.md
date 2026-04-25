# Avito Monitor (V1.2)

Персональная система мониторинга Avito и ценовой разведки. См. `../DOCS/TZ_Avito_Monitor_V1.md` (главное ТЗ) и `../DOCS/V1_EXECUTION_PLAN.md` (план реализации).

**Текущий статус:** Блок 0 — каркас. Поднимается `app` (FastAPI), `db` (Postgres 16), `redis` (Redis 7). Доступна страница логина и пустой дашборд с надписью «V1.2».

---

## Быстрый старт

Требуется Docker Desktop. `make` опционален — на Windows можно запускать команды напрямую через `docker compose`.

### 1. Подготовь `.env`

```bash
cp .env.example .env
# открой .env и впиши APP_SECRET_KEY (любые ≥32 случайных символа)
```

PowerShell-вариант:
```powershell
Copy-Item .env.example .env
```

### 2. Подними сервисы

С `make`:
```bash
make up
```

Без `make` (Windows / голый docker):
```bash
docker compose up -d --build
```

Поднимутся 3 контейнера: `app`, `db`, `redis`. На `db` стоит healthcheck — `app` стартует только когда Postgres готов.

### 3. Применить миграции

```bash
make migrate
# или:
docker compose run --rm app alembic upgrade head
```

Создаст таблицы `users` и `system_settings`.

### 4. Создать админа

```bash
make admin user=owner pass=your-strong-password
# или:
docker compose run --rm app python -m scripts.create_admin owner your-strong-password
```

### 5. Открой дашборд

http://localhost:8000/login → введи логин/пароль → откроется dashboard с бейджем «V1.2».

---

## Полезные команды

| Команда | Эквивалент `docker compose` |
|---|---|
| `make logs service=app` | `docker compose logs -f app` |
| `make ps` | `docker compose ps` |
| `make down` | `docker compose down` |
| `make migration name=add_search_profiles` | `docker compose run --rm app alembic revision --autogenerate -m "add_search_profiles"` |
| `make shell` | `docker compose exec app /bin/bash` |

---

## Структура

```
avito-monitor/
├── app/                # FastAPI-приложение
│   ├── main.py
│   ├── config.py       # pydantic-settings
│   ├── deps.py         # FastAPI DI
│   ├── db/
│   │   ├── base.py     # async engine + sessionmaker
│   │   └── models/     # SQLAlchemy 2.0 модели
│   ├── services/       # бизнес-логика (auth и т.д.)
│   ├── web/            # Jinja2-страницы (login, dashboard)
│   └── ...
├── alembic/            # миграции
├── scripts/            # CLI-утилиты (create_admin)
├── shared/             # модели, общие с avito-mcp (Блок 1+)
└── tests/
```

---

## Что дальше

См. `../DOCS/V1_EXECUTION_PLAN.md`:

- **Блок 1** — `avito-mcp` MCP-сервер (4 tools)
- **Блок 2** — Search Profiles (БД + CRUD + дашборд)
- **Блок 3** — LLM Analyzer
- **Блок 4** — Worker pipeline (TaskIQ)
- **Блок 5** — Telegram bot
- **Блок 6** — Дашборд statistics
- **Блок 7** — Price Intelligence
- **Блок 8** — Polish + deploy на homelab
