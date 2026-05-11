# Phase B — Опрос autopilot (Seller-dialog stages 2 + 3)

**Дата:** 2026-05-11
**Статус:** утверждено пользователем, готово к плану (writing-plans)
**Базовый дизайн:** [`2026-05-10-seller-dialog-design.md`](./2026-05-10-seller-dialog-design.md) (rev 4)
**Предыдущая фаза:** Phase A (commit `5b81a31` + `b4b49dd`, реализована и валидирована 2026-05-11)

---

## 1. Цель

Доделать seller-dialog pipeline для двух следующих стадий после `contact`:

- **`questions_setup`** (operator-driven) — оператор через UI выбирает темы для опроса конкретного лота и нажимает «Запустить опрос».
- **`questions`** (bot auto) — бот ходит по выбранным темам один-за-один, парсит ответы продавца, формирует recap, ждёт подтверждения от продавца, и SUGGEST'ит operator'у переход в `price_negotiation`.

После Phase B карточка лота автоматически проходит цепочку `accept → contact → questions_setup → questions → recap_confirmed → SUGGEST в Согласование цены`, минимизируя ручной труд оператора на quasi-механической части (стандартные вопросы перед торгом).

Дополнительно: фильтр по профилю в kanban «В работе» — оператор видит только лоты конкретной модели.

## 2. Non-goals (что НЕ в Phase B)

- Silence-timeout worker (`dialog_silence_tick`) — отложен в **Phase E**. Dialog'и без ответа продавца зависают; operator чистит через кнопку «Отклонить».
- Slide-out drawer для карточки — Phase B использует **modal**. Drawer = Phase C.
- Severity-per-topic + auto-pretick — Phase 2 backlog (нужна статистика).
- Stages 4-9 (price negotiation → deal closure) — Phase D.
- Per-stage Avito-side проверки (items/{id} price watch, shipment markers) — Phase D/E.
- TG-пинги SLA timeout — Phase E (только 2 transition-пинга в Phase B).
- **Тема `delivery_method`** — обсуждение доставки требует подхода (не всем продавцам можно/нужно отправить, "в лоб" через LLM много отказов). Объединяется с этапом 4 (Согласование цены) — обсуждение скидки + способа передачи как единый торг-блок. Сейчас delivery — операторская часть, не LLM-вопрос.

## 3. Принятые решения (brainstorm 2026-05-11)

