# Unified Criteria — слияние V2 LLM pipeline в defect-features

**Дата:** 2026-05-12
**Статус:** утверждено пользователем, готово к плану (writing-plans)
**Базовый дизайн:** [`2026-05-12-defect-checklist-design.md`](./2026-05-12-defect-checklist-design.md)
**Стартовое состояние:** Phase 1 defect-checklist shipped 2026-05-12 (22 defect-фичи, `listing_features` + `profile_feature_rules`); V2 LLM-pipeline (`criteria_templates` / `profile_criteria` / `llm_analyses` / `profile_listing_evaluations`) работает вхолостую — bucket больше не пишется из V2.

---

## 1. Цель

Унифицировать две параллельно живущие LLM-системы в **одну модель «фич на лоте + правил на профиле»** с тремя `kind`-типами (`defect` / `price_signal` / `info_api`). База — новая defect-таксономия (Phase 1). V2 удаляется целиком в той же миграции.

Конкретно:

- **Защипано:** sidebar nav «🛠 Настройки модели» (захардкоженный на первый профиль) удалить; feature-rules переезжают в форму конкретного парсинга/профиля как таб.
- **Defect taxonomy расширяется** с 22 до 26 фич (добавляются 4 ключа, которые в V2 были `criterion`-kind, а в defect отсутствовали).
- **Price-signal фичи** (2 шт: `battery_health`, `repaired_components`) — новый `kind=price_signal`. Это не «info» в чистом виде: они влияют на оценку цены при перепродаже / торге (АКБ 87% даёт +N₽ skidka, заменён aftermarket-экран − ещё больше). Сейчас отображаются на карточке; Phase 3 pricing intelligence будет читать `value` напрямую без миграции.
- **Info-API фичи** (3 шт: `memory_gb`, `color`, `vendor_model`) — `kind=info_api`. Direct read из `listing.parameters`, чисто описательные, для контекста на карточке.
- Все 31 фичей хранятся в той же таблице `listing_features` с новым полем `kind` и `value` JSONB. Только defect-фичи имеют rules и влияют на bucket.
- **V2 артефакты** (4 таблицы + grader + bucket computer + UI section) удаляются в Phase 2.1.

После shipping:
- Один pipeline на лот (`analyze_listing` extended), одна таблица фич, один UI-туч-пойнт для настройки парсинга.
- Оператор видит на карточке полный паспорт лота: дефекты + price-signals (АКБ 87%, экран = aftermarket) + info (128 ГБ, чёрный, iPhone 12 Pro Max).
- Один и тот же model может иметь несколько парсингов с разными feature-rules — это уже архитектурно поддержано, теперь явно через UI (отдельный профиль = отдельный парсинг = отдельный набор правил).

## 2. Use case (мотивация унификации)

**Проблема, выявленная после shipping Phase 1 (2026-05-12):**

1. **Sidebar nav «🛠 Настройки модели» захардкожен на первый-созданный профиль** — для второго профиля (iPhone 13) нет UI-trigger'а к feature-rules. Семантически nav-пункт не должен быть глобальным: feature-rules — часть конфига конкретного парсинга, не глобальная «настройка пользователя».
2. **Две LLM-системы с пересечениями ≥5 ключей:** V2 (`icloud_locked`, `screen_broken`, `not_starting`, `modem_broken`, `biometric_broken`, `parts_only`, `frp_locked`, `account_blocked`) перекрывается с defect (`locks.icloud_linked`, `display.glass_broken` × 3, `operability.boot_loop` × 3, `sensors.sim`, `sensors.face_id` × 2). Оператор должен настраивать дубликаты в двух местах.
3. **V2 bucket вычисляется но не используется** (`profile_listings.bucket` пишется из defect compute_bucket). V2 LLM-grader работает «вхолостую» — расходует cost + время.
4. **info-only данные V2** (battery_health %, цвет, память) сейчас не отображаются на карточке — они кэшируются в `llm_analyses`, но UI их не читает.

Один и тот же model (например, iPhone 12 PM) может парситься под разные задачи: «для перепродажи» (строгие feature-rules, узкая alert-вилка) vs «для разбора на запчасти» (relaxed rules, дешёвая вилка). Это уже поддержано через несколько SearchProfile с одним model. После унификации UI делает эту возможность явной — feature-rules в форме каждого профиля, не глобально.

## 3. Non-goals

