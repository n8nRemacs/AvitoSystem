# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком, потом проверь сервисы по §2, потом выбери действие из §4. Детали по конкретному блоку — в `DOCS/V1_BLOCKS_TZ.md` §4.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, и работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito + ценовой разведки. Single-user, homelab-deploy, Avito-Cosplay UI.

**Дата последнего обновления:** 2026-04-28 (после длинного сеанса фиксов и UI-стройки).

### ⚠ Текущий блип

На момент компакта **homelab не отвечает по SSH** (порт 22 timeout) и HTTP-страницы тоже timeout. SOCKS-туннель технически живой (наружу IP видно), но дальше глухо. Скорее всего сетевой блип у провайдера или на стороне VPS. **Последний коммит `2c92f43` (triage funnel) ещё НЕ задеплоен.** Когда связь оживёт — сразу sync + restart.

### Готово (закоммичено в git)

| Этап | Что | Коммит |
|---|---|---|
| Pre-V1 | Block 0/1/2/3, V2.0 reliability, V2.1 notification interception | `0c2be7f` … `9dc8a70` |
| **V1 Block 4** | TaskIQ pipeline (poll → analyze → match → notify) + analytics + cleanup + dispatch_pending. **Default LLM = `google/gemini-2.5-flash-lite`** | `9786e72`, `92f09ff`, `46a4250`, `a291050` |
| **V1 Block 5** | aiogram TG bot + pluggable `MessengerProvider` + 9 шаблонов + WhitelistMiddleware + `runtime_state` (system_paused / silent_until) | `1ae2f03` |
| **V1 Block 6** | `/search-profiles/{id}/stats` — 4 виджета на Chart.js (line/donut/histogram/events) | `e08365e` |
| Server-driven token refresh | таблица `avito_device_commands` + xapi long-poll/ack/admin + APK `commandPollJob` + health-checker `token_refresher.py` | `b11e465`, `040477a`, `dd5a29d` |
| Homelab compose overlays | apparmor=unconfined + bind-mount `./src` + ports remap | `37f34c7`, `6a07b1f` |
| **V1 Block 7** | Price Intelligence: миграция `0003_price_intel`, `PriceIntelligenceService` (4-step) + REST API + 3 web-страницы (list/new/report) + 26 unit-тестов + Markdown export для TG | `be5f633` |
| **Pipeline fixes** | (a) analyze_listing подтягивает детали через MCP перед classify — починил `class=unknown` (LLM получал пустое description); (b) Telegram через Xray HTTP-прокси `:10808` + `aiohttp-socks` + graceful fallback — TG работает из РФ; (c) кнопка «Удалить» для search-профилей в UI | `8707667` |
| **3 stub-страницы** | Полные `/listings` (фильтры по profile/condition/zone/period/sort) + `/logs` (события за 24ч из profile_runs+notifications+audit+activity) + `/settings` (LLM расход, Avito session live status, TG token, system pause, silent N мин, тест-отправка) | `d69c2d0` |
| **Search-bug fixes** | xapi: `ru.avito://` → `https://www.avito.ru/{id}` (URL не открывались в браузере). mcp/search.py пробрасывает `category_id` (мобильные телефоны=87 etc.) — больше нет часов/планшетов в выдаче iPhone-профиля. Brand+category → model hint (Apple+phones → query=`iPhone`). Backfill 226 старых ru.avito-URL в БД | `91c542a` |
| **Triage funnel (НЕ ЗАДЕПЛОЕНО)** | UserAction enum +`accepted`+`rejected`. /listings 3 вкладки: «Новые» (pending+viewed) / «В работе» (accepted) / «Отклонённые» (rejected) с счётчиками. POST `/listings/{p}/{l}/action` (accept/reject/undo). Карточки разворачиваются inline через `<details>` — описание + LLM verdict + 8-фото галерея + ✓/✗ кнопки в развёрнутом виде | `2c92f43` (LOCAL) |

