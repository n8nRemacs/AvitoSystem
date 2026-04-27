# CONTINUE — Быстрый рестарт сессии V1

> **Если ты — Claude в новой сессии:** прочитай этот файл целиком, потом проверь сервисы по §2, потом выбери действие из §4. Детали по конкретному блоку — в `DOCS/V1_BLOCKS_TZ.md` §4.
>
> **Если ты — пользователь:** скопируй этот файл в новую сессию Claude Code, и работа продолжится.

---

## 1. Где мы сейчас

**Проект:** `c:/Projects/Sync/AvitoSystem/avito-monitor/` — V1 персонального мониторинга Avito + ценовой разведки. Single-user, homelab-deploy, Avito-Cosplay UI.

**Дата последнего обновления:** 2026-04-27 (Block 6 closed + server-driven token refresh deployed).

### Готово (закоммичено в git)

| Этап | Что | Коммит |
|---|---|---|
| Pre-V1 | Block 0/1/2/3, V2.0 reliability, V2.1 notification interception | `0c2be7f` … `9dc8a70` |
| **V1 Block 4** | TaskIQ pipeline (poll → analyze → match → notify) + analytics (median/p25/p75/triggers) + cleanup (ADR-009 retention) + dispatch_pending. **Default LLM = `google/gemini-2.5-flash-lite`** (~11× дешевле haiku) | `9786e72`, `92f09ff`, `46a4250`, `a291050` |
| **V1 Block 5** | aiogram Telegram bot + pluggable `MessengerProvider` (Telegram + Max stub) + 9 Jinja2 шаблонов + WhitelistMiddleware + inline-кнопки + `runtime_state` (system_paused / silent_until). `silent_until` гейтит **только** листинг-уведомления; системные алерты идут всегда | `1ae2f03` |
| **V1 Block 6** | `/search-profiles/{id}/stats` — 4 виджета на Chart.js (line/donut/histogram/events) + KPI-row + recommended alert-band + placeholder | `e08365e` |
| **Server-driven token refresh** | таблица `avito_device_commands` (миграция `006`) + 3 эндпоинта в xapi (long-poll GET, ack POST, admin insert POST с dedup) + APK `commandPollJob` + refresh state-machine (root `monkey` → `input swipe` → re-read SharedPrefs → `am force-stop` → sync → ack) + health-checker `token_refresher.py` (тик 30с, окно `ttl<=180s`, 3 strikes → TG алерт). **Baseline берётся из server-supplied `payload.prev_exp`**, не из self-read SharedPrefs | `b11e465`, `040477a`, `dd5a29d` |
| Homelab compose overlays | `avito-monitor/docker-compose.homelab.yml` + `avito-xapi/docker-compose.homelab.yml` (apparmor=unconfined + bind-mount `./src` + `--reload`; ports remap для конфликта с supabase-kong/avito-xapi/avito-mcp-homelab) | `37f34c7`, `6a07b1f` |

### Что задеплоено на homelab прямо сейчас

| Сервис | Где | Статус |
|---|---|---|
| avito-monitor app | `213.108.170.194:8088` (через ssh-tunnel `localhost:8088`) | Up |
| avito-monitor db / redis / avito-mcp / worker / scheduler / telegram-bot | docker compose, `host.docker.internal:8080` → xapi | Up |
| avito-monitor health-checker | `token_refresher.py` тикает 30с | Up |
| xapi | `213.108.170.194:8080` (внешне доступен) | Up, bind-mount `./src` |
| Supabase self-hosted | `213.108.170.194:8000` (Studio) / `:5433` (db direct) | Миграция `006` применена |
| AvitoSessionManager APK | OnePlus 8T (`110139ce`), serverUrl=`http://213.108.170.194:8080`, api_key=`test_dev_key_123` | SessionMonitorService running |
| Telegram bot | `@Avitisystem_bot`, whitelist `id=6416413182` | Long-poll active |
| Avito session | `ttl ≈ 23h` (свежий, refresh-loop спит) | Healthy |

**Доступ к UI с локалки:**
```bash
ssh -L 8088:127.0.0.1:8088 homelab
# затем в браузере: http://localhost:8088/login (owner / block0test)
```

---

## 2. Главное ожидание — завтрашний smoke (≈ 2026-04-28 14:00 UTC)

Когда Avito-сессия подойдёт к expiry (`ttl ≤ 180s`), полный server-driven refresh-цикл должен сработать сам:

1. `health-checker.token_refresher` тик → видит `ttl ≤ 180`
2. POST `/api/v1/devices/me/commands` с `payload.prev_exp = <current exp>`
3. APK long-poll вернёт команду (~50ms latency)
4. APK: wake → `monkey -p com.avito.android` → 90с скроллит `input swipe` → re-read SharedPrefs
5. **Bug fixed (`dd5a29d`):** baseline = `min(payload.prev_exp, prefs.cachedExpiresAt, fresh self-read)` + альтернативная проверка по сравнению самого JWT-string. Avito-internal-refresh не угонит baseline.
6. На diff: `am force-stop com.avito.android` → POST `/sessions` со свежим JWT → `ack ok=true`
7. Если 3 неудачи подряд (90с correlation × 3 strikes) → TG-алерт «открой Avito вручную»

