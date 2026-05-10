# CONTINUE — следующая сессия

> **Если ты Claude в новой сессии:** прочитай этот файл целиком + `DOCS/REFERENCE/README.md` (последние «Обновлено» 2026-05-09/10) + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory в `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`. Главная цель — **автоматизация диалогов с продавцами для лотов в статусе "В работе"**.
>
> **Если ты пользователь:** скопируй промпт из §9 в новую сессию.

---

## §1. Что было сделано в прошлых сессиях (контекст 30 секунд)

Стек уже работает end-to-end:
- **Polling** ходит в Avito mobile API через ru-vpn (`155.212.217.226`), достаёт лоты структурированным запросом (`params[110617]=model_id&params[110618]=brand_id&params[110680]=type_id`), пагинация до 25 страниц, jitter 2-5 сек, активные часы 8-23 Moscow, random breaks 8-12 polls / 20-40 мин.
- **Pre-check API killers** в Python — 5 правил по `listing.parameters` (Работа устройства / Аккумулятор / Не работают функции / Не работают датчики / Камера). На текущей выдаче **35 / 78 листингов** уходят в red bucket без LLM-вызова.
- **LLM evaluation** (V2 per_criterion strategy) — 8 hard criteria + 2 новых text-based (`modem_broken`, `biometric_broken`). Bucket: red если any criterion red ≥ 0.7, green если ВСЕ green ≥ 0.7, иначе grey.
- **UI**: thumbnail-сетка фото в expanded body, lightbox с TaoBao magnifier (lens + adjacent zoom 3×) + wheel zoom + drag-pan, цветные bucket-chips с tab-aware counts, 3-state decision toggle (✗/—/✓) + bulk Apply.
- **Reservation tracking** schema готов (`listings.reservation_status / reserved_at_price` + `listing_status_events` table) — ждём первого живого reserved-event для confirmation field name в Avito payload.

**Текущая выдача** (профиль `iPhone 12 Pro max 10500-13500`, 78 active listings):
- red: 52 (api-killers + LLM)
- grey: 36
- green: 0 (criteria набор пока довольно строгий — для байер-перепродажи нужно убрать `screen_broken` / `parts_only` из profile_criteria, см. memory `project_screen_broken_not_killer.md`)

---

## §2. Production state — 2026-05-10

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU). 9 контейнеров up. systemd `avito-vpn-tunnel.service` up. |
| **Outbound к Avito** | xapi → `socks5h://172.18.0.1:1081` → ssh -D туннель → ru-vpn `155.212.217.226` |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt project `drwgozasaypgphkxyizt`. Pooler 6543 + `prepared_statement_cache_size=0` для asyncpg+pgbouncer. |
| **Single user** | `remacs` (admin) |
| **Single profile** | `iPhone 12 Pro max 10500-13500`, search=alert=10500-13500, with_delivery=true (в URL — Avito mobile API игнорирует, но в нашем post-filter работает) |
| **Pool** | `auto-431483569-61238c` active TTL 22ч. `auto-157920214-61238c` needs_refresh (JWT истёк). Cap cooldown 60 мин (было 24ч). |
| **Phone** | OnePlus 8T `110139ce`, USB к Windows ПК. Multi-profile в Avito-app — ОДИН JWT для всех 4 профилей |
| **HEAD** | `b80d382` (feat: modem_broken + biometric_broken). Запушено на origin/main. |
| **Migrations head** | `0012_reservation_tracking` (chain: 0010 catalog → 0011 humanization → 0012 reservation) |

---

## §3. Главная цель next session — диалоги с продавцами

Когда юзер нажимает **«✓ В работу»** на карточке лота — это значит лот интересен и надо начинать диалог с продавцом. Сейчас этот шаг manual (юзер сам пишет в Avito-app). **Автоматизировать первичный сбор информации** через бот.

### §3.1 Что бот должен делать

