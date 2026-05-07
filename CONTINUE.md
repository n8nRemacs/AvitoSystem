# CONTINUE — следующая сессия

> **Если ты Claude в новой сессии:** прочитай этот файл целиком. Главная цель сейчас — **найти числовые ID параметров Avito mobile API** (brand, model, состояние, память, цвет и т.д.), чтобы строить precise structured-запросы вместо fuzzy text + post-filter. Полная методология — `DOCS/REFERENCE/06-structured-params-discovery.md`.
>
> **Если ты пользователь:** скопируй промпт из §5 в новую сессию.

---

## 1. Главная цель следующей сессии

Сейчас polling работает на **fuzzy text + post-filter**: шлём `query="Iphone 12 Pro Max"` без structured params, Avito возвращает ~12'000 fuzzy-iPhone'ов всех моделей, мы режем их `\w+`-токенами по `brand+model` в title. Это работает, но:
- Не отделяет iPhone 12 Pro Max от iPhone 12 (без "Pro Max")
- Не даёт фильтровать по объёму памяти, цвету, состоянию батареи на стороне Avito
- Не масштабируется на не-phone-категории (нет mapping web-slug → mobile-categoryId, нет brand/model ID для машин/одежды/etc.)

**Решение:** собрать **catalog таблицу** `avito_param_catalog` с тройками `(category_id, param_id, param_value, human_name)`. Источник — subscription deeplink'и (auto-extraction из `autosearch_sync`). Когда catalog заполнен — URL parser резолвит brand+model в `params[110617][0]=491590&params[110618][0]=469735` и polling шлёт structured запрос.

**Полная спека:** `DOCS/REFERENCE/06-structured-params-discovery.md` — 4 подхода (subscription mining ★/catalog API/mitm/jadx), пример schema БД, action items на ~3ч кодинга.

---

## 2. Production state — 2026-05-07 (после today's session)

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU). 9 active services. **+ systemd `avito-vpn-tunnel.service`** (новое сегодня) |
| **Outbound к Avito** | xapi → `socks5h://172.18.0.1:1081` → ssh -D туннель → ru-vpn `155.212.217.226` → Avito |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt (`drwgozasaypgphkxyizt`). Pooler 6543. |
| **Single user** | `remacs` (admin, пароль `31415926`) |
| **Single profile** | `iPhone 12 Pro max 11000-13500` (manual_url, owner=NULL → LRU). `poll_interval=5min`. **На паузе** (is_active=false) после соак-тестов. |
| **Phone** | OnePlus 8T `110139ce`, USB → Windows ПК. APK ловит push'ы Avito-app. |
| **Branch state** | `main` ahead origin = 1 коммит (`0c8e759`). Не пушено. |

### Pool state (2026-05-07 ~09:15 UTC):

| Аккаунт | Avito user | state | JWT TTL |
|---|---|---|---|
| Clone (`42c179db`) | 157920214 | dead | истёк 5 дней назад |
| auto-157920214 (`b5cbf28b`) | 157920214 | active (cooldown reset) | **caa81d6b** TTL≈24h, но **QRATOR-зажат** от тестов (нужен либо ещё один logout/login в Avito-app, либо ~1ч cooldown) |
| auto-431483569 (`14acfef4`) | 431483569 | active | TTL отрицательный, нужен refresh |

---

## 3. Что сделано в session 2026-05-07 (commit `0c8e759`)

### Новая архитектура outbound

- **Найдено эмпирически:** Avito QRATOR делает per-(JWT, IP) trust-binding. Свежий токен с другого IP = 403 captcha с первого запроса. Подтверждено реверсивной корреляцией: `new_token+VPS=403, new_token+phone-IP=200; old_token+VPS=200, old_token+phone-IP=403`.
- **Решение:** ssh -D туннель от VPS до ru-vpn (`155.212.217.226` — same outbound IP что у Avito-app на телефоне).
- **Реализация:**
  - `/etc/systemd/system/avito-vpn-tunnel.service` — `ssh -i /root/.ssh/id_ed25519 -N -D 172.18.0.1:1081 root@155.212.217.226`, `Restart=always`
  - `AVITO_SOCKS_PROXY=socks5h://172.18.0.1:1081` в `/opt/avito-system/.env`
  - `avito-xapi/src/workers/base_client.py` читает env → пробрасывает `proxies=` в `curl_cffi.Session`
  - `ops/server/docker-compose.yml`: `extra_hosts: ["host.docker.internal:host-gateway"]` (на случай если потом захотим биндить на host loopback)

