# Avito Mobile API — Subscriptions (autosearches)

**Реверс от:** 2026-04-28
**Источник:** Avito-app v222.5 (com.avito.android, versionCode 3301), `base.apk` 357 МБ, decompiled через `jadx 1.5.4`.
**Метод:** static analysis (decompiled DEX), не runtime — Avito-app имеет anti-Frida tampering защиту, runtime-перехват потребовал бы Magisk Zygisk DenyList + reboot.

В Avito UI это «Сохранённые поиски» (web `https://www.avito.ru/autosearch`). Mobile API называет их **subscriptions**, идентификатор называется **filterId** (число, Long).

---

## Хост

```
https://app.avito.ru/api
```

Это **тот же `BASE_URL`**, что наш xapi уже использует для search items (`/11/items`), item details (`/19/items/{id}`), messenger (`/1/messenger/*`), auth (`/1/auth/suggest`, `/11/auth`). См. `avito-xapi/src/workers/base_client.py:11`. Subscriptions — это просто **добавление** новых методов рядом с существующими, никакой новой инфраструктуры (auth, headers, rate-limit, curl-cffi) не нужно.

Полные URL'ы для subscriptions:
- `https://app.avito.ru/api/4/subscriptions/{filterId}` (PUT update)
- `https://app.avito.ru/api/4/subscription` (POST create)
- `https://app.avito.ru/api/5/subscriptions` (GET list — реверс GET-интерфейса в процессе)
- `https://app.avito.ru/api/2/subscriptions/{subscriptionId}` (DELETE — реверс в процессе)
- `https://app.avito.ru/api/2/subscriptions/count_with_new_items` (GET counts)

## Retrofit annotation prefix

В декомпилированном Avito-app:

| Avito alias | Retrofit standard |
|---|---|
| `@Mg1.f("path")` | `@GET` |
| `@Mg1.o("path")` | `@POST` |
| `@Mg1.p("path")` | `@PUT` |
| `@Mg1.b("path")` | `@DELETE` |
| `@Mg1.s("name")` | `@Path` |
| `@Mg1.t("name")` | `@Query` |
| `@Mg1.a` | `@Body` |
| `@Mg1.c("name")` | `@Field` |
| `@Mg1.d` | `@FieldMap` |
| `@Mg1.e` | `@FormUrlEncoded` |
| `@Mg1.k({"hdr"})` | `@Headers` |

Стандартные Avito-headers (в дополнение к auth):

```
X-Geo-required: true
```

---

## Endpoints (известные)

### 1. PUT /4/subscriptions/{filterId}  — обновить настройки подписки

**Источник:** `ou0.InterfaceC46814a` (decompile from `SavedSearchesCoreApi.kt`).

```kotlin
@PUT("4/subscriptions/{filterId}")
@Headers("X-Geo-required: true")
suspend fun update(
    @Path("filterId") filterId: Long,
    @Body request: SubscriptionMobileUpdateV4Request
): TypedResult<SubscriptionMobileUpdateV4Response>
```

#### Request body — `SubscriptionMobileUpdateV4Request` (`pu0.d`)

```json
{
  "emailFrequency": "instant" | "daily" | "weekly" | null,    // pu0.a (enum)
  "isEmailEnabled": true | false | null,
  "isPushAllowed": true | false | null,
  "isPushEnabled": true | false | null,
  "isUpdateLastViewTime": true | false | null,
  "pushFrequency": "instant" | ... | null,                    // pu0.b (enum)
  "title": "iPhone 12 Pro Max"
}
```

#### Response — `SubscriptionMobileUpdateV4Response` (`pu0.C47208c`)

```json
{
  "id": 12345678,                                  // Long, this is filterId
  "searchSubscriptionAction": "avito://..."        // DeepLink (опционально)
}
```

---

### 2. POST /4/subscription  — создать подписку из form-encoded params

**Источник:** `mu0.InterfaceC46015a`.