### Как утром завтра проверить результат

```bash
# 1. Свежий ack в БД device_commands?
ssh homelab 'docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT id, status, created_at, acked_at, result FROM avito_device_commands \
   ORDER BY created_at DESC LIMIT 5;"'
# Ожидаешь: status=done, result.ok=true, result.payload.new_exp > prev_exp

# 2. Сервер видит свежую сессию?
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' \
  http://127.0.0.1:8080/api/v1/sessions/current"
# Ожидаешь: ttl_human ~ 23h (новый), is_active=true

# 3. APK логи — был ли реальный refresh?
$ADB="C:\Users\EloNout\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v3.3.4\adb.exe"
& $ADB -s 110139ce logcat -d -t 5000 \
  -s "SessionMonitorService:V" "ServerApi:V" "AvitoSessionReader:V"
# Ищи: "command received cmd=refresh_token", "Avito launched via root (monkey)",
#      "notifications.sent" или "no_refresh"
```

**Если smoke провалился:** проверь TG — должен прилететь алерт. И смотри логи `health-checker` (`docker logs avito-monitor-health-checker-1 | grep token_refresh`) — там видно strikes counter и причину.

---

## 3. Operational заметки

- **TIMEZONE = `Europe/Astrakhan`** (UTC+4). Все health-checker алерты рендерятся в `+04`. Логи и DB всё ещё в UTC.
- **Default LLM model = `google/gemini-2.5-flash-lite`** (текст + vision, $0.0001/картинка). Per-profile override через `SearchProfile.llm_classify_model` / `llm_match_model`.
- **OPENROUTER_API_KEY** в `avito-monitor/.env` (не коммитится). Дневной лимит 10 USD, sum по `llm_analyses.cost_usd` за 24ч.
- **Phone setup для V2.1:** на устройстве `settings put global hidden_api_policy 1` (через root) и `cmd deviceidle whitelist +com.avitobridge.sessionmanager` — иначе NotificationListenerService замораживается Oplus battery saver.
- **APK build:** `JAVA_HOME=C:\Program Files\Android\Android Studio4\jbr; cd AvitoAll/AvitoSessionManager; .\gradlew.bat assembleDebug`. Install: `adb -s 110139ce install -r app/build/outputs/apk/debug/app-debug.apk`. ADB у юзера лежит в `C:\Users\EloNout\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v3.3.4\adb.exe`.
- **Homelab deploy:** обе compose всегда нужно поднимать с homelab.yml override (в `docker-compose.override.yml` symlink уже стоит на homelab.yml). Без него `apparmor` блокирует AF_UNIX socketpair() и asyncio падает.

### Известные хвосты

- 5 health_checker tests сломаны после Stage 9 (русские строки vs ожидаемые английские, переименование `keepalive_ms` → `second_event_ms`). ~20 мин на починку, не блокер.
- Block 1 query parsing (`avito_fetch_search_page`): для category-only URLs query из brand слишком широкий ("apple" → AirPods + iPhone). Worker (Block 4) обходит — передаёт полный URL, xapi пробрасывает category_id.

---

## 4. Что делать дальше

| Опция | Что | Когда выбрать |
|---|---|---|
| **A. Завтрашний smoke** | Утром проверить server-driven refresh по плану §2. Если ОК — закрываем V2.1 хвост окончательно | Просто стартовая задача нового дня |
| **B. Block 7** — Price Intelligence | Полные триггеры `historical_low` / `price_drop_listing` / `price_dropped_into_alert` (сейчас в `analytics.py` minimal: `market_trend_*` / `supply_surge` / `condition_mix_change`). Page `/price-intelligence/{id}` с `LLMAnalyzer.compare_to_reference`. Recommended alert-band с кнопкой «Применить». Smoothed 7d-rolling median. ~4–6 ч | Не зависит от refresh-теста, можно начать сразу |
| **C. Block 8** — Polish + 72h soak | Caddy/TLS, Makefile, документация, мониторинг, ручной 72h soak. Финальный блок V1 | После Block 7, нужны ≥ 1 живой профиль |
| **D. Запустить реальный поллинг** | Активировать iPhone-профиль на 24+ часа, смотреть что прилетит — реальные лоты, классификация, нотификации в TG. Stats-страница наполнится. Параллельно с любым из A/B/C | Если хочешь увидеть систему «вживую» |

**Рекомендация:** D в фоне + B параллельно. К завтра у тебя живые данные на /stats + Block 7 готов.

### Промпт-стартер для нового блока

```
Проект: c:/Projects/Sync/AvitoSystem/avito-monitor/
Прочитай: CONTINUE.md (текущий статус) + DOCS/V1_BLOCKS_TZ.md §4 «Block N» (твоё ТЗ).
Глобальные секреты: c:/Projects/Sync/CLAUDE.md.

Я хочу запустить Block N. Сначала проверь сервисы (см. §2 CONTINUE.md). Если что-то не up — подними и сообщи мне.
```