- **Phase 2.0/2.1 НЕ включают:**
  - **Retroactive re-parse отказов** — кнопка «↻ Перепарсить отказы за N дней по новым правилам» в форме профиля. Use case: парсинг переключился с «перепродажа» на «запчасти» и нужно достать релевантные лоты из отказов. Описано в §12 Future work, Phase 2.2 после соака Phase 2.1.
  - **Customizable taxonomy через UI** — оператор-редактор feature_definitions (key, kind, prompt, severity), migration yaml → БД таблица с versioning. Описано в §12, Phase 3+.
  - Templates / clone-rules между профилями. Если оператор делает «iPhone 11 для перепродажи» — копирует rules из «iPhone 12 PM» вручную. Автоматизацию (button «Скопировать правила из...») — Phase 2.2.
  - Severity-weighted bucket (defect-фичи имеют веса для scoring). Сейчас boolean ok/defect/unknown + rule green/red/ignore. Phase 2.3+.
  - **Price-signal фичи влияют на bucket / pricing.** Сейчас они отображаются на карточке, но не feed в auto-pricing / auto-negotiation. Pricing intelligence — Phase 3.
  - Defect-фичи с числовым порогом-параметром («отклонить лоты с АКБ < 80%»). Phase 3 — extension того же kind=defect + params в profile_feature_rules.
  - Multi-language UI. RU only, как сейчас.
  - Tab «Источники данных» / «Аналитика» / прочие будущие. Открываем 3 tabs (Поиск / Признаки / Уведомления), расширение — следующие итерации.

- **Удержание `condition_class` enum** (working/blocked_icloud/broken_screen/...) и `classify_condition` LLM-вызова — не трогаем, market-stats работает на нём.

## 4. Принятые решения (brainstorm 2026-05-12)

| # | Решение | Обоснование |
|---|---|---|
| Q1 | **Фазы B**: Phase 2.0 (stop-gap UI placement, ~3-4h) → 1-2 дня соак → Phase 2.1 (schema unification + V2 rip + info-фичи, ~8-12h) → 3-4 дня соак. | UI move изолированно проверяется без LLM-риска; schema change отдельно — riskier, нужен отдельный мониторинг. |
| Q2 | **Single extended table** (вариант A). Расширяем `listing_features` + `profile_feature_rules` через `kind` discriminator. База = defect-features. | Phase 1 infrastructure уже работает; минимум инвазии; один pipeline, один UI. |
| Q3 | **`sensors.face_id` + `sensors.touch_id` split** | Будущая поддержка Android-устройств / возврата Touch ID на iPhone (Apple rumors 2025+). Гранулярность позволяет per-profile решения. |
| Q4 | **Filter-kind не нужен.** `memory_gte` / `title_matches_model` — drop V2; их функция уже выполняется в Avito search URL (operator ставит memory_volume / model в фильтре URL). В системе оставляем только `info_api` projection (`memory_gb`, `vendor_model`). | URL-based search profile (ADR-001) — единственный источник истины для фильтрации поиска. Дублировать логику в системе не нужно. |
| Q5 | **Info-фичи показываются только на карточке лота**, не на странице feature-rules. Страница (= tab «Признаки») содержит только настраиваемые фичи с переключателями. | Info — read-only факты, не настройка. Засорять страницу rules ими — UX-шум. |
| Q6 | **Tabs в форме профиля** — 3 tabs: «Поиск» / «Признаки» / «Уведомления». Не отдельная sub-page, не accordion. | Feature-rules — часть конфига парсинга, а не глобальное меню. Tabs масштабируются под будущие настройки. |
| Q7 | **Rip V2 целиком** в одной Alembic-миграции — drop tables `criteria_templates`, `profile_criteria`, `llm_analyses`, `profile_listing_evaluations` + удалить V2 код. | V2 bucket уже dead code; V2 cache не читается ни одним UI-компонентом; mapping rules iPhone 12 PM не нужен (defect-rules там уже выставлены оператором). |
| Q8 | **`kind=price_signal` отдельно от `info_api`** — `battery_health` + `repaired_components` семантически отличаются от чистых атрибутов (память/цвет). Они влияют на оценку цены / торг. Сейчас behavior как у info (display only), но kind заранее отделён под Phase 3 pricing intelligence. `repaired_components` extract расширяется до `{component, quality, evidence}` (original / aftermarket / unknown). | Юзер указал: «это не инфо фича, это триггер для оценки цены». Отделение kind заранее избавляет от миграции в Phase 3. |

## 5. Таксономия (31 фича)

