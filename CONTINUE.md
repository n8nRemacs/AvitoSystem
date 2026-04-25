# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude и видишь этот файл первым:** ты подхватываешь работу над V1 системы мониторинга Avito. Прочитай этот файл целиком, потом проверь сервисы по разделу 2, потом выбери действие из раздела 4. Детали по конкретному блоку — в `DOCS/V1_BLOCKS_TZ.md` §4.
>
> **Если ты — пользователь:** просто скопируй этот файл целиком в новую сессию Claude Code, и работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito + ценовой разведки. Single-user, homelab-deploy, Avito-Cosplay UI.

### Готово (закоммичено в git)

| Блок | Что | Коммит |
|---|---|---|
| Block 0 | Каркас FastAPI + SQLAlchemy 2.0 + auth + Avito-Cosplay light theme + Inter | `0c2be7f` |
| Block 1 (UI design spec) | `DOCS/UI_DESIGN_SPEC_V1.md` + `AvitoSystemUI.zip` (Claude Design выдал 8 hero-screens × 2 стиля, выбран Avito-Cosplay) | `0c2be7f` |
| Block 2 | 8 SQLAlchemy моделей §5.1 + URL-парсер + двойная вилка ±25% + sidebar+topbar layout + 4 страницы профилей + REST API + 3 demo-профиля | `0c2be7f` |
| Документация | `DOCS/V1_BLOCKS_TZ.md` — per-block self-contained TZ + parallelization matrix | `251d78d` |

### В работе / следующий шаг

**Зависит от того, есть ли инфраструктура:**
- ❓ Рутирован ли OnePlus 8t? Установлен ли AvitoSessionManager APK? Льётся ли токен в Supabase?
- ❓ Развёрнут ли avito-xapi на homelab (213.108.170.194:8080) и работает?

Проверь через раздел 2 ниже. По результату — раздел 4.

### Что осталось (7 блоков)

`Block 1 (avito-mcp)`, `Block 3 (LLM Analyzer)`, `Block 4 (worker)`, `Block 5 (TG bot)`, `Block 6 (stats charts)`, `Block 7 (price intel)`, `Block 8 (deploy + 72h soak)`. Подробности — `DOCS/V1_BLOCKS_TZ.md`.

---

## 2. Поднять сервисы (Quick Health Check)

Запускай команды из репо-корня `c:/Projects/Sync/AvitoSystem/`. Если какой-то шаг падает — иди в раздел 3 «Восстановление».

### 2.1. SOCKS5-туннель к homelab (нужен для запросов к Avito с зарубежной машины)

```bash
curl -s --max-time 5 --socks5-hostname 127.0.0.1:1081 https://ifconfig.me
# Ожидаемый ответ: 213.108.170.194
```

Если пустой ответ — туннель упал. **Поднять:**
```bash
ssh -D 127.0.0.1:1081 -N -f homelab
```

(SessionStart hook `.claude/settings.json` поднимает его автоматически в начале каждой сессии — обычно делать ничего не надо.)

### 2.2. Docker Desktop

```bash
docker info >/dev/null 2>&1 && echo "✅ docker up" || echo "❌ docker down"
```

Если down — запусти Docker Desktop вручную через Windows GUI (или PowerShell):
```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# Подожди ~30-60 секунд пока daemon запустится
```

### 2.3. avito-monitor стек (app + db + redis)

```bash
cd c:/Projects/Sync/AvitoSystem/avito-monitor
docker compose ps
```

Ожидаемый вывод — три контейнера в статусе `Up` / `healthy`:
```
avito-monitor-app-1     Up   0.0.0.0:8000->8000/tcp
avito-monitor-db-1      Up (healthy)   5432/tcp
avito-monitor-redis-1   Up   6379/tcp
```

Если контейнеры не запущены:
```bash
docker compose up -d
sleep 5
docker compose ps
```

### 2.4. Приложение отвечает

```bash
curl -s -w "\n%{http_code}\n" http://localhost:8000/health
# Ожидаемый ответ:
# {"status":"ok"}
# 200
```

### 2.5. Login работает

```bash
COOKIE=/tmp/c.txt && rm -f $COOKIE
curl -s -c $COOKIE -o /dev/null --max-redirs 0 \
  -d "username=owner&password=block0test" \
  http://localhost:8000/login
curl -s -b $COOKIE -o /dev/null -w "GET / -> %{http_code}\n" \
  http://localhost:8000/
# Ожидаемый ответ:
# GET / -> 200
```

Тестовый юзер: `owner / block0test`. Поменять можно через:
```bash
docker compose run --rm app python -m scripts.create_admin owner новый_пароль
```

### 2.6. БД-миграции применены и есть demo-данные

```bash
curl -s -b $COOKIE -H "Accept: application/json" http://localhost:8000/api/search-profiles | head
# Ожидаешь: JSON-список из 3-4 профилей
```

Если 0 профилей — выполни seed:
```bash
docker compose run --rm app python -m scripts.seed_demo_data
```

Если миграции не применились (ошибка `relation does not exist`):
```bash
docker compose run --rm app alembic upgrade head
```

### 2.7. avito-xapi (если уже развёрнут)

```bash
curl -s -w "\n%{http_code}\n" http://213.108.170.194:8080/health
# или если xapi локально:
curl -s -w "\n%{http_code}\n" http://localhost:8080/health
```