### Фиксы формата запросов

- **`/11/items` без structured params не должен иметь categoryId** — голый `categoryId` (даже правильный mobile id `84`) триггерит QRATOR 403. Avito-app шлёт categoryId только в составе deeplink'а с brand+model. Фикс: `http_client.py search_items()` шлёт categoryId только если в `params_extra` уже есть structured `params[X][Y]=Z`.
- **Bool → lowercase string:** `withDelivery=True` (Python repr "True") тоже триггерит QRATOR. Заменили на `"true"/"false"`. Same для `forceLocation`.
- **Post-filter word-boundary:** `polling.py` теперь использует `re.findall(r"\w+", title.lower())` set вместо substring `tok in title_lower`. `12` больше не матчит `128` в title'ах iPhone 14 Pro Max. Импорт `re` + `_WORD_RE` constant.

### Документация (committed)

- **DOCS/REFERENCE/01-avito-api.md** — note про categoryId behavior + per-(token, IP) binding
- **DOCS/REFERENCE/05-search-query-formation.md** — секция «Эмпирические находки 2026-05-07» с curl-diff таблицами
- **DOCS/REFERENCE/06-structured-params-discovery.md** — **новый файл**, 4 подхода для сбора param-ID, рекомендуемая `avito_param_catalog` schema
- **DOCS/TZ_AvitoBridge_PhoneProxy_V1.md** — **новый ТЗ** на phone-MCP-bridge (~10-18ч кодинга), будет нужен только если QRATOR начнёт детектить chrome120 vs OkHttp на TLS-уровне

### Auto-memory (новые)

- `reference_qrator_token_ip_binding.md` — эмпирика per-(JWT, IP) binding

### Cleanup

- Удалено 41 не-iPhone profile_listing'а (кружки, чайники, весы — наследие fuzzy без post-filter'а), 772 orphan listings purged. В БД остались 14 реальных iPhone 12 Pro Max.

### Soak

- **`09:04:12 success seen=14 new=14`** — единственный успешный прогон сегодня после fix'ов. 14 настоящих iPhone 12 Pro Max в БД (`/listings` UI должно показывать).
- Дальше тесты пережгли токен, нужен logout/login в Avito-app для нового прогона.

---

## 4. Action items по приоритету

### КРИТИЧНО для следующей сессии

1. **Structured params discovery (Phase 1-3, ~3ч)** — главная цель. Полный план в `DOCS/REFERENCE/06-structured-params-discovery.md` §6. Шаги:
   - SQL миграция `avito_param_catalog` (CREATE TABLE)
   - `_extract_params_to_catalog()` в `autosearch_sync.py`
   - Юзер сохраняет 5-10 разных autosearch'ей в Avito-app (разные модели, может разные категории)
   - URL parser lookup'ит brand+model в catalog → добавляет в `params_extra` для search_items
   - Profile получает precise результаты (только iPhone 12 Pro Max, ничего больше)

### ОСНОВНОЕ (после structured params)

2. **Refresh-flow gap** (~10ч) — JWT истекает за 24h, Avito-app refresh'ит молча → APK не ловит push → у нас stale JWT → 403. Pull-based архитектура: xapi помечает `refresh_requested_at`, APK polls SharedPrefs Avito-app, POST'ит свежий JWT либо `POST /refresh-failed` → TG alert. Без этого работает только пока юзер ручками logout/login.
3. **Phase B соак V2 LLM pipeline** — `condition_class` сейчас `unknown` для 14 новых iPhone'ов. План `c:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md` Phase B/C закроет.

### НИЗКИЙ ПРИОРИТЕТ