В `app/data/dialog_topics.yaml` taxonomy расширяется. Каждая запись получает поле `kind` (default = `defect` для обратной совместимости).

### 5.1 Defect (26 фич, kind=defect)

22 уже существующих (Phase 1 shipped) — без изменений:

| section | keys |
|---|---|
| display | replaced, glass_broken, touchscreen_glitch, stains_stripes |
| case | back_broken, midframe_bent, midframe_cracked |
| locks | icloud_linked, passcode_forgotten |
| sensors | face_id, truetone, wifi, sim, bluetooth, other |
| charging | not_charging, wireless_only, unstable |
| operability | boot_loop, reboots, no_boot, apple_loop |

**+4 новые** (миграция Phase 2.1):

| Новый ключ | Section | V2-источник | Title (UI) | Notes |
|---|---|---|---|---|
| `sensors.touch_id` | sensors | `biometric_broken` (split) | Не работает Touch ID | Для iPhone 8/SE и будущих Android. По умолчанию для iPhone 12+ профилей rule=ignore. |
| `locks.frp_locked` | locks | `frp_locked` | FRP / MDM-блокировка | Android-specific. Для iPhone профилей rule=ignore. |
| `locks.vendor_account` | locks | `account_blocked` | Заблокирован Mi/Samsung/Huawei аккаунтом | Не-iCloud, не-FRP. Для iPhone профилей rule=ignore. |
| `operability.parts_only` | operability | `parts_only` | Продаётся только на запчасти | Intent-based, не hardware. Парсер ищет explicit «не работает + на разбор» combination. |

### 5.2 Price-signal (2 фичи, kind=price_signal)

LLM-extract structured value. **В Phase 2.1 behavior идентичен info-фичам** — только отображаются на карточке для оператора, **не влияют ни на bucket, ни на автоматическую цену** (последней не существует). Оператор сам оценивает цену по своей аналитике, glance на блок «Цена / торг» помогает ему быстро прикинуть скидку.

**Зачем отдельный kind?** Чисто семантическая разметка под будущее. В Phase 3+ когда наберётся статистика наших продаж + интегрируется market data (см. §12.3), kind=price_signal feed'нет в auto-price scoring без миграции схемы. Если оставить эти фичи в `info_api` — Phase 3 потребует пересортировки записей в БД.

| Ключ | V2-источник | Title (UI) | Format value JSONB |
|---|---|---|---|
| `battery_health` | `battery_health` | АКБ | `{"percent": 87}` или `{"text": "новый АКБ"}` или `null` |
| `repaired_components` | `repaired_components` | Заменено | `{"items": [{"component": "screen", "quality": "original\|aftermarket\|unknown", "evidence": "цитата из описания"}]}` или `null` |

**`repaired_components` детальнее:** LLM должна не только перечислить заменённые компоненты, но и попытаться оценить **качество замены**:
- `original` — продавец явно говорит «оригинал», «service center», «Apple Genuine»
- `aftermarket` — продавец говорит «копия», «китайский аналог», «совместимый»
- `unknown` — упомянута замена, но качество не указано (default)

Это важно для будущего pricing: aftermarket-замена влияет на цену сильнее чем original.

### 5.3 Info-API (3 фичи, kind=info_api)

Direct read из `listing.parameters`, без LLM. Показывается на карточке.

| Ключ | V2-источник | Title (UI) | API path | Format value JSONB |
|---|---|---|---|---|
| `memory_gb` | `memory_gb` | Память | `Встроенная память` | `{"gb": 128}` или `null` |
| `color` | `color` | Цвет | `Цвет` | `{"text": "Чёрный"}` или `null` |
| `vendor_model` | `vendor_model` | Модель | `Производитель`, `Модель` (объединяется) | `{"text": "Apple iPhone 12 Pro Max"}` или `null` |

### 5.4 Yaml формат — расширение

