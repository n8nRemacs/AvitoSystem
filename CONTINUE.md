# CONTINUE — следующая сессия

> **Если ты Claude в новой сессии:** прочитай этот файл целиком. Главная цель сейчас — **научиться правильно формировать поисковый запрос к Avito**, чтобы получать те же результаты что Avito-app (точные iPhone 12 Pro Max), а не fuzzy-текстовый мусор (формы для склейки стекла, чайники, рюмки Beluga). Все детали — в `DOCS/REFERENCE/05-search-query-formation.md`.
>
> **Если ты пользователь:** скопируй промпт из §6 в новую сессию.

---

## 1. Главная цель

Юзер кладёт в profile **URL из браузера** Avito (с `?f=ASgB...&pmin=...&s=104`). Нам надо превратить его в запрос к mobile API, который Avito-app отправляет — со structured `params[110617][0]=491590` (brand) + `params[110618][0]=469735` (model) + price + sort.

Без этого Avito mobile-API делает fuzzy text-search и возвращает ~95% мусора. Post-filter (commit `dc91ce5`) режет мусор по brand+model в title — но реальных iPhone'ов в результатах остаётся 0.

**Полная спека и 3 пути решения** — `DOCS/REFERENCE/05-search-query-formation.md` (создан в этой сессии).

---

## 2. Production state — 2026-05-07

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU, 2c/4GB Ubuntu 24.04, Docker 29). 9 active services (после удаления `owner` user'а — pool тише): caddy, avito-xapi, avito-monitor, avito-mcp, redis, scheduler, health-checker, telegram-bot, worker (1 инстанс). |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt (`drwgozasaypgphkxyizt`). Pooler 6543. |
| **Single user** | `remacs` (admin, пароль `31415926`). UI логин и парсинг — одна БД. |
| **Single profile** | `iPhone 12 Pro max 11000-13500` (manual_url, owner=NULL → LRU mode). `poll_interval_minutes=5`. |
| **Phone** | OnePlus 8T `110139ce`, USB → Windows ПК. APK `com.avitobridge.sessionmanager` ловит push'ы. |
| **Branch state** | `main` ahead origin = 0. HEAD = `dc91ce5` (search 4xx surface + post-filter). Вся ветка `feat/account-rotation-hardening` смержена. |

### Pool state (2026-05-07 ~07:50 UTC):

| Аккаунт | Avito user | state | JWT TTL |
|---|---|---|---|
| Clone (`42c179db`) | 157920214 | dead | истёк 5 дней назад |
| auto-157920214 (`b5cbf28b`) | 157920214 | active/needs_refresh | **истекает каждые ~24h** — нужен refresh |
| auto-431483569 (`14acfef4`) | 431483569 | cooldown ratchet | подвергался 403 многократно |

---

## 3. Что было сделано в сессии 2026-05-06..07

### Account Pool hardening (Tasks A+B+C, ветка `feat/account-rotation-hardening` → main)

- `f4d48de` — **Task 1**: liveness predicate `.gt("expires_at", NOW()+5min)` в `poll_claim` — pool никогда не выдаёт почти-истёкший JWT
- `cd9f9a2` — **Task 2**: `account_tick._recover_expired_cooldowns` — раз в 30s flip'ит `state=cooldown && cooldown_until<NOW()` обратно в `active` (если сессия свежая) или `needs_refresh` (если нет)
- `5e2d0b2` — **Task 3**: owner-aware claim — `POST /poll-claim {"account_id": X}` пинит конкретного owner'а; polling для autosearch-based профилей передаёт `required_owner=profile.owner_account_id`, retry отключён (wrong owner = forever wrong)
- `4a0e67a` — **hotfix**: `QueryBuilder.gt/gte/lt/lte` — был AttributeError 500 на проде потому что custom httpx wrapper не имел `.gt()`
- `042faf1` — fresh session arrival flip'ит state cooldown/needs_refresh/waiting_refresh → active (раньше только waiting_refresh)
- `a0f4bd2` — UI timestamps в browser-local TZ через `<time data-utc>` + js converter

### URL parser & search 2026-05-07

- `3cca3d0` — **`_is_filter_token`** теперь требует mixed-case + digit. Раньше слишком жадный — ловил lowercase model slug'и (`iphone_12_pro_max`) → попывал → brand/model = None → fallback `query="Apple"` → мусор.
- `dc91ce5` — два фикса:
  1. **xapi search.py** ловит `HTTPError` от curl_cffi и surface'ит upstream Avito 4xx статус наружу (раньше любой 4xx становился 500 → state machine не cooldown'ила правильно).
  2. **polling.py post-filter** — отбрасывает listings'ы где title.lower() не содержит ВСЕ tokens of `parsed_brand + parsed_model`. Self-heals NULL `parsed_brand/parsed_model` re-parse'ом URL on-the-fly.

