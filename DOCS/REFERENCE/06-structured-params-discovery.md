# Structured Params Discovery — как найти числовые ID для precise search

**Создано:** 2026-05-07
**Обновлено:** 2026-05-08 — после полного APK reverse engineering v222.5 добавлены §5-§7
**Обновлено:** 2026-05-08 (вечер) — **live testing endpoints** добавлен §6.5 с empirical findings (POST! не GET!)
**Назначение:** методология добычи параметр-ID и значений Avito mobile API, чтобы строить точные `params[brand_id][0]=brand_value&params[model_id][0]=model_value&...` запросы вместо fuzzy text + post-filter.

**Связано:**
- `05-search-query-formation.md` — TL;DR проблемы, 3 пути решения, эмпирика QRATOR
- `01-avito-api.md` §B.1 — описание endpoint'а `/api/11/items`
- `07-retrofit-api-classes.md` — Retrofit Api interfaces (включая candidate'ов для catalog endpoint)
- `08-data-models.md` — `DictionaryEntity`, `SelectParameter`, `ParametersTree`
- `09-deeplinks-and-screens.md` — Beduin server-driven UI (alternative path)
- `DOCS/avito_api_snapshots/autosearches/README.md` — реверс `/2/subscriptions/{id}` с примером deeplink

---

## 1. Что нам известно (известные ID)

Источник: парсинг одного реального subscription deeplink (`/2/subscriptions/{filterId}.deepLink`) на 2026-04-28:

```
ru.avito://1/items/search
  ?categoryId=84            ← mobile id «Мобильные телефоны»
  &geoCoords=55.755814,37.617635
  &locationId=621540        ← вся Россия
  &params[110617][0]=491590 ← brand  : 110617=Производитель, 491590=Apple
  &params[110618][0]=469735 ← model  : 110618=Модель, 469735=iPhone 12 Pro Max
  &params[110680]=458500    ← состояние/пробег (TBD)
  &priceMax=13500
  &priceMin=11000
  &sort=date
  &withDeliveryOnly=1
```

| Семантика | param_id | пример value | покрытие |
|---|---|---|---|
| Категория top-level | (categoryId, не в params[]) | 84 = Мобильные телефоны | mobile id; web URL использует другие |
| Производитель (brand) | `110617` | 491590 = Apple | только phones-категория? |
| Модель | `110618` | 469735 = iPhone 12 Pro Max | только phones, и под конкретный brand |
| Состояние/пробег | `110680` | 458500 (TBD значение) | только phones? |
| Регион | `locationId` (top-level) | 621540 = вся Россия, 637640 = Москва | глобальное |
| GeoCoords | `geoCoords` (top-level) | "lat,lng" | глобальное |
| Цена min/max | `priceMin`/`priceMax` (top-level) | int rubles | глобальное |
| Доставка | `withDeliveryOnly` (top-level) | 1/0 | глобальное |
| Sort | `sort` (top-level) | `date`, `price_asc`, `price_desc` | глобальное |

Все эти значения мы получили из ОДНОГО subscription. Чтобы поддерживать произвольную модель/категорию, нужны полные mapping-таблицы.

---

## 2. Что мы НЕ знаем

### По phones-категории (84):

- **Все brand_id** (для не-Apple). `phone_catalog.xml` (`DOCS/avito_api_snapshots/`) содержит 524 текстовых названия брендов, **без числовых ID**.
- **Все model_id** для каждого brand. Тот же файл — 16'149 моделей, only names.
- **Param 110680 ("Состояние/пробег")** — какие values: «новое»/«б/у»/«на запчасти»/etc. ID не известны.
- **Объём памяти** (Memory: 64/128/256/512/1ТБ) — param_id не известен.
- **Цвет** — param_id не известен.
- **eSIM/SIM** — param_id не известен.
- **Состояние батареи** (новый Avito-параметр, на iPhone 12+ показывается) — param_id не известен.

### По другим категориям (НЕ phones):

- Auto, недвижимость, одежда, бытовая техника, и т.д. — **полностью** свои таксономии.
- Имеем только slug-and-name'ы из categories_tree.json.

### Универсально-неизвестное:

- Полный mapping категорий: web `category_id` ↔ mobile `categoryId`. Известно: phones=84 (mobile)/87 (web). Остальные категории — TBD. Возможны конфликты.

---

## 3. Четыре подхода добычи (в порядке предпочтения)

### A. Subscription deeplink mining (рекомендуется как primary) ★

**Идея:** массовый импорт subscription'ов из Avito-app разных юзеров → парсинг `/2/subscriptions/{filterId}.deepLink` → extraction всех `params[X][Y]=Z` пар → накопление mapping table в БД.

**План:**
1. Юзер сохраняет в Avito-app autosearch'и под РАЗНЫЕ модели/категории/фильтры (например, 5 моделей iPhone, 5 моделей Samsung, авто Toyota Camry, квартиры в СПб).
2. Наш `autosearch_sync` импортирует их и сохраняет `deepLink` в `search_profiles.avito_search_url_deeplink` (новое поле).
3. Скрипт-discovery'ор iterate'ит все deeplink'и, парсит `params[X][Y]=Z`, складывает в новую таблицу:
   ```
   CREATE TABLE avito_param_catalog (
     category_id  INT NOT NULL,    -- 84 для phones
     param_id     INT NOT NULL,    -- 110617 для brand
     param_value  INT NOT NULL,    -- 491590 для Apple
     human_name   TEXT,            -- "Apple", "iPhone 12 Pro Max"
     param_kind   TEXT,            -- "brand", "model", "memory" (заполняется руками)
     first_seen   TIMESTAMPTZ,
     PRIMARY KEY (category_id, param_id, param_value)
   );
   ```
4. Human-name берётся из `subscription.title` или `subscription.description` (parse-able в большинстве случаев).
5. Через 20-50 разных subscription'ов накопится 80% покрытия популярных категорий.

**Цена:** ~3-5ч кодинга. Главная нагрузка — **юзер должен сохранить много autosearch'ей** в Avito-app. На каждую новую категорию = 1 новый autosearch минимум.

**Плюсы:**
- 100% корректные ID (взяты из самого Avito)
- Auto-update: новые subscription'и → новые param values без правки кода
- Покрывает любые категории, не только phones

**Минусы:**
- Покрытие зависит от того, какие фильтры юзер уже использовал
- Не получим ID до первого юзера-сохранения
- Не получим human-friendly metadata (param_kind типа "brand") автоматически — нужна heuristic или ручная разметка

---

### B. Catalog endpoint discovery (опциональный — если найдётся)

**Идея:** Avito mobile API может иметь endpoint типа `GET /api/N/categories/{id}/parameters` который возвращает список доступных фильтров с ID и values. Если такой endpoint есть — мы вытащим всё одним запросом на категорию.

**План:**
1. jadx разбор APK: ищем строки `categories`, `parameters`, `attributes`, `filters` в Retrofit-аннотациях (см. `04-reverse-engineering-howto.md`).
2. Тестим candidates через наш xapi с свежим JWT.
3. Если найдётся — пишем discovery-скрипт который iterate'ит по всем известным `categoryId` и сохраняет всё в `avito_param_catalog`.

**Цена:** 2-4ч. Главное препятствие — не факт что endpoint существует и доступен моб-юзеру.

**Что попробовать первым делом:**
- `GET /api/3/items/category/{categoryId}/filters`
- `GET /api/2/categories/{categoryId}/parameters`
- `GET /web/1/category/{categoryId}/filters` (web endpoint, может работать с mobile JWT)
- Поиск по `category_filter` или `attribute` строкам в DEX

**Плюсы:** одноразовое полное покрытие, не нужны subscription'и.

**Минусы:** может не существовать; даже если есть — может требовать особой авторизации (web JWT, не mobile).

---

### C. mitm capture при использовании фильтров в Avito-app

**Идея:** на phone'е с root + Magisk → mitmproxy с trusted CA. Юзер открывает Avito-app, идёт «Поиск → Мобильные телефоны → Фильтры», тапает каждый фильтр (бренд, модель, память, цвет, состояние) → mitm перехватывает запросы (вероятно `/3/items/category/84/filter-options` или подобное) с full filter metadata в response. Парсим и складываем.

**План:**
1. mitmproxy на phone'е (`DOCS/REFERENCE/04-reverse-engineering-howto.md` §mitm).
2. Запись session'а юзера, проходящего по фильтрам phone-категории + 2-3 других категорий.
3. Парсинг всех ответов, сохранение в `avito_param_catalog`.

**Цена:** 4-8ч (если mitm setup всё ещё рабочий).

**Плюсы:** видим РЕАЛЬНЫЕ запросы Avito-app — можем заодно reverse-инжинирить любые недокументированные эндпоинты.

**Минусы:** SSL-pinning Avito-app блокирует mitm без bypass-патча; phone'у нужен root (есть); требует ручного UI walkthrough; capture'ы могут устаревать при обновлении Avito-app.

---

### D. Reverse APK (jadx) — search-resource definitions

**Идея:** в DEX Avito-app есть filter resource files: либо string resources, либо JSON в assets, либо protobuf со списками categories/params/values. Распаковка APK + grep/jadx находит таблицы.

**План:**
1. `apktool d base.apk` или `unzip base.apk` → `assets/`, `res/raw/`, проверить на JSON/proto/binary list-файлы.
2. jadx обход: классы вокруг `FilterParameter`, `CategoryAttribute`, `ItemFilterValue`.
3. Если найдётся — extraction в csv/json для сидинга `avito_param_catalog`.

**Цена:** 8-15ч. Хрупко: каждое обновление APK ломает.

**Когда брать:** только если A/B/C не работают.

---

## 4. Рекомендуемая архитектура

### 4.1 Таблица `avito_param_catalog`

```sql
CREATE TABLE avito_param_catalog (
  id              SERIAL PRIMARY KEY,
  category_id     INTEGER NOT NULL,         -- mobile categoryId (84 = phones)
  param_id        INTEGER NOT NULL,         -- e.g. 110617
  param_value     INTEGER NOT NULL,         -- e.g. 491590 (= Apple)
  human_name      TEXT,                     -- "Apple"
  param_kind      TEXT,                     -- "brand" | "model" | "memory" | "color" | "condition" | "esim" | NULL
  parent_param_id INTEGER,                  -- для модели → ID brand-param
  parent_value    INTEGER,                  -- для модели → value brand'а (Apple)
  first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source          TEXT NOT NULL,            -- "subscription" | "catalog_api" | "mitm" | "jadx" | "manual"
  source_ref      TEXT,                     -- subscription_id, mitm-session-id, etc.
  UNIQUE (category_id, param_id, param_value)
);
CREATE INDEX idx_param_catalog_lookup ON avito_param_catalog (category_id, param_kind, human_name);
```

### 4.2 Auto-population из subscriptions

В `autosearch_sync.py` после успешного `get_subscription_deeplink(filter_id)` делать `_extract_params_to_catalog(deeplink, subscription_title)`:

```python
def _extract_params_to_catalog(deeplink: str, title: str, source_id: str) -> list[CatalogEntry]:
    # parse_qs deeplink, для каждого params[X][Y]=Z extract
    # human_name пытаемся из title (для brand/model часто работает re.match)
    ...
```

### 4.3 Lookup в URL parser

Когда юзер вставляет web URL и мы парсим brand+model текстом, делаем `SELECT param_value FROM avito_param_catalog WHERE category_id=84 AND param_kind='brand' AND lower(human_name)=lower(parsed_brand)`. Если найдено → добавляем в `params_extra` для search_items. Если нет → fallback на fuzzy text + post-filter.

### 4.4 Фоновый discovery worker (V2)

Раз в неделю iterate'ить по всем `subscription.deepLink` всех юзеров → upsert в `avito_param_catalog`. Покрытие растёт автоматически.

---

## 5. Сейчас (без structured params)

Пока не реализовано discovery — продолжаем работать через fuzzy:

1. xapi search.py шлёт **только** `query=<brand+model text>` + `priceMin/priceMax/sort` → Avito 200 + `~12'000` результатов.
2. polling.py post-filter режет по word-boundary `\w+` tokens из `parsed_brand` + `parsed_model` (фикс 2026-05-07).
3. Получается ~10-30 настоящих лотов/прогон. iPhone 14 не пролезает в выдачу iPhone 12 (и наоборот).

Этот режим достаточен для V1 monitoring. Discovery нужен когда (а) расширим на другие категории кроме phones, (б) появится много моделей с пересекающимися названиями (Samsung S20 vs S20+), (в) хотим вырезать лоты со «неправильной памятью / состоянием» уже на стороне Avito.

---

## 6. Action items для следующей сессии

1. **Phase 1 (~30 мин):** написать `_extract_params_to_catalog()` + миграция `avito_param_catalog` + интеграция в `autosearch_sync.py`. Без UI и lookup'а — просто начать копить данные.
2. **Phase 2 (~1ч):** юзер сохраняет в Avito-app 5-10 разных autosearch'ей (Apple iPhone {11, 12 Pro Max, 13, 14}, Samsung S22, Xiaomi 12), `autosearch_sync` импортирует, проверяем что catalog заполнился разумным набором brand/model.
3. **Phase 3 (~1ч):** `_category_id_for(parsed)` + URL parser → пробует найти brand+model в catalog → добавляет structured params в `params_extra`. Profile с известным brand/model получает precise результаты как Avito-app.
4. **Phase 4 (~30 мин):** вычистить из listings table fuzzy-pollution от прошлых прогонов (те же iPhone 14 в выдаче iPhone 12 от word-boundary-fix-pre).
5. **Опционально (Phase B catalog API discovery, ~2-4ч):** jadx грэп + curl-test candidate endpoints. Если найдётся `/api/N/categories/{id}/parameters` или подобное — bulk import.

Estimate Phase 1-3: **~3ч кодинга** для базового pipeline. Дальше — рост покрытия от пользователя.

---

## 5. APK v222.5 Reverse — Findings (2026-05-07/08)

После полного reverse engineering Avito Android APK v222.5 (359 МБ, classes*.dex, 18320 файлов unpacked) — на основании 8 discovery passes + cross-validation — собрана полная картина:

### 5.1 Что подтверждено

- ✅ URL endpoints `15/dicts/parameters`, `16/dicts/parameters`, `2/dicts/parameters/filter`, `1/dicts/navigation` — **существуют как DEX strings** (classes3, 11, 18). Проверено cross-validation 40/43 endpoints PASS.
- ✅ Data classes verified — `DictionaryEntity`, `CategoryParameters`, `SelectParameter` (10 inner forms), `ParametersTree`, `SimpleParametersTree`, `SearchParams` (33 fields) — все 18/18 PASS.
- ✅ `SubscriptionListMobileApi` data class **точно совпадает** с `DOCS/avito_api_snapshots/autosearches/README.md` (поля `deepLink`, `id`=filterId, `ssid`, `title`, `hasNewItems`, `pushFrequency`, `editAction`, `openAction`, `description`, `sendEmail`).
- ✅ `NewCarsMarkModelFilterApi` confirmed — методы `apiNewCarsFilterBrands()`, `apiNewCarsFilterModels(brandIds)`, `apiNewCarsFilterApply(brands, models)`. **Это blueprint для phone-equivalent catalog endpoint.**
- ✅ Brand+model IDs (491590, 469735, 110617, 110618, 110680) **0 hits в DEX** — fully server-side (не hardcoded в APK).

### 5.2 Что НЕ найдено в auto-generated Api classes

**`15/dicts/parameters` declaring class — TBD.** В 263 auto-generated Avito Api classes (полный dump в `Reverse Avito/findings/raw/all_api_methods.txt`) метода `apiDictsParameters` / `getDictsParameters` / `dictsParameters` нет.

**Hypothesis:**
1. Endpoint declared в **manual/legacy** Retrofit interface (Avito имеет obfuscated annotation prefix `@Mg1.f("URL")` — см. `04-reverse-engineering-howto.md`)
2. ИЛИ endpoint **deprecated** в v222.5 (string survives в R8 build, но больше не вызывается)
3. ИЛИ filter taxonomy теперь serves through **Beduin server-driven UI** (`ru.avito://1/beduin/v2/universalPage`) — см. `09-deeplinks-and-screens.md`

### 5.3 Top-5 candidate endpoints (ranked by confidence)

| # | Endpoint | Retrofit method | Confidence | Notes |
|---|---|---|---|---|
| 1 | `GET /api/1/serp/pro/filters/init` | `UserAdvertsApi.proFiltersInitV1(String, String)` | ⭐⭐⭐ HIGH | Verified Retrofit method ✓. Two String args likely `(categoryId, contextOrToken)`. Risk: может требовать Pro-account. |
| 2 | `GET /api/1/items/profile/search/inline-filters` | unknown (likely в legacy interface) | ⭐⭐ MEDIUM | URL ✓, naming directly matches "inline filters". Risk: "profile/search" prefix может ограничить use case. |
| 3 | `GET /api/15/dicts/parameters?categoryId=84` | unknown (TBD) | ⭐⭐ MEDIUM | URL ✓, likely takes `categoryId` query. Возможно deprecated. |
| 4 | `GET /api/16/dicts/parameters?categoryId=84` | unknown (TBD) | ⭐⭐ MEDIUM | URL ✓, newer version v16. Same hypothesis. |
| 5 | `GET /api/2/params/suggest` | `PublishApi.suggestParamsApiV2(SuggestApiRequest)` | ⭐ LOW | Verified Retrofit method ✓, но в **PublishApi** (для posting, не для search). |

**Backup candidate:** `FilterApi.subscriptionsMobileFilter(filterId: Long)` [classes4] — взять saved subscription и получить filter taxonomy для её категории. Pattern: создать 1 subscription для phones → дёрнуть filter endpoint → получить таксономию.

---

## 6. Test plan (когда будет fresh JWT)

### ⚠ SAFETY WARNING

Pool QRATOR-locked при первой попытке тестирования endpoints. Для fresh JWT юзер должен logout/login в Avito-app под `157920214` — токен должен быть born на ru-vpn IP (155.212.217.226). Каждый test request имеет ~5% risk триггера 403 captcha. **Тестировать в этом порядке** для максимума инфо-per-request.

### Phase 1 — low-risk endpoints (можно отправлять первыми)

Mimic Avito-app's normal startup behavior:

```bash
# 1. Subscription list (we know works)
curl -X GET "https://app.avito.ru/api/5/subscriptions" \
  -H "X-Auth: Bearer $TOKEN" \
  -H "X-Geo-required: true" \
  --proxy socks5h://172.18.0.1:1081

# 2. Category tree (low risk)
curl -X GET "https://app.avito.ru/api/1/category/tree" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081
```

### Phase 2 — catalog candidate testing (60s паузы между)

```bash
# 3. Test 15/dicts/parameters with categoryId=84
curl -X GET "https://app.avito.ru/api/15/dicts/parameters?categoryId=84" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 4. Test 16/dicts/parameters with categoryId=84
curl -X GET "https://app.avito.ru/api/16/dicts/parameters?categoryId=84" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 5. Test 16/dicts/parameters с paramId queries
curl -X GET "https://app.avito.ru/api/16/dicts/parameters?categoryId=84&parameterIds=110617,110618" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 6. Test 16/dicts/parameters parent-aware (Apple's models)
curl -X GET "https://app.avito.ru/api/16/dicts/parameters?categoryId=84&parameterId=110618&parentValue=491590" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 7. Test 2/dicts/parameters/filter
curl -X GET "https://app.avito.ru/api/2/dicts/parameters/filter?categoryId=84" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081
```

### Phase 3 — backup catalog candidates

```bash
# 8. Inline filters для current SERP (URL имеет dashes, не slashes для last segment)
curl -X GET "https://app.avito.ru/api/1/items/profile/search/inline-filters?categoryId=84" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 9. Pro filters init (может требовать Pro-account)
curl -X GET "https://app.avito.ru/api/1/serp/pro/filters/init?categoryId=84" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081

# 10. New cars (verified to work — get response shape)
curl -X GET "https://app.avito.ru/api/1/new-cars/filter/brands" \
  -H "X-Auth: Bearer $TOKEN" \
  --proxy socks5h://172.18.0.1:1081
```

### Phase 4 — definitive validation

Если что-то из выше returns brand+model list with IDs:
1. Compare returned `iPhone 12 Pro Max → ID` against known `469735`
2. Verify response schema matches `DictionaryEntity` shape `{id: Long, name: String, parent?: Long}`

### Fallback plan

Если всё выше returns 403/404/unexpected → **Variant A subscription mining** из §3:
- User saves ~35 subscriptions в Avito-app (по 1 на iPhone модель)
- `autosearch_sync` импортирует все → парсит `deepLink` → extracts `params[110617]` + `params[110618]`
- Build `avito_param_catalog` from accumulated data

**Time estimate:** 30 min user clicks + 1 hr coding (vs ~3-5 hrs для catalog endpoint test).

---

## 6.5 EMPIRICAL FINDINGS (live testing 2026-05-08) ⭐⭐⭐

**Тестировано через xapi с fresh JWT (auto-431483569-61238c, TTL 23.9h, ru-vpn outbound):**

### 6.5.1 GET tests результаты

| # | Endpoint (GET) | Status | Conclusion |
|---|---|---|---|
| 1 | `/5/subscriptions` (sanity) | **200** | токен живой ✓ |
| 2 | `/15/dicts/parameters?categoryId=84` | **405** Method Not Allowed | endpoint EXISTS, требуется POST |
| 3 | `/16/dicts/parameters?categoryId=84` | **405** | endpoint EXISTS, требуется POST |
| 4 | `/2/dicts/parameters/filter?categoryId=84` | **405** | endpoint EXISTS, требуется POST |
| 5 | `/1/items/profile/search/inline-filters?categoryId=84` | 403 captcha | сжёг trust на этом URL — возможно тоже POST |
| 6 | `/1/serp/pro/filters/init?categoryId=84` | **500** internal error | endpoint работает, но мои query params неправильные |

### 6.5.2 POST attempt результаты

```
POST /16/dicts/parameters
Content-Type: application/json
Body: {"categoryId": 84}

→ 400 "invalid content type"
```

```
POST /16/dicts/parameters
Content-Type: application/x-www-form-urlencoded
Body: categoryId=84

→ 403 captcha (токен уже зажат к этому моменту от 7+ предыдущих запросов)
```

### 6.5.3 КЛЮЧЕВЫЕ ВЫВОДЫ

1. ✅ **Catalog endpoints `15/16/dicts/parameters` СУЩЕСТВУЮТ** и доступны нашему JWT
2. ❌ Они **НЕ принимают `application/json`** — error "invalid content type"
3. ❓ `application/x-www-form-urlencoded` не успели проверить (token burned)
4. ⚠ **Trust score у QRATOR расходуется на ЛЮБОЙ unusual статус** (405, 400, 500), не только на 403. После ~5-7 запросов на endpoint'ы которые JWT не должен дёргать — токен помечается captcha-mode на all-IP
5. ⚠ Lesson: **max 2-3 запроса на endpoint per JWT** — иначе сжигание

### 6.5.4 План для NEXT session (с fresh JWT)

ОЧЕНЬ ОСТОРОЖНО, max 2 запроса:

```bash
# Variant 1 — naked categoryId
POST https://app.avito.ru/api/16/dicts/parameters
Content-Type: application/x-www-form-urlencoded
Body: categoryId=84
```

Возможные исходы:
- `200 + JSON {"110617":[...], "110618":[...]}` → ⭐ **SUCCESS, у нас catalog**
- `400 invalid content type` → попробовать `multipart/form-data`
- `400 missing field X` → добавить X в body (например `parameterIds[0]=110617`)
- `403 captcha` → токен зажат — STOP

```bash
# Variant 2 (only if Variant 1 returns 400 missing field)
POST https://app.avito.ru/api/16/dicts/parameters
Content-Type: application/x-www-form-urlencoded
Body: categoryId=84&parameterIds[0]=110617&parameterIds[1]=110618
```

Если оба варианта 400 — значит endpoint требует знания которое из APK не достать без jadx. Fallback на Variant A subscription mining.

### 6.5.5 Test script (готовый — копируй и запускай)

В `CONTINUE.md` §6 — full bash command which: load fresh session by nickname → POST request → print response. Главное: change `NICK = "auto-FRESH-NICKNAME-HERE"` на актуальный после refresh.

---

## 6.6 Если catalog endpoint НЕ работает — Subscription mining как fallback

См. §3.A "Subscription deeplink mining" выше — эталонный fallback. Кратко:
- User saves 35 subscriptions в Avito-app (по 1 на iPhone модель + 3-5 для других параметров)
- `autosearch_sync` импортирует → парсит `deepLink` → extracts `params[110617]/[110618]/[...]`
- Build `avito_param_catalog` from accumulated data

Time: ~30 мин user click + ~1ч кодинга `_extract_params_to_catalog()`.

---

## 7. Что НЕ работает (для справки)

Подтверждено from APK reverse + 2026-05-07 empirical findings:
- ❌ Querying `categoryId` alone on `/11/items` без full structured params → **QRATOR 403**
- ❌ `/api/N/categories/{id}/parameters` — endpoints не existent (no URL strings в DEX)
- ❌ Декодирование web URL `f=AS...` blob — opaque protobuf, no public schema
- ❌ Hardcoded ID lookup table inside APK — IDs 100% server-side
- ❌ `apiDictsParameters` / `getDictsParameters` / `dictsParameters` — methods НЕ в 263 auto-generated Api classes
- ❌ `retrofit2/http/*` annotations — fully obfuscated в DEX (0 hits)

---

## 8. Связанные документы

- `05-search-query-formation.md` § «3 пути исправления» — Variant B (subscription flow) — этот документ его развивает в практическую таксономию
- `07-retrofit-api-classes.md` — все Retrofit Api interfaces (включая candidate'ов для catalog endpoint)
- `08-data-models.md` — `DictionaryEntity`, `SelectParameter`, `ParametersTree`, `SearchParams`
- `09-deeplinks-and-screens.md` — Beduin server-driven UI + deeplink subtypes
- `DOCS/avito_api_snapshots/autosearches/README.md` — реверс subscriptions endpoint'ов
- `DOCS/avito_api_snapshots/categories_tree.json` — категории (web slug+id)
- `DOCS/avito_api_snapshots/phone_catalog.xml` — phone brand/model names (без ID)
- `04-reverse-engineering-howto.md` — методика jadx + mitm + DEX byte-grep
- `Reverse Avito/findings/` — raw scan outputs APK v222.5 reverse (gitignored): all_api_methods.txt (1408 строк), retrofit_urls.txt (1904), test_results.txt
- `avito-monitor/app/services/autosearch_sync.py` — где встроить _extract_params_to_catalog
- `avito-monitor/avito_mcp/tools/search.py:_category_id_for()` — где встроить catalog lookup