```yaml
- key: sensors.touch_id
  kind: defect
  section: sensors
  title_ru: "Не работает Touch ID"
  severity_hint: red
  opener_phrasing: "не работает Touch ID"
  prompt_fragment: |
    Цель: определить состояние сканера отпечатка пальца (Touch ID).
    defect — продавец прямо упоминает неработающий Touch ID...
    ok — продавец прямо подтверждает работу Touch ID.
    unknown — Touch ID не упомянут, либо модель явно без Touch ID (iPhone X+).

- key: battery_health
  kind: price_signal
  title_ru: "АКБ"
  prompt_fragment: |
    Извлеки информацию об аккумуляторе. Если упомянут процент — верни {"percent": N}.
    Если состояние словесно ("новый", "родной", "слабый") — верни {"text": "..."}.
    Если ничего не сказано — верни null.

- key: repaired_components
  kind: price_signal
  title_ru: "Заменено"
  prompt_fragment: |
    Перечисли заменённые компоненты с оценкой качества.
    Для каждого компонента (экран, АКБ, корпус, разъём, динамик и т.п.) определи quality:
    - original: явно сказано «оригинал», «service center», «Apple Genuine»
    - aftermarket: «копия», «китайский аналог», «совместимый»
    - unknown: качество не указано
    Верни {"items": [{"component": "...", "quality": "...", "evidence": "..."}]} или null.

- key: memory_gb
  kind: info_api
  title_ru: "Память"
  api_path: "Встроенная память"
  parser: numeric_gb   # built-in parser: matches "128 ГБ" → 128
```

## 6. Data model

### 6.1 Schema changes

```sql
-- Alembic 0016_unified_criteria

-- 1) Extend listing_features
ALTER TABLE listing_features
  ADD COLUMN kind text NOT NULL DEFAULT 'defect',
  ADD COLUMN value jsonb NULL,
  ALTER COLUMN state DROP NOT NULL;  -- info_* типы не имеют state

-- 2) Drop V2 tables
DROP TABLE profile_listing_evaluations CASCADE;
DROP TABLE llm_analyses CASCADE;
DROP TABLE profile_criteria CASCADE;
DROP TABLE criteria_templates CASCADE;

-- 3) profile_feature_rules не трогаем — оно только для kind=defect.
--    Существующие rows на iPhone 12 PM остаются как есть.

-- 4) Constraint: для kind=defect — state NOT NULL; для price_signal / info_api — state может быть NULL.
--    Реализуется CHECK constraint:
ALTER TABLE listing_features
  ADD CONSTRAINT lf_kind_shape_chk CHECK (
    (kind = 'defect' AND state IS NOT NULL) OR
    (kind IN ('price_signal', 'info_api'))
  );
```

### 6.2 Migration data

- Все существующие `listing_features` rows автоматически получают `kind='defect'` (default).
- `profile_feature_rules` rows не трогаются — это были только defect-rules.
- V2 кэш (`llm_analyses`) удаляется вместе с таблицей — он не используется.
- iPhone 13 profile_feature_rules: после миграции на форме появятся 4 новые фичи с rule=ignore по умолчанию (как и для всех остальных профилей).

### 6.3 Pipeline (analyze_listing extended)

```
analyze_listing(listing_id):
  classify_condition(listing)                     # existing, для market-stats
  ↓
  parse_defect_features(listing, active_keys):    # existing, +4 новые defect-фичи
    - match_avito_parameters(iCloud, passcode)    # short-circuit
    - asyncio.gather over 6 sections              # +touch_id в sensors,
                                                  #  +frp_locked / vendor_account в locks,
                                                  #  +parts_only в operability
    → upsert listing_features kind=defect
  ↓
  extract_price_signal_features(listing):          # NEW
    - one batched LLM call для battery_health + repaired_components
    - structured output: {"battery_health": {...}, "repaired_components": {...}}
    → upsert listing_features kind=price_signal
  ↓
  read_info_api_features(listing):                 # NEW
    - pure Python: read listing.parameters['Встроенная память'] → numeric_gb → {"gb": 128}
    - read 'Цвет' → {"text": "Чёрный"}
    - read 'Производитель' + 'Модель' → {"text": "Apple iPhone 12 Pro Max"}
    → upsert listing_features kind=info_api
  ↓
  compute_bucket(features, rules):                # existing, filter only kind=defect
    → only kind=defect фичи влияют; price_signal / info_api игнорируются для bucket
  ↓
  write pl.bucket, auto-reject если bucket=red
```

**Cost impact:** +1 LLM call (price_signal batched) ≈ $0.0001/лот. Total ≈ $0.0007/лот.

**Error handling:** price_signal LLM fail → value=null для обеих фич, не блокирует pipeline. info_api fail (нет ключа в parameters) → value=null. defect parse fail — как раньше (safe fallback state='unknown' для секции).

## 7. UI changes

### 7.1 Phase 2.0 (stop-gap, ~3-4h)

**Удалить:**
- Sidebar nav пункт «🛠 Настройки модели» (был захардкожен на первый-созданный профиль).