```kotlin
@POST("4/subscription")
@FormUrlEncoded
suspend fun create(
    @FieldMap params: Map<String, String>,        // search params как form-fields
    @Field("drawId") drawId: String?,
    @Field("xHash") xHash: String?,
    @Field("type") type: String?,
    @Field("isPushAllowed") isPushAllowed: Boolean,
    @Field("isTitleEdited") isTitleEdited: Boolean?,
    @Field("from") from: String?
): TypedResult<SearchSubscription>
```

`params: Map<String, String>` сюда уходят все search-параметры (categoryId, locationId, priceMin, priceMax, query, и каждый параметр из `params[parameter_id]=value_id`). Эта Map собирается из `SearchParams` через `SearchParamsConverterKt`.

---

### 3. GET /5/subscriptions  — список autosearches  ✅ live-validated

```
GET https://app.avito.ru/api/5/subscriptions
```

Без параметров. Возвращает все автосохранённые поиски юзера. **Описания фильтров — только текстовые (human-readable), без structured params.**

#### Response

```json
{
  "success": {
    "items": [
      {
        "id": 264239719,                                                      // ← это filterId (Long)
        "ssid": 459778524,                                                    // вторичный id (purpose unclear)
        "title": "IPhone 12 pro max",                                         // user-defined
        "description": "Все регионы, Телефоны, Тип телефона: Мобильные телефоны, Производитель: Apple, Модель: iPhone 12 Pro Max, Только с доставкой, Цена 11 000 — 13 500 ₽",
        "deepLink": "",
        "editAction": "ru.avito://1/searchSubscription/show?categoryId=84&fromPage=ssfav&subscriptionId=264239719",
        "openAction": "ru.avito://1/searchSubscription/open?from=ssfav&fsid=264239719",
        "hasNewItems": false,                                                 // true если есть новые лоты с прошлого открытия
        "pushFrequency": 0                                                    // 0 = no push, 1 = push enabled
      }
      // … остальные autosearches
    ]
  }
}
```

---

### 4. GET /2/subscriptions/{filterId}  — search-deeplink для autosearch  ✅ live-validated

```
GET https://app.avito.ru/api/2/subscriptions/264239719
```

**Это и есть путь к точной выдаче без чайников.** Возвращает deeplink, чей query-string содержит полный набор structured search params для конкретного autosearch.

#### Response

```json
{
  "status": "ok",
  "result": {
    "deepLink": "ru.avito://1/items/search?categoryId=84&context=...&geoCoords=55.755814,37.617635&localPriority=0&locationId=621540&params[110617][0]=491590&params[110618][0]=469735&params[110680]=458500&presentationType=serp&priceMax=13500&priceMin=11000&sort=date&withDeliveryOnly=1"
  }
}
```

Парсим query-string из deepLink → получаем `dict[str, Any]`:

```python
{
  "categoryId":         "84",
  "geoCoords":          "55.755814,37.617635",
  "localPriority":      "0",
  "locationId":         "621540",
  "params[110617][0]":  "491590",   # Производитель = Apple
  "params[110618][0]":  "469735",   # Модель = iPhone 12 Pro Max
  "params[110680]":     "458500",   # ещё параметр (состояние/пробег)
  "priceMin":           "11000",
  "priceMax":           "13500",
  "sort":               "date",
  "withDeliveryOnly":   "1",
  "presentationType":   "serp"
}
```

Эти параметры скармливаются нашему xapi `search_items()` через `params_extra: dict` — параметр уже есть в `avito-xapi/src/workers/http_client.py:185`. Avito API отдаст ТОЧНУЮ выдачу как в веб-фильтре пользователя, без fuzzy-match чайников.

---

### 5. GET /2/subscriptions/count_with_new_items  ✅ live-validated

```
GET https://app.avito.ru/api/2/subscriptions/count_with_new_items
```

Возвращает суммарное число «новых» лотов по всем autosearches (бейдж в UI).

```json
{"result": {"count": 5}, "status": "ok"}
```

---

### 6. POST /4/subscription  — создать подписку (form-encoded)

См. выше (Retrofit-интерфейс `mu0.InterfaceC46015a`). Не нужен для нашей V1 (мы только sync, не create).

---

### 7. PUT /4/subscriptions/{filterId}  — обновить settings подписки

См. выше (`ou0.InterfaceC46814a`). Не нужен для V1.

---