### Что задеплоено на homelab (на момент `91c542a`, до блипа)

| Сервис | Где | Статус |
|---|---|---|
| avito-monitor app | `213.108.170.194:8088` (через ssh-tunnel `localhost:8088`) | Up |
| db / redis / avito-mcp / worker / scheduler / telegram-bot / health-checker | docker compose | Up |
| xapi | `213.108.170.194:8080` | Up, bind-mount `./src` |
| Supabase self-hosted | `213.108.170.194:8000` (Studio) / `:5433` (db) | Миграция `006` + `0003_price_intel` применены |
| AvitoSessionManager APK | OnePlus 8T (`110139ce`) | Полл server commands |
| Telegram bot | `@Avitisystem_bot`, whitelist `id=6416413182` | Long-poll active **через Xray-прокси** |
| Avito session | `ttl ≈ 23h` (свежий) | Healthy |

**Реальные данные в БД (на момент перед блипом):** 185+ лотов, 73 прогона, 186 LLM-вызовов, **6+ working** (после фикса), 2 в `analyzed` (прошли match но не matched). 8 synth-нотификаций ушли в `failed` (старые smoke от Block 5).

**Доступ к UI:**
```bash
ssh -L 8088:127.0.0.1:8088 homelab
# затем в браузере: http://localhost:8088/login (owner / block0test)
```

---

## 2. Что сделать сразу при возврате связи

```bash
# 1. Sync последний коммит на homelab
cd c:/Projects/Sync/AvitoSystem
ssh homelab 'echo OK'  # пока не вернёт OK — ждём

# 2. Sync файлы triage funnel + restart
cd c:/Projects/Sync/AvitoSystem/avito-monitor && tar -cf - \
  app/db/models/enums.py \
  app/services/listings_view.py \
  app/web/routers.py \
  app/web/templates/listings.html \
  | ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && tar -xf - && docker compose restart app worker'

# 3. Проверь UI
# открой http://localhost:8088/listings — должно быть 3 вкладки
# раскрой карточку — описание + фото + ✓/✗
# нажми ✓ — лот должен переехать во «В работе»
```

### Параллельный нерешённый трек: завтрашний smoke token-refresh

**Дата ожидаемого срабатывания:** ~2026-04-28 14:00–15:00 UTC (когда Avito-сессия `ttl ≤ 180s`). Был запланирован cron `bf2c1cd4` в этой сессии — он session-only и **умрёт когда Claude закроется**. Перепланируй вручную в новой сессии или просто проверь утром.

**Как проверить вручную:**
```bash
# Свежий ack в БД device_commands?
ssh homelab 'docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT id, status, created_at, acked_at, result FROM avito_device_commands \
   ORDER BY created_at DESC LIMIT 5;"'
# Ожидаешь: status=done, result.ok=true, result.payload.new_exp > prev_exp

# Сервер видит свежую сессию?
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' \
  http://127.0.0.1:8080/api/v1/sessions/current"
# Ожидаешь: ttl_human ~ 23h, is_active=true

# APK логи (если телефон рядом)
$ADB="C:\Users\EloNout\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v3.3.4\adb.exe"
& $ADB -s 110139ce logcat -d -t 5000 -s "SessionMonitorService:V" "ServerApi:V"
```

Если smoke провалился — в TG прилетит алерт, и в логах `health-checker` (`docker logs avito-monitor-health-checker-1 | grep token_refresh`) будет strikes counter.

---

## 3. Operational заметки