4. **Catalog API discovery (Variant B в `06-structured-params-discovery.md`)** — попробовать `GET /api/N/categories/{id}/parameters` через jadx grep. Если найдётся — bulk import всех param ID за один прогон. Опционально, ~2-4ч.
5. **AvitoBridge Phone Proxy** (`DOCS/TZ_AvitoBridge_PhoneProxy_V1.md`) — нужен только если QRATOR начнёт детектить chrome120 vs OkHttp. Триггер: периодические 403 на работающих токенах после 7-14 дней соака.
6. **Bug: zombie running runs** — polling.py делает early return при `profile.is_active=false` после создания ProfileRun(running) → запись остаётся `running` навсегда. Минор.

---

## 5. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/.

Прочитай CONTINUE.md и DOCS/REFERENCE/06-structured-params-discovery.md.

Главная цель: реализовать сбор catalog'а параметров Avito (brand, model,
память, цвет, состояние) через subscription mining — Phase 1-3 из §6 doc'а.
~3ч кодинга. После этого URL parser сможет строить precise structured
запросы вместо fuzzy text + post-filter.

Production: VPS 81.200.119.132 + Cloud Supabase Frankfurt. Один UI юзер
remacs/31415926. Один profile (iPhone 12 Pro max 11000-13500, manual_url),
сейчас на паузе. Pool: 1 active токен (но QRATOR-зажат после вчерашних
тестов — может потребоваться logout/login в Avito-app для свежего).

Outbound к Avito идёт через ssh -D туннель VPS → ru-vpn 155.212.217.226
(systemd avito-vpn-tunnel.service, env AVITO_SOCKS_PROXY). Без этого —
QRATOR 403 на любой свежий токен (per-(JWT, IP) binding).

HEAD = 0c8e759.
```

---

## 6. Команды на проверку

```bash
# Containers
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose ps'

# Tunnel + outbound check
ssh root@81.200.119.132 'systemctl is-active avito-vpn-tunnel.service && docker compose -f /opt/avito-system/docker-compose.yml exec -T avito-xapi sh -c "curl -s -x socks5h://172.18.0.1:1081 -m 10 ifconfig.io"'
# Должно вернуть: 155.212.217.226

