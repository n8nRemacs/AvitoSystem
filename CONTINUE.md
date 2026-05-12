# CONTINUE — следующая сессия

> **Если ты Claude в новой сессии:** прочитай этот файл целиком + `DOCS/REFERENCE/README.md` (общая карта state'а) + `DOCS/superpowers/specs/2026-05-10-seller-dialog-design.md` (rev 4, дизайн всех 9 stages) + `c:/Projects/Sync/CLAUDE.md` (глобальные секреты) + auto-memory в `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/MEMORY.md`. **Главная задача сейчас — доработка UI seller-dialog** (после shipped Phase A + B 2026-05-11).

---

## §1. TL;DR

Phase A (`contact → questions_setup`) и Phase B (Опрос autopilot — `questions_setup → questions → SUGGEST price_negotiation`) **зашиплены в prod 2026-05-11**, end-to-end валидированы:

- accept лота → auto-greeting улетает продавцу → SSE handler детектит ответ через LLM → переход в `questions_setup`
- operator кликает «➜ настрой опрос» на карточке → modal с 11 baseline-темами + ad-hoc-поле → «Запустить опрос» → бот шлёт opening line + первый вопрос
- продавец отвечает → LLM парсит ответ + side_topics → закрывает темы по одной → recap → ждёт «всё верно» → SUGGEST + TG-пинг

13 commits на main за 2026-05-11. 17 unit-тестов Phase B + 21 Phase A проходят.

**Сейчас следующий этап — UI доработка** (на твоё указание).

---

## §2. Production state — 2026-05-12

| Что | Где |
|---|---|
| **VPS** | `81.200.119.132` (Beget RU). 10 контейнеров up. |
| **Public URL** | `https://avitosystem.duckdns.org` |
| **БД** | Cloud Supabase Frankfurt project `drwgozasaypgphkxyizt`. Pooler 6543 + `prepared_statement_cache_size=0`. |
| **Outbound к Avito** | ru-vpn `155.212.217.226` через SOCKS5 SSH-туннель `socks5h://172.18.0.1:1081` |
| **Профиль** | `iPhone 12 Pro max 10500-13500` (единственный пока) |
| **HEAD на main** | `bfda244 fix(ui): modal cancel + ad-hoc buttons via delegated handlers` |
| **Alembic head** | `0014_phase_b_topics` (chain: 0012 reservation → 0013 seller_dialogs → 0014 phase_b_topics) |
| **Phone** | OnePlus 8T `110139ce`, USB к Windows ПК |
| **V2 reliability autoreply** | **OFF** через `MESSENGER_BOT_ENABLED=false` (соак-таймаут). SSE listener сам жив, seller_dialog ветка работает |

### §2.1 Контейнеры

| Сервис | Назначение |
|---|---|
| `caddy` | HTTPS reverse-proxy, ACME |
| `avito-xapi` | FastAPI шлюз к мобильному Avito API (curl_cffi + SOCKS5) |
| `avito-monitor` | Web UI + поиск/мониторинг (FastAPI + Jinja + Tailwind) |
| `avito-mcp` | FastMCP SSE сервер |
| `worker` | TaskIQ-воркер (polling + LLM analysis + seller_dialog tasks) |
| `scheduler` | TaskIQ-планировщик (cron'ы) |
| `messenger-bot` | SSE listener `/api/v1/messenger/realtime/events` → handler → seller_dialog ветка. V2 reliability ветка отключена через env |
| `telegram-bot` | aiogram long-poll бот для уведомлений |
| `health-checker` | account_tick loop, scenarios A-I |
| `redis` | TaskIQ broker + кэши |

---

## §3. Seller-dialog pipeline — что есть сейчас

### §3.1 State machine

Реализованы и работают в проде stages **1-3**:

```
[1. Контакт]                          AUTO
   ↓ продавец ответил «да продаётся» (LLM detect_yes_selling)
[2. Настройка опроса]                 OPERATOR
   ↓ operator → modal → выбирает темы → «Запустить опрос»
[3. Опрос]                            AUTO bot
   ↓ темы закрыты + recap confirmed
   → SUGGEST → TG-пинг #2 operator'у
   → operator click «Подключиться к торгу» (TODO кнопка)
[4. Согласование цены]                Phase D, stub
   ↓ ... ↓
[9. Сделка закрыта]                   Phase D, заглушка
```

### §3.2 Phase A — `contact` stage

- Acceptance в табе "Новые" → TaskIQ `start_seller_dialog` → xapi `create_channel_by_item` + `send_text(GREETING_TEMPLATE)` → dialog row создан, stage='contact'.
- GREETING_TEMPLATE: «Здравствуйте! Меня заинтересовал ваш аппарат. Ещё продаётся?»
- SSE inbound через messenger-bot → seller_dialog branch (line ~417 в `messenger_bot/handler.py`) → `handle_seller_inbound` → LLM `detect_yes_selling` (threshold 0.7) → если True → транзишн на `questions_setup` + TG-пинг #1 operator'у.

**Schema** (`alembic 0013_seller_dialogs`): `seller_dialogs(id, profile_id, listing_id, channel_id, stage, operator_mode, opened_at, last_event_at, closed_at, closed_reason)` + `messenger_messages.dialog_id` FK nullable.

### §3.3 Phase B — `questions_setup` + `questions` stages

- `questions_setup` карточка показывает badge «➜ настрой опрос» — кликабельная. Открывает modal на нативном `<dialog>` элементе:
  - default-unchecked checkbox'ы для 11 baseline-тем профиля
  - textarea «Добавить свой вопрос» + кнопка «+» — ad-hoc вопрос upsert'ится в `dialog_topics` + auto-link в `profile_dialog_topics` → permanent extension библиотеки
  - кнопка «Запустить опрос» (submit) / «Отмена» (закрывает modal)
- Submit → endpoint `/dialogs/{id}/start-questions` → `init_dialog_topics` (INSERT'ит выбранные темы в `seller_dialog_topics` со status='pending') → transition в stage='questions' → enqueue `dialog_tick_questions.kiq(dialog_id)`
- **Worker** `dialog_tick_questions`: первый tick шлёт OPENING_LINE «У меня есть несколько вопросов по Вашему аппарату, ответьте пожалуйста, если Вас это не затруднит.» + `sleep(3)` + первый вопрос. Дальше один-за-другим по `priority`. После закрытия всех тем — `formulate_recap` → status='pending_answer'.
- **SSE handler** stage=questions ветка: при inbound — `parse_topic_answer` → mark_answered + side_topics (LLM ловит когда продавец сам приоткрыл другие открытые темы). При recap reply — `parse_seller_agreement` → если yes → status='confirmed' + TG-пинг #2.

**Schema** (`alembic 0014_phase_b_topics`):
- `dialog_topics` — global library: `key`, `title`, `category`, `default_phrasing`, `expected_format`, `created_by`, `is_active`. Seeded из `app/data/dialog_topics.yaml`.
- `profile_dialog_topics(profile_id, topic_key, priority)` — какие темы в baseline профиля.
- `seller_dialog_topics(id, dialog_id, topic_key, priority, status, question_text, question_msg_id, answer_text, answer_msg_id, asked_at, answered_at, retry_count)` — per-dialog state machine.
- `seller_dialogs +recap_text/recap_msg_id/recap_status` — recap state.

**11 baseline тем** (iPhone 12 Pro Max, см. `app/data/dialog_topics.yaml`):
1. `battery_health` (АКБ %) — percent
2. `face_id_works` — yesno
3. `icloud_unlinked` — yesno
4. `replaced_display` — yesno
5. `broken_glass` — yesno
6. `display_stains_stripes` — yesno
7. `broken_back` — yesno
8. `cameras_work` — text
9. `charging_stability` — text
10. `replaced_parts` — text
11. `complectness` (коробка/кабель/зарядка) — text

`delivery_method` отложен в Phase D (часть торга).

### §3.4 LLM dispatchers (4 шт, в `app/services/llm_analyzer.py`)

| Функция | Что делает | Prompt |
|---|---|---|
| `formulate_question(topic, history_tail)` | Сформулировать вопрос по теме, тон natural & polite | `app/prompts/dialog_formulate_question.md` |
| `parse_topic_answer(topic, seller_text, open_topics)` | Парс ответ продавца → answered/unclear/off_topic + extracted + side_topics | `app/prompts/dialog_parse_topic_answer.md` |
| `formulate_recap(answered)` | Собрать recap-сообщение (с deterministic fallback) | `app/prompts/dialog_formulate_recap.md` |
| `parse_seller_agreement(text)` | Классификация ответа на recap: yes/no/unclear | `app/prompts/dialog_parse_seller_agreement.md` |

Все 4 через OpenRouter `google/gemini-2.5-flash-lite`, safe fallback на ошибке (не блокировать pipeline).

### §3.5 TG-пинги

2 типа в `notifications` таблице, диспатчатся через `app/tasks/notifications.py` + Jinja templates в `app/prompts/messenger/`:
- `seller_dialog_ready_to_setup` — при `contact → questions_setup`
- `seller_dialog_ready_to_negotiate` — при `questions → SUGGEST price_negotiation`

Текст: `🟢 Лот {avito_id} ({title}, {price}₽)\n{action_prompt}\n→ {kanban_url}`.

### §3.6 UI surface

- **Kanban** `?tab=in_progress` — 3 колонки: Контакт / Настройка опроса / **Опрос**. Сверху dropdown фильтра профиля.
- **Reject** — кнопка «× Отклонить» в каждой карточке (любого stage). POST на `/listings/{pid}/{lid}/action?action=reject` → blacklist + close_dialog(reason='rejected_by_operator').
- **Setup modal** — нативный `<dialog>` + vanilla JS. Trigger через delegated listener в parent template (`<script>` injected via innerHTML НЕ исполняются — это известная DOM rule, поэтому ad-hoc handler тоже delegated).
- **Topic library** `/dialog-topics` — page для view всех тем + add form.

---

## §4. Главная цель next session — доработка UI

Юзер хочет улучшить UX seller-dialog flow. Конкретики пока не задано — нужно обсудить в начале новой сессии что именно править. Возможные направления (см. spec rev 4 §4.7 и Phase C scope в CONTINUE.md backlog):

### §4.1 Логичные кандидаты на доработку

1. **Drawer вместо modal** — `dialog_drawer.html` slide-out справа с lazy-load (`hx-get /dialogs/{id}/drawer`). Внутри: фотогалерея, chat history с timestamps + read-markers, extracted_data sidebar (закрытые/не закрытые темы с ответами), кнопки stage-specific actions. Это Phase C по плану.
2. **Карточка `questions_setup`** сейчас компактная — нет превью первого ответа продавца. Можно добавить snippet inbound message внутри карточки.
3. **Карточка `questions`** показывает badge «идёт опрос», но без счётчика «3/7 закрыто». Можно добавить.
4. **`confirmed` recap → кнопка «Подключиться к торгу»** на карточке — сейчас её нет, только TG-пинг. Operator должен зайти в БД ручкой UPDATE stage. Это блокер для real progress в Phase D.
5. **`/dialog-topics` библиотека** — пока минимум (view + add). Edit/delete — через SQL. Можно расширить inline-edit.
6. **Profile filter** работает, но без визуальной обратной связи когда выбран профиль (например, ничего в выдаче — пустое kanban без сообщения «нет лотов для этого профиля»).
7. **Stage-specific cards** — сейчас все три карточки структурно одинаковы (только badge меняется). По spec rev 4 каждый stage должен иметь свой KPI-strip.

### §4.2 Что вне доработки UI

- **Stages 4-9** (Phase D) — отдельная фаза, не UI.
- **Silence-timeout worker** (Phase E) — backend.
- **Severity-per-topic + auto-pretick** (V1.5) — нужна статистика.
- **Whitelist bug в V2 reliability** — отдельный baклог, V2 пока выключен.

---

## §5. Backlog

### §5.1 Известные мелочи (V1.5)

- **AVITO_OWN_USER_ID env** не сконфигурирован → если Avito будет echo'ить наши outgoing'и через SSE, direction в `messenger_messages` будет грязный («in» вместо «out»). Установить когда уверены какой user_id в pool принадлежит нам.
- **SSE durability / catch-up** — текущий listener теряет события при reconnect (нет resume-token). Решение: periodic pull `/channels/{id}/messages` для active dialog'ов + dedup по PK.
- **«Евгений: » prefix в SSE text payload** — SSE handler получает text с префиксом имени отправителя, в REST-API без префикса. Нормализовать.
- **accept→reject race** — если operator reject'ит лот ДО того как async `start_seller_dialog` job создал dialog row, worker всё ещё создаст dialog (с уже-blacklisted listing). Фикс: проверять `profile_listings.user_action` в worker.
- **accept→reject→accept resurrection** — второй accept не реанимирует закрытый dialog (idempotency на existing). Если нужно — clear closed_at в start или явная resurrect-логика.
- **`RELIABILITY_DISABLED_SCENARIOS=G`** — раньше scenario G в health-checker'е скипалась потому что messenger-bot не был задеплоен. Теперь сервис есть — пора включить probe.
- **docker-compose.yml не в git** — `/opt/avito-system/docker-compose.yml` редактируется напрямую на VPS, расходится с любой локальной копией. Решить: положить в `ops/docker-compose.production.yml` или принять как ops-only артефакт.
- **V2 reliability whitelist bug** — `whitelist_own_listings_only=True` не отсёк чужой канал (когда seller_dialog row временно отсутствовал из-за worker-разрыва, бот успел ответить продавцу «Минуту, оператор»). Разобраться когда вернёмся к V2.

### §5.2 Будущие фазы seller-dialog

- **Phase C**: drawer + полный screen «Настройка опроса» + operator overrides (+ Уточнить / Передать вручную / drag-drop reorder тем). См. spec rev 4 §4.7.
- **Phase D**: stages 4-9 (`price_negotiation` → `price_changed` → `purchased` → `shipped` → `received` → `closed`). Включает «Согласование цены» (operator-driven), polling `items/{id}.price` watch, shipment markers, Avito-delivery tracking (V1.5).
- **Phase E**: SLA worker `dialog_silence_tick` (silent auto-reject на 1/3, notified-with-prolongate на 5/7) + 4 оставшихся TG-пинга + sortings/filters в kanban + Phase 2 smart auto-tick.

---

## §6. Команды для проверки состояния (любая сессия)

### §6.1 БД — seller_dialogs + topics

```powershell
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm --no-deps -w /app -e PYTHONPATH=/app avito-monitor python -c "
import asyncio, asyncpg, os
async def m():
    url = os.environ[\"DATABASE_URL\"].replace(\"postgresql+asyncpg://\", \"postgresql://\")
    c = await asyncpg.connect(url, statement_cache_size=0)
    rows = await c.fetch(\"\"\"
        SELECT sd.stage, sd.operator_mode, count(*),
               sum((sd.channel_id IS NOT NULL)::int) AS with_channel
        FROM seller_dialogs sd
        WHERE sd.closed_at IS NULL
        GROUP BY sd.stage, sd.operator_mode
        ORDER BY 3 DESC
    \"\"\")
    for r in rows: print(dict(r))
    await c.close()
asyncio.run(m())"'
```

### §6.2 Worker логи на seller_dialog

```powershell
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose logs --tail=200 worker 2>&1 | grep -iE 'seller_dialog|dialog_tick|start_seller|formulate_question|parse_topic|recap|ERROR'"
```

### §6.3 Health check

```powershell
curl.exe -sS -o NUL -w "kanban -> %{http_code}`n" "https://avitosystem.duckdns.org/listings?tab=in_progress"
ssh root@81.200.119.132 "cd /opt/avito-system && docker compose ps --format 'table {{.Service}}\t{{.Status}}'"
```

### §6.4 Дамп активных диалогов

В корне репо есть готовые diag-скрипты (untracked): `diag_stages.py`, `diag_recent.py`, `diag_seller_dialogs.py`. Запускаются через mounted volume:

```bash
ssh root@81.200.119.132 'cd /opt/avito-system && docker compose run --rm --no-deps -v /opt/avito-system/repo/diag_stages.py:/app/d.py -w /app -e PYTHONPATH=/app avito-monitor python /app/d.py'
```

---

## §7. Промпт-стартер для новой сессии

```
Проект: c:/Projects/Sync/AvitoSystem/

Прочитай CONTINUE.md (§1-§4), DOCS/REFERENCE/README.md, и
DOCS/superpowers/specs/2026-05-10-seller-dialog-design.md.

Seller-dialog Phase A + B зашиплены 2026-05-11. End-to-end
работает: accept → contact → questions_setup → questions →
recap → SUGGEST. Текущая задача — доработка UI (§4.1 даёт
кандидатов — drawer вместо modal, кнопка «Подключиться к
торгу» на карточке confirmed, и т.п.).

Уточни у меня что именно править сейчас, потом invoke
superpowers:brainstorming для дизайна.

Production: VPS 81.200.119.132 + Cloud Supabase Frankfurt.
UI https://avitosystem.duckdns.org. HEAD = bfda244.
V2 reliability bot выключен (MESSENGER_BOT_ENABLED=false).
```

---

## §8. Что НЕ работает / избежать повторений

- ❌ **Никогда не пересобирай только один service** через `docker compose build avito-monitor` — shared image `./repo/avito-monitor` собирается per-service. Worker/scheduler/messenger-bot останутся со старым кодом. **Использовать**: `docker compose build` (без аргументов) + `docker compose up -d --force-recreate <все потребители>`.
- ❌ **`<script>` теги в HTML, инжектируемом через `innerHTML`, НЕ выполняются**. Это DOM security rule. Solution: delegated handlers в parent template, либо вручную создавать новые `<script>` элементы через `document.createElement`, либо inline `onclick` атрибуты.
- ❌ **`templates.TemplateResponse` новая сигнатура**: `(request, name, context)` позиционно, а не `(name, ctx_with_request)`. Старая работала, новая Starlette требует позиционный request. Чекни Phase A endpoints как образец.
- ❌ **JWT-сессии могут стать server-side-зомби**: TTL валиден, но Avito ревокнул раньше → 401. Recovery: запустить Avito-app на телефоне на 60 сек, APK push'ит свежий JWT.
- ❌ **Avito createItemChannel хочет itemId как int**, не string. SendMessage разворачивает response в `result.message.{id, ...}`, createChannel — в `result.channel.{id, ...}`.
- ❌ **Не забывать регистрировать новые TaskIQ-task'и** в `app/tasks/broker.py::_register_tasks()` через import — иначе worker не подхватит. (Фаза B `dialog_tick_questions` зарегистрирован автоматически через существующий import `seller_dialog_tasks`.)
- ❌ **Card partials НЕ должны линковать на `/listings/{id}`** — этот route не существует. Использовать Avito URL или drawer (Phase C).
- ❌ **Не deploy'ить через rsync с Windows** — нет в системе. Использовать `tar + scp + ssh tar -xzf` (видно в недавних коммитах bulk-syncov).
- ❌ **PowerShell не имеет grep** — либо grep внутри ssh, либо PowerShell `Select-String`.

---

## §9. Где секреты

- **Глобальные:** `c:/Projects/Sync/CLAUDE.md`
- **VPS** `/opt/avito-system/.env`
- **Auto-memory:** `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/`