### Cleanup

- Удалён UI юзер `owner` со всем содержимым: 1 user + 7 profiles + 987 runs + 517 profile_listings + 38 criteria + 4 evals + 17 blacklist + 2 notifications. Listings'ы (товары) оставлены.

---

## 4. Текущее состояние парсинга

### Что работает ✅

- **URL parsing** корректно извлекает `brand="Iphone"`, `model="12 Pro Max"`, `category_path="all/telefony/mobilnye_telefony/apple"`
- **Pool**: 1 active токен → polling делает запросы → Avito отвечает
- **Post-filter** отбрасывает мусор (title не содержит "iphone"+"12"+"pro"+"max")
- **State machine** правильно реагирует на Avito 4xx (cooldown / expire session)

### Что **не** работает ❌

- **Avito возвращает мусор по text-search**. Direct запрос `GET /api/v1/search/items?query=Iphone+12+Pro+Max&category_id=87&sort=date` отдаёт:
  ```
  Форма для склейки стекла iPhone (Молд)
  Зип пакеты 21x12 см / сейф пакеты
  Стекло с заменой iPhone ремонт poco xiaomi
  Замена стекла iPhone ремонт xiaomi poco
  Набор из 6 рюмок Beluga
  ```
  → post-filter отбрасывает всё → `seen=0 new=0`. Ни одного реального iPhone 12 Pro Max.

- **JWT refresh-flow**. Avito-app refresh'ит JWT молча (без push-notification) → APK ничего не ловит → у нас остаётся stale JWT → через 24 часа Avito 403'ит. Manual workaround: logout/login full в Avito-app — push гарантирован.

- **Mobile vs web categoryId mismatch** — мы шлём web id `87` в mobile API endpoint `/15/items`, который ожидает `84`. См. §05.

---

## 5. Action items по приоритету

### КРИТИЧНО — без этого нельзя двигаться дальше

1. **Refresh-flow gap** — pull-based архитектура где xapi помечает `refresh_requested_at` на account при TTL<30мин, APK периодически polls, читает Avito-app SharedPrefs через root, POST'ит свежий JWT либо `POST /refresh-failed` → TG alert. **~10ч работы** (xapi 4ч + APK 4ч + e2e 2ч). Без этого JWT'ы протухают каждые 24h.

### ОСНОВНОЕ — главная цель этой сессии