Если 200 — есть xapi. Если timeout/refused — xapi пока не развёрнут (см. раздел 4 P5).

---

## 3. Восстановление (если что-то сломалось)

| Симптом | Что делать |
|---|---|
| `docker compose ps` — контейнеры в `Restarting` или `Exited` | `docker compose logs --tail=50 app` чтобы понять причину; типичные: пароль БД (значит сменился `.env`), миграции не применены, синтакс-ошибка в новых файлах |
| Тема dashboard вернулась к dark | Проверь что в `app/web/templates/base.html` `data-theme="light"` (не `dark`) и есть блок CSS variables `[data-theme="light"]` с `--p: 84 67% 48%` |
| Login 500 | Чаще всего — забытая `await session.commit()` или сломанная сессия. Перезапусти `docker compose restart app` |
| Алембик ругается на `relation already exists` | Откатить и снова: `docker compose run --rm app alembic downgrade base && alembic upgrade head` (потеряешь данные!) |
| Порт 8000 занят | Останови другой проект или поменяй mapping в `docker-compose.yml` на 8001:8000 |

---

## 4. Что делать дальше — зависит от состояния

### 🅰 Если инфра НЕ готова (OnePlus не рутирован / xapi не развёрнут)

Текущий блокер — Block 1 нельзя запускать без xapi и токена.

**Параллельно можно:**
- **Block 3 (LLM Analyzer)** — не требует Avito, только OpenRouter API key. См. `DOCS/V1_BLOCKS_TZ.md` §4 «Block 3»
- **P3** — собрать `AvitoSessionManager.apk` (есть Android Studio JBR? `cd AvitoAll/AvitoSessionManager && gradlew.bat assembleDebug`)
- **P5** — развернуть avito-xapi на homelab (`ssh homelab; cd /mnt/projects/repos/AvitoSystem/avito-xapi; docker compose up -d xapi`)

### 🅱 Если инфра готова (телефон льёт токен → xapi отвечает на /api/v1/search/items)

Запускай блоки последовательно:
1. **Block 1** — avito-mcp (тонкая обёртка над xapi)
2. **Block 3** — LLM Analyzer (если ещё не сделан, можно параллельно с Block 1)
3. **Block 4** — worker pipeline
4. **Pre-flight §3** в `DOCS/V1_BLOCKS_TZ.md` (split routers.py)
5. **Block 5/6/7** — параллельно или последовательно
6. **Block 8** — deploy + 72h soak

Каждый блок — отдельная сессия. Скопируй секцию «Block N» из `DOCS/V1_BLOCKS_TZ.md` §4 как первое сообщение в новую сессию.

### 🆎 Промпт-стартер для нового блока (универсальный)

```
Проект: c:/Projects/Sync/AvitoSystem/avito-monitor/

Прочитай:
1. CONTINUE.md в корне (этот файл) — узнаешь текущее состояние
2. c:/Projects/Sync/CLAUDE.md (глобальные секреты)
3. DOCS/V1_BLOCKS_TZ.md §0 + §4 «Block N» (твоё ТЗ)

Я хочу запустить Block N. Сначала проверь сервисы по разделу 2 CONTINUE.md.
Если сервисы up — приступай. Если нет — подними и сообщи мне.
```

Замени `N` на нужный номер блока.

---

## 5. Где лежат секреты

- **Глобальные** (Supabase, JWT, homelab IP, Telegram bot token, etc.): `c:/Projects/Sync/CLAUDE.md` — НЕ в git, локальный
- **Avito Official API credentials** (для V2): `c:/Projects/Sync/AvitoSystem/.env` — НЕ в git
- **avito-monitor локальный конфиг:** `c:/Projects/Sync/AvitoSystem/avito-monitor/.env` — gitignored, есть пример в `.env.example`
- **OpenRouter API key** (нужен с Block 3): добавь в `avito-monitor/.env` строку `OPENROUTER_API_KEY=...`
- **Auto-memory** (что Claude помнит про юзера): `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 6. Полезные команды

```bash
# Полная картина состояния
cd c:/Projects/Sync/AvitoSystem && git log --oneline -10 && echo "---" && \
  cd avito-monitor && docker compose ps

# Логи приложения за последние 5 минут
cd c:/Projects/Sync/AvitoSystem/avito-monitor && docker compose logs --tail=100 --since=5m app

# Зайти в контейнер app
docker compose exec app /bin/bash

# Подключение к Postgres из хоста
docker compose exec db psql -U avito avito_monitor

# Перезапуск только app (после правки кода без --reload)
docker compose restart app

# Полный рестарт
docker compose down && docker compose up -d
```

---

## 7. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/V1_EXECUTION_PLAN.md` | Высокоуровневый план 9 блоков |
| `DOCS/V1_BLOCKS_TZ.md` | **Самое важное** — per-block ТЗ для запуска в отдельных сессиях, граф зависимостей, матрица параллелизма |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главное ТЗ V1.2 — все требования |
| `DOCS/DECISIONS.md` | 10 ADR (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM) |
| `DOCS/UI_DESIGN_SPEC_V1.md` | UI спека: 8 экранов, sample data, style guide |
| `avito-monitor/README.md` | Quick start avito-monitor |

---

**TL;DR:** скопируй этот файл в новую сессию → Claude проверит сервисы по §2 → выберет действие по §4. Все детали — в `DOCS/V1_BLOCKS_TZ.md`.