- **TIMEZONE = `Europe/Astrakhan`** (UTC+4). DB и внутренние логи в UTC.
- **Default LLM model = `google/gemini-2.5-flash-lite`** ($0.0001/картинка). Per-profile override через `SearchProfile.llm_classify_model` / `llm_match_model`.
- **OPENROUTER_API_KEY** в `avito-monitor/.env` (homelab). Дневной лимит $10.
- **Telegram через прокси:** `TELEGRAM_PROXY_URL=http://host.docker.internal:10808` (Xray HTTP-прокси на Финляндию). Без него — timeouts. Зависимость `aiohttp-socks==0.11.0` установлена в worker/tg-bot/health-checker контейнерах **руками** через `uv pip install`. **При следующем `docker compose up -d` пакет потеряется** — добавлен в pyproject.toml но образ ещё не пересобран. Полное пересобрание блокируется AppArmor LXC при `uv sync`. Workaround: после `compose up` — `docker exec <container> uv pip install aiohttp-socks` для каждого.
- **Phone setup для V2.1:** `settings put global hidden_api_policy 1` + `cmd deviceidle whitelist +com.avitobridge.sessionmanager` (Oplus battery saver иначе морозит NotificationListener).
- **APK build:** `JAVA_HOME=C:\Program Files\Android\Android Studio4\jbr; cd AvitoAll/AvitoSessionManager; .\gradlew.bat assembleDebug`. Install: `adb -s 110139ce install -r app/build/outputs/apk/debug/app-debug.apk`. ADB: `C:\Users\EloNout\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v3.3.4\adb.exe`.
- **Homelab compose:** оба проекта обязательно с `docker-compose.homelab.yml` overlay (apparmor=unconfined). Без него asyncio падает на AF_UNIX socketpair.

### Ключевые архитектурные insights (свежие)

- **`Listing.description` пустое после polling** — search-API возвращает только title/price/images. Подтягивать через `mcp.get_listing(avito_id)` ИЛИ в polling, ИЛИ в analyze_listing. Сейчас в analyze_listing (commit `8707667`).
- **Avito mobile API URL = `ru.avito://...` deep-link** — не открывается в браузере. Fix: `https://www.avito.ru/{id}` → Avito 301-redirect на canonical slug.
- **iPhone-профиль возвращал часы/iPad/AirPods** — потому что mcp слал `query=Apple` без `category_id`. Fix: маппинг category-slug → numeric id (`mobilnye_telefony`=87, `noutbuki`=86, etc.) + brand+category model hint (Apple+phones → "iPhone").
- **TG api заблокирован в РФ** — нужен прокси через Xray HTTP `:10808`. aiogram использует aiohttp_socks даже для HTTP-прокси.

### Известные хвосты

- 5 health_checker tests сломаны после Stage 9 (русские строки vs ожидаемые английские). ~20 мин на починку.
- `aiohttp-socks` не в собранном образе — установлен runtime. Лечится rebuild когда AppArmor отпустит.
- Старые 179 лотов с `class=unknown` остаются (LLM-кеш по cache_key). Очистятся естественно через cleanup (ADR-009 retention).

---

## 4. Что делать дальше

| Опция | Что | Приоритет |
|---|---|---|
| **A. Доезд triage funnel** | Sync `2c92f43` + smoke. Принять/отклонить лот, проверить вкладки. ~10 мин | Делать **сразу** после возврата homelab |
| **B. Завтрашний smoke token-refresh** | Утром проверить server-driven refresh по §2. Если ОК — V2.1 закрыт | Утром |
| **C. V2 messenger — спросить у продавца** | Кнопка «💬 Спросить» в карточке /listings. Шаблон «Здравствуйте, актуально? Состояние/аккумулятор/комплект?». xapi уже умеет (`create_chat_by_item` + `send_message`). Фоновый поллинг ответов раз в 5 мин. На карточке индикатор «есть ответ». ~3-4 ч | **Юзер озвучил это как ядро V1, не V2.** Приоритет после A+B |
| **D. Block 8 — Polish + 72h soak** | Caddy/TLS, Makefile, документация, мониторинг, ручной 72h soak. Финальный блок V1 | После C |
| **E. Lifecycle-статусы (lite)** | Юзер озвучил идею конфигурируемых статусов с действиями. Пока остановились на triage funnel (`accepted`/`rejected`) — это упрощённая версия. Полные статусы — V1.5/V2 | После C+D |