После `accept` лота:
1. **Создать чат с продавцом** через Avito messenger API (`POST /1/messenger/createItemChannel` — есть в xapi).
2. **Отправить первое сообщение** — приветствие + квалифицирующие вопросы (приоритет — то что не указано в описании / параметрах).
3. **Слушать ответы** — через SSE стрим (уже есть для текущего messenger_bot reliability).
4. **Парсить структурированные данные**: уточнённая цена, готовность к торгу, доставка, дополнительные фото, время для встречи/call.
5. **Передать оператору** (telegram-канал) когда диалог дошёл до точки решения.

### §3.2 Состав вопросов (бизнес-логика, нужен brainstorm с юзером)

Например (нужно подтвердить):
- «Здравствуйте! Цена окончательная или возможен торг?»
- «Можно ли увидеть АКБ статус через настройки? Скрин пришлёте?»
- «Видеообзор сделать сможете? Хочется убедиться что всё работает.»
- «Доставка Авито? Сколько по времени получится?»
- «На лоте указано N — это последняя цена или есть рассылочная скидка?»

Разные категории вопросов для разных профилей (iPhone vs ноутбук vs etc) → возможно тоже YAML-driven как criteria_templates.

### §3.3 Что хранить per-dialog

- `dialog_id` (per chat / per accepted listing)
- `channel_id` (Avito messenger channel)
- `state` machine: `awaiting_response`, `negotiating`, `ready_for_operator`, `seller_silent`, `closed`
- `extracted_data` JSONB: цена_финальная, торг_возможен, акб_фото_url, доставка_возможна, etc.
- `messages` history (in/out)
- `next_action_at` для timeouts

---

## §4. Что уже есть в коде (reuse)

| Где | Что | Статус |
|---|---|---|
| `avito-xapi/src/workers/http_client.py` | `create_channel_by_item(item_id)`, `send_text(channel_id, text)`, `get_messages(channel_id)`, `mark_read(channel_ids)` | ✅ ready |
| `avito-xapi/src/routers/messenger.py` | HTTP wrappers поверх http_client — POST/GET endpoints | ✅ ready |
| `avito-monitor/app/services/messenger_bot/runner.py` | SSE listener loop (long-lived `/api/v1/messenger/realtime/events`) с reconnect+backoff | ✅ ready (используется reliability ботом) |
| `avito-monitor/app/services/messenger_bot/handler.py` | Dispatcher для inbound events. `_bump_event() / _bump_reply()` counters | ⚠ нужен новый branch для seller-dialog (сейчас всё уходит в reliability auto-reply) |
| `avito-monitor/app/services/messenger_bot/{rate_limit,dedup,kill_switch,whitelist}.py` | Anti-detection helpers — глобальный rate-limit, дедуп ответов, kill-switch, whitelist | ✅ reuse |
| `avito-monitor/app/db/models/messenger_chat.py + messenger_message.py + chat_dialog_state.py` | Schema для chat-state + messages | ✅ reuse — нужно расширить `chat_dialog_state` под новые fields |

**Важно:** существующий messenger_bot — это **reliability auto-reply** (имитация активности юзера через ответы на чужие чаты). Бизнес-диалоги это **разный** flow: triggered не входящим сообщением, а accept-action юзера. Соответственно нужна отдельная state machine — но reuse `runner.py` для inbound listening + `dedup.py` / `rate_limit.py`.

---

## §5. План на сессию (примерно 4-6 часов)

### §5.1 Brainstorm (~30 мин)
- Согласовать с юзером список вопросов (по приоритету, по категориям)
- Согласовать state machine состояний диалога
- Что считать «готов передать оператору»
- Когда сдаваться (продавец молчит N часов)
- TG-канал для оператор-handoff (общий с green-алертами или отдельный?)

### §5.2 Schema (~30 мин)
- Migration 0013: новая таблица `seller_dialogs` (или расширение `chat_dialog_state`):
  - `id`, `profile_listing_id` FK, `channel_id` (Avito), `state` enum, `extracted` JSONB, `next_action_at`, `created_at`, `closed_at`, `closed_reason`
- Migration 0014: `dialog_questions` (если scripted YAML — может не нужно table, всё в YAML)

### §5.3 Question library (~1ч)
- `app/data/dialog_questions.yaml` — scripted templates с placeholders. Каждый question: `key`, `text`, `expects` (price | yesno | photo | text), `next_question_if_yes`, `next_question_if_no`, `priority`.
- Или LLM-driven (более гибко, но дорого) — обсудить с юзером.