### 8. DELETE /2/subscriptions/{subscriptionId}  — удалить подписку

Литерал в DEX strings. Не нужен для V1 (мы только зеркалим Avito → нас).

---

### 9. GET /4/subscriptions  — устаревшая версия списка

Возвращает прямой массив items (без `success` обёртки). На V1 не используем — `/5/subscriptions` новее.

---

## SearchParams — главный объект

`com.avito.android.remote.model.SearchParams` — 33 поля, покрывающие всё что юзер может настроить в Avito-веб-фильтре.

```kotlin
data class SearchParams(
    val categoryId: String?,
    val geoCoords: Coordinates?,
    val locationId: String?,
    val suggestLocationId: String?,
    val metroIds: List<String>?,
    val directionId: List<String>?,
    val districtId: List<String>?,
    val params: Map<String, SearchParam<*>>?,    // ← structured filters: brand, model, capacity, color и т.д.
    val priceMax: Long?,
    val priceMin: Long?,
    val query: String?,
    val title: String?,
    val owner: List<String>?,                    // private/company filter
    val sort: String?,
    val withImagesOnly: Boolean?,
    val searchRadius: String?,
    val radius: Int?,
    val footWalkingMetro: String?,
    val withDeliveryOnly: Boolean?,
    val localPriority: Boolean?,
    val earlyAccess: Boolean?,
    val moreExpensive: String?,
    val widgetCategory: String?,
    val expanded: String?,
    val sellerId: String?,
    val cv2Vacancy: String?,
    val displayType: SerpDisplayType?,
    val shopId: String?,
    val forcedLocationForRecommendation: Boolean?,
    val area: Area?,
    val source: Source?,
    val clarifyIconType: String?,
    val drawId: String?
)
```

**`params: Map<String, SearchParam>`** — это контейнер именно тех structured-фильтров, которые на веб-сайте упакованы в `f=` blob. Получив SearchParams из subscriptions list, мы кормим эту Map в наш xapi `search_items` (параметр `params_extra` уже есть в `avito-xapi/src/workers/http_client.py:185`) — и Avito API возвращает точные результаты без чайников.

---

## Маппинг на наш план интеграции (ADR-011)

| Наш этап | Avito endpoint |
|---|---|
| Sync списка autosearches → SearchProfiles | `GET /5/subscriptions` (нужен реверс GET-интерфейса или эмпирическая проверка) |
| Опрос items для конкретного профиля | передавать `SearchSubscription.searchParams` в существующий xapi `search_items()` через `params_extra` |
| Soft-delete профиля при удалении на Avito | sync видит отсутствие → `archived_at = now()` локально |
| User reject лота | поверх Avito ничего не делаем — это локальный blacklist |

---

## Что осталось реверсить

1. **`GET /5/subscriptions`** — точная сигнатура (query params? pagination?). Может быть в обфусцированных пакетах вне `ou0/mu0`. Полный grep по всем Retrofit-аннотациям дал бы ответ, но 200K Java файлов оптимально только с правильным поиском (требует minute+).
2. **`DELETE /2/subscriptions/{subscriptionId}`** — есть строка, но интерфейс не найден.
3. **Auth headers** — какой именно header / token expected. Скорее всего тот же что наш xapi уже шлёт (Avito-app использует один auth-механизм для всех endpoints).
4. **Точные имена SearchSubscription полей** (b...k) — увидим в первом live-call ответе.

---

## Артефакты

- `endpoint_candidates.txt` — список всех subscription-related строк из DEX (~30 эндпоинтов и моделей)
- `find_retrofit.py` — Python script для Retrofit-аннотации scan
- `find_class.py` — script для xref-анализа через androguard
- Декомпилированные классы: `ou0/InterfaceC46814a.java`, `mu0/InterfaceC46015a.java`, `pu0/d.java`, `pu0/C47208c.java`, `com/avito/android/saved_searches/model/SearchSubscription.java`, `com/avito/android/remote/model/SearchParams.java`

(Все артефакты сейчас в `c:/Users/EloNout/AppData/Local/Temp/avito_apk/`. Не коммитятся — APK proprietary, перезапустится при следующем decompile.)
