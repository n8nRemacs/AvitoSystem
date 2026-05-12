# Defect Checklist + Per-profile Feature Rules

**Дата:** 2026-05-12
**Статус:** утверждено пользователем, готово к плану (writing-plans)
**Базовый дизайн:** [`2026-05-11-seller-dialog-phase-b-design.md`](./2026-05-11-seller-dialog-phase-b-design.md)
**Подразумеваемая модель профиля:** iPhone 12 Pro Max (единственный пока), но архитектура per-profile.

---

## 1. Цель

Превратить kanban-карточку лота в **визуальный чек-лист признаков** (defect features), извлекаемых из объявления автоматически, и заменить confidence-based bucketing (V2 reliability) на **детерминированный bucketing от per-profile feature-rules**.

Конкретно:

- Структурированная таксономия признаков (6 категорий, ~22 пункта) — yaml.
- LLM-парсер по разделам + приоритет Avito-параметров → каждый признак на лоте имеет state `ok | defect | unknown`.
- На профиле оператор per-feature ставит правило: **🟢 green-flag / 🔴 red-flag / ⊘ ignore** через UI в новом slide-out drawer слева.
- Bucket (`green | grey | red`) вычисляется детерминированно из (features × rules):
  - red-flag + confirmed defect → **bucket=red, user_action=rejected (auto)**, дальше не идём
  - green-flag + defect → bucket=grey (operator разберёт)
  - любой неопределённый признак с rule ≠ ignore → bucket=grey (опрос подтвердит)
  - все green-flag подтверждены ok, ни одного red-flag-defect → bucket=green
- В expanded body карточки kanban (и tab «Новые») — новый блок «Признаки» с иконками ✓/⊘/⚪.
- В Phase 2: setup-modal переехала в drawer, унаследовала чек-лист с тоглами на unknown-фичах, **personalised opener бота** на основе confirmed-defects + **двойной LLM на каждый inbound** (targeted topic-parse + broad feature-scan) для динамического движения лота по бакетам в реальном времени опроса.

После shipping:
- Лоты с iCloud locked (или другим red-flag, что оператор сконфигурит) идут в Отклонённые автоматически, не требуют ручной триажа.
- Оператор видит на карточке сразу что LLM нашла как дефект (без чтения описания) и быстро решает на грэй-лотах.
- При подключении новой модели — оператор копирует правила, корректирует под ремонтные возможности (например, для iPhone 11 правило `sensors.face_id` = green, а не red, потому что он может починить), и система переиспользует ту же таксономию.

## 2. Use case (ключевая мотивация для per-profile rules)

Профиль ≈ модель/линейка. Оператор имеет различные ремонтные возможности для разных моделей:

- iPhone до 13 серии (НЕ включая 13) — может починить Face ID → `sensors.face_id` на профиле такой модели = **green-flag** (defect=grey, не auto-reject).
- iPhone до 12 (кроме 12 Pro Max, 12 mini) — может поменять тачскрин → `display.touchscreen_glitches` = **green-flag** для этих моделей.
- iCloud — нерешаемо для всех → `locks.icloud_linked` = **red-flag** для всех профилей.

То есть таксономия одна, правила per-profile. Изменение правил на профиле должно **переcчитать bucket для всех существующих лотов профиля** без повторного LLM-парсинга (features already known).

## 3. Non-goals

- **Phase 1 (этот spec, обе фазы вместе) НЕ включает:**
  - Авто-pretick тоглов unknown-фич с приоритетом по category — Phase 2 backlog (нужна статистика по точности LLM).
  - Keyword/regex fallback для критичных фич (icloud, broken_back) — добавим в Phase 1.5 если recall LLM ≤ 95% на soak'е.
  - Realtime UI update карточки во время опроса (SSE/poll) — F5/page-refresh достаточно сейчас, добавим позже если станет тесно.
  - Re-parsing LLM при изменении таксономии (добавили новый feature) — пока пересоберём руками для существующих active-лотов через скрипт, автоматизация позже.
  - Severity-per-feature (weighted bucket score) — сейчас boolean ok/defect/unknown.