2. **Правильное формирование запроса.** 3 пути (детально — `DOCS/REFERENCE/05-search-query-formation.md`):
   - **A. Subscription flow (рекомендуется как primary)** — юзер сохраняет поиск в Avito-app как «🔔 autosearch» → наш `autosearch_sync` импортирует subscription_id → polling Task 3 уже умеет работать через `fetch_subscription_items()`. Готовый код есть. Нужен только свежий JWT (зависит от #1) + manual setup в Avito-app.
   - **B. Mitm capture** (опционально, 2-4ч) — на phone'е перехватить реальные `/15/items` запросы Avito-app, дамп `params[*]` → построить brand/model ID mapping → URL parser сможет конвертить web URL → structured params без subscription'а.
   - **C. Decode `f=AS...` token напрямую** (8-15ч реверса, хрупко) — protobuf reverse через jadx + Frida, не рекомендуется.

3. **Mobile vs web categoryId mapping** — добавить `_WEB_TO_MOBILE_CATEGORY` в `avito-monitor/avito_mcp/tools/search.py`, либо дропать `category_id` для URL-based search и полагаться на text query до получения structured params. Quick fix (~30 мин).

### НИЗКИЙ ПРИОРИТЕТ

4. **Phase B соак V2 LLM pipeline** — был запланирован вчера (план `c:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md`). Ждёт чтобы у нас был стабильный polling с реальными iPhone-листингами для evaluation. Заблокирован #2.
5. **Ротация засветившихся секретов** (root password VPS, Supabase JWT, UI пароли) — все они в чате нескольких сессий.
6. **Bug: zombie running runs** — polling.py делает early return при `profile.is_active=false` после создания ProfileRun(running) → запись остаётся `running` навсегда. Минор, можно cleanup'ом.

---

## 6. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/.

Прочитай CONTINUE.md и DOCS/REFERENCE/05-search-query-formation.md.

Главная цель: научиться правильно формировать поисковый запрос к Avito так,
чтобы polling возвращал точные iPhone 12 Pro Max (как Avito-app), а не
fuzzy мусор (формы для склейки стекла, чайники).

Production: VPS 81.200.119.132 + Cloud Supabase Frankfurt. Один UI юзер
remacs/31415926. Один profile (iPhone 12 Pro max 11000-13500, manual_url).
Pool: 1-2 active токена с TTL ~24h (требуют refresh). HEAD=dc91ce5.

Блокер #1: refresh-flow gap (Avito-app рефрешит JWT молча, APK не ловит
push, у нас stale JWT, Avito 403 при TTL<30мин). Без починки этого все
3 пути формирования запроса не сработают (Avito 403'ит).
```

---

## 7. Команды на проверку

```bash
# Containers
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose ps'

# Public smoke
curl -s https://avitosystem.duckdns.org/health

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
        print(f\"  {r[\"nickname\"]:30s} state={r[\"state\"]:15s}{ttl}\")
    await conn.close()
asyncio.run(main())
"'

# Last 5 runs + recent listings
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio, os, asyncpg
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    print(\"=== last 5 runs ===\")
    rs = await conn.fetch(\"SELECT started_at, status, listings_seen, listings_new, error_message FROM profile_runs ORDER BY started_at DESC LIMIT 5\")
    for r in rs:
        print(f\"  {r[\"started_at\"].strftime(\"%H:%M:%S\")} {r[\"status\"]:10s} seen={r[\"listings_seen\"]} new={r[\"listings_new\"]} {(r[\"error_message\"] or \"\")[:60]}\")
    await conn.close()
asyncio.run(main())
"'

# Logs
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose logs --tail=30 avito-xapi | grep -E "search|sub|403|500"'

# Trigger immediate run for the profile
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio
from app.tasks.polling import poll_profile
async def main():
    task = await poll_profile.kiq(\"a37d2226-3907-4a10-a585-22dd519cb431\")
    print(task.task_id)
asyncio.run(main())
"'

# Manual flip account → active (если recovery не сработал)
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose exec -T avito-monitor python -c "
import asyncio, os, asyncpg
async def main():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\")
    conn = await asyncpg.connect(url, statement_cache_size=0)
    await conn.execute(\"UPDATE avito_accounts SET state='active', cooldown_until=NULL, consecutive_cooldowns=0 WHERE id='b5cbf28b-c9fe-46ff-aea1-bc332abf6bad'\")
    await conn.close()
asyncio.run(main())
"'
```

---

## 8. Где детальная документация

| Файл | Что |
|---|---|
| **`DOCS/REFERENCE/05-search-query-formation.md`** | **Основное для следующей сессии** — корень mismatch'а web URL ↔ mobile params, 3 пути решения, известные параметр-ID'ы, refresh-flow gap |
| `DOCS/REFERENCE/01-avito-api.md` | Avito endpoints + headers + structured params |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT, refresh flow, pool state machine |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus + System Clone, Magisk grants, ADB, NotificationListener |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | jadx + curl_cffi + Frida workflow |
| `DOCS/avito_api_snapshots/autosearches/README.md` | реверс /5/subscriptions с live-validated примерами |
| `DOCS/superpowers/plans/2026-05-06-account-rotation-hardening.md` | План A+B+C task'ов (выполнен) |
| `c:/Users/EloNout/.claude/plans/sequential-seeking-trinket.md` | План V2 LLM pipeline (Phase A done, B/C ожидают) |
| `ops/server/{docker-compose.yml,Caddyfile,.env.template}` | Production deploy artifacts |

---

## 9. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md` (homelab Supabase legacy — закрыт)
- **VPS** `/opt/avito-system/.env` (chmod 600 root):
  - `DATABASE_URL` (asyncpg pooler 6543)
  - `SUPABASE_URL=https://drwgozasaypgphkxyizt.supabase.co`
  - `SUPABASE_KEY=sb_secret_*`
  - `AVITO_XAPI_API_KEY=test_dev_key_123`
  - `AVITO_MCP_AUTH_TOKEN=7235ad5be6bbc6ea7dc0a3d692eb51e9ccbc136e184f2222`
  - `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_DAILY_USD_LIMIT=20`
- **APK prefs:** `/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml` (per android-user)
- **Avito-app session:** `/data/user/{0|10}/com.avito.android/shared_prefs/com.avito.android_preferences.xml`
- **DuckDNS** token в `/usr/local/bin/duckdns-update.sh` на VPS
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## TL;DR

1. **Сегодня починили pool** (A+B+C + 4 hotfix'а), polling делает запросы и не падает.
2. **НЕ работает корень**: Avito mobile-API на наш fuzzy text-search возвращает мусор. Нужны structured `params[brand_id][model_id]`.
3. **3 пути** к structured params: subscription flow (готов в коде, ждёт setup в Avito-app), mitm capture (2-4ч), decode `f=AS...` blob (8-15ч реверса). Детали — `05-search-query-formation.md`.
4. **Блокер для всего**: refresh-flow gap. JWT истекает за 24h, APK не ловит молчаливый refresh. Pull-based флоу — план на ~10ч.
5. **Главная цель следующей сессии**: научиться формировать запрос так, чтобы polling возвращал реальные iPhone'ы, а не чайники.
