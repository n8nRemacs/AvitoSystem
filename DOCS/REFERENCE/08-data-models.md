# Avito Mobile API — Data Models (DEX-extracted)

**Создано:** 2026-05-08 (перенесено из `Reverse Avito/findings/03-data-models.md`)
**Источник:** classes*.dex from APK Avito Android v222.5
**Метод:** raw DEX byte-grep + androguard low-level parsing

**Связано:**
- `01-avito-api.md` §B — endpoints (use these models as request/response types)
- `07-retrofit-api-classes.md` — Retrofit interfaces (use these models as method signatures)
- `06-structured-params-discovery.md` §1 — known param IDs (491590=Apple, 110617=brand, etc.)
- Raw scan outputs: `Reverse Avito/findings/raw/key_data_classes.txt`, `data_models_extended.txt`, `package_explorer.txt`

---

## Critical model classes for catalog discovery

### `Lcom/avito/android/remote/model/DictionaryEntity;`

**DEX:** classes3 (1 base class + `$1` synthetic)
**Гипотеза:** response item type для `15/dicts/parameters` и `16/dicts/parameters`.

Без Java decompile точная structure unknown. Inferred (UNVERIFIED) Kotlin pattern:
```kotlin
data class DictionaryEntity(
    val id: Long,           // e.g. 491590, 469735
    val name: String,       // e.g. "Apple", "iPhone 12 Pro Max"
    val parent: Long?,      // для nested (model has parent=brand)
)
```

Synthetic class `$1` typical для Kotlin compilation — `Companion` или anonymous lambda.

---

### `Lcom/avito/android/remote/model/category_parameters/CategoryParameters;`

**DEX:** classes3, 5, 14, 16, 18 (5 DEX)
**Companion:** `CategoryParameters$Companion` в classes3 (`fromJson`, `defaultEmpty` likely).

Top-level container всех parameters категории. Используется в publish flow И в search filter screen.

---

### `Lcom/avito/android/remote/model/category_parameters/SelectParameter;`

**DEX:** classes3, 4, 5, 13, 14, 16, 18 (7 DEX)
**Inner classes — 10 разных форм** select-параметра:

| Inner class | Likely meaning |
|---|---|
| `SelectParameter$Value` | Один option (id + label). **Здесь runtime mapping `491590 → "Apple"`.** |
| `SelectParameter$Sectioned` | Grouped by sections (e.g. brands by alphabet) |
| `SelectParameter$Flat` | Flat list (e.g. iPhone models после Apple selected) |
| `SelectParameter$Type` | Enum widget types |
| `SelectParameter$Widget` | UI widget config |
| `SelectParameter$Displaying` | Display rules |
| `SelectParameter$EarlyAccess` | Early access feature gating |
| `SelectParameter$Separator` | UI separator |
| `SelectParameter$UserChosenValue` | Persisted user selection |

---

### `Lcom/avito/android/remote/model/category_parameters/ParametersTree;`

Interface (с `DefaultImpls`). Tree из `SelectParameter`/других param types. Models full category-parameter hierarchy.

---

### `Lcom/avito/android/remote/model/filters_parameter/SimpleParametersTree;`

**DEX:** classes3 + classes4
**Inner classes:**
- `SimpleParametersTree$Creator` (Parcelable creator)
- `SimpleParametersTree$ParameterHolder`
- `SimpleParametersTree$findParameter$1` (lambda)
- `SimpleParametersTree$findParameterHolder$1` (lambda)

**Runtime data structure** для search-filter параметров (vs. publish-flow). Likely deserialization target для `15/dicts/parameters` response.

---

### `Lcom/avito/android/remote/model/SearchParams;`

**DEX:** широко используется (12 DEX)
**33 fields** — already documented в `DOCS/avito_api_snapshots/autosearches/README.md`.