- **Удержание `condition_class` enum (working/blocked_icloud/broken_screen/...).** Текущий `classify_condition` LLM-вызов остаётся, поле в БД остаётся. Старый bucket-расчёт (V2 reliability, confidence-based) — **отключаем**, его место занимает feature-based. Market-stats / distribution UI на `condition_class` продолжают работать без изменений.

## 4. Принятые решения (brainstorm 2026-05-12)

| # | Решение | Обоснование |
|---|---|---|
| Q1 | **Фазы B**: (Phase 1) парсер + read-only чек-лист в карточке + правила на профиле + bucketing-replacement → soak 3-4 дня → (Phase 2) setup-modal-redesign + personalised opener + двойной inbound-LLM. | Read-only фаза безопасна; качество LLM-парсера видно визуально до того, как влияет на бота. |
| Q2 | **Per-profile rules**, не глобальные | Использовать-кейс: разные ремонтные возможности для разных моделей. iPhone 12 PM ремонтирует тачскрин — для iPhone 11 нет. |
| Q3 | **3-state rule per feature на профиле**: 🟢 green-flag / 🔴 red-flag / ⊘ ignore | Юзеровская терминология. `ignore` = N/A для модели (фича физически отсутствует или непринципиальна), `green` = желательна как ok, `red` = критична. Дефолт ignore. |
| Q4 | **Unknown по green/red-rule → bucket=grey**, НЕ auto-reject авансом | Без явного подтверждения дефекта мы можем выкинуть нормальный лот, если LLM пропустил. Reject только на confirmed defect. |
| Q5 | **Хранение features на лоте — таблица `listing_features`** (одна строка на feature, не jsonb-блоб) | Возможность писать запросы «сколько лотов с дефектом X», аналитика per-feature, индексы. |
| Q6 | **Хранение rules на профиле — таблица `profile_feature_rules`** (одна строка на правило) | Симметрично с listing_features; легче для UI-edit (PATCH одно поле); миграции расширяемее. |
| Q7 | **Парсер — 6 промптов по разделам, параллельно через asyncio.gather** + приоритет Avito-параметров | Точность > монолитного промпта. Cost ~$0.0006/лот (Gemini Flash Lite). Если в `listing.parameters` уже сказано «Face ID: не работает» — state finalised без LLM. |
| Q8 | **Conservative prompting** — при малейшем сомнении state=unknown, не ok | LLM-ok должен быть явным; "не упомянуто" = unknown, спросим в опросе. |
| Q9 | **Auto-reject в analyze pipeline**, до показа в kanban. `user_action='rejected'`, `rejected_reason='auto:<feature>'` | Лот никогда не появляется в «Новые», сразу в Отклонённые. Recovery — кнопка «↶ Вернуть в новые» (уже есть). |
| Q10 | **Single sidebar item «🛠 Настройки модели»** открывает slide-out drawer с таблицей фич + 3-state переключателями. Сайдбар-collapse — параллельная задача в Phase 1. | Юзер планирует AvitoSystem как часть большей системы, общий nav-pattern полезен. |
| Q11 | **No-defects opener — НЕ нужен** | Если confirmed-defects = 0, opener-подтверждающую строку не делаем. Сразу первый «А вот это как?» по unknown-тоглам или recap (если тоглов нет). |
| Q12 | **Двойной LLM на каждый inbound** в Phase 2: targeted parse_topic_answer (existing) + новый scan_message_for_features (broad sweep) | Продавец может проговориться об ином признаке отвечая на вопрос про АКБ — мы должны это поймать и пересчитать bucket. |
| Q13 | **`condition_class` остаётся**, но bucket больше им не считается. condition_class — derived из condition + используется только market-stats / legacy UI. | Не ломаем аналитику; убираем единственный источник истины для bucketing → feature-rules. |

## 5. Таксономия (полный список)

В `app/data/dialog_topics.yaml` расширяется до 22 пунктов в 6 категориях. Старые 11 ключей мигрируем через rename-map (Alembic data-migration):