---

## 5. Quick health check

Перед стартом любой работы — пробежать.

```bash
# Туннель к homelab
curl -s --max-time 5 --socks5-hostname 127.0.0.1:1081 https://ifconfig.me
# Ожидаешь: 213.108.170.194 (если пусто — `ssh -D 127.0.0.1:1081 -N -f homelab`)

# Homelab стек жив?
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose ps --format "table {{.Service}}\t{{.Status}}"'
# avito-mcp / app / db (healthy) / redis / scheduler / telegram-bot / worker / health-checker — все Up

# UI открывается? (через SSH tunnel)
# В отдельном окне: ssh -L 8088:127.0.0.1:8088 homelab
# Потом: http://localhost:8088/login (owner / block0test)

# avito-xapi жив?
curl -s -w "\nHTTP %{http_code}\n" http://213.108.170.194:8080/health
# Ожидаешь: HTTP 200

# Avito-сессия valid?
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' http://127.0.0.1:8080/api/v1/sessions/current"
# Ожидаешь: is_active=true, ttl_seconds > 180
```

Если что-то падает — логи: `ssh homelab 'docker logs <container> --tail=50'`.

### Восстановление

| Симптом | Что делать |
|---|---|
| Контейнер `Restarting` / `Exited` | `docker compose logs --tail=50 <service>`. На homelab — обязательно с homelab.yml overlay (apparmor блокирует asyncio без него) |
| `avito_monitor` БД пустая на homelab | `docker compose exec -T db psql -h 127.0.0.1 -U avito -d postgres -c 'CREATE DATABASE avito_monitor OWNER avito;' && docker compose exec -T app alembic upgrade head` |
| Login 500 | Перезапусти `app` (`docker compose restart app`) |
| Stats `/search-profiles/{id}/stats` пуст | Это placeholder когда `< 7 дней истории И нет current snapshot`. Запусти hand-trigger `compute_market_stats` или дождись поллинга |
| Token refresh висит в `delivered`, не `done` | Скорее всего APK свернут / процесс убит. Проверь `adb logcat` + что SessionMonitorService running. UPDATE `avito_device_commands SET status='expired'` для cleanup |

---

## 6. Где секреты

- **Глобальные** (Supabase URL/keys, JWT, homelab IP, Telegram bot token): `c:/Projects/Sync/CLAUDE.md` — НЕ в git
- **avito-monitor локальный конфиг:** `c:/Projects/Sync/AvitoSystem/avito-monitor/.env` — gitignored, пример в `.env.example`
- **На homelab `.env` отдельный** в `/mnt/projects/repos/AvitoSystem/avito-monitor/.env` (там `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, реальные значения)
- **xapi homelab:** `SUPABASE_URL=http://213.108.170.194:8000` (self-hosted), `AVITO_XAPI_API_KEY=test_dev_key_123`
- **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` — менять через root (`adb shell su -c`)
- **Auto-memory** (что Claude помнит про юзера): `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## 7. Полезные команды

```bash
# История коммитов V1
cd c:/Projects/Sync/AvitoSystem && git log --oneline -15

# Все логи на homelab
ssh homelab 'cd /mnt/projects/repos/AvitoSystem/avito-monitor && docker compose logs --tail=100 --since=10m'

# Avito-сессия в БД (homelab)
ssh homelab "docker exec supabase-db psql -U postgres -d postgres -c 'SELECT user_id, source, expires_at, is_active FROM avito_sessions ORDER BY created_at DESC LIMIT 5;'"

# Force-trigger token refresh (для теста, без ждать)
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{\"command\":\"refresh_token\",\"payload\":{\"timeout_sec\":60,\"prev_exp\":0},\"issued_by\":\"manual\"}' \
  -X POST http://127.0.0.1:8080/api/v1/devices/me/commands"

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
| `DOCS/V1_BLOCKS_TZ.md` | **Самое важное** — per-block ТЗ (особенно §4 Block 7/8 ещё актуальны) |
| `DOCS/TZ_Avito_Monitor_V1.md` | Главное ТЗ V1.2 |
| `DOCS/DECISIONS.md` | 10 ADR (особенно ADR-001 URL-based, ADR-008 двойная вилка, ADR-010 двухступенчатый LLM, ADR-009 market stats) |
| `DOCS/UI_DESIGN_SPEC_V1.md` | UI спека: 8 экранов, sample data, style guide |
| `avito-monitor/docker-compose.homelab.yml` | объяснение почему apparmor=unconfined + ports remap (комментарии в файле) |
| `avito-xapi/docker-compose.homelab.yml` | объяснение почему bind-mount + reload вместо rebuild |

---

**TL;DR для следующей сессии:**
1. §2 проверь утренний smoke (taken `device_commands` → `done`?)
2. §4 выбери опцию (рекомендую B + D параллельно)
3. Все детали — в `DOCS/V1_BLOCKS_TZ.md` §4