**Key fields для нашей задачи:**
```kotlin
data class SearchParams(
    val categoryId: String?,                           // "84" для phones
    val locationId: String?,                           // "621540" для России
    val params: Map<String, SearchParam<*>>?,          // structured filters: brand, model, etc
    val priceMin: Long?,
    val priceMax: Long?,
    val withDeliveryOnly: Boolean?,
    val sort: String?,
    val query: String?,
    val geoCoords: Coordinates?,
    val metroIds: List<String>?,
    val directionId: List<String>?,
    val districtId: List<String>?,
    val owner: List<String>?,                          // private/company filter
    val withImagesOnly: Boolean?,
    val searchRadius: String?,
    val radius: Int?,
    val footWalkingMetro: String?,
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
    val drawId: String?,
    val title: String?,
    val suggestLocationId: String?,
)
```

`params: Map<String, SearchParam<*>>` сериализуется в `params[110617][0]=491590` URL-формат.

---

### `Lcom/avito/android/remote/model/search/Filter`

**Inside:** `Lcom/avito/android/remote/model/search/Filter;` — много inner classes:
- `Filter$Config`
- `Filter$Config$Creator`
- `Filter$AutoShowPresetFiltersDialog`
- `Filter$AutoShowPresetFiltersDialog$Button`

Search **filter configuration** objects. Filter — это **schema** ("какие фильтры доступны"), SearchParams — **values** ("какие фильтры применены").

---

### `Lcom/avito/android/remote/search/{Address,Direction,District}FilterValue`

Specialized filter value types для location-related фильтров. Каждый имеет `$Creator` (Parcelable).

---

### `Lcom/avito/android/category_parameters/ParameterElement` (UI layer)

**75 inner classes** (`$A` through `$z` plus named: `$Header`, `$RealtyVerificationItem`, `$SelectorCardsCarousel`, `$VariableLengthParameter`, `$DisplayType`).

UI presentation layer — converts `SelectParameter`/`ParameterElement` to renderable UI items. Каждый `ParameterElement$X` — different widget (chips, dropdown, sectioned list, etc).

75 widget types значит Avito's filter UI **extremely flexible** — нет hardcoded UI per parameter, fully data-driven from `15/dicts/parameters` response.

---

### `Lcom/avito/android/inline_filters/InlineFiltersCommonViewInfo;`

В `inline_filters/` package. Имеет companion `$a`. Используется для inline filters над SERP (quick price brackets, sort, condition).

---

### `Lcom/avito/android/inline_filters/InlineFiltersSource;`

Likely enum source contexts (откуда inline filters triggered).

---

### `Lcom/avito/android/inline_filters/State;`

State machine для inline filter UI.

---

## Subscription / saved-searches data models

### `SubscriptionListMobileApi` (data class) [classes18]

```kotlin
data class SubscriptionListMobileApi(
    val deepLink: DeepLink,
    val description: String,
    val editAction: String,
    val hasNewItems: Boolean,
    val id: Long,                    // = filterId
    val openAction: String,
    val pushFrequency: Long,
    val sendEmail: Boolean?,
    val ssid: Long,
    val title: String,
)
```

**Verified ✓** (точно совпадает с `DOCS/avito_api_snapshots/autosearches/README.md`).

---

### `SubscriptionFilterListMobileApi` (data class) [classes4]

Response of `FilterApi.subscriptionsMobileFilter(filterId)`. Поля (extracted via method dump):
- `getMultiThemeImages()` → `SubscriptionFilterListMobileApiMultiThemeImages`
- (other inner getters)

UI wrapper для saved-search.

---

### `Lcom/avito/android/deep_linking/links/DeepLink`

Used as typed wrapper для `ru.avito://...` deep links. Имеет 96+ subtypes (каждый screen has its own DeepLink subclass для routing).

For search-deeplinks (subscription URLs):
- `SearchDeepLink` (likely) — wraps `ru.avito://1/items/search?categoryId=84&params[110617][0]=491590...`
- `ItemShowDeepLink` — `ru.avito://1/item/show?itemId=...`
- `GlobalCategoriesDeepLink` — `ru.avito://1/globalCategories?categoryId=...`