| Новый ключ | Старый ключ | Категория | Title (UI / opener) | Format |
|---|---|---|---|---|
| `display.replaced` | `replaced_display` | display | Дисплей менялся | yesno |
| `display.glass_broken` | `broken_glass` | display | Стекло дисплея разбито | yesno |
| `display.touchscreen_glitch` | — | display | Тачскрин глючит | yesno |
| `display.stains_stripes` | `display_stains_stripes` | display | Пятна / полосы на дисплее | yesno |
| `case.back_broken` | `broken_back` | case | Задняя крышка разбита | yesno |
| `case.midframe_bent` | — | case | Средняя часть корпуса погнута | yesno |
| `case.midframe_cracked` | — | case | Средняя часть корпуса поломана | yesno |
| `locks.icloud_linked` | `icloud_unlinked` (инверс)¹ | locks | iCloud привязан к чужому | yesno |
| `locks.passcode_forgotten` | — | locks | Пароль на экран забыт | yesno |
| `sensors.face_id` | `face_id_works` (инверс) | sensors | Face ID не работает | yesno |
| `sensors.truetone` | — | sensors | TrueTone не работает | yesno |
| `sensors.wifi` | — | sensors | WiFi не работает | yesno |
| `sensors.sim` | — | sensors | SIM-слот не работает | yesno |
| `sensors.bluetooth` | — | sensors | Bluetooth не работает | yesno |
| `sensors.other` | — | sensors | Другие датчики не работают | text |
| `charging.not_charging` | — | charging | Не заряжается | yesno |
| `charging.wireless_only` | — | charging | Заряжается только беспроводной | yesno |
| `charging.unstable` | `charging_stability` (инверс)² | charging | Зарядка нестабильна (нужно двигать кабель) | yesno |
| `operability.boot_loop` | — | operability | Висит на прошивке (boot-loop) | yesno |
| `operability.reboots` | — | operability | Периодически перезагружается | yesno |
| `operability.no_boot` | — | operability | Стартует и не загружается | yesno |
| `operability.apple_loop` | — | operability | Висит / перезагружается на яблоке | yesno |

¹ Старые «инвертированные» ключи (`icloud_unlinked` = «отвязан ли») мигрируем в дефект-ориентированные (`locks.icloud_linked` = «привязан ли»). Семантика state: ok = не привязан, defect = привязан.

² `charging_stability` (text) → `charging.unstable` (yesno). Text-form ответы извлекаются в `evidence` поле; для bucketing достаточно yesno-state.

**Удалённые из baseline**: `battery_health (percent)`, `cameras_work (text)`, `replaced_parts (text)`, `complectness (text)`. Не входят в новую таксономию defect-checklist. Однако `complectness` нужен для торга (Phase D) — оставляем в `dialog_topics.yaml` с category=`extra`, но **не парсится** parse_section и **не отображается в чек-листе карточки**; operator может добавить как ad-hoc топик в опрос. `battery_health` восстановим если будет нужно (text-form через ad-hoc).

Yaml дополняется полями `severity_hint: red|green|info` — рекомендация дефолта для новых профилей (что copy в profile_feature_rules при создании). `severity_hint=info` ≈ дефолт=ignore.

## 6. Schema (Alembic `0015_defect_checklist`)

```sql
CREATE TABLE listing_features (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id    UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    feature_key   TEXT NOT NULL,                    -- e.g. 'display.glass_broken'
    state         TEXT NOT NULL,                    -- 'ok' | 'defect' | 'unknown'
    confidence    DOUBLE PRECISION,                 -- NULL if source != 'llm'
    source        TEXT NOT NULL,                    -- 'avito_parameters' | 'llm' | 'description_kw' | 'seller_dialog'
    evidence      TEXT,                             -- цитата / Avito-параметр / quote из inbound
    parsed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (listing_id, feature_key)
);
CREATE INDEX ix_listing_features_listing_id ON listing_features(listing_id);
CREATE INDEX ix_listing_features_feature_state ON listing_features(feature_key, state);

CREATE TABLE profile_feature_rules (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id    UUID NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE,
    feature_key   TEXT NOT NULL,
    rule          TEXT NOT NULL,                    -- 'green' | 'red' | 'ignore'
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (profile_id, feature_key)
);
CREATE INDEX ix_profile_feature_rules_profile_id ON profile_feature_rules(profile_id);
```

