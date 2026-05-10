# Seller Dialog Flow — Design Spec

**Дата:** 2026-05-10
**Статус:** Design approved (brainstorm закрыт), готов к написанию плана реализации
**Связанные документы:** `CONTINUE.md` §3, `DOCS/REFERENCE/01-avito-api.md` (messenger endpoints), существующая таблица `chat_dialog_state` (используется reliability-bot'ом).

---

## 1. Цель

Автоматизировать первичный диалог с продавцом для лотов в статусе **«В работу»** через CRM-style kanban с 5 этапами + таб «Отказы». LLM ведёт диалог самостоятельно, оператор вмешивается только на критичных моментах или при escalation.

**Сейчас:** оператор кликает `✓ В работу` → переключается в Avito-app → вручную пишет приветствие, вопросы по аппарату, торгуется. Это 5-10 минут per лот, оператор теряет фокус, многие лоты остаются нетронутыми.

**После V1:** оператор кликает `✓ В работу` → бот сам стартует диалог. Оператор подключается только когда:
- LLM сигналит готовность к финальному решению (зафиксировать цену / подтвердить отправку)
- SLA-таймер сработал (продавец молчит выше нормы)
- Оператор сам захотел уточнить что-то конкретное по карточке

## 2. Non-goals (V1 — явно вне области)

- **Avito-delivery tracking endpoint** в этапе Сделка. Нужен новый xapi-метод, V1 показывает только факт «куплено» без real-time трекинга. → V1.5.
- **Phase 2 smart auto-tick тем** по эвристике из `parameters` / `description` лота. Phase 1 = оператор сам ставит галочки.
- **Аналитика по отказам** (графики причин, conversion rate по этапам). UI просмотра отказов есть, графики позже.
- **Reactivation отказа** обратно в pipeline. В MVP закрыт = закрыт.
- **Multi-operator** (роли, claim карточек). Один оператор.
- **Drag-and-drop карточек** между колонками. LLM-driven flow несовместим с drag-drop, конфликтует с авто-переходами. Карточки двигаются автоматически или через явные action-кнопки.
- **Reuse существующего reliability-bot для sales flow.** Reliability bot — это auto-reply на чужие чаты для имитации активности юзера. Sales flow — другая state machine (триггер по accept-action, не по входящему сообщению). Общая инфраструктура (SSE-listener, rate_limit, dedup) переиспользуется, но handler — новый.

## 3. Принятые решения (brainstorm 2026-05-10)

| # | Вопрос | Решение |
|---|---|---|
| D1 | Этапы пайплайна | 5 stages: **Контакт → Опрос → Цена → Отправка → Сделка**. Параллельно **Отказы** — отдельный таб |
| D2 | Кто двигает карточки между этапами | **LLM-driven** автоматически. Оператор может из любого этапа: `+ Уточнить`, `Откатить на Опрос`, `Передать вручную`, `В Отказы` |
| D3 | «Молчит» как состояние | **Не отдельный статус, а SLA-таймер per этап.** Timeout → escalation (TG-пинг + UI-badge) или auto-route в Отказы. Per-stage конфиг |
| D4 | Список вопросов | **Hybrid:** per-profile YAML-library с чекбоксами (baseline) + per-listing ad-hoc темы. Library растёт через UI |
| D5 | Финал Опроса | LLM шлёт **recap-сообщение** «Итого: АКБ 87%, коробка есть, доставка 2-3 дня. Всё верно?» — подтверждение продавца → переход в Цена |
| D6 | Per-stage Avito API | Каждый этап = свои API-вызовы кроме мессенджера: polling `items/{id}` на reservation/price/delivery-marker |
| D7 | Card layout | **Stage-specific** — 5 partial-templates с разным KPI strip (4/7 тем закрыто / цена-counter / ETA отправки и т.д.) |
| D8 | UI диалога | Drawer справа при клике на карточку = full chat history с timestamps + extracted_data + action buttons |
| D9 | Sortings | 4 пресета: **SLA-deadline / время-без-ответа / цена / дата принятия**. + filter chip по профилю/модели |
| D10 | Отказы | Отдельный таб с табличкой (дата / причина / профиль / stage-when-rejected). Без реактивации в V1 |
| D11 | Build vs buy | **Своё** на HTMX (~16-18ч кодинга). AmoCRM не покрывает structured `extracted_data` + LLM auto-transitions, плюс sync hell |

## 4. Архитектура

### 4.1 State machine

```
              accept-action юзера
                       ↓
              [Контакт]
              ↓ LLM detects "да, продаётся"
              [Опрос]
              ↓ все темы закрыты + recap confirmed
              [Цена]
              ↓ финальная цена зафиксирована
              [Отправка]
              ↓ метод отправки согласован
              [Сделка ✓]

  Из любого этапа → [Отказы]:
   • SLA timeout (с per-stage политикой: escalate / auto-reject)
   • Operator manual close
   • LLM detects refusal / sold-elsewhere

  Operator overrides из любого этапа (через drawer):
   • + Уточнить — добавить темы → LLM шлёт follow-up в текущем этапе (без смены)
   • Откатить → Опрос — пересобрать ответы
   • Передать вручную — LLM мьютится, далее операторский ручной ввод
   • В Отказы — закрыть с causes-enum
```

### 4.2 Per-stage workers

Каждый этап = отдельный TaskIQ task `dialog_tick_<stage>`. Триггеры:
- **Recurring** (каждые 5-10 мин для polling-проверок Avito-side)
- **On-demand** (при SSE inbound от продавца → handler.py роутит в нужный stage tick)

| Этап | LLM-действие | Avito-side проверка | Условие auto-перехода вперёд |
|---|---|---|---|
| **Контакт** | Шлёт приветствие 1 раз | SSE listen на первый ответ | LLM-классификатор детектит утвердительный ответ продавца → Опрос |
| **Опрос** | Темы → вопросы → recap | Periodic-poll `items/{id}` на reservation_status / price changes | Все baseline + ad-hoc темы answered, продавец подтвердил recap → Цена |
| **Цена** | Согласовать финальную цену | `items/{id}.price` watch (продавец мог изменить ценник в объявлении) | LLM detects явное commitment продавца на цене (XX,XXX ₽) → Отправка |
| **Отправка** | Обсудить метод и сроки | `items/{id}` — детектим включение Avito-доставки | LLM detects подтверждение метода (Avito-доставка / курьер / самовывоз) → Сделка |
| **Сделка** | Шлёт «оплачу через Avito» / координация | (V1.5) Avito-delivery tracking endpoint | Operator manual «Получено» / Avito-доставка статус «доставлено» |

### 4.3 SLA timing

Per-stage конфигурируется в `dialog_stage_config` (либо в одном dict в коде — решается в плане):

| Этап | SLA по умолчанию | Действие при timeout |
|---|---|---|
| Контакт | 4ч | escalate (продавец редко отвечает > 4ч на простой вопрос) |
| Опрос | 24ч | escalate |
| Цена | 48ч | escalate |
| Отправка | 72ч | escalate |
| Сделка | 14d | escalate (Avito-доставка может ехать неделю) |

Worker `dialog_sla_tick` (every 5min):
1. Find dialogs WHERE `now() > sla_deadline AND NOT escalated AND closed_at IS NULL`
2. Set `escalated=true`, send TG-ping
3. Operator действия из drawer'а: продлить SLA / отправить в Отказы / Передать вручную

Per-stage политика «escalate vs auto-reject» — поле в `dialog_stage_config.timeout_action` (`escalate` / `auto_reject`). По умолчанию все escalate.

### 4.4 Topic library

**`dialog_topics`** — глобальная библиотека (mirror YAML-сида в БД):

```
key              VARCHAR(64) PRIMARY KEY  -- battery_health / box_present / replaced_display
title            TEXT                      -- "АКБ здоровье"
category         VARCHAR(32)               -- battery / complectness / damage / shipping / price / other
default_phrasing TEXT                      -- "Узнать % здоровья АКБ из настроек, попросить скрин"
expected_format  VARCHAR(32)               -- text / yesno / number / percent / photo
created_at       TIMESTAMPTZ
created_by       VARCHAR(32)               -- 'system_seed' / 'operator'
```

Seed: `avito-monitor/app/data/dialog_topics.yaml` (15-20 тем для iPhone в plan'е).

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
custom_text     TEXT NULLABLE              -- ad-hoc вопрос
status          VARCHAR(16)                -- pending / asked / answered / skipped
question_msg_id UUID NULLABLE              -- ссылка на messenger_message с вопросом
answer_text     TEXT NULLABLE              -- LLM-extracted из ответа
answer_msg_id   UUID NULLABLE
asked_at        TIMESTAMPTZ NULLABLE
answered_at     TIMESTAMPTZ NULLABLE
```

### 4.5 Data model — `seller_dialogs`

```
id               UUID PRIMARY KEY
profile_listing_id UUID FK UNIQUE          -- 1 диалог на 1 (profile, listing)
channel_id       VARCHAR(128) NULLABLE     -- Avito messenger channel
stage            VARCHAR(16)               -- contact/questions/price/shipping/closing/rejected
sla_deadline     TIMESTAMPTZ
last_event_at    TIMESTAMPTZ               -- последнее in/out сообщение
escalated        BOOLEAN DEFAULT false     -- TG-пинг отправлен оператору
operator_mode    BOOLEAN DEFAULT false     -- LLM мьют, оператор пишет вручную
extracted_data   JSONB DEFAULT '{}'        -- структурированные ответы по темам
opened_at        TIMESTAMPTZ
closed_at        TIMESTAMPTZ NULLABLE
closed_reason    VARCHAR(32) NULLABLE      -- silent/refused/price_too_high/sold/other
final_price      NUMERIC NULLABLE
shipping_method  VARCHAR(32) NULLABLE      -- avito/courier/pickup
```

Chat history → переиспользуем существующую `messenger_message` (шарится с reliability-bot — добавим колонку `dialog_id NULLABLE` для дискриминации; reliability-сообщения = NULL).

### 4.6 UI surface

**Routes:**
- `GET /listings?tab=in_progress` — KANBAN view (5 колонок) **— это новый view, заменяет текущий flat-список в табе «В работе»**
- `GET /listings?tab=rejected` — таблица отказов (новый таб «Отказы»; existing «Отклонённые» = rejected by user before contact, переименовать или совместить — решается в плане)
- `GET /profiles/{id}` — расширить форму чек-боксами тем из библиотеки + блок дефолтных SLA per этап
- `GET /dialog-topics` — read/edit библиотеки тем (минимальный CRUD)

**Components (HTMX partials):**
- `kanban_board.html` — 5 колонок + sticky filter/sortings bar
- `kanban_card_contact.html` / `_questions.html` / `_price.html` / `_shipping.html` / `_closing.html` — 5 stage-specific partials
- `dialog_drawer.html` — slide-out справа, lazy-loaded по `hx-get /dialogs/{id}/drawer`. Внутри: chat-style messages с timestamps + extracted_data sidebar + action buttons
- `topic_picker.html` — modal со scroll-чекбоксами + `+ Добавить тему`
- `sla_badge.html` — color-coded по `now()` vs `sla_deadline` (yellow > 70%, red > 90%)

**Operator action endpoints:**
- `POST /dialogs/{id}/clarify` — body: `{topics: [keys], custom: "free text"}` → enqueue LLM follow-up
- `POST /dialogs/{id}/rewind?to=questions` — set stage=questions, return to opened
- `POST /dialogs/{id}/manual` — operator_mode=true, LLM mute
- `POST /dialogs/{id}/close?reason=silent` — closed_at=now, closed_reason set

### 4.7 Migration существующих лотов

В момент первого запуска V1:
- Для каждой `profile_listing WHERE user_action='accepted'` → создать `seller_dialog` со stage=`contact`, **`operator_mode=true`** (LLM не пишет, чтобы не спамить продавца повторно если оператор уже общался вручную).
- Карточка показывается в kanban в колонке Контакт с badge `Ручной режим`.
- Оператор может вручную в drawer'е: либо отметить «Перевести в автомат» (LLM возьмёт диалог с того места, где оператор остановился — но это рискованно, лучше force-стартовать с Опроса) либо просто использовать как notes-карточку.

Переход существующих диалогов в auto-режим — opt-in per карточка, не общий toggle.

## 5. Точки переиспользования существующего кода

| Компонент | Что берём | Изменения |
|---|---|---|
| `avito-xapi/src/workers/http_client.py` | `create_channel_by_item`, `send_text`, `get_messages`, `mark_read` | reuse as-is |
| `avito-xapi/src/routers/messenger.py` | HTTP wrappers поверх http_client | reuse as-is |
| `avito-monitor/app/services/messenger_bot/runner.py` | SSE listener loop с reconnect/backoff | reuse — общий для reliability и sales |
| `avito-monitor/app/services/messenger_bot/handler.py` | dispatcher inbound events | NEW branch: если channel принадлежит `seller_dialogs` → роутить в sales handler, иначе в существующий reliability |
| `messenger_bot/{rate_limit,dedup,kill_switch}.py` | anti-detection helpers | reuse as-is |
| `app/services/llm_analyzer.py` | LLM dispatch с granular cache | NEW методы: `generate_greeting`, `formulate_questions`, `extract_topic_answer`, `detect_stage_completion`, `formulate_recap` |
| `app/db/models/messenger_message.py` | chat history table | NEW колонка `dialog_id` (nullable, FK) |

## 6. Open questions для plan-стадии

(вопросы, требующие code-detail решений во время написания плана)

- **SLA defaults** — точные числа per stage и формат `dialog_stage_config` (table vs dict в коде)
- **Seed `dialog_topics.yaml`** — конкретный список 15-20 baseline-тем для iPhone (battery_health, box_present, replaced_display, charge_cable, headphones, original_box, repair_history, water_damage, screen_scratches, body_dents, payment_method, avito_delivery_ready, courier_acceptable, pickup_location, etc.)
- **Prompts per stage** — тексты для LLM (`generate_greeting`, `formulate_questions`, etc.) — создать `app/prompts/dialog_*.md`
- **Stage-detection LLM call** — отдельный prompt для классификации «готов ли переходить в следующий stage» (low-cost classifier, как existing per-criterion eval) или используем эмбеддер confidence от `extract_topic_answer`
- **TG-пинг формат** для escalation — текст и кнопки (открыть карточку / отложить / в отказы)
- **Reliability vs sales sharing** `messenger_message` — добавить `dialog_id NULLABLE` или сделать отдельную таблицу `seller_messages`. Принципиально не критично, решается в плане
- **Существующий таб «Отклонённые»** vs новый «Отказы» — слить в один таб с фильтром «отклонено оператором / отказ продавца» или держать раздельно
- **Recap-confirmation parsing** — как LLM детектит «всё верно» от продавца (yes/no классификатор с фоллбэком на operator)

## 7. Стоимость

~16-18 часов кодинга:
- Schema (3 миграции: seller_dialogs, dialog_topics+seed+links, messenger_message.dialog_id) — 1ч
- State machine + transitions в Python — 2ч
- LLM dispatchers + 5 prompt-файлов — 3ч
- Per-stage workers (dialog_tick_*) — 2ч
- SLA worker + escalation TG-ping — 1.5ч
- Kanban view (5 columns + sortings/filter) — 3ч
- 5 stage-specific card partials — 2ч
- Dialog drawer (lazy chat + extracted_data + actions) — 1.5ч
- Topic-picker UI на профиле + dialog_topics CRUD — 1.5ч
- Migration существующих accepted-лотов — 0.5ч
- Тесты + полу-end-to-end smoke (1 живой диалог) — 1ч

Plan-стадия покажет точную декомпозицию; цифра ориентир.

## 8. Ссылки

- `CONTINUE.md` §3 — изначальный план seller-dialog (этот спек его расширяет и закрывает open questions)
- `~/.claude/plans/sequential-seeking-trinket.md` — Phase A V2 LLM pipeline (паттерн per-criterion + granular cache, переиспользуется)
- `DOCS/REFERENCE/01-avito-api.md` §H — messenger endpoints (createChannel, send, getMessages, markRead)
- Brainstorm transcript — этот документ написан после диалога 2026-05-10 (Q1-Q7 разрешены)