Full DeepLink subtype enumeration not done.

---

## Mortgage-side dictionaries (alternate pattern)

### `Lcom/avito/android/mortgage/api/model/DictionariesResult;`

Для `1/mortgage-form/dictionaries` endpoint.

### `Lcom/avito/android/mortgage/api/model/dictionary/Parameter;`
Subtypes:
- `IconParameter`
- `MonthParameter`
- `UsualParameter`
- `ProgramParameter`
- `StringNumberParameter`

**Typed parameters** — каждый subtype carries different metadata. Mortgage forms используют их для dropdowns/pickers в credit application form.

**Useful template** для того как `dicts/parameters` response **может** выглядеть — typed/discriminated union of parameter values.

---

## Search-result item models

`Lcom/avito/android/remote/model/search/...` имеет **156 классов** включая:
- `EntryPoint`, `EntryPoint$Onboarding` — search entry-point metadata
- `ConfigCalendarSelectionType`, `ConfigWidgetType` — config enums
- `Filter`, `FilterValue` (per-domain)
- `AddressFilterValue`, `DirectionFilterValue`, `DistrictFilterValue` — geo filter values

---

## Data model file organization

`com.avito.android.remote.model` имеет **2155 top-level classes** (Pass 6) покрывающих ВСЕ API responses.

Subpackages of interest:

| Subpackage | Class count | Назначение |
|---|---|---|
| `category_parameters/` | 827 | publish-flow & search filter parameters |
| `search/` | 156 | search-related models |
| `filters_parameter/` | 9 | search filter parameters |
| `dictionary/` | 0 | (empty — DictionaryEntity at top-level) |
| `subscription/` | 0 | (empty — saved_searches_core has them) |
| `saved_searches/` | 0 | (empty — saved_searches_core has them) |

Empty subpackages = классы placed elsewhere — saved_searches lives in `com.avito.android.saved_searches_core.generated.api.subscriptions_mobile_list_v_2.*`.

---

## Cross-validation status

| Class | Found in DEX | Notes |
|---|---|---|
| `DictionaryEntity` | ✓ classes3 | needs decompile to verify field shape |
| `CategoryParameters` | ✓ 5 DEX | |
| `SelectParameter` (+ 9 inner) | ✓ 7 DEX | |
| `SelectParameter$Value` | ✓ 8 DEX | |
| `SelectParameter$Sectioned` | ✓ 5 DEX | |
| `SelectParameter$Flat` | ✓ 6 DEX | |
| `ParametersTree` | ✓ 7 DEX | |
| `SimpleParametersTree` | ✓ 4 DEX | |
| `SearchParams` | ✓ 12 DEX | matches autosearches/README.md |
| `Lcom/avito/.../SubscriptionListMobileApi;` | ✓ classes18 | matches autosearches/README.md ✓ |
| `Lcom/avito/.../SavedSearchesCoreApi;` | ✓ classes14, 18 | only 2 methods |
| `Lcom/avito/.../FilterApi;` | ✓ classes4, 14 | 1 method `subscriptionsMobileFilter` |
| `Lcom/avito/.../NewCarsMarkModelFilterApi;` | ✓ classes14, 17 | 3 methods |
| `Lcom/avito/.../CategoryItemsTreeApi;` | ✓ classes13, 14 | 2 methods |
| `Lcom/avito/.../InlineFiltersApi;` | ✓ classes14, 18 | 3 methods (realty-only) |
| `Lcom/avito/.../SearchApi;` | ✓ classes12, 14, 16 | only 1 real method (mainShortVideosOnAppV3) |
| `Lcom/avito/.../PublishApi;` | ✓ classes14, 16, 18 | 15+ methods |
| `Lcom/avito/.../UserAdvertsApi;` | ✓ classes5, 14, 16 | has `proFiltersInitV1` ⭐ |

**Result:** 18/18 PASS.