Поле `profile_listings.rejected_reason TEXT NULL` — если не существует, добавляем (для auto-reject reason); если есть — переиспользуем. Формат `'auto:<feature_key>'` для системного reject, `'manual:operator'` для ручного.

**Data migration:**
1. Все строки `seller_dialog_topics` с old keys (`battery_health`, `face_id_works`, ...) — обновить `topic_key` на new keys через rename-map. Сохранить state.
2. Все строки `profile_dialog_topics` — то же.
3. `dialog_topics` (library) — обновить keys, title, category.
4. Существующие listings без `listing_features`-строк — НЕ заполняем в миграции (миграция атомарная и быстрая). Заполнение делает отдельный backfill-скрипт (§13.9) — он гоняет parser-пайплайн на active-лоты после деплоя; либо в фоне через scheduler.

## 7. LLM-парсер: `parse_section_defects`

### 7.1 Поток на одном лоте (Phase 1)

```
analyze_listing(listing)
  ↓
  (existing) classify_condition → condition_class, reasoning, confidence
  ↓
  NEW: parse_defect_features(listing, active_features):
       active_features = {feature_key: section} для всех keys где
                          profile_feature_rules.rule ≠ ignore
       (если несколько профилей подписаны на лот, объединение)
       ↓
       Step A. match_avito_parameters(listing.parameters, active_features)
               → finalised[feature_key] = (state, source='avito_parameters', evidence=value)
       ↓
       Step B. match_description_keywords(listing.description, active_features\finalised)
               regex/dict из app/data/defect_keywords.yaml
               (Phase 1.5: добавляется при необходимости)
       ↓
       Step C. parallel LLM per section:
               for section in {display, case, locks, sensors, charging, operability}:
                   keys = active_features[section] \ finalised
                   if not keys: continue
                   prompt = render_section_prompt(section, listing, keys)
                   result = await llm(prompt)  # asyncio.gather
               → results[feature_key] = (state, confidence, source='llm', evidence)
       ↓
       Merge finalised + LLM results → upsert listing_features rows
  ↓
  NEW: recompute_bucket(listing, profile)
```

### 7.2 Prompt skeleton (одна секция)

`app/prompts/parse_section_<section>.md`:

```
Ты анализируешь объявление о продаже {model}. Извлеки состояние следующих
признаков из текста объявления + полей Avito.

Признаки:
{{#each features}}
- {{key}}: {{title}} ({{format}})
{{/each}}

ВАЖНО: при малейшем сомнении ставь "unknown". "ok" только если продавец
ЯВНО сказал что признак в порядке. "defect" если продавец явно описал
проблему. Если признак вообще не упомянут — "unknown".

Описание объявления:
"""
{{description}}
"""

Avito-параметры:
{{parameters_yaml}}

Ответь JSON-объектом:
{ "<feature_key>": { "state": "ok|defect|unknown",
                     "confidence": 0.0-1.0,
                     "evidence": "цитата или null" }, ... }
```

Pydantic-валидация ответа. Если LLM возвращает невалидный JSON — fallback: все unknown, error в `evidence`.

### 7.3 Broad-scan на inbound (Phase 2)

`scan_message_for_features(message_text, profile, listing)` — ОДИН LLM-промпт (не 6, т.к. контекст крошечный — одно сообщение):

```
Продавец прислал в чат: "{{message_text}}"

Проверь, не упомянул ли он что-то из этих признаков аппарата:
{{#each active_features}}
- {{key}}: {{title}}
{{/each}}

Ответь JSON только для УПОМЯНУТЫХ:
{ "<feature_key>": { "state": "ok|defect|unknown",
                     "confidence": 0.0-1.0,
                     "evidence": "цитата" }, ... }

Если ничего не упомянуто — пустой объект {}.
```

