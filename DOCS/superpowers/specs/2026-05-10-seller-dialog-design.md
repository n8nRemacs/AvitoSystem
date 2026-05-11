# Seller Dialog Flow — Design Spec

**Дата:** 2026-05-10 (revision 4 — расширена SLA-модель: silent на early-этапах, notified-with-prolongate на post-agreement)
**Статус:** Design approved, готов к написанию плана реализации
**Связанные документы:** `CONTINUE.md` §3, `DOCS/REFERENCE/01-avito-api.md` (messenger endpoints), существующая таблица `chat_dialog_state` (используется reliability-bot'ом).

---

## 1. Цель

Автоматизировать первичный диалог с продавцом для лотов в статусе **«В работу»** через CRM-style kanban с 9 этапами + таб «Отказы». LLM работает на дешёвых стадиях (приветствие, сбор информации, мониторинг состояния), оператор подключается на критичных решениях (настройка опроса, торг, выкуп, приём товара).

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
| D1 | Этапы пайплайна | **9 stages**: Контакт → **Настройка опроса** → Опрос → Согласование цены → Цена изменена → Лот выкуплен → Отправка совершена → Товар получен → Сделка закрыта. Параллельно **Отказы** — отдельный таб |
| D2 | Auto-greeting | Стандартное приветствие шлётся **автоматически в момент перемещения лота в «В работу»** (клик `✓` на /listings). Hardcoded template, без модерации оператора |
| D3 | «Настройка опроса» — отдельный этап | После того как продавец откликнулся в Контакте, карточка попадает в **Настройка опроса** — operator-driven этап. Оператор ставит галочки на темах из библиотеки + ad-hoc вопросы, кликает «Запустить опрос» → переход в Опрос. Без блокирующего pre-стейджа до приветствия (приветствие auto). Бот не сможет вести диалог без тем — поэтому это блокирующий gate ПОСЛЕ Контакта |
| D4 | Кто двигает карточки | **Бот детектит триггер → предлагает оператору сменить статус → оператор подтверждает.** Auto без подтверждения только для: Контакт → Настройка опроса (бинарное «да, продаётся»), любой этап → Опрос если оператор добавил новые темы |
| D5 | Operator-driven этапы | Этапы 3 / 5 / 8 — оператор pилотирует. На стадии 3 (торг): бот молчит наружу, но слушает SSE, парсит «согласен/не согласен», заполняет extracted_data. Оператор сам печатает каждое сообщение |
| D6 | Тематика вопросов | Hybrid: per-profile YAML-library с чекбоксами (baseline) + per-listing ad-hoc. Library растёт через UI |
| D7 | Финал Опроса | LLM шлёт **recap-сообщение** «Итого: АКБ 87%, коробка есть, доставка 2-3 дня. Всё верно?» — продавец подтверждает → бот предлагает оператору перевод в «Согласование цены» |
| D8 | Per-stage Avito API | Каждый этап = свои API-вызовы кроме мессенджера: polling `items/{id}` на reservation/price/delivery markers |
| D9 | Card layout | **Stage-specific** — 9 partial-templates с разным KPI strip |
| D10 | UI диалога | Drawer справа при клике на карточку = full chat history с timestamps + extracted_data + action buttons |
| D11 | Sortings | 4 пресета: SLA-deadline / время-без-ответа / цена / дата принятия. + filter chip по профилю/модели |
| D12 | Отказы | Отдельный таб с табличкой (дата / причина / профиль / на каком этапе слетел). Без реактивации в V1 |
| D13 | SLA-модель | **Двухуровневая.** Silent auto-reject на early-этапах (1 Контакт 72ч, 3 Опрос 72ч) — мёртвые лоты молча уходят в Отказы без пингов. Notified-with-prolongate на post-agreement этапах (5 Цена изменена 24ч, 7 Отправка совершена 120ч) — TG-пинг оператору с действиями «Прологнировать / Закрыть в Отказы / Передать вручную» |
| D14 | TG-пинги оператору | Шесть триггеров, все «нужно действие оператора»: (1) продавец откликнулся → настрой темы, (2) recap готов → торг, (3) цена изменилась в лоте → выкупать, (4) товар получен → закрыть сделку, (5) timeout на этапе 5 → продлить или закрыть, (6) timeout на этапе 7 → продлить или закрыть |
| D15 | Возврат товара | На этапе 8 «Сделка закрыта» оператор может пометить `✗ возвращено` — карточка едет в Отказы с reason=`mismatch` + поле `return_reason TEXT` (что не сошлось, почему вернули) |
| D16 | Build vs buy | **Своё** на HTMX. AmoCRM не покрывает structured `extracted_data` + sync hell |

## 4. Архитектура

### 4.1 State machine

```
              accept-action юзера → auto-greeting в Avito-чат
                       ↓
              [1. Контакт]                    AUTO bot
                  ↓ LLM detects "да, продаётся"
                  ↓ (auto без подтверждения) + TG-пинг оператору
              [2. Настройка опроса]           OPERATOR-driven
                  ↓ оператор ставит галочки + ad-hoc вопросы
                  ↓ оператор клик «Запустить опрос»
              [3. Опрос]                      AUTO bot
                  ↓ темы закрыты + recap confirmed
                  ↓ TG-пинг оператору + bot SUGGESTS transition
                  ↓ оператор клик «Подключиться к торгу»
              [4. Согласование цены]          OPERATOR-driven
                  ↓ оператор зафиксировал финальную цену
                  ↓ оператор клик «Цена согласована»
              [5. Цена изменена]              AUTO wait
                  ↓ bot detects items/{id}.price ≈ final_price
                  ↓ TG-пинг оператору + bot SUGGESTS transition
                  ↓ оператор клик «Выкупить» (идёт в Avito)
              [6. Лот выкуплен]               OPERATOR-driven
                  ↓ оператор кликает «Куплено»
              [7. Отправка совершена]         AUTO wait
                  ↓ bot detects shipment marker (messages / items state)
                  ↓ bot SUGGESTS transition
              [8. Товар получен]              AUTO wait
                  ↓ Avito-delivery state = доставлено (V1.5) или manual confirm
                  ↓ TG-пинг + bot SUGGESTS
              [9. Сделка закрыта]             OPERATOR-driven
                  ↓ оператор: ✓ соответствует / ✗ возвращено + return_reason
                  ↓
              done

  Из любого этапа → [Отказы]:
   • Silence timeout silent (1/3) — auto-reject в Отказы без TG
   • Silence timeout notified (5/7) — TG-пинг с действиями Прологнировать / Закрыть / Передать вручную
   • LLM detects refusal / sold-elsewhere — bot SUGGESTS, оператор клик
   • Operator manual close — кнопка в drawer'е
   • Возврат товара (с этапа 9) — reason=mismatch, return_reason заполняется

  Operator overrides (drawer любой карточки):
   • + Уточнить — добавить темы → AUTO откат на Опрос (этап 3) → LLM формирует follow-up
   • Передать вручную — LLM мьютится, дальше operator-typed messages в Avito-чат
   • В Отказы — закрыть с causes-enum
```

### 4.2 Per-stage workers

Каждый этап = отдельный TaskIQ task `dialog_tick_<stage>`. Триггеры:
- **Recurring** (5-10 мин для polling-проверок Avito-side)
- **On-demand** (SSE inbound от продавца → handler.py роутит в нужный stage tick)

| # | Этап | Driver | LLM-действие | Avito-side проверка | Условие auto-перехода |
|---|---|---|---|---|---|
| 1 | Контакт | бот auto | Шлёт hardcoded приветствие 1 раз при входе | SSE listen первый ответ | LLM-classifier: «продаётся=yes» → AUTO в Настройку опроса + TG-пинг |
| 2 | Настройка опроса | **оператор** | Тихо | (нет) | Operator manual click «Запустить опрос» → этап 3 |
| 3 | Опрос | бот auto | Темы → вопросы → recap | Periodic-poll items/{id} на reservation/price | Все темы answered + recap confirmed → SUGGEST оператору перевод в этап 4 |
| 4 | Согласование цены | **оператор** | Молчит наружу, парсит SSE inbound, заполняет extracted_data | items/{id}.price watch | Operator manual click «Цена согласована» (с заполненной final_price) → этап 5 |
| 5 | Цена изменена | бот auto-wait | Тихо | items/{id}.price polling каждые 5 мин | Detect price ≈ final_price → SUGGEST оператору «выкупай» |
| 6 | Лот выкуплен | **оператор** | Тихо | (нет — оператор делает покупку out-of-band) | Operator manual click «Куплено» → этап 7 |
| 7 | Отправка совершена | бот auto-wait + silence-SLA | Тихо | items/{id} shipment marker / messenger keywords («отправил», tracking number) + tracking Avito-cancel state | Detect shipment → SUGGEST оператору перевод в этап 8. Если 120ч не отправил → notified-timeout (TG-ping) |
| 8 | Товар получен | бот auto-wait | Тихо | (V1.5) Avito-delivery tracking; в MVP — manual confirm | Avito-delivery=delivered ИЛИ manual click → SUGGEST оператору закрыть сделку |
| 9 | Сделка закрыта | **оператор** | Тихо | — | Operator manual click `✓ соответствует` / `✗ возвращено + reason` → done |

### 4.3 SLA-модель (silence timeout)

Применяется на этапах где мы **ждём действия продавца**: 1 / 3 / 5 / 7. На operator-driven этапах (2 / 4 / 6 / 9) и на чистом Avito-delivery wait (8 — там Avito сам отрабатывает) SLA не применяется.

**Две политики timeout:**

| Политика | Этапы | При истечении |
|---|---|---|
| **Silent auto-reject** | 1 Контакт, 3 Опрос | Тихо закрыть → Отказы с `closed_reason='silent'`. Никаких TG-пингов — мёртвый лот, не тратим внимание оператора |
| **Notified with prolongate** | 5 Цена изменена, 7 Отправка совершена | TG-пинг оператору с тремя actions: **Прологнировать** (reset таймера на ту же длительность) / **Закрыть в Отказы** / **Передать вручную**. Карточка остаётся в текущей колонке с badge «timeout — нужно действие» |

**Reset таймера на inbound от продавца**: на этапе 3 (Опрос) каждый их ответ обнуляет SLA для следующего вопроса.

Per-stage конфиг (defaults, можно поднастроить per-profile позже):

| Этап | Default | Политика | Обоснование |
|---|---|---|---|
| 1. Контакт | 72ч | silent | Если 3 дня не ответил на стандартное приветствие — мёртвый лот |
| 3. Опрос | 72ч | silent | Аналогично — на каждый вопрос даём 3 дня, иначе мёртв |
| 5. Цена изменена | 24ч | notified | Договорились о цене, продавец не зашёл изменить ценник. Оператор может позвонить / напомнить через Avito → продлить таймер |
| 7. Отправка совершена | 120ч (5 дней) | notified | Avito-доставка terms: продавцу даётся ~5 рабочих дней на сдачу в пункт. После этого Avito автоотменит и вернёт предоплату — нужно ловить раньше |

Worker `dialog_silence_tick` (every 5min):
- Находит dialogs WHERE `silence_deadline < now() AND closed_at IS NULL`
- Если политика `silent` → закрывает в Отказы
- Если политика `notified` → шлёт TG-пинг + ставит флаг `timeout_notified=true` (чтобы не спамить); карточка остаётся в колонке с timeout-badge до операторского решения

Поле `prolongation_count` на `seller_dialogs` для статистики (сколько раз оператор продлевал per карточка) — пригодится в Phase 2 для тюнинга дефолтов.

### 4.4 TG-пинги оператору

Шесть триггеров — все «нужно действие оператора». Без TG только silent-timeout (этапы 1/3).

| # | Trigger | Текст | Действия |
|---|---|---|---|
| 1 | Контакт → Настройка опроса | «Лот N: продавец откликнулся. Настрой темы для опроса» | [Открыть карточку] |
| 2 | Опрос → Согласование цены | «Лот N: продавец подтвердил все темы. Готов к торгу» | [Открыть карточку] |
| 3 | Цена изменена → Лот выкуплен | «Лот N: продавец обновил цену в лоте. Выкупай» | [Открыть карточку] |
| 4 | Товар получен → Сделка закрыта | «Лот N: товар прибыл. Проверь и закрой сделку» | [Открыть карточку] |
| 5 | Timeout на этапе 5 | «Лот N: продавец не изменил цену в лоте за 24ч. Прологнировать или закрыть?» | [Открыть карточку] → в drawer'е кнопки `+24ч`, `Закрыть`, `Передать вручную` |
| 6 | Timeout на этапе 7 | «Лот N: продавец не отправил товар за 5 дней. Avito скоро отменит сделку и вернёт деньги. Прологнировать или закрыть?» | [Открыть карточку] → в drawer'е кнопки `+24ч`, `Закрыть`, `Передать вручную` |

V1: TG-сообщения — только text + ссылка на карточку. Действия выполняются в UI карточки. Inline TG-кнопки для one-click prolong/close → V1.5 (если окажется что operator часто действует с телефона прямо из TG).

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
stage             VARCHAR(24)              -- contact / questions_setup / questions /
                                           -- price_negotiation / price_changed / purchased /
                                           -- shipped / received / closed / rejected
silence_deadline  TIMESTAMPTZ NULLABLE     -- NULL на operator-driven этапах
timeout_notified  BOOLEAN DEFAULT false    -- TG-ping уже отправлен на этом deadline (notified-политика)
prolongation_count INT DEFAULT 0           -- сколько раз оператор продлевал silence_deadline
last_event_at     TIMESTAMPTZ              -- последний in/out event
operator_mode     BOOLEAN DEFAULT false    -- LLM мьют, оператор пишет вручную (для этапа 4 включается auto)
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
- `GET /listings?tab=in_progress` — KANBAN view (9 колонок). Заменяет текущий flat-список таба «В работе».
- `GET /listings?tab=rejected` — таблица отказов (existing «Отклонённые» + новые отказы продавца — слить или раздельно решается в плане).
- `GET /profiles/{id}` — расширить форму чек-боксами тем + поле «greeting_template_override» (опционально).
- `GET /dialog-topics` — read/edit библиотеки тем (минимальный CRUD).

**Components (HTMX partials):**
- `kanban_board.html` — 9 колонок + sticky filter/sortings bar. Drag-drop disabled.
- `kanban_card_<stage>.html` — 9 stage-specific partials с разным KPI strip.
- `dialog_drawer.html` — slide-out справа, lazy-loaded по `hx-get /dialogs/{id}/drawer`. Внутри:
  - Photo gallery (от `listings.images`, full)
  - Chat history с timestamps + read-markers
  - Extracted data sidebar (закрытые / не закрытые темы с ответами)
  - Action buttons: `+ Уточнить` / `Передать вручную` / `В Отказы` + stage-specific (`Подключиться к торгу` / `Цена согласована` / `Куплено` / etc.)
- `topic_picker.html` — modal со scroll-чекбоксами + `+ Добавить тему`.
- `silence_badge.html` — compact индикатор «осталось 18ч до тихого закрытия» (только на этапах 1/3/5).

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

- **Точные silence-timeout** числа (сейчас default 72ч / 72ч / 24ч / 120ч на этапах 1/3/5/7) — финальные значения после первого soak-period.
- **Avito auto-cancel timing для Avito-доставки** — точное число дней после оплаты до автоотмены сделки. Defaultlогически взято 5 дней (120ч) — нужно подтвердить через тестовую сделку или анализ `items/{id}` payload. Если Avito возвращает явный `cancel_at` timestamp в payload — использовать его вместо фиксированного 120ч.
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

~21-25 часов кодинга:

- Schema (3 миграции: seller_dialogs, dialog_topics+seed+links, messenger_message.dialog_id) — 1ч
- State machine + 9 transitions в Python — 3ч
- LLM dispatchers + 6 prompt-файлов — 3ч
- Per-stage workers (`dialog_tick_<stage>` × 9) — 3ч
- Silence timeout worker + auto-reject + notified-with-prolongate — 1.5ч
- Action-required TG-пинги (6 триггеров) + prolongate action в drawer — 1.5ч
- Kanban view (9 columns + sortings/filter) — 3ч
- 9 stage-specific card partials — 3ч
- Dialog drawer (lazy chat + extracted_data + actions) — 2ч
- Topic-picker UI (этап 2 «Настройка опроса» — full-card overlay внутри drawer'а с большим списком тем) + dialog_topics CRUD — 2ч
- Operator overrides (+Уточнить, Передать вручную, action buttons per stage) — 1.5ч
- Migration существующих accepted-лотов — 0.5ч
- Тесты + полу-end-to-end smoke (1 живой диалог) — 1.5ч

Plan-стадия покажет точную декомпозицию.

## 8. Что НЕ закрыто и пойдёт в V1.5+

- **Avito-delivery tracking endpoint** — нужен новый xapi-метод для real-time tracking (этапы 7 и 8). MVP полагается на manual confirm от оператора + heuristic на messages keywords.
- **Phase 2 smart auto-tick тем + per-model severity** — когда наберётся статистика по диалогам и шаблоны вопросов, для каждого профиля (= per-model) появится:
  - **Severity per topic**: одна и та же тема (например «замена дисплея») для модели A — критичная (red-flag, suggest reject если seller подтверждает), для модели B — info-only (просто записать в extracted_data)
  - **Auto-pretick**: при попадании лота в этап 2 (Настройка опроса) система автоматически проставляет галочки на темах, которые НЕ закрыты `parameters`/`description` (e.g., «коробка не упомянута → авто-тикнуть»)
  - **Pre-build initial greeting**: в стандартное приветствие можно зашить 1-2 базовых вопроса, специфичных для модели («ещё продаётся? + готов ли к Avito-доставке?») — экономит цикл диалога
  - Реализация: добавить `profile_dialog_topics.severity` (critical / important / info) + heuristic-engine на `description`/`parameters`
- **Mobile app для оператора** с voice-to-text для этапа 4 (Согласование цены) — V2/V3.
- **LLM-assisted draft на этапе 4** — бот предлагает черновик контр-предложения, оператор edit+approve. Пока в V1 оператор печатает с нуля.
- **Аналитика по отказам** — графики причин, conversion-funnel-метрики.
- **Reactivation отказа** — возврат закрытой карточки в pipeline.

## 9. Ссылки

- `CONTINUE.md` §3 — изначальный план seller-dialog
- `~/.claude/plans/sequential-seeking-trinket.md` — Phase A V2 LLM pipeline (паттерн per-criterion + granular cache, переиспользуется)
- `DOCS/REFERENCE/01-avito-api.md` §H — messenger endpoints (createChannel, send, getMessages, markRead)
- Brainstorm transcript — этот документ написан после диалога 2026-05-10 (Q1-Q7 + revisions D1-D16 разрешены)
