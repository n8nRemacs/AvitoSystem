# ТЗ: Scan Loop + Авто-уведомления + Деплой AvitoBayer

Обновлено: 2026-03-25 19:00 (GMT+4)

## Цель

Превратить AvitoBayer из ручного инструмента в автономный сервис:
- Автоматический прогон saved_searches по расписанию
- Автоматическая отправка новых лидов в Telegram (Avito-бот)
- Деплой как systemd-сервис на Homelab

---

## Контекст

**Проект:** `C:\Projects\Sync\AvitoSystem\AvitoBayer`
**Сервер:** 213.108.170.194 (Homelab)
**REST API:** порт 8131 (api.py)
**БД:** Homelab Supabase (http://213.108.170.194:8000)
**Avito-бот:** `8703595821:AAGt0Xi3tNBscmyfa_-9yUy9PMQ8KcrsXNA` (chat_id: 6416413182)
**XApi:** https://avito.newlcd.ru/api/v1

### Что уже есть
- REST API — CRUD searches, rules, leads, tg/send
- MCP server — 20+ инструментов для Claude Code
- XApiClient → avito.newlcd.ru (поиск, детали, мессенджер)
- LLM-оценка (verdict: ok/partial/risk/skip, score 0-10)
- Отправка в Telegram через `/api/tg/send` (ручная, по одному item)
- БД: saved_searches, search_processing_rules, search_runs, leads, scanned_items

### Чего не хватает
- **Scan loop** — нет автоматического прогона saved_searches
- **Авто-уведомления** — нет автоматической отправки новых лидов в Telegram
- **Деплой** — не крутится как сервис на Homelab

---

## Этап 1 — Scan Loop (scheduler)

### 1.1 Новый файл: `scheduler.py`

APScheduler (или asyncio-based) с логикой:

1. При старте загрузить все `saved_searches` где `is_active = true`
2. Для каждого search получить `processing_rules` через `processing_rules_id`
3. Запланировать прогон с интервалом `check_interval_minutes` из правила
4. Дефолтные интервалы (из seed-правил):
   - buy: 30 мин
   - competitors: 360 мин
   - price_monitor: 120 мин

### 1.2 Логика одного прогона (`run_scan`)

```
async def run_scan(search_id: str) -> ScanResult:
```

Шаги:
1. Получить saved_search из БД
2. Получить связанные processing_rules
3. Вызвать `xapi_client.search_items()` с параметрами из search URL
4. Для каждого item:
   - Проверить есть ли уже в scanned_items (по item_id) — дедупликация
   - Новые → LLM-оценка (если настроена в правиле)
   - Сохранить в scanned_items
5. Отфильтровать по `score_threshold` из правила
6. Квалифицированные → автоматически создать leads (если `max_leads_per_run > 0`)
7. Записать search_run (results_count, avg_price, new_items_count, leads_created)
8. Обновить saved_search (last_run_at, last_results_count)
9. Вернуть результат для уведомлений

### 1.3 Управление через API

Добавить эндпоинты в `api.py`:

| Эндпоинт | Метод | Назначение |
|-----------|-------|------------|
| `/api/scheduler/status` | GET | Статус scheduler: running/stopped, список задач с next_run |
| `/api/scheduler/start` | POST | Запустить scheduler |
| `/api/scheduler/stop` | POST | Остановить scheduler |
| `/api/scheduler/run/{search_id}` | POST | Принудительный прогон одного search |
| `/api/scheduler/run-all` | POST | Принудительный прогон всех активных |

### 1.4 Перезагрузка расписания

При изменении saved_search или processing_rules через API — обновить расписание в scheduler без рестарта.

---

## Этап 2 — Авто-уведомления в Telegram

### 2.1 Новый файл: `notifier.py`

Модуль отправки уведомлений в Avito-бот.

**Бот:** `8703595821:AAGt0Xi3tNBscmyfa_-9yUy9PMQ8KcrsXNA`
**Chat_id:** `6416413182`
**Прокси:** SOCKS5 через Homelab (api.telegram.org заблокирован)

### 2.2 Типы уведомлений

#### После каждого скана — сводка

```
📊 Скан: iPhone 15 Pro Max Москва
Найдено: 47 | Новых: 3 | Лидов: 2
Цены: 65 000 – 89 000 ₽ (медиана 74 500 ₽)
```

Отправлять только если есть новые items или изменения цен.

#### Новый лид — карточка

Использовать существующую логику из `/api/tg/send` (api.py:444-517):
- Фото + verdict emoji + title + price
- Score, green/red flags, missing info
- Ссылка на Avito

Отправлять автоматически для лидов с `score >= score_threshold`.

#### Алерты по правилам

Из processing_rules:
- `alert_on_new: true` → уведомление о новых items (тип buy)
- `alert_on_price_change: true` → уведомление об изменении цены (тип competitors)
- `alert_on_price_drop_pct: 10` → уведомление о падении цены >10% (тип price_monitor)

### 2.3 Формат алертов

```
🔻 Цена упала: iPhone 15 Pro 256GB
85 000 ₽ → 72 000 ₽ (−15%)
avito.ru/...
```

```
🆕 Новый конкурент: iPhone 15 Pro Max
79 990 ₽ | Москва
avito.ru/...
```

### 2.4 Конфигурация

В `.env`:
```
TG_NOTIFY_BOT_TOKEN=8703595821:AAGt0Xi3tNBscmyfa_-9yUy9PMQ8KcrsXNA
TG_NOTIFY_CHAT_ID=6416413182
TG_NOTIFY_PROXY=socks5://127.0.0.1:1080
TG_NOTIFY_ENABLED=true
```

---

## Этап 3 — Интеграция в api.py

### 3.1 Lifespan

При старте api.py:
- Инициализировать scheduler
- Инициализировать notifier
- Автозапуск scheduler (если `SCHEDULER_AUTOSTART=true`)

### 3.2 Хук после скана

`run_scan()` → результат → `notifier.send_scan_summary()` + `notifier.send_new_leads()`

### 3.3 Хук при создании лида

При автосоздании лида через scan loop → `notifier.send_lead_card()`

---

## Этап 4 — Деплой

### 4.1 Systemd сервис

```ini
[Unit]
Description=AvitoBayer REST API + Scheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/mnt/projects/repos/AvitoSystem/AvitoBayer
EnvironmentFile=/mnt/projects/repos/AvitoSystem/AvitoBayer/.env
ExecStart=/mnt/projects/repos/AvitoSystem/AvitoBayer/venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8131
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.2 Деплой на Homelab

```bash
# Скопировать проект
scp -r AvitoBayer root@213.108.170.194:/mnt/projects/repos/AvitoSystem/

# Создать venv и установить зависимости
ssh root@213.108.170.194 'cd /mnt/projects/repos/AvitoSystem/AvitoBayer && python3 -m venv venv && venv/bin/pip install -r requirements.txt'

# Установить и запустить сервис
ssh root@213.108.170.194 'systemctl enable --now avitobayer'
```

### 4.3 Порт

8131 — уже прописан в api.py, конфликтов нет (orchestrator-mcp тоже 8131 — **проверить и развести**).

---

## Файлы

| Действие | Файл | Назначение |
|----------|------|------------|
| Создать | `scheduler.py` | Scan loop, APScheduler, run_scan() |
| Создать | `notifier.py` | Telegram уведомления в Avito-бот |
| Изменить | `api.py` | Lifespan + scheduler endpoints + хуки уведомлений |
| Изменить | `config.py` | Новые настройки: TG_NOTIFY_*, SCHEDULER_* |
| Изменить | `.env` | Добавить TG_NOTIFY_*, SCHEDULER_AUTOSTART |
| Изменить | `requirements.txt` | Добавить APScheduler (если используется) |
| Создать | `avitobayer.service` | Systemd unit file |

---

## Что НЕ трогаем

- server.py (MCP режим) — без изменений
- xapi_client.py — без изменений
- supabase_client.py — без изменений
- Миграции БД — таблицы уже есть
- Frontend (AvitoView.vue, ScannedItemsView.vue) — без изменений

---

## Порядок работы

| Шаг | Что | Зависимости |
|-----|-----|-------------|
| 1 | `config.py` — добавить настройки | — |
| 2 | `notifier.py` — Telegram клиент | 1 |
| 3 | `scheduler.py` — scan loop + run_scan | 1, 2 |
| 4 | `api.py` — lifespan + endpoints + хуки | 1, 2, 3 |
| 5 | `.env` — заполнить переменные | 1 |
| 6 | Тест локально | 1-5 |
| 7 | Деплой на Homelab | 6 |
| 8 | Проверить: скан → лид → уведомление в Avito-бот | 7 |

---

## Конфликт портов

orchestrator-mcp уже на порту 8131. Варианты:
- AvitoBayer → **8132**
- Или orchestrator-mcp → другой порт

Решить перед деплоем.

---

## Критерии готовности

1. Scheduler автоматически прогоняет активные saved_searches по интервалу из rules
2. Новые items сохраняются в scanned_items с дедупликацией
3. Квалифицированные items автоматически создаются как leads
4. После каждого скана — сводка в Avito-бот
5. Новые лиды с фото — карточки в Avito-бот
6. Алерты по правилам (цена упала, новый конкурент)
7. API endpoints для управления scheduler
8. Systemd сервис на Homelab
9. Scheduler не ломается при ошибках отдельных searches