Запускается параллельно с existing `parse_topic_answer` на каждом inbound в seller_dialog stage='questions' (и stage='contact' на opener-reply). Результат → upsert `listing_features` со `source='seller_dialog'`, evidence=quote, parsed_at=NOW(). Затем recompute_bucket.

Если новый bucket=red → close_dialog(`auto_reject:<feature>`), пишем notification operator'у. Если grey остался или стал green — diaог не трогаем.

**Стоимость:** +1 LLM Flash Lite на каждый inbound ≈ $0.0001 × 10-20 inbound/лот ≈ $0.002/dialog. Negligible.

## 8. Bucketing: `compute_bucket(features, rules) → (bucket, reason)`

Чистая функция, никакого I/O. Тестируется отдельно.

```python
def compute_bucket(features: dict[str, FeatureState],
                   rules: dict[str, FeatureRule]) -> tuple[str, str | None]:
    """
    features: {feature_key: 'ok'|'defect'|'unknown'} — current parsed state per lot
    rules:    {feature_key: 'green'|'red'|'ignore'} — per profile

    Returns:
      bucket = 'green' | 'grey' | 'red'
      reason = feature_key that triggered red/grey, or None for green
    """
    # Step 1: red-flag confirmed defects → auto-reject, short-circuit
    for fkey, rule in rules.items():
        if rule == 'red' and features.get(fkey) == 'defect':
            return ('red', fkey)

    # Step 2: any non-ignored unknown → grey (must clarify)
    for fkey, rule in rules.items():
        if rule in ('green', 'red') and features.get(fkey, 'unknown') == 'unknown':
            return ('grey', fkey)

    # Step 3: green-flag defect → grey (operator decides)
    for fkey, rule in rules.items():
        if rule == 'green' and features.get(fkey) == 'defect':
            return ('grey', fkey)

    # Step 4: all green-rules confirmed ok, no red-defect → green
    return ('green', None)
```

Применяется:
- В analyze_listing после parse_defect_features.
- В UI-handler «save profile rules» после persist — для всех accepted+new лотов профиля.
- В Phase 2 после broad-scan inbound — для одного лота.

Если bucket=red и `user_action ∈ (NULL, 'pending', 'viewed')` → автоматически выставляем `user_action='rejected'`, `rejected_reason='auto:<reason>'`. Если уже `accepted` — НЕ ретроактивно reject'им (operator уже взял лот в работу, его не убираем). В Phase 2 broad-scan на accepted-лот меняет только feature state + закрывает активный диалог (`close_dialog(reason='auto_reject_from_dialog:<feature>')`) + шлёт notification operator'у; user_action остаётся `accepted`, лот остаётся в kanban-карточке «В работе» (но без активного dialog) — operator сам решает reject вручную или recover.

## 9. UI — Phase 1

### 9.1 Блок «Признаки» в expanded body карточки (kanban + tab Новые)

Перед description, компактная 2-column сетка по категориям:

```
┌─────────────────────────────────────────────────┐
│ Дисплей    ✓ Стекло целое                       │
│            ⊘ Тачскрин глючит                     │
│            ⚪ Пятна / полосы            [спросить]│
│                                                  │
│ Корпус     ✓ Задняя крышка                       │
│            ✓ Средняя часть погнута? — ✓          │
│                                                  │
│ Блокировки ⊘ iCloud привязан                     │
│            ⚪ Пароль забыт?            [спросить]│
│ …                                                │
└─────────────────────────────────────────────────┘
```

Иконки:
- ✓ зелёная (text-emerald-600) — state=ok
- ⊘ красный круг перечёркнутый (text-rose-600) — state=defect
- ⚪ серый кружок (text-stone-400) — state=unknown

Tooltip на иконке — `evidence` (цитата или Avito-поле). Маленький бейдж source: `🅰` для avito_parameters, `🤖` для llm, `💬` для seller_dialog.