**Рекомендация на утро:** A → B → начало C.

### Промпт-стартер для нового блока

```
Проект: c:/Projects/Sync/AvitoSystem/avito-monitor/
Прочитай: CONTINUE.md (текущий статус) + DOCS/V1_BLOCKS_TZ.md §4 «Block N» (твоё ТЗ).
Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Я хочу запустить Block N. Сначала проверь сервисы (см. §2 CONTINUE.md). Если что-то не up — подними и сообщи мне.
```

---

## 5. Quick health check

```bash
# Туннель к homelab жив?
curl -s --max-time 5 --socks5-hostname 127.0.0.1:1081 https://ifconfig.me
# Ожидаешь: 213.108.170.194 (если пусто — `ssh -D 127.0.0.1:1081 -N -f homelab`)

# SSH живой?
ssh -o ConnectTimeout=10 homelab 'echo OK'
# Если timeout — homelab или сеть лежит

# Homelab стек жив?
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose ps --format "table {{.Service}}\t{{.Status}}"'
# avito-mcp / app / db (healthy) / redis / scheduler / telegram-bot / worker / health-checker — все Up

# UI открывается?
# ssh -L 8088:127.0.0.1:8088 homelab → http://localhost:8088/login (owner / block0test)

# avito-xapi жив?
curl -s -w "\nHTTP %{http_code}\n" http://213.108.170.194:8080/health
# Ожидаешь: HTTP 200

# Avito-сессия valid?
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/sessions/current"
# Ожидаешь: is_active=true, ttl_seconds > 180

# Реальный пайплайн работает?
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor \
  -c \"SELECT condition_class, COUNT(*) FROM listings GROUP BY condition_class;\""
# Ожидаешь: working > 0 (значит классификация рабочая)
```

### Восстановление

| Симптом | Что делать |
|---|---|
| SSH timeout к homelab | Сетевой блип. Подождать; проверить SOCKS-туннель (`ifconfig.me` должен вернуть homelab IP). Если он мёртвый — `ssh -D 127.0.0.1:1081 -N -f homelab` |
| Контейнер `Restarting` / `Exited` | `docker compose logs --tail=50 <service>`. На homelab — обязательно с homelab.yml overlay |
| `avito_monitor` БД пустая | `docker compose exec -T db psql -h 127.0.0.1 -U avito -d postgres -c 'CREATE DATABASE avito_monitor OWNER avito;' && docker compose exec -T app alembic upgrade head` |
| TG send timeouts (`TelegramNetworkError`) | Прокси отвалился. `docker exec avito-monitor-worker-1 uv pip install aiohttp-socks` (если контейнер пересоздан и пакет потерялся) + `docker compose restart worker telegram-bot` |
| /listings класс везде `unknown` | Проверь есть ли свежие лоты с `description IS NOT NULL`. Если нет — analyze_listing не дёргает MCP get_listing (см. commit `8707667`). Логи: `grep "fetch_detail_failed\|classify.success" worker logs` |
| /listings часы/iPad/AirPods вместо iPhone | Не пробрасывается `category_id`. Проверь commit `91c542a` есть в синке. Перезапусти worker |
| Token refresh висит в `delivered`, не `done` | APK свернут / убит. `adb logcat` + что SessionMonitorService running. Force-cleanup: `UPDATE avito_device_commands SET status='expired'` |
| Login 500 | `docker compose restart app` |
| Stats `/search-profiles/{id}/stats` пуст | placeholder когда `< 7 дней истории И нет current snapshot`. Дождаться поллинга или hand-trigger `compute_market_stats` |

---

## 6. Где секреты

