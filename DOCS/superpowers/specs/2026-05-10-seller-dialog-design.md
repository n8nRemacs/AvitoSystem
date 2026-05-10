# Seller Dialog Flow — Design Spec

**Дата:** 2026-05-10 (revision 2 — после уточнений по пайплайну и SLA-модели)
**Статус:** Design approved, готов к написанию плана реализации
**Связанные документы:** `CONTINUE.md` §3, `DOCS/REFERENCE/01-avito-api.md` (messenger endpoints), существующая таблица `chat_dialog_state` (используется reliability-bot'ом).

---

## 1. Цель

Автоматизировать первичный диалог с продавцом для лотов в статусе **«В работу»** через CRM-style kanban с 8 этапами + таб «Отказы». LLM работает на дешёвых стадиях (приветствие, сбор информации, мониторинг состояния), оператор подключается на критичных решениях (торг, выкуп, приём товара).

**Сейчас:** оператор кликает `✓ В работу` → переключается в Avito-app → вручную пишет приветствие, вопросы по аппарату, торгуется. 5-10 минут per лот, оператор теряет фокус, многие лоты остаются нетронутыми.

**После V1:** оператор кликает `✓ В работу` → бот сразу шлёт стандартное приветствие → ждёт ответ. Оператор подключается только на этапах где его экспертиза нужна, остальное — автомат.

## 2. Non-goals (V1 — явно вне области)

- **Avito-delivery tracking endpoint** для этапов 6-7 (Отправка совершена / Товар получен). Нужен новый xapi-метод. MVP может полагаться на manual confirmation оператором; полный auto-tracking → V1.5.
- **Phase 2 smart auto-tick тем** по эвристике из `parameters` / `description`. Phase 1 = оператор сам ставит галочки, дефолт = profile baseline.
- **Аналитика по отказам** (графики причин, conversion rate). UI просмотра есть, графики позже.
- **Reactivation отказа** обратно в pipeline. В MVP закрыт = закрыт.
- **Multi-operator** (роли, claim карточек). Один оператор.
- **Drag-and-drop карточек** между колонками. LLM/operator-driven flow несовместим с drag-drop.
- **Reuse reliability-bot для sales flow.** Общая инфраструктура (SSE listener, rate_limit, dedup) переиспользуется, но handler — новый.
- **Мобильное приложение для оператора** с voice-to-text для оперативных ответов на этапе торга. Запаркировано в V2/V3.
- **Эскалация на оператора при silence-timeout.** Не делаем — нет смысла дёргать оператора по dead-leads. Тихий auto-reject в Отказы.

## 3. Принятые решения (brainstorm 2026-05-10)

| # | Вопрос | Решение |
|---|---|---|
| D1 | Этапы пайплайна | **8 stages**: Контакт → Опрос → Согласование цены → Цена изменена → Лот выкуплен → Отправка совершена → Товар получен → Сделка закрыта. Параллельно **Отказы** — отдельный таб |
| D2 | Auto-greeting | Стандартное приветствие шлётся **автоматически в момент перемещения лота в «В работу»** (клик `✓` на /listings). Hardcoded template, без модерации оператора |
| D3 | «Подготовка» как колонка | **Нет.** Темы Опроса используют profile-baseline по умолчанию. Оператор может править в drawer'е во время Контакт wait — параллельная работа, не блокирующий gate |
| D4 | Кто двигает карточки | **Бот детектит триггер → предлагает оператору сменить статус → оператор подтверждает.** Auto без подтверждения только для: Контакт → Опрос (бинарное «да, продаётся»), любой этап → Опрос если оператор добавил новые темы |
| D5 | Operator-driven этапы | Этапы 3 / 5 / 8 — оператор pилотирует. На стадии 3 (торг): бот молчит наружу, но слушает SSE, парсит «согласен/не согласен», заполняет extracted_data. Оператор сам печатает каждое сообщение |
| D6 | Тематика вопросов | Hybrid: per-profile YAML-library с чекбоксами (baseline) + per-listing ad-hoc. Library растёт через UI |
| D7 | Финал Опроса | LLM шлёт **recap-сообщение** «Итого: АКБ 87%, коробка есть, доставка 2-3 дня. Всё верно?» — продавец подтверждает → бот предлагает оператору перевод в «Согласование цены» |
| D8 | Per-stage Avito API | Каждый этап = свои API-вызовы кроме мессенджера: polling `items/{id}` на reservation/price/delivery markers |
| D9 | Card layout | **Stage-specific** — 8 partial-templates с разным KPI strip |
| D10 | UI диалога | Drawer справа при клике на карточку = full chat history с timestamps + extracted_data + action buttons |
| D11 | Sortings | 4 пресета: SLA-deadline / время-без-ответа / цена / дата принятия. + filter chip по профилю/модели |
| D12 | Отказы | Отдельный таб с табличкой (дата / причина / профиль / на каком этапе слетел). Без реактивации в V1 |
| D13 | SLA-модель | **Тихий auto-reject** на silence-этапах (1, 2, 4). Глобальный default 24ч. Никаких эскалаций к оператору, никаких TG-пингов на silence — оператор не должен тратить внимание на мёртвые лоты |
| D14 | TG-пинги оператору | Только для «нужно действие оператора»: recap готов (→ торг), цена изменилась в лоте (→ выкупать), товар получен (→ закрыть сделку) |
| D15 | Возврат товара | На этапе 8 «Сделка закрыта» оператор может пометить `✗ возвращено` — карточка едет в Отказы с reason=`mismatch` + поле `return_reason TEXT` (что не сошлось, почему вернули) |
| D16 | Build vs buy | **Своё** на HTMX. AmoCRM не покрывает structured `extracted_data` + sync hell |

## 4. Архитектура

### 4.1 State machine

```
              accept-action юзера → auto-greeting в Avito-чат
                       ↓
              [1. Контакт]                    AUTO bot
                  ↓ LLM detects "да, продаётся"
                  ↓ (auto без подтверждения)
              [2. Опрос]                      AUTO bot
                  ↓ темы закрыты + recap confirmed
                  ↓ TG-пинг оператору + bot SUGGESTS transition
                  ↓ оператор клик «Подключиться к торгу»
              [3. Согласование цены]          OPERATOR-driven
                  ↓ оператор зафиксировал финальную цену
                  ↓ оператор клик «Цена согласована»
              [4. Цена изменена]              AUTO wait
                  ↓ bot detects items/{id}.price изменилась
                  ↓ TG-пинг оператору + bot SUGGESTS transition
                  ↓ оператор клик «Выкупить» (идёт в Avito)
              [5. Лот выкуплен]               OPERATOR-driven
                  ↓ оператор кликает «Куплено»
              [6. Отправка совершена]         AUTO wait
                  ↓ bot detects shipment marker (messages / items state)
                  ↓ bot SUGGESTS transition
              [7. Товар получен]              AUTO wait
                  ↓ Avito-delivery state = доставлено (V1.5) или manual confirm
                  ↓ TG-пинг + bot SUGGESTS
              [8. Сделка закрыта]             OPERATOR-driven
                  ↓ оператор: ✓ соответствует / ✗ возвращено + return_reason
                  ↓
              done

  Из любого этапа → [Отказы]:
   • Silence timeout (на этапах 1/2/4) — auto-reject silently
   • LLM detects refusal / sold-elsewhere — bot SUGGESTS, оператор клик
   • Operator manual close — кнопка в drawer'е
   • Возврат товара (с этапа 8) — reason=mismatch, return_reason заполняется

  Operator overrides (drawer любой карточки):
   • + Уточнить — добавить темы → AUTO откат на Опрос → LLM формирует follow-up
   • Передать вручную — LLM мьютится, дальше operator-typed messages в Avito-чат
   • В Отказы — закрыть с causes-enum
```

### 4.2 Per-stage workers

Каждый этап = отдельный TaskIQ task `dialog_tick_<stage>`. Триггеры:
- **Recurring** (5-10 мин для polling-проверок Avito-side)
- **On-demand** (SSE inbound от продавца → handler.py роутит в нужный stage tick)

| # | Этап | Driver | LLM-действие | Avito-side проверка | Условие auto-перехода |
|---|---|---|---|---|---|
| 1 | Контакт | бот auto | Шлёт hardcoded приветствие 1 раз при входе | SSE listen первый ответ | LLM-classifier: «продаётся=yes» → AUTO в Опрос |
| 2 | Опрос | бот auto | Темы → вопросы → recap | Periodic-poll items/{id} на reservation/price | Все темы answered + recap confirmed → SUGGEST оператору перевод в этап 3 |
| 3 | Согласование цены | **оператор** | Молчит наружу, парсит SSE inbound, заполняет extracted_data | items/{id}.price watch | Operator manual click «Цена согласована» (с заполненной final_price) → этап 4 |
| 4 | Цена изменена | бот auto-wait | Тихо | items/{id}.price polling каждые 5 мин | Detect price ≈ final_price → SUGGEST оператору «выкупай» |
| 5 | Лот выкуплен | **оператор** | Тихо | (нет — оператор делает покупку out-of-band) | Operator manual click «Куплено» → этап 6 |
| 6 | Отправка совершена | бот auto-wait | Тихо | items/{id} shipment marker / messenger keywords («отправил», tracking number) | Detect shipment → SUGGEST оператору перевод в этап 7 |
| 7 | Товар получен | бот auto-wait | Тихо | (V1.5) Avito-delivery tracking; в MVP — manual confirm | Avito-delivery=delivered ИЛИ manual click → SUGGEST оператору закрыть сделку |
| 8 | Сделка закрыта | **оператор** | Тихо | — | Operator manual click `✓ соответствует` / `✗ возвращено + reason` → done |

### 4.3 SLA-модель (silence timeout)

**Только** на этапах 1, 2, 4 (где мы реально **ждём действия продавца**). На operator-driven этапах SLA не применяется — оператор работает в своём темпе.

- **Default**: 24ч с момента последнего исходящего сообщения от бота / последнего изменения состояния
- **На каждый inbound от продавца**: reset таймера (например на этапе Опрос — каждый их ответ обнуляет SLA для следующего вопроса)
- **При истечении**: silently закрыть карточку → Отказы с `closed_reason='silent'`. **Никаких TG-пингов оператору.**

Per-stage конфиг:
- 1. Контакт: 24ч
- 2. Опрос: 24ч
- 4. Цена изменена: 48ч (продавцу нужно зайти и поменять ценник в листинге — даём чуть больше)

Worker `dialog_silence_tick` (every 5min): закрывает истёкшие.

### 4.4 TG-пинги оператору

**Только** на «нужно действие оператора» переходах:

| Trigger | Текст | Кнопки в TG (или просто ссылка на карточку) |
|---|---|---|
| Опрос → Согласование цены | «Лот N: продавец подтвердил все темы. Готов к торгу» | [Открыть карточку] |
| Цена изменена | «Лот N: продавец обновил цену в лоте. Выкупай» | [Открыть карточку] |
| Товар получен | «Лот N: товар прибыл. Проверь и закрой сделку» | [Открыть карточку] |

Никаких пингов на silence-timeouts, никаких пингов на «бот переслал сообщение».

### 4.5 Topic library

**`dialog_topics`** — глобальная библиотека (mirror YAML-сида в БД):

```
key              VARCHAR(64) PRIMARY KEY  -- battery_health / box_present / replaced_display
title            TEXT                      -- "АКБ здоровье"
category         VARCHAR(32)               -- battery / complectness / damage / shipping / other
default_phrasing TEXT                      -- LLM hint: "Узнать % здоровья АКБ из настроек, попросить скрин"
expected_format  VARCHAR(32)               -- text / yesno / number / percent / photo
created_at       TIMESTAMPTZ
created_by       VARCHAR(32)               -- 'system_seed' / 'operator'
```

Seed: `avito-monitor/app/data/dialog_topics.yaml` (15-20 тем для iPhone в plan-стадии).

**`profile_dialog_topics`** — какие baseline-темы выбраны на профиле:

```
profile_id  UUID FK
topic_key   VARCHAR(64) FK
priority    INT                            -- порядок задавания
PRIMARY KEY (profile_id, topic_key)
```

**`seller_dialog_topics`** — темы конкретного диалога:

```
id              UUID PK
dialog_id       UUID FK seller_dialogs(id)
topic_key       VARCHAR(64) FK dialog_topics(key) NULLABLE  -- NULL = ad-hoc
custom_text     TEXT NULLABLE                                -- ad-hoc
status          VARCHAR(16)                                  -- pending / asked / answered / skipped
question_msg_id UUID NULLABLE                                -- ссылка на messenger_message
answer_text     TEXT NULLABLE                                -- LLM-extracted
answer_msg_id   UUID NULLABLE
asked_at        TIMESTAMPTZ NULLABLE
answered_at     TIMESTAMPTZ NULLABLE
```

### 4.6 Data model — `seller_dialogs`

```
id                UUID PRIMARY KEY
profile_listing_id UUID FK UNIQUE          -- 1 диалог на 1 (profile, listing)
channel_id        VARCHAR(128) NULLABLE    -- Avito messenger channel
stage             VARCHAR(24)              -- contact / questions / price_negotiation /
                                           -- price_changed / purchased / shipped / received / closed / rejected
silence_deadline  TIMESTAMPTZ NULLABLE     -- NULL на operator-driven этапах
last_event_at     TIMESTAMPTZ              -- последний in/out event
operator_mode     BOOLEAN DEFAULT false    -- LLM мьют, оператор пишет вручную (для этапа 3 включается auto)
extracted_data    JSONB DEFAULT '{}'       -- структурированные ответы по темам
opened_at         TIMESTAMPTZ
closed_at         TIMESTAMPTZ NULLABLE
closed_reason     VARCHAR(32) NULLABLE     -- silent / refused / price_too_high / sold / mismatch / other
target_price      NUMERIC NULLABLE         -- задаётся оператором на этапе 3
final_price       NUMERIC NULLABLE         -- финальная согласованная
shipping_method   VARCHAR(32) NULLABLE     -- avito / courier / pickup
return_reason     TEXT NULLABLE            -- если closed_reason=mismatch
```

Chat history → переиспользуем существующую `messenger_message` (шарится с reliability-bot — добавим колонку `dialog_id NULLABLE` для дискриминации; reliability-сообщения = NULL).

### 4.7 UI surface

**Routes:**
- `GET /listings?tab=in_progress` — KANBAN view (8 колонок). Заменяет текущий flat-список таба «В работе».
- `GET /listings?tab=rejected` — таблица отказов (existing «Отклонённые» + новые отказы продавца — слить или раздельно решается в плане).
- `GET /profiles/{id}` — расширить форму чек-боксами тем + поле «greeting_template_override» (опционально).
- `GET /dialog-topics` — read/edit библиотеки тем (минимальный CRUD).

**Components (HTMX partials):**
- `kanban_board.html` — 8 колонок + sticky filter/sortings bar. Drag-drop disabled.
- `kanban_card_<stage>.html` — 8 stage-specific partials с разным KPI strip.
- `dialog_drawer.html` — slide-out справа, lazy-loaded по `hx-get /dialogs/{id}/drawer`. Внутри:
  - Photo gallery (от `listings.images`, full)
  - Chat history с timestamps + read-markers
  - Extracted data sidebar (закрытые / не закрытые темы с ответами)
  - Action buttons: `+ Уточнить` / `Передать вручную` / `В Отказы` + stage-specific (`Подключиться к торгу` / `Цена согласована` / `Куплено` / etc.)
- `topic_picker.html` — modal со scroll-чекбоксами + `+ Добавить тему`.
- `silence_badge.html` — compact индикатор «осталось 18ч до тихого закрытия» (только на этапах 1/2/4).

### 4.8 Migration существующих лотов

В момент первого запуска V1:
- Для каждой `profile_listing WHERE user_action='accepted'` → создать `seller_dialog` со stage=`contact`, **`operator_mode=true`** (LLM не пишет, чтобы не отправить дубликат приветствия если оператор уже общался).
- Карточка показывается в kanban в колонке Контакт с badge `Ручной режим`.
- Оператор может в drawer'е либо отметить «Возобновить с Опроса» (LLM продолжит с того места) либо закрыть в Отказы.

Auto-greeting НЕ шлётся для существующих accepted-лотов. Только для новых acceptов после релиза V1.

## 5. Точки переиспользования существующего кода

| Компонент | Что берём | Изменения |
|---|---|---|
| `avito-xapi/src/workers/http_client.py` | `create_channel_by_item`, `send_text`, `get_messages`, `mark_read` | reuse as-is |
| `avito-xapi/src/routers/messenger.py` | HTTP wrappers поверх http_client | reuse as-is |
| `avito-monitor/app/services/messenger_bot/runner.py` | SSE listener loop с reconnect/backoff | reuse — общий для reliability и sales |
| `avito-monitor/app/services/messenger_bot/handler.py` | dispatcher inbound events | NEW branch: если channel принадлежит `seller_dialogs` → роутить в sales handler |
| `messenger_bot/{rate_limit,dedup,kill_switch}.py` | anti-detection helpers | reuse as-is |
| `app/services/llm_analyzer.py` | LLM dispatch с granular cache | NEW методы: `formulate_questions`, `extract_topic_answer`, `detect_yes_selling`, `formulate_recap`, `parse_seller_agreement` |
| `app/db/models/messenger_message.py` | chat history table | NEW колонка `dialog_id` (nullable, FK) |

## 6. Open questions для plan-стадии

(вопросы, требующие code-detail решений во время написания плана — НЕ принципиальные)

- **Точные silence-timeout** числа (сейчас default 24ч / 24ч / 48ч на этапах 1/2/4) — финальные значения после первого soak-period.
- **Seed `dialog_topics.yaml`** — конкретный список 15-20 baseline-тем для iPhone (battery_health, box_present, replaced_display, charge_cable, headphones, original_box, repair_history, water_damage, screen_scratches, body_dents, payment_method, avito_delivery_ready, courier_acceptable, pickup_location, etc.).
- **Prompts per stage** — тексты для LLM (`generate_greeting`, `formulate_question`, `detect_yes_selling`, `parse_topic_answer`, `formulate_recap`, `parse_seller_agreement`) — создать `app/prompts/dialog_*.md`.
- **Hardcoded greeting** — финальный текст приветствия (CONTINUE.md §3.1 предлагает «Здравствуйте! Меня заинтересовал ваш аппарат, ещё продается?» — оставить или подкорректировать).
- **TG-пинг формат** для трёх действий-required триггеров — text + кнопки/ссылки.
- **Reliability vs sales sharing** `messenger_message` — добавить `dialog_id NULLABLE` или сделать отдельную таблицу `seller_messages`. Принципиально не критично.
- **Существующий таб «Отклонённые»** vs новый «Отказы» — слить в один таб с фильтром «отклонено оператором / отказ продавца» или держать раздельно.
- **Stage-detection LLM call** — отдельный prompt (low-cost classifier, как existing per-criterion eval) для условий auto-перехода на этапе 1 и для SUGGEST на этапах 2/4/6/7.
- **Recap-confirmation parsing** — как LLM детектит «всё верно» от продавца (yes/no классификатор с фоллбэком).
- **Migration policy** для существующих accepted-лотов — auto operator_mode или предложить выбор оператору.

## 7. Стоимость

~18-22 часа кодинга (увеличение из-за двух дополнительных stages и операторских overrides):

- Schema (3 миграции: seller_dialogs, dialog_topics+seed+links, messenger_message.dialog_id) — 1ч
- State machine + 8 transitions в Python — 3ч
- LLM dispatchers + 6 prompt-файлов — 3ч
- Per-stage workers (`dialog_tick_<stage>` × 8) — 3ч
- Silence timeout worker + auto-reject — 1ч
- Action-required TG-пинги (3 триггера) — 1ч
- Kanban view (8 columns + sortings/filter) — 3ч
- 8 stage-specific card partials — 3ч
- Dialog drawer (lazy chat + extracted_data + actions) — 2ч
- Topic-picker UI на профиле + dialog_topics CRUD — 1.5ч
- Operator overrides (+Уточнить, Передать вручную, action buttons per stage) — 1.5ч
- Migration существующих accepted-лотов — 0.5ч
- Тесты + полу-end-to-end smoke (1 живой диалог) — 1.5ч

Plan-стадия покажет точную декомпозицию.

## 8. Что НЕ закрыто и пойдёт в V1.5+

- **Avito-delivery tracking endpoint** — нужен новый xapi-метод для real-time tracking (этапы 6 и 7). MVP полагается на manual confirm от оператора + heuristic на messages keywords.
- **Phase 2 smart auto-tick тем** по эвристике description/parameters.
- **Mobile app для оператора** с voice-to-text для этапа 3 (Согласование цены) — V2/V3.
- **LLM-assisted draft на этапе 3** — бот предлагает черновик контр-предложения, оператор edit+approve. Пока в V1 оператор печатает с нуля.
- **Аналитика по отказам** — графики причин, conversion-funnel-метрики.
- **Reactivation отказа** — возврат закрытой карточки в pipeline.

## 9. Ссылки

- `CONTINUE.md` §3 — изначальный план seller-dialog
- `~/.claude/plans/sequential-seeking-trinket.md` — Phase A V2 LLM pipeline (паттерн per-criterion + granular cache, переиспользуется)
- `DOCS/REFERENCE/01-avito-api.md` §H — messenger endpoints (createChannel, send, getMessages, markRead)
- Brainstorm transcript — этот документ написан после диалога 2026-05-10 (Q1-Q7 + revisions D1-D16 разрешены)