**Добавить:**
- В шаблон `templates/search_profiles/edit.html` (или эквивалент) — компонент tabs:
  - Tab 1 **«Поиск»** — текущие поля формы (URL, регион, search/alert вилки, sort, delivery, расписание).
  - Tab 2 **«Признаки»** — встроенная страница `/profiles/{id}/feature-rules` (как iframe или inline-render текущей таблицы 26 фич).
  - Tab 3 **«Уведомления»** — текущие поля Telegram-settings (если они в форме; иначе плейсхолдер «настройки переедут сюда» под Phase 2.1+).
- Active tab сохраняется в `localStorage.profile_edit_active_tab` для UX (вернулся на форму — попадаешь на тот же tab).
- URL поддерживает `?tab=features` — глубокий линк, для редиректов из других страниц / уведомлений.

**Решение «iframe vs inline»:** inline render предпочтительнее (один HTTP-request, один TemplateResponse). Если страница `/profiles/{id}/feature-rules` сейчас self-contained — выделить partial template и подключить в tab. Если она зависит от внешнего layout — рефакторить partial в Phase 2.0 (тот же сессион).

### 7.2 Phase 2.1 — карточка лота

Расширенный блок на каждой карточке (kanban + listings) — **под текущим блоком «Признаки»** добавляются два новых блока: **«Цена / торг»** (price_signal фичи) и **«Параметры»** (info_api фичи).

Mockup структуры (text):

```
┌──────────────────────────────────────────────┐
│ Заголовок лота + цена + thumbnail            │
│ ────────────────────────────────────────────│
│ Признаки:                                    │
│   display: ✓✓⊘⚪                             │
│   locks:   ✓✓                                │
│   ...                                        │
│ ────────────────────────────────────────────│
│ Цена / торг:                                 │  ← NEW (price_signal)
│   🔋 АКБ 87%                                  │  ← battery_health
│   🔧 Заменено: экран (aftermarket), АКБ      │  ← repaired_components с quality
│ ────────────────────────────────────────────│
│ Параметры:                                   │  ← NEW (info_api)
│   📱 Apple iPhone 12 Pro Max                 │  ← vendor_model
│   💾 128 ГБ        🎨 Чёрный                 │  ← memory_gb, color
└──────────────────────────────────────────────┘
```

Если value = null — строка не рендерится (gracefully degrade). Если все строки в блоке = null — блок целиком скрывается. Quality badge `aftermarket` рендерится оранжевым (визуальный сигнал для торга); `original` — зелёным; `unknown` — серым.

## 8. Phasing & ship plan

### Phase 2.0 (UI only, ~3-4h)

1. Удалить sidebar nav пункт «🛠 Настройки модели» из layout template.
2. Реализовать tabs-компонент в форме `/search-profiles/{id}/edit`:
   - Vanilla JS (без новых dependencies), радио-buttons или role="tab" semantics.
   - localStorage.profile_edit_active_tab.
   - URL `?tab=features` deep-link.
3. Встроить текущую страницу `/profiles/{id}/feature-rules` в tab «Признаки» (extract partial, render inline).
4. Smoke test: создать iPhone 13 профиль → перейти в edit → tab «Признаки» → выставить 1-2 rules → проверить что upsert работает.

**Ship → 1-2 дня соак.** Метрики: оператор может ли настроить rules на iPhone 13 без захода в DB / без знания URL? Если да — Phase 2.0 done.

### Phase 2.1 (schema + V2 rip + price-signal/info-фичи, ~8-12h)

1. **Alembic migration 0016_unified_criteria** — schema changes (`kind`, `value`, drop V2 tables, CHECK constraint).
2. **Yaml extension** — добавить 4 defect + 2 price_signal + 3 info_api записи в `dialog_topics.yaml`. Каждая с `kind` полем.
3. **Pipeline extension:**
   - `parse_defect_features` — расширить section parsers (sensors: +touch_id, locks: +frp_locked / +vendor_account, operability: +parts_only).
   - `extract_price_signal_features` — новый модуль, один batched LLM-call для battery_health + repaired_components (structured output с quality detection).
   - `read_info_api_features` — новый модуль, pure Python из listing.parameters.
   - Embed в `analyze_listing` в правильном порядке.
4. **V2 code rip:**
   - Удалить V2 grader (`app/services/v2_criteria/...` или эквивалент).
   - Удалить V2 bucket computer.
   - Удалить V2 UI section в форме профиля.
   - Удалить V2 yaml-seed (`criteria_templates.yaml`) и его loader.