- **Глобальные** (Supabase URL/keys, JWT, homelab IP, Telegram bot token, Xray-прокси): `c:/Projects/Sync/CLAUDE.md` — НЕ в git
- **avito-monitor локальный конфиг:** `c:/Projects/Sync/AvitoSystem/avito-monitor/.env` — gitignored
- **На homelab `.env` отдельный** в `/mnt/projects/repos/AvitoSystem/avito-monitor/.env` (там `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `TELEGRAM_PROXY_URL=http://host.docker.internal:10808`)
- **xapi homelab:** `SUPABASE_URL=http://213.108.170.194:8000` (self-hosted), `AVITO_XAPI_API_KEY=test_dev_key_123`
- **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (root)
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 7. Полезные команды

```bash
# История коммитов V1
cd c:/Projects/Sync/AvitoSystem && git log --oneline -20

# Все логи на homelab
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose logs --tail=100 --since=10m'

# Sync ОДНОГО файла на homelab (типичный паттерн)
cd c:/Projects/Sync/AvitoSystem/avito-monitor && tar -cf - app/services/some.py | \
  ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && tar -xf -'

# Запустить тесты внутри контейнера
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker cp tests/services/test_X.py avito-monitor-app-1:/app/tests/services/test_X.py && \
  docker compose exec -T app sh -c "cd /app && python -m pytest tests/services/test_X.py -x -q"'

# Avito-сессия в БД
ssh homelab "docker exec supabase-db psql -U postgres -d postgres -c 'SELECT user_id, source, expires_at, is_active FROM avito_sessions ORDER BY created_at DESC LIMIT 5;'"

# Force-trigger token refresh (для теста, без ждать)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{\"command\":\"refresh_token\",\"payload\":{\"timeout_sec\":60,\"prev_exp\":0},\"issued_by\":\"manual\"}' \
  -X POST http://127.0.0.1:8080/api/v1/devices/me/commands"

# Проверить распределение лотов по статусам
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor \
  -c \"SELECT user_action, COUNT(*) FROM profile_listings GROUP BY user_action;\""

# Откатить triage у одного лота вручную
ssh homelab "docker exec avito-monitor-db-1 psql -h 127.0.0.1 -U avito -d avito_monitor \
  -c \"UPDATE profile_listings SET user_action='pending' WHERE listing_id='<UUID>';\""

# APK logcat фильтр (PowerShell)
$adb = "C:\Users\EloNout\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v3.3.4\adb.exe"
& $adb -s 110139ce logcat -d -t 1000 -s "SessionMonitorService:V" "ServerApi:V"

# Ручной seed (если БД пуста)
ssh homelab "cd /mnt/projects/repos/AvitoSystem/avito-monitor && \
  docker compose exec -T app python -m scripts.create_admin owner block0test && \
  docker compose exec -T app python -m scripts.seed_demo_data"
```

---

## 8. Где детальная документация

| Файл | Что |
|---|---|
| `DOCS/V1_BLOCKS_TZ.md` | Per-block ТЗ. Block 7 уже сделан, Block 8 актуален |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главное ТЗ V1.2 (особенно §4.2 Price Intel, §6.4 REST) |
| `DOCS/DECISIONS.md` | 10 ADR (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM, ADR-009 retention) |
| `DOCS/UI_DESIGN_SPEC_V1.md` | UI спека: 8 экранов, sample data, style guide. §4.5 листинги, §4.6 price report |
| `avito-monitor/docker-compose.homelab.yml` | объяснение apparmor=unconfined + ports remap |
| `avito-xapi/docker-compose.homelab.yml` | bind-mount + reload вместо rebuild |

---

**TL;DR для следующей сессии:**
1. **Если homelab жив** → выполни §2 (sync `2c92f43` + restart) → smoke triage funnel
2. **Если homelab лежит** → подожди или ткни сетевую инфраструктуру; SOCKS-туннель проверь через `ifconfig.me`
3. **Утренний smoke token-refresh** (§2 второй блок) — вне зависимости от deploy triage
4. **Дальше** — V2 messenger («Спросить продавца») по §4-C, потом Block 8