| # | Решение | Обоснование |
|---|---|---|
| Q1 | **Bundle stages 2+3** (не разбиваем по mini-фазам) + **фильтр по профилю** в kanban | Связанные стадии: B-only оставит operator писать руками 17 текущих карточек. Фильтр нужен уже для подготовки к нескольким профилям. |
| Q2 | **11 baseline тем для iPhone 12 Pro Max**: battery_health, face_id_works, icloud_unlinked, replaced_display, broken_glass, display_stains_stripes, broken_back, cameras_work, charging_stability, replaced_parts, complectness. **С defects** (хотя изначально планировали отложить — оператор явно их затребовал в baseline). `category` — гибкий VARCHAR, не enum. `imei_clean` исключён (в России нет blacklist'ов). `delivery_method` исключён (обсуждение доставки требует подхода / эмоциональной части — отложено в Phase D как часть Согласования цены / торга, не LLM-вопрос). | Минимальный subset под текущий профиль. |
| Q3 | **Default-unchecked**: оператор сам тикает темы. Smart auto-pretick — позже (Phase 2 backlog). | Дисциплина: оператор думает что нужно конкретно для этого лота, до накопления статистики. |
| Q4 | **One-question-at-a-time pacing** | Натурально как реальный диалог. LLM-парсер простой. Защита от перегрузки Avito выборкой. LLM-extractor умеет попутно закрывать другие topics ("side_topics" в response). |
| Q5 | **Short recap, human tone**: «Итак: АКБ 87%, Face ID работает, iCloud отвязан, IMEI чистый, в комплекте коробка + шнур. Всё правильно понял? Проверьте, пожалуйста, и подтвердите или поправьте меня.» Тон распространяется на все LLM-prompts. | Натурально, продавец сразу видит ошибки extracted_data, может поправить. |
| Q6 | **Ad-hoc вопросы разрешены, сохраняются в `dialog_topics`** + auto-link в `profile_dialog_topics`. Permanent extension библиотеки. | Гибкость для разовых вопросов + automatic enrichment baseline-списка для будущих лотов. |
| Q7 | **TG-пинги #1 и #2 включены в Phase B**, business тон | Operator должен знать когда нужно действие без постоянной проверки UI. |
| Q8 | **Modal на kanban для настройки опроса** (а не drawer/page/inline) | Минимум переходов, не уходим со страницы. Drawer = Phase C. |
| Q9 | **Opening line отдельным сообщением** перед первым вопросом: «У меня есть несколько вопросов по Вашему аппарату, ответьте пожалуйста, если Вас это не затруднит.» Отправляется один раз при первом тике в stage='questions' (когда ни одна тема ещё не asked). Через ~3 сек после opening — первый topic-question. | Натуральная переписка (2 коротких сообщения подряд как у реального человека). Risk Avito rate-limit minimal (1.0 rps + burst 3 хватает). |

## 4. Архитектура

### 4.1 State machine flow

```
[Контакт]                                                    (Phase A — done)
    │  inbound от продавца → detect_yes_selling=True
    ▼
[Настройка опроса]                                           (Phase B — new)
    │ ← TG-пинг #1 «Лот N: продавец откликнулся. Настрой темы»
    │ ← клик на карточку → MODAL "Настройка опроса":
    │     • baseline-темы профиля (unchecked checkboxes)
    │     • textarea "Добавить вопрос" + кнопка "+" (ad-hoc → upsert в dialog_topics + auto-link)
    │     • кнопка "Запустить опрос" / "Отклонить"
    │
    │ Submit → INSERT в seller_dialog_topics (status=pending) + transition stage='questions'
    │       + enqueue dialog_tick_questions(dialog_id)
    ▼
[Опрос]                                                       (Phase B — new)
    │ Worker dialog_tick_questions:
    │   1. Берёт следующую тему со status=pending (по priority)
    │   2. formulate_question(topic, dialog_history_tail) → текст
    │   3. send_text в Avito + INSERT messenger_messages (с dialog_id)
    │   4. UPDATE topic.status='asked', .question_text, .question_msg_id, .asked_at
    │
    │ ← SSE inbound от продавца → handle_seller_inbound (stage='questions' branch):
    │   1. parse_topic_answer(asked_topic, text) → {status, extracted, side_topics}
    │   2. answered → UPDATE topic.status='answered', .answer_text, .answer_msg_id, .answered_at
    │   3. side_topics → UPDATE их тоже (попутно закрытые)
    │   4. unclear → re-ask один раз (slight rephrase), второй unclear → status='skipped'
    │   5. off_topic → store message, ask тот же topic ещё раз (один retry)
    │   6. enqueue dialog_tick_questions для следующей итерации
    │
    │ Когда все темы answered/skipped:
    │   formulate_recap(answered_topics) → send_text →
    │   UPDATE seller_dialogs.recap_text/recap_msg_id/recap_status='pending_answer'
    │
    │ ← SSE inbound (recap reply от seller'а) → parse_seller_agreement:
    │   • agreement=yes → recap_status='confirmed' → SUGGEST:
    │       TG-пинг #2 «Лот N: продавец подтвердил темы. Готов к торгу»
    │       Карточка остаётся в "Опрос" с badge "готов к торгу"
    │   • agreement=no → operator_mode=true (бот замолкает; operator вмешивается)
    │   • unclear → re-ask recap один раз, потом operator_mode=true
    │
    │ Operator click «Подключиться к торгу» → transition stage='price_negotiation'
    ▼
[Согласование цены]                                          (Phase D — позже, заглушка)
```

### 4.2 Schema — миграция `0014_phase_b_topics`

```sql
-- Global topic library
CREATE TABLE dialog_topics (
    key              VARCHAR(64) PRIMARY KEY,
    title            TEXT NOT NULL,
    category         VARCHAR(32),
    default_phrasing TEXT,
    expected_format  VARCHAR(32),
    created_at       TIMESTAMPTZ DEFAULT now(),
    created_by       VARCHAR(32) DEFAULT 'system_seed',
    is_active        BOOLEAN DEFAULT true
);

-- Per-profile baseline subset
CREATE TABLE profile_dialog_topics (
    profile_id UUID REFERENCES search_profiles(id) ON DELETE CASCADE,
    topic_key  VARCHAR(64) REFERENCES dialog_topics(key) ON DELETE CASCADE,
    priority   INT DEFAULT 0,
    PRIMARY KEY (profile_id, topic_key)
);

-- Per-dialog topic state
CREATE TABLE seller_dialog_topics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dialog_id       UUID NOT NULL REFERENCES seller_dialogs(id) ON DELETE CASCADE,
    topic_key       VARCHAR(64) REFERENCES dialog_topics(key),
    priority        INT DEFAULT 0,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',   -- pending/asked/answered/skipped
    question_text   TEXT,
    question_msg_id TEXT REFERENCES messenger_messages(id),
    answer_text     TEXT,
    answer_msg_id   TEXT REFERENCES messenger_messages(id),
    asked_at        TIMESTAMPTZ,
    answered_at     TIMESTAMPTZ,
    retry_count     INT DEFAULT 0
);
CREATE INDEX ix_seller_dialog_topics_dialog ON seller_dialog_topics(dialog_id);
CREATE INDEX ix_seller_dialog_topics_status ON seller_dialog_topics(status);

-- Extend seller_dialogs for recap state
ALTER TABLE seller_dialogs
    ADD COLUMN recap_text   TEXT,
    ADD COLUMN recap_msg_id TEXT REFERENCES messenger_messages(id),
    ADD COLUMN recap_status VARCHAR(16);   -- pending_answer/confirmed/disputed
```

Также: data-migration upsert'ит 7 baseline тем из `avito-monitor/app/data/dialog_topics.yaml` + автолинкует к существующему профилю (`iPhone 12 Pro max 10500-13500`).

### 4.3 Topic seed — `avito-monitor/app/data/dialog_topics.yaml`

```yaml
- key: battery_health
  title: АКБ здоровье (%)
  category: battery
  expected_format: percent
  default_phrasing: "Спроси точный процент здоровья АКБ из настроек"

- key: face_id_works
  title: Face ID работает
  category: function
  expected_format: yesno
  default_phrasing: "Уточни, работает ли Face ID без сбоев"

- key: icloud_unlinked
  title: iCloud отвязан
  category: function
  expected_format: yesno
  default_phrasing: "Спроси, отвязан ли iCloud с прошлого аккаунта"

- key: replaced_display
  title: Дисплей менялся
  category: damage
  expected_format: yesno
  default_phrasing: "Уточни — менялся ли дисплей (оригинальный или замена)"

- key: broken_glass
  title: Разбито стекло дисплея
  category: damage
  expected_format: yesno
  default_phrasing: "Спроси, целое ли стекло дисплея (трещины, сколы)"

- key: display_stains_stripes
  title: Пятна/полосы на дисплее
  category: damage
  expected_format: yesno
  default_phrasing: "Уточни — есть ли пятна, полосы, битые пиксели на дисплее"

- key: broken_back
  title: Разбита задняя крышка
  category: damage
  expected_format: yesno
  default_phrasing: "Спроси, целая ли задняя крышка телефона"

- key: cameras_work
  title: Все камеры работают
  category: function
  expected_format: text
  default_phrasing: "Уточни — все ли камеры работают (основная, широкоугольная, теле, фронт); если есть дефекты — какая именно"

- key: charging_stability
  title: Зарядка и стабильность
  category: function
  expected_format: text
  default_phrasing: "Спроси — стабильно ли заряжается, не перезагружается ли, не греется ли при использовании"

- key: replaced_parts
  title: Что ещё менялось
  category: damage
  expected_format: text
  default_phrasing: "Уточни — менялись ли какие-то части помимо дисплея (АКБ, камеры, плата и т.п.)"

- key: complectness
  title: Комплект (коробка/кабель/зарядка)
  category: complectness
  expected_format: text
  default_phrasing: "Спроси, что есть в комплекте: коробка, кабель, зарядка (адаптер)"
```

### 4.4 LLM dispatchers (новые в `app/services/llm_analyzer.py`)

```python
async def formulate_question(topic: DialogTopic, history_tail: list[dict]) -> str:
    """Generate natural-sounding question for one topic.
    Uses topic.default_phrasing as hint. Live & polite tone (Phase A greeting style).
    history_tail: last 5-10 messages for context.
    Prompt: app/prompts/dialog_formulate_question.md
    """

async def parse_topic_answer(topic: DialogTopic, seller_text: str) -> dict:
    """Extract structured answer for the currently-asked topic.
    Returns: {
        "status": "answered" | "off_topic" | "unclear",
        "extracted": str | None,
        "side_topics": [{"topic_key": str, "extracted": str}]
    }
    side_topics — if seller mentioned other open topics, close them too.
    Prompt: app/prompts/dialog_parse_topic_answer.md
    """

async def formulate_recap(answered_topics: list[tuple[DialogTopic, str]]) -> str:
    """Compose the recap message.
    Template guide: 'Итак: <comma-separated list>. Все правильно понял?
                     Проверьте, пожалуйста, и подтвердите или поправьте меня.'
    Prompt: app/prompts/dialog_formulate_recap.md
    """

async def parse_seller_agreement(text: str) -> dict:
    """Classify seller's reply to the recap.
    Returns: {"agreement": "yes"|"no"|"unclear", "corrections": str | None}
    Prompt: app/prompts/dialog_parse_seller_agreement.md
    """
```

Все 4 — через OpenRouter `google/gemini-2.5-flash-lite` (default из env), 0.7 confidence threshold. Идемпотентность через cache в `llm_analyses` (как у Phase A `detect_yes_selling`).

### 4.5 Worker — `app/tasks/seller_dialog_tasks.py`

Новая TaskIQ task:

```python
@broker.task(task_name="app.tasks.seller_dialog_tasks.dialog_tick_questions")
async def dialog_tick_questions(dialog_id: str) -> dict:
    """One tick of the questions state machine.
    Triggered:
      - After questions_setup → questions transition (from /dialogs/{id}/start-questions endpoint)
      - From handle_seller_inbound after each inbound в stage='questions' (via .kiq())

    Algorithm:
      1. Load dialog + topics. If stage != 'questions' or operator_mode → return.
      2. If any topic.status='asked' AND .answer_text IS NULL → wait (return).
         (We're waiting for seller's reply to current question.)
      3. If NO topic.status IN ('asked','answered','skipped') → first tick:
           a. Send OPENING_LINE («У меня есть несколько вопросов по Вашему аппарату,
              ответьте пожалуйста, если Вас это не затруднит.») via xapi.
           b. await asyncio.sleep(3) — humanlike gap.
           c. Continue to step 4 (pick first pending topic).
      4. If any topic.status='pending' → pick highest-priority,
           formulate_question(topic, history_tail), send_text, mark 'asked'.
      5. Else if all topics answered/skipped AND seller_dialogs.recap_status IS NULL →
           formulate_recap(answered_topics), send_text, set recap_status='pending_answer'.
      6. Else if recap_status='pending_answer' → wait (return).
      7. Else if recap_status='confirmed' → SUGGEST: enqueue TG-ping #2 + update last_event_at.
    """
```

`OPENING_LINE` — constant в `app/services/seller_dialog/constants.py` рядом с `GREETING_TEMPLATE`.

Failure modes:
- LLM call failure → log + не транзишн (тик можно повторить вручную через kiq)
- xapi send failure (rate-limit/network) → exception → outer catch → operator_mode=true
- xapi `Forbidden because item do not support create channel` (снято с публикации) → close_dialog(reason='unpublished')

### 4.6 SSE handler — `app/services/seller_dialog/handler.py`

Расширение `handle_seller_inbound` для stage `questions`:

```python
if dialog.stage == STAGE_QUESTIONS:
    # 1. If recap is pending — parse seller's agreement
    if dialog.recap_status == 'pending_answer':
        agreement = await parse_seller_agreement(text)
        if agreement['agreement'] == 'yes':
            dialog.recap_status = 'confirmed'
            await enqueue_tg_ping('seller_dialog_ready_to_negotiate', dialog.id)
        elif agreement['agreement'] == 'no':
            dialog.operator_mode = True
            # store corrections in extracted_data for operator review
        else:
            # unclear — re-ask recap once, then operator_mode
            ...
        return

    # 2. Otherwise — answer to a topic question
    asked = await get_asked_topic(session, dialog.id)
    if asked is None:
        # spam / out-of-band — just log
        return
    parsed = await parse_topic_answer(asked, text)
    if parsed['status'] == 'answered':
        update_topic(asked, status='answered', extracted=parsed['extracted'])
        for st in parsed['side_topics']:
            update_topic_by_key(st['topic_key'], status='answered', extracted=st['extracted'])
    elif parsed['status'] == 'unclear':
        asked.retry_count += 1
        if asked.retry_count >= 2:
            update_topic(asked, status='skipped')
        # else: re-ask via tick
    # off_topic — same retry logic

    await dialog_tick_questions.kiq(str(dialog.id))
```

### 4.7 UI surface

**Kanban (`listings_kanban.html`):**
- Добавить 3-ю колонку `Опрос` (новый partial `kanban_card_questions.html` с badge «идёт опрос: 3/5 (закрыто)» + footer кнопка «× Отклонить»).
- Header: `<select name="profile_id">` с опциями user's profiles + «Все профили». Submit reload'ит kanban с `?profile_id=<uuid>`. `KanbanFilters.profile_ids` уже принимает list.

**Setup modal (`_partials/setup_modal.html`):**
- Триггер: `<a href="..." data-dialog-id="..." class="setup-modal-trigger">Настроить опрос</a>` в `kanban_card_questions_setup.html`
- Vanilla JS — fetch `/dialogs/{id}/setup` (HTML fragment) → inject в `<dialog>` element → `.showModal()`
- Fragment рендерит:
  - Список baseline-тем профиля (unchecked checkboxes)
  - Textarea «Добавить вопрос» + кнопка «+» → AJAX к `/dialog-topics/quick-add` → перерисовка списка
  - Кнопки «Запустить опрос» / «Отмена»
- Submit POST → `/dialogs/{id}/start-questions` → server transition + enqueue `dialog_tick_questions` → 303 redirect к kanban

**Topic library page (`/dialog-topics`):**
- View: list `dialog_topics` (key, title, category, format)
- Add form внизу страницы (single submit)
- Edit/Delete — V1.5 (через SQL пока)

**Карточка `kanban_card_questions.html`:**
- Image + title + price (как у других)
- Progress badge: «опрос: N/M» где M — total topics, N — answered/skipped
- Если recap_status='pending_answer' → badge «ждём confirm»
- Если recap_status='confirmed' → badge «готов к торгу» + кнопка «Подключиться к торгу»
- Reject button (как у других)

### 4.8 TG-пинги (#1 и #2 — Phase B subset)

Используется существующая `notifications` инфраструктура (`app/tasks/notifications.dispatch_pending`). Добавляем 2 новых типа в `notifications.type` enum:
- `seller_dialog_ready_to_setup` — при `contact → questions_setup`
- `seller_dialog_ready_to_negotiate` — при `questions → SUGGEST price_negotiation`

Helper `app/services/seller_dialog/service.py::enqueue_tg_ping(notification_type, dialog_id)` — INSERT в `notifications` table с payload `{listing_avito_id, listing_title, listing_price}`.

Шаблон:
```
🟢 Лот {avito_id} ({title}, {price}₽)
{action_prompt}
→ {kanban_url}
```

Где `action_prompt` = «Продавец откликнулся. Настрой темы для опроса» (#1) или «Продавец подтвердил темы. Готов к торгу» (#2).

## 5. Error handling

| Source | Failure | Action |
|---|---|---|
| LLM (OpenRouter) | API call failed / timeout | log; не транзишн (тик можно повторить вручную через kiq) |
| LLM | invalid JSON response | retry один раз; если опять — log + skip topic (status='skipped') |
| xapi send_text | rate-limit (429) | exception → outer catch → operator_mode=true |
| xapi send_text | network error | то же — operator_mode=true |
| xapi create_channel | Forbidden (item closed) | close_dialog(reason='unpublished') |
| SSE handler | unknown channel | log warning, return (как сейчас) |
| Worker tick | dialog.stage != questions при entry | log info, return (idempotent guard) |
| Worker tick | concurrent execution | вторая итерация увидит `topic.status='asked'` и вернётся (no double-send) |

## 6. Testing

**Unit tests (no live DB):**
- `tests/dialog_topics/test_topic_library.py` — seed load, ad-hoc upsert, profile auto-link
- `tests/seller_dialog/test_dialog_tick_questions.py` — state machine: pending → asked → answered → recap → suggest. Каждая ветка отдельным тестом.
- `tests/seller_dialog/test_llm_dispatchers.py` — mocked OpenRouter response → assert structure {status, extracted, side_topics}
- `tests/seller_dialog/test_handler_questions.py` — SSE inbound stage=questions: правильное update topic / правильный enqueue tick / правильная recap branch
- `tests/seller_dialog/test_view_phase_b.py` — query_kanban_cards возвращает третью колонку questions + правильный count

**Integration smoke (post-deploy на VPS):**
1. Acceptit новый лот через UI
2. Дождаться auto-greeting'а в "Контакт"
3. Продавец отвечает «Да продаю»
4. Карточка автоматически в "Настройка опроса" (Phase A — already works)
5. Operator открывает modal, чикает 2-3 темы, жмёт "Запустить"
6. Карточка переезжает в "Опрос"
7. Бот шлёт первый вопрос
8. Продавец отвечает → бот шлёт следующий
9. После всех тем — recap
10. Продавец отвечает «Да всё верно»
11. TG-пинг #2 + карточка с badge «готов к торгу»

## 7. Migration

- `alembic upgrade 0014_phase_b_topics` — schema (3 таблицы + 3 колонки в seller_dialogs)
- Data-migration в той же revision — INSERT 7 тем из YAML seed + auto-link к существующему профилю (`iPhone 12 Pro max 10500-13500`)
- Существующие dialog'и в `questions_setup` не затрагиваются (просто получают новый UI для настройки)
- TG `notifications.type` enum extending — отдельный simple migration

## 8. Точки переиспользования

| Что | Источник |
|---|---|
| LLM dispatcher pattern + `llm_analyses` cache | `app/services/llm_analyzer.py::detect_yes_selling` |
| xapi `send_text` adapter | `app/tasks/seller_dialog_tasks._XapiMessengerAdapter` |
| `ensure_chat_row` (FK persistence) | `app/services/messenger_bot/dedup.py` |
| SSE handler hook | `app/services/seller_dialog/handler.py::handle_seller_inbound` (расширим branch'ем для stage='questions') |
| Kanban query + KanbanFilters | `app/services/seller_dialog_view.py` (фильтр profile_ids уже есть) |
| Notifications infrastructure | `app/tasks/notifications.py::dispatch_pending` |
| TaskIQ broker registration | `app/tasks/broker.py::_register_tasks` (добавить новую task) |

## 9. Estimate

~6-7 часов кодинга:

- Schema + alembic migration + YAML seed loader — 1ч
- LLM dispatchers + 4 prompt-файла — 1.5ч
- Worker `dialog_tick_questions` + handler integration — 1.5ч
- Setup modal UI + JS + endpoint /dialogs/{id}/setup + /start-questions — 1.5ч
- Kanban — 3-я колонка + profile filter dropdown + kanban_card_questions.html — 1ч
- Topic library CRUD page (view + add) — 0.5ч
- TG-пинги (2 типа) + integration в transitions — 0.5ч
- Tests (4 файла) + smoke — 0.5ч

Plan-стадия (writing-plans) разобьёт на конкретные waves для параллельных subagent'ов.

## 10. Open questions для plan-стадии

(не блокируют design, требуют code-level decisions)

- **Exact prompt text для 4 LLM dispatchers** — написать в `app/prompts/dialog_*.md` во время реализации
- **JS framework для modal** — vanilla или мини-helper. Решить в plan'е (vanilla скорее всего, держим минимум depend's)
- **Edge case: семантически дублирующиеся ad-hoc** — если operator пишет вопрос близкий по смыслу к существующей теме (например «батарея какая?» при существующем `battery_health`), создаём новую тему или похожую находим? — В Phase B создаём всегда новую. Dedup — V1.5 backlog.
- **Recap timing** — что если последний topic answered прямо перед deadline какого-нибудь silence-timeout (Phase E concern)? — Phase E добавит грейс-период, в Phase B без таймеров.
- **Кнопка "Подключиться к торгу"** — где её показывать? На карточке `kanban_card_questions.html` (если recap_status='confirmed') или в modal'е (как у setup)? — Решим в plan'е, скорее всего inline на карточке.

## 11. Ссылки

- [`2026-05-10-seller-dialog-design.md`](./2026-05-10-seller-dialog-design.md) — базовый дизайн (9 этапов, rev 4)
- [`2026-05-11-seller-dialog-phase-a.md`](../plans/2026-05-11-seller-dialog-phase-a.md) — план Phase A (executed)
- `CONTINUE.md` §3.5 — Phase A ship state + ship-blocker фиксы
- `DOCS/REFERENCE/01-avito-api.md` §H — messenger endpoints