5. **UI карточки** — добавить блоки «Цена / торг» и «Параметры» в card-template (kanban + listings expanded body). Условные render для null values; quality-badges для repaired_components.
6. **Backfill script extension** — `scripts.backfill_features` принимает `--include-non-defect` (или просто всегда обрабатывает все kinds). One-shot запуск на 120 лотов iPhone 12 PM.
7. **Tests:**
   - Unit: `extract_price_signal_features` — mock LLM, проверить parsing форматов (percent / text / items со всеми quality values).
   - Unit: `read_info_api_features` — для каждого info_api ключа, edge cases (отсутствие ключа, мусорный формат).
   - Integration: full `analyze_listing` flow, проверить что non-defect фичи появляются в `listing_features` с правильным kind.
   - Migration: alembic upgrade + downgrade на тестовой БД.

**Ship → 3-4 дня соак.** Метрики:
- Recall price_signal parser — на 30-50 лотах вручную проверить: правильно ли извлекается battery_health %? Правильно ли quality detection (original vs aftermarket) для repaired_components?
- Bucket stability — после миграции `compute_bucket` должен дать те же результаты что и до (price_signal / info_api не должны влиять). Diff before/after на iPhone 12 PM = 0 bucket changes.
- LLM cost — +$0.05/день максимум.
- UI — карточки рендерятся без layout-jank при отсутствии не-defect полей.

## 9. Что НЕ работает / risks

- **V2 rip — irreversible.** llm_analyses cache уничтожается. Если price_signal parser окажется сломанным — придётся backfill'ить с нуля. **Mitigation:** Phase 2.1 ship отдельно после Phase 2.0 соака; staging environment перед prod миграцией (если есть); pg_dump перед миграцией.
- **iPhone 12 PM rules могут потерять смысл.** Если оператор настраивал V2 `biometric_broken=red`, а defect `sensors.face_id=ignore` (Phase 1 default) — после миграции лот с разбитой биометрией перестанет авто-реджектиться. **Mitigation:** перед миграцией показать оператору V2 rules + предложить mapping в defect terms. Скрипт `scripts.migrate_v2_to_defect_rules --dry-run`. Решим в плане implementation.
- **`vendor_model` info_api — может быть None** для некоторых лотов (если Avito не отдал параметр). Фallback: null → не показывается на карточке (acceptable).
- **`battery_health` price_signal — может extract'ить мусор** ("АКБ как новый" → text вместо percent). Acceptable — value JSONB структурирован, UI render conditional (percent vs text branch).
- **`repaired_components` quality detection — нестабильна.** Продавцы часто пишут «менял экран в сервисе» без явного указания original/aftermarket. LLM будет default'ить на `unknown` в этом случае — это ожидаемо, не баг. **Acceptable:** unknown — валидное состояние; в Phase 3 pricing будет penalty для unknown как для aftermarket (хуже original).
- **CHECK constraint на listing_features** должен быть transactional с data migration. Если в момент миграции есть partial state — может failed. **Mitigation:** миграция в одной транзакции, добавление constraint AFTER data backfill.
- **3-tabs UI — overlap с защитой от двойного клика.** Если активный tab меняется быстро во время PATCH запроса rule — может быть UX hiccup. **Mitigation:** disabled-guard уже есть в Phase 1 кода.

## 10. Связанное

- [`2026-05-12-defect-checklist-design.md`](./2026-05-12-defect-checklist-design.md) — Phase 1 база.
- [`2026-05-11-seller-dialog-phase-b-design.md`](./2026-05-11-seller-dialog-phase-b-design.md) — Phase B seller-dialog.
- ADR-001 (URL-based search profiles) — обоснование почему `memory_gte` / `title_matches_model` уходят в Avito URL.
- ADR-010 (двухступенчатый LLM) — `classify_condition` остаётся, defect parser работает поверх.

## 11. Открытые вопросы (для writing-plans)

1. **Mapping V2 rules → defect-rules** — стратегия. Manual review оператором перед миграцией или авто-mapping table в скрипте? (Q7 решил «rip целиком», но iPhone 12 PM V2 settings могут содержать смысловую информацию.)
2. **Tabs реализация** — vanilla JS / Alpine / HTMX. Текущий стек HTMX-based; вероятно простой `_active_tab` state + 3 partial includes. Решим в плане.
3. **`extract_price_signal_features` промпт** — один большой промпт на обе фичи (battery + repaired со structured output), или отдельные с asyncio.gather? Cost vs latency vs точность quality-detection.
4. **Карточка mockup** — финальная вёрстка «Цена/торг» и «Параметры» секций (иконки, layout, mobile-responsive, quality-badges цвета). Низко-приоритетно для плана, средне-приоритетно для implementation.
5. **price_signal в backfill** — при first run на 120 лотов iPhone 12 PM ожидаемая стоимость ~$0.1 (один extract на лот). Параллелить через `asyncio.gather` с rate-limit?