Фичи с rule=ignore — НЕ отображаются (даже если parser их распарсил, что не должно случаться т.к. парсер skip их).

Header карточки получает badge bucket+reason: `🔴 reject: locks.icloud_linked` / `🟡 grey: sensors.face_id` / `🟢 green`.

### 9.2 Sidebar-collapse

`<aside>` в `_layout.html` получает `id="sidebar"`, ширина управляется dataset.

```html
<aside id="sidebar" data-collapsed="false"
       class="w-60 [data-collapsed=true]:w-14 transition-[width] duration-200 ...">
```

(Точный синтаксис Tailwind может потребовать `[data-collapsed=true]:` через arbitrary-variant; альтернатива — `aria-expanded` + класс через JS.)

Hamburger в topbar — toggle button. Click → `sidebar.dataset.collapsed = !`; persist в `localStorage.kpis_sidebar_collapsed`. В collapsed состоянии — иконки видны, label-текст скрыт через `[data-collapsed=true]:hidden` на спанах с `flex-1` и badge'ах.

На mobile (< 768px) — sidebar полностью overlay-режим (off-canvas), показ через transform. Phase 1.5 если станет тесно.

### 9.3 Новый nav-пункт «🛠 Настройки модели»

Добавляется в `_items` в `_layout.html`:

```python
('model-settings', '/profiles/{active_profile_id}/feature-rules', '🛠', 'Настройки модели', None),
```