# Pool state + JWT TTL
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio, os, asyncpg, base64, json
from datetime import datetime, timezone
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    now = datetime.now(timezone.utc)
    rs = await conn.fetch(\"SELECT a.nickname, a.state, s.tokens FROM avito_accounts a LEFT JOIN avito_sessions s ON s.account_id=a.id AND s.is_active=true ORDER BY a.created_at\")
    for r in rs:
        tok = r[\"tokens\"]
        if isinstance(tok, str): tok = json.loads(tok)
        st = (tok or {}).get(\"session_token\", \"\") if tok else \"\"
        ttl = \"\"
        if st:
            p = json.loads(base64.urlsafe_b64decode(st.split(\".\")[1] + \"==\").decode())
            ttl_min = int((datetime.fromtimestamp(p[\"exp\"], tz=timezone.utc) - now).total_seconds() / 60)
            ttl = f\" TTL={ttl_min}min\"
        print(f\"  {r[\\\"nickname\\\"]:30s} state={r[\\\"state\\\"]:15s}{ttl}\")
    await conn.close()
asyncio.run(main())
"'

# Last 5 runs
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio, os, asyncpg
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    rs = await conn.fetch(\"SELECT started_at, status, listings_seen, listings_new, error_message FROM profile_runs ORDER BY started_at DESC LIMIT 5\")
    for r in rs:
        print(f\"  {r[\\\"started_at\\\"].strftime(\\\"%H:%M:%S\\\")} {r[\\\"status\\\"]:10s} seen={r[\\\"listings_seen\\\"]} new={r[\\\"listings_new\\\"]} {(r[\\\"error_message\\\"] or \\\"\\\")[:60]}\")
    await conn.close()
asyncio.run(main())
"'

# Unpause + trigger run (когда есть свежий токен)
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import sys, asyncio
sys.path.insert(0, \"/app\")
import asyncpg, os
from app.tasks.polling import poll_profile
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    await conn.execute(\"UPDATE search_profiles SET is_active=true WHERE id=\\\"a37d2226-3907-4a10-a585-22dd519cb431\\\"\")
    await conn.execute(\"UPDATE avito_accounts SET state=\\\"active\\\", cooldown_until=NULL, consecutive_cooldowns=0 WHERE id=\\\"b5cbf28b-c9fe-46ff-aea1-bc332abf6bad\\\"\")
    await conn.close()
    task = await poll_profile.kiq(\"a37d2226-3907-4a10-a585-22dd519cb431\")
    print(task.task_id)
asyncio.run(main())
"'

# Tunnel debug (если что-то не так)
ssh root@81.200.119.132 'systemctl status avito-vpn-tunnel.service --no-pager -n 20 ; ss -tlnp | grep 1081'
```

---

## 7. Где детальная документация

| Файл | Что |
|---|---|
| **`DOCS/REFERENCE/06-structured-params-discovery.md`** | **Основное для следующей сессии** — методология сбора param ID, schema БД, 4 подхода |
| `DOCS/REFERENCE/05-search-query-formation.md` | Эмпирические находки 2026-05-07: QRATOR per-(token,IP), categoryId-403 |
| `DOCS/REFERENCE/01-avito-api.md` | Avito endpoints + headers + structured params + сегодняшние notes |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow, pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk, ADB, NotificationListener |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi + Frida + mitm workflow |
| **`DOCS/TZ_AvitoBridge_PhoneProxy_V1.md`** | ТЗ phone-MCP-bridge (V2 escalation, ~10-18ч) |
| `DOCS/avito_api_snapshots/autosearches/README.md` | реверс /5/subscriptions с live-validated примерами |
| `c:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md` | План V2 LLM pipeline (Phase A done, B/C ожидают живых лотов) |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Production deploy artifacts |

---

## 8. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env` (chmod 600 root):
  - `DATABASE_URL` (asyncpg pooler 6543)
  - `SUPABASE_URL=https://drwgozasaypgphkxyizt.supabase.co`
  - `SUPABASE_KEY=sb_secret_*`
  - `AVITO_XAPI_API_KEY=test_dev_key_123`
  - `AVITO_MCP_AUTH_TOKEN=7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222`
  - `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_DAILY_USD_LIMIT=20`
  - **`AVITO_SOCKS_PROXY=socks5h://172.18.0.1:1081`** (новое сегодня)
- **VPS SSH ключ к ru-vpn:** `/root/.ssh/id_ed25519` (скопирован сегодня; используется только systemd-юнитом туннеля)
- **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml`
- **Avito-app session:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml`
- **DuckDNS** token в `/usr/local/bin/duckdns-update.sh` на VPS
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## TL;DR

1. **Сегодня прорыв:** найден root cause 403 (per-(JWT,IP) binding QRATOR), решён через ssh -D туннель VPS→ru-vpn. Plus фиксы: `categoryId` без structured params → skip, `bool → lowercase string`, post-filter `\w+` word-boundary. Прогон **успешный**: `seen=14 new=14` настоящих iPhone 12 Pro Max.
2. **Сейчас работает в режиме fuzzy text + post-filter** — для V1 monitoring этого достаточно. Для precision (точно iPhone 12 Pro Max, без iPhone 12/14, фильтр по памяти/цвету/состоянию) нужны structured `params[brand][model]`.
3. **Главная цель следующей сессии:** реализовать `avito_param_catalog` collection через subscription deeplink mining. ~3ч кодинга, полная спека в `DOCS/REFERENCE/06-structured-params-discovery.md`.
4. **Блокер для всего:** refresh-flow gap. Avito-app refresh'ит JWT молча, APK не ловит push. Нужен pull-based флоу — план на ~10ч.
5. **БД почищена** — 41 не-iPhone листинг удалён, остались 14 настоящих iPhone 12 Pro Max. Profile на паузе до пинга юзера + свежего токена.