## 12. Future work (Phase 2.2+ и Phase 3)

### 12.1 Phase 2.2 — Retroactive re-parse rejected (~2-4h, после соака Phase 2.1)

**Мотивация:** парсинг переключился с «перепродажа» на «запчасти» — оператор поменял rules, но старые лоты уже в отказах (`user_action='rejected'`, `rejected_reason='auto:...'`). Нужна возможность пересмотреть отказы по новым правилам и вернуть подходящие в работу.

**UI:** в форме профиля под tab «Признаки» — кнопка «↻ Перепарсить отказы за N дней» (выбор N: 1 / 3 / 7 / 30 / все).

**Worker job:**
```
для каждого rejected listing в SELECT WHERE
  pl.profile_id = ? AND pl.user_action='rejected'
  AND pl.rejected_reason LIKE 'auto:%'   -- manual:* blacklist не трогаем
  AND pl.rejected_at > now() - N days:

  1) Refresh listing status from Avito API (xapi /items/{id})
     — если status in (sold, reserved, removed, blocked) → skip + mark listings.last_seen
  2) Re-run parse_defect_features с текущим active_keys (rule != ignore)
  3) Re-run compute_bucket(features, rules)
  4) Если new_bucket != red → pl.user_action='pending', pl.bucket=new_bucket, очистить rejected_reason
  5) Если new_bucket == red → no-op (остается в отказах, но с обновлёнными features)
```

**Constraints:**
- LLM cost: ~$0.0007 × N лотов. На 1000 отказов ~$0.7 — отдельно сообщаем оператору в confirmation modal перед запуском.
- Avito API rate-limit: 1 refresh request per listing through xapi SOCKS5 tunnel. На 1000 лотов ~10-15 мин при текущих лимитах.
- Idempotency: повторный запуск с теми же rules → no-op (features re-parsed одинаково).
- Job status: writable progress в UI (HTMX-poll `/profiles/{id}/reparse-status`).

**Edge cases:**
- Лот sold/reserved/removed — НЕ re-parse, но обновить `listings.status` и `listings.last_seen` (иначе будет sold лот висеть как rejected пустой).
- Лот удалён с Avito (404) — `listings.status='deleted'`, `pl.user_action` не меняем.
- Конфликт с активным polling-проходом — re-parse job lock'ит profile_id, polling ждёт.

### 12.2 Phase 3 — Customizable taxonomy через UI (~12-20h)

**Мотивация:** сейчас 31 ключ hardcoded в `dialog_topics.yaml`. Оператор хочет добавлять собственные defect-фичи (например, «царапины на экране ≥ N штук» как separate defect), редактировать prompt fragments (улучшать LLM accuracy на своих данных), переклассифицировать существующие фичи (perевести `display.replaced` из defect в price_signal).