Активен когда есть `active_profile_id` в session/cookie (Phase 1: hardcode на первый профиль user'а; Phase 2: profile-switcher в topbar). Открывает страницу или **slide-out drawer** (см. ниже).

### 9.4 Slide-out drawer «Настройки модели»

Запускается из пункта sidebar (либо overlay-drawer с overlay backdrop, либо страница `/profiles/{id}/feature-rules`). Phase 1 — отдельная страница (проще), drawer-обёртка добавляется в Phase 2.

Содержит таблицу:

| Категория | Признак | Правило |
|---|---|---|
| Дисплей | Дисплей менялся | [🟢] [🔴] [⊘] |
| Дисплей | Стекло разбито | [🟢] [🔴] [⊘] |
| … | … | … |

Каждая строка — 3-state segment-toggle (как `decision-toggle` в `listings.html`). State persisted немедленно через PATCH `/profiles/{id}/feature-rules` (per-key, optimistic UI).

После save — **синхронный** recompute_bucket для всех лотов профиля (N обычно ≤ нескольких сотен, чистая функция без LLM-вовлечения) + toast «Бакеты пересчитаны: <green> зелёных / <grey> серых / <red> отклонено». Если N большое (> 5k) — async через TaskIQ, индикатор «пересчёт…» в toast.

Save endpoint вызывает:
```python
async def recompute_buckets_for_profile(session, profile_id):
    # Все profile_listings с user_action IN (NULL, 'pending', 'viewed')
    # для accepted — пересчитываем bucket, но user_action не трогаем
    ...
```

## 10. UI — Phase 2

### 10.1 Setup-modal → checklist-drawer

Существующий setup-modal (нативный `<dialog>`) заменяется на slide-out drawer справа (для seller-dialog), либо переиспользует слева. Содержит:

- Тот же чек-лист признаков что в карточке, но интерактивный.
- Каждая фича с `state=unknown` и `rule ∈ (green, red)` — рендерится как тогл **включён по умолчанию** (спросим в опросе).
- Operator может отключить тогл (пропустить вопрос).
- Operator может вкл тогл на фиче с state=ok или defect (хочет переспросить продавца).
- Поле ad-hoc «Добавить вопрос» — как сейчас, переиспользуем.
- Кнопка «Запустить опрос».

Submit → init `seller_dialog_topics` rows только для активированных тоглов (со `priority` из таксономии) → транзишн в stage=questions → kick off `dialog_tick_questions`.

### 10.2 Personalised opener бота

В `dialog_tick_questions` first tick (новый код):

```python
async def build_opener(listing, features, rules) -> str | None:
    confirmed_defects = [
        topics[k].opener_phrasing for k, st in features.items()
        if st == 'defect' and rules.get(k) in ('green', 'red')
    ]
    if not confirmed_defects:
        return None  # no opener, idu сразу к первому вопросу
    return (
        "Я внимательно прочитал ваше объявление. Понял, что у вас: "
        + ", ".join(confirmed_defects)
        + ". Всё верно?"
    )
```

`opener_phrasing` — новое поле в `dialog_topics.yaml`, короткая натуральная формулировка дефекта («разбито стекло дисплея», «привязан iCloud», «не работает Face ID»).

Если opener вернул `None` — bot шлёт сразу первый «А вот это как? — <question>» как раньше.

Если opener послан — bot ждёт ответ → `parse_seller_agreement` (existing) + `scan_message_for_features` (new) параллельно.
- agreement=yes → продолжаем к unknown-тоглам.
- agreement=no и broad-scan нашёл feature-correction → update listing_features (`source='seller_dialog'`), recompute_bucket. Если bucket=green → recap → SUGGEST. Если grey/red остались — продолжаем опрос (или close при red).
- agreement=unclear → бот переспрашивает («Подскажите пожалуйста точно, какие из этих моментов в порядке, а какие нет?»). Counter retry_count++; на 2-м retry эскалация в operator_mode.

### 10.3 Двойной LLM на каждый inbound (questions stage)

В SSE handler для seller_dialog inbound (existing `handle_seller_inbound`):

```python
parsed, scanned = await asyncio.gather(
    parse_topic_answer(open_topic, text, open_topics_list),
    scan_message_for_features(text, profile_active_features, listing),
)
# update topic state from parsed
# update listing_features from scanned, recompute_bucket
# if bucket=red → close_dialog + notify, stop processing
```

## 11. Backwards compat

- `classify_condition` LLM-вызов остаётся в `analyze_listing`. Поле `listings.condition_class`/`condition_reasoning`/`condition_confidence` пишутся как сейчас.
- Старый bucket-расчёт (V2 reliability, confidence-based) — **отключается**. Новый bucket пишется в `profile_listings.bucket` через `compute_bucket(features, rules)`.
- Phase 1 миграция: на запуске prod scheduler пробегает по всем listings без `listing_features` → re-analyze через `parse_defect_features` → bucket recompute. Возможно ~часы LLM-времени; запускаем отдельным rake-скриптом `python -m scripts.backfill_features`.
- Старые `seller_dialog_topics` для активных диалогов — мигрируем feature_keys через rename-map. Активные диалоги не прерываются.
- Market-stats / distribution UI на `condition_class` — без изменений.

## 12. Re-evaluation policy

| Триггер | Действие |
|---|---|
| Profile rule изменён (per-feature) | recompute_bucket для всех profile_listings.user_action IN (NULL, pending, viewed). Для accepted — bucket recompute, но user_action не трогаем (operator уже взял в работу). |
| Profile rule изменён на ignore (был red/green) | listing_features для этого feature_key для лотов профиля можно **не удалять**, но они перестают участвовать в bucket. При повторной активации (ignore→red/green) парсер запускается re-LLM для тех фич, которые ушли в ignore слишком давно (старше 30 дней) — для свежести. |
| Новый feature_key добавлен в таксономию | scheduler-job: для всех active listings → запустить parse_section для соответствующей категории, заполнить новые `listing_features` rows. |
| Listing обновился (новое description / parameters) | парсер запускается заново на все active_features для этого лота. listing_features upsert'ит с новым parsed_at. Bucket recompute. |
| Seller-dialog inbound поменял feature state (Phase 2) | bucket recompute локально, без вовлечения всех лотов. |

## 13. Phasing & rollout

### Phase 1 (~12h dev + 3-4d soak)

1. Taxonomy yaml + rename-map (Alembic data-migration, 2h)
2. Schema migrations + SQLAlchemy models (2h)
3. `match_avito_parameters` (dict-based, 1h) + `parse_section_defects` LLM (6 промптов, asyncio.gather, 2h)
4. `compute_bucket` function + unit tests (1h)
5. Pipeline integration in `analyze_listing` (1h)
6. `listing_features` rendering на карточке kanban + listings new tab (1h)
7. Sidebar-collapse JS + CSS (0.5h)
8. Страница `/profiles/{id}/feature-rules` (CRUD form + save + recompute_buckets) (1.5h)
9. Backfill-script + smoke (0.5h)
10. Deploy + soak

**Acceptance criteria Phase 1:**
- На карточке kanban видны Признаки (минимум для accepted-лотов с свежим parser-run).
- Auto-reject работает: лот с confirmed locks.icloud_linked при rule=red уходит в Отклонённые без operator-вмешательства.
- Изменение правила на профиле пересчитывает bucket для существующих лотов.
- Backfill-script отрабатывает на текущие ~hundreds лотов.

**Soak observe:**
- Recall LLM-парсера на ~50 свежих лотов (manual eval).
- Сколько false-positive auto-reject? Recovery rate через «↶ Вернуть в новые».
- Стоимость LLM /день.

Если recall < 95% по критическим фичам (icloud, broken_glass) — Phase 1.5: keyword fallback.

### Phase 2 (~6h dev + 1-2d soak)

1. Setup-modal → checklist-drawer с тоглами (2h)
2. Persistence seller_dialog_topics из тоглов (0.5h)
3. `build_opener` + opener-reply handler (1h)
4. `scan_message_for_features` LLM + integration в `handle_seller_inbound` (1.5h)
5. Auto-close dialog при bucket=red от broad-scan (0.5h)
6. UI индикатор «динамика bucket» (Phase 2.5 если будет нужно)

**Acceptance criteria Phase 2:**
- На активацию опроса bot шлёт personalised opener (с защитой no-defects=no-opener).
- На inbound product test scenario: seller проговорился об iCloud → лот auto-closed dialog + перешёл в rejected.

## 14. Open questions / future work

- **Severity-weighted bucket** — некоторые green-flag дефекты «менее grey» чем другие. Например, царапины ≪ полосы на дисплее. Сейчас булевы. Phase 3+.
- **Per-profile-feature confidence threshold** — бывает LLM возвращает confidence 0.3, state=defect, evidence='—'. Нужно ли минимальное confidence чтобы считать state валидным? Сейчас не используем, но добавим если будет mass false-positives.
- **Automatic taxonomy expansion** — операторы могут вручную добавлять признаки через UI? Сейчас нет, yaml-only. Phase 3.
- **Multi-profile listings** — один лот может попадать в несколько профилей с разными правилами. Сейчас bucket пишется в `profile_listings`, так что per-profile. OK.
- **A/B opener tone** — formal vs casual. Сейчас формальный. Phase 3.

## 15. Risks

| Risk | Mitigation |
|---|---|
| LLM ошибается → auto-reject хорошего лота | conservative-prompt (unknown по умолчанию), recovery «↶ Вернуть в новые», мониторинг recall на soak. |
| Стоимость LLM | Парсим только rule≠ignore. Gemini Flash Lite копейки. Soak monitor + threshold alert на 1$/день. |
| Schema-migration ломает активные диалоги | Rename-map в data-migration, integration test «активный dialog → переход stage» после миграции. |
| Бакет-логика mismatch UI/back-end | `compute_bucket` чистая функция, unit-тесты. UI badge — derived из profile_listings.bucket (один источник истины). |
| Параллельные LLM-запросы — rate-limit | OpenRouter rate-limit для Gemini Flash Lite высокий; 6 в asyncio.gather на 1 лот — далеко от потолка. На массовом backfill — batched (max_concurrent=20). |
| Двойной LLM на каждый inbound (Phase 2) накапливает | Кэшируем `scan_message_for_features` по hash(text) — если seller дублирует сообщение, не платим заново. |