### §5.4 Trigger + flow (~2ч)
- Таска `start_seller_dialog(profile_listing_id)` triggered после `user_action='accepted'`.
- Создать channel через xapi.
- Послать первое сообщение из question library.
- SSE listener при inbound от seller → `process_seller_reply(channel_id, message_text)`:
  - LLM extraction `extract_dialog_field` (или regex для simple cases)
  - Update `seller_dialogs.extracted`
  - Решить next question или handoff

### §5.5 UI (~1ч)
- В таб «В работе» — для каждой карточки показать dialog state + last messages
- Кнопки: «Передать оператору» / «Закрыть диалог» / «Написать вручную»

### §5.6 Test (~30 мин)
- Юзер нажимает Accept на одном тестовом лоте → бот стартует → первое сообщение уходит. Watch logs.
- Имитировать ответ продавца через Avito-app на phone'е → SSE catch → бот следующий вопрос.

---

## §6. Где документация

| Файл | Что |
|---|---|
| `DOCS/REFERENCE/README.md` | Главный index. Последняя секция «Обновлено» 2026-05-09/10 описывает все недавние фичи. |
| `DOCS/REFERENCE/01-avito-api.md` §H | Все endpoints + headers + JWT structure |
| `DOCS/REFERENCE/02-auth-and-tokens.md` | JWT lifecycle, refresh, ban detection. Memory `reference_avito_token_refresh.md` дополнительно: refresh-flow gap (silent JWT refresh в Avito-app не push'ит — наша БД отстаёт). |
| `DOCS/REFERENCE/03-android-setup.md` | OnePlus, Magisk, ADB, NotificationListener |
| `DOCS/REFERENCE/05-search-query-formation.md` | Web URL ↔ mobile API mismatch |
| `DOCS/REFERENCE/10-blob-decoder.md` | Декодер `f=AS...` blob — как мы вытащили catalog |

**Memory** (auto-loaded в каждую сессию через `MEMORY.md`):
- `feedback_no_qrator_excuse.md` — НЕ списывать ошибки на QRATOR; Avito-app работает = root cause в наших запросах
- `reference_outbound_ip.md` — ru-vpn 155.212.217.226 не блокирован per-IP; rate-limit per-JWT
- `project_filter_change_reeval.md` — bump criteria → re-LLM всех active кроме manual:* blacklist
- `project_bucket_flow_design.md` — green→urgent TG (план), grey→ручной разбор, red→видим с badge
- `project_screen_broken_not_killer.md` — для байера разбитый экран не deal-breaker
- `project_price_tiered_criteria.md` — backlog: строгость criteria зависит от цены внутри alert-вилки

---

## §7. Команды на проверку (любая сессия)

### §7.1 Pool state + JWT TTL
```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm --no-deps avito-monitor python -c "
import asyncio, asyncpg, os, json, base64
from datetime import datetime, timezone
async def m():
    conn = await asyncpg.connect(os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\",\"postgresql://\"), statement_cache_size=0)
    rs = await conn.fetch(\"SELECT a.nickname, a.state, s.tokens, s.expires_at FROM avito_accounts a LEFT JOIN avito_sessions s ON s.account_id=a.id AND s.is_active=true ORDER BY a.nickname\")
    now = datetime.now(timezone.utc)
    for r in rs:
        ttl = round((r[\"expires_at\"] - now).total_seconds()/3600, 1) if r[\"expires_at\"] else None
        print(f\"  {r[\"nickname\"]:<25} state={r[\"state\"]:<14} ttl={ttl}h\")
    await conn.close()
asyncio.run(m())
"'
```

### §7.2 Bucket distribution + criteria
```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm --no-deps -v /opt/avito-system/repo/final_check.py:/app/d.py avito-monitor python /app/d.py'
```

### §7.3 Tunnel + containers
```bash
ssh root@81.200.119.132 'systemctl is-active avito-vpn-tunnel.service && cd /opt/avito-system && docker compose ps --format "table {{.Service}}\t{{.Status}}"'
```

### §7.4 UI check
```bash
curl -sS -o /dev/null -w "/listings -> %{http_code}\n" https://avitosystem.duckdns.org/listings
```

---

## §8. Что в backlog (не для этой сессии)

- **TG-канал для urgent green** — уведомление оператору при новом green буцет (`project_bucket_flow_design.md`)
- **Reservation tracking field name confirmation** — пока probe-only по 5 candidate keys, ждём живой reserved-event
- **Pool decay через `last_event_at`** — state machine готов, но `routers/accounts.py` пока не пишет колонку, decay inactive
- **LLM `not_starting` ещё триггерится на marketing-фразы** — иногда false-positive на «не работает фронтальная камера, но сам аппарат рабочий»; переписать prompt v3
- **Price-tiered criteria** (backlog `project_price_tiered_criteria.md`) — строгость от цены
- **Profile criteria для байера**: убрать `screen_broken`, `parts_only` (косметика не killer для перепродажи)
- **Per_listing strategy** для случаев где per_criterion даёт false positives на marketing copy

---

## §9. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/.

Прочитай CONTINUE.md (§1-§5) — там полный контекст текущего state и
плана новой фазы: автоматизация диалогов с продавцами для лотов
"в работе".

Что сейчас работает: polling с humanization, api_killer pre-check,
V2 LLM pipeline (8 hard criteria + modem_broken/biometric_broken),
bulk decision UI, reservation tracking schema. Текущая выдача 78
лотов, 52 red / 36 grey / 0 green на профиле "iPhone 12 Pro max
10500-13500".

Главная цель next: dialog flow с продавцом после accept. Скрипт
квалифицирующих вопросов (цена/торг/АКБ-фото/доставка), state
machine диалога, передача оператору. Reuse существующего
messenger_bot infra (SSE listener, dedup, rate_limit) — но separate
flow от текущего reliability auto-reply.

Production: VPS 81.200.119.132 + Cloud Supabase Frankfurt. UI
https://avitosystem.duckdns.org. HEAD = b80d382.

Сначала brainstorm с юзером (§5.1) — список вопросов и state
machine. Затем по плану §5.2-§5.6.
```

---

## §10. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`:
  - `DATABASE_URL=postgresql+asyncpg://postgres.drwgozasaypgphkxyizt:...@aws-1-eu-central-1.pooler.supabase.com:6543/postgres?...`
  - `AVITO_XAPI_API_KEY=test_dev_key_123`
  - `AVITO_MCP_AUTH_TOKEN=...`
  - `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`
  - `AVITO_SOCKS_PROXY=socks5h://172.18.0.1:1081`
- **VPS SSH ключ к ru-vpn:** `/root/.ssh/id_ed25519`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`

---

## §11. Что НЕ работает (избежать повторений)

- ❌ Не предполагать, что `screen_broken` / `parts_only` — killer для байера. Memory `project_screen_broken_not_killer.md`
- ❌ Не записывать ошибки 4xx на QRATOR. Memory `feedback_no_qrator_excuse.md`
- ❌ `auto_red:*` blacklist — НЕ insert'ить, red это визуальный signal, manual:reject — единственный hide
- ❌ `criteria_set_hash` это VARCHAR(64) — нельзя добавлять long suffixes
- ❌ `ConditionClass.BROKEN` не существует — enum: WORKING/BLOCKED_ICLOUD/BLOCKED_ACCOUNT/NOT_STARTING/BROKEN_SCREEN/BROKEN_OTHER/PARTS_ONLY/UNKNOWN
- ❌ `_close_disappeared` пропускать на incremental polls (только full pagination)
- ❌ `image` column в `listings` — поле JSONB, не Text. Конвертировать через `model_dump(mode='json')`

---

## TL;DR

Polling+LLM-pipeline стабильно работает, лоты находятся правильно классифицируются. **Следующий шаг — автоматический диалог с продавцом** для лотов которые юзер пометил «В работу». Reuse существующего messenger_bot infra (SSE listener, rate_limit, dedup), но новый business flow: scripted questions → state machine → operator handoff. Сначала brainstorm вопросов и state machine с юзером.