**Объём:**
- **Schema migration:** yaml → таблица `feature_definitions` (id, key, kind, section, title_ru, prompt_fragment, severity_hint, version, is_deleted, created_at).
- **FK constraints:** `listing_features.feature_key` + `profile_feature_rules.feature_key` → references `feature_definitions.key`. Versioning: `listing_features` хранит `feature_version` (на каком версии prompt'а парсилась) → invalidation при bump.
- **UI редактор:** глобальное меню «Настройки детектирования». Список фич, кнопки добавить/edit/delete, preview prompt, test на sample-листинге. Publish flow: bump version → invalidate stale `listing_features` → backfill prompt'ом нового версии.
- **Safety:** оператор может сломать prompt и парсер начнёт галлюцинировать. Mitigation — required test-on-sample перед publish, dry-run mode, rollback к предыдущей версии.
- **Code rewrite:** parse_defect_features загружает taxonomy из БД вместо yaml. Кэш в memory с TTL / pubsub-invalidation.

**Зависимости от Phase 2.0/2.1:** none (Phase 3 переключает SOURCE OF TRUTH, но не data model). Можно стартовать независимо после Phase 2.1 ships.

### 12.3 Phase 3+ — Pricing intelligence (~20-30h, blocked на сборе данных)

**Мотивация:** оператор хочет полуавтоматическое / автоматическое назначение цены на оффер при готовности купить лот (или на торге с продавцом «дай N% off, и заберу»). `kind=price_signal` фичи сейчас собираются, но без рыночных данных они только подсказки оператору. Для auto-pricing нужны 3 дополнительных источника:

**Требуемые data sources (предварительные требования):**

1. **Историческая статистика наших продаж** — что мы сами купили и продали (нет своего marketplace fulfillment в V1, но есть лог покупок в системе). Нужна таблица `our_deals` (listing_id, bought_price, sold_price, sold_at, condition_at_sale, repaired_components). На текущем потоке оператор должен начать заносить продажи (либо UI «зафиксировать продажу за N₽», либо integration с Avito autoload V2).
2. **Market min / avg по России** — текущие активные лоты по тому же model + condition. Можно derive из существующего `profile_market_stats` (ADR-008 двойная вилка уже собирает медиану рыночной цены) — но нужно агрегировать кросс-профильно (модель → cohort).
3. **Market price в регионе оператора** — те же лоты с region-filter. Сейчас polling region-specific (один профиль = один region_slug), но для авто-цены нужен кросс-regional aggregator.
4. **Recovery economics** — для каждой defect-фичи (или комбинации) на каждой модели:
   - **Цена запчастей** — справочник `parts_catalog (model, component, source, price_min, price_avg, price_max)`. Источники: AliExpress, российские поставщики (zip-mobile, parts-shop), used-parts с того же Avito. Нужна периодическая синхронизация.
   - **Стоимость работ по восстановлению** — `repair_labor (component, complexity, cost)`. Зависит от оператора (своими руками = self-cost, или outsource в сервис = market rate).
   - **Вероятность успешного восстановления** — `repair_success_rate (model, component, defect_state) → float [0..1]`. Заполняется на основе истории попыток. Стартовые значения hand-tuned (icloud_locked = 0, glass_broken = 0.95, no_boot = 0.4 etc).
   - **«As-is» price** — цена продажи нерабочего/частично-рабочего лота как donor/parts. Для каждой модели + critical-defect combo (например, iPhone 12 PM не-включается → as-is ~3000-5000 ₽).

**Pricing model (когда data sources готовы):**

Recovery-economics формула вместо простой регрессии:

```
expected_value = max(
  as_is_price - cost_of_listing,                    # просто перепродать как есть
  (sold_clean_price - parts_cost - labor_cost) * P_repair_success
    + as_is_price * (1 - P_repair_success)          # рискнуть и восстанавливать
)
recommended_buy_price = expected_value - target_margin
```

Где `P_repair_success` derived из repair_success_rate на основе defect-features этого лота.

- UI на карточке: «🎯 Рекомендую купить за: 11500 ₽ (восстановить → 14000 ₽, P=0.8, expected 12700)».
- Auto-offer в seller_dialog (Phase D): tight интеграция с seller-dialog Phase D `price_negotiation` stage.
- Confidence threshold: если data sources thin (новая модель, мало истории) — auto-pricing disabled, fallback на оператора.

**Зависимости:**
- Phase 2.1 ships (kind=price_signal в БД) — без этого данные не накапливаются. **Blocker = время:** нужно 3-6 месяцев соака чтобы накопить достаточно лотов с battery_health / repaired_components для тренировки модели.
- Sales tracking (наши продажи) — отдельная feature, V2 ish.
- Cross-profile market aggregator — отдельная feature, требует pgquery + cohort logic.
- **Parts catalog** — отдельная feature с периодическим скрапером + UI редактор справочника. Может быть hand-bootstrapped стартово (топ-20 ходовых запчастей iPhone).
- **Repair labor + success_rate** — самые сложные: оператор должен начать вести лог попыток (что чинил, успешно ли, во сколько встало). UI «зафиксировать ремонт» в lifecycle лота. Без этого pricing model для defect-лотов — guesstimate, не data-driven.

**Non-goals Phase 3 pricing:**
- Полностью автоматическое closing сделки. Оператор всегда последний approve.
- Real-time price war с конкурентами. Это другая лига.

---

**Готово к writing-plans.** Phase 2.0 и Phase 2.1 имеют разные риск-профили и тестовые требования — рекомендуется **отдельный план на каждую фазу**. Phase 2.2, Phase 3 (taxonomy), Phase 3+ (pricing) — отдельные spec'и + планы (формат «1 spec на feature»).
