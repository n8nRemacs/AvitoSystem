# Retrofit API Classes — APK v222.5 Reverse Engineering

**Создано:** 2026-05-08 (перенесено из `Reverse Avito/findings/02-retrofit-api-classes.md`)
**Источник:** APK Avito Android v222.5 (versionCode 3301, 359 МБ, скачан 2026-05-07 с `avito.st/s/app/apk/avito.apk`)
**Метод:** raw DEX byte-grep + androguard 4.1.3 low-level parsing (jadx не использовался — download failed exit 28/56 трижды)

**Связано:**
- `01-avito-api.md` §B — endpoints overview + verified live calls
- `06-structured-params-discovery.md` §5 — testing plan для catalog candidate endpoints
- `08-data-models.md` — структура data classes (DictionaryEntity, SelectParameter, ParametersTree)
- `04-reverse-engineering-howto.md` §DEX-byte-grep — методика без jadx
- Raw scan outputs: `c:/Projects/Sync/AvitoSystem/Reverse Avito/findings/raw/all_api_methods.txt` (1408 строк, 263 Api class method dumps)

---

## TL;DR — Retrofit naming convention (CRITICAL)

Avito-app использует **regular Retrofit codegen**: URL → method name следует kebab/snake → camelCase правилам. Зная URL, можно предсказать имя метода и наоборот.

| URL component | Method-name convention |
|---|---|
| `/api/X/...` (X — digit) | prefix `apiX` (e.g. `api1`, `api2`, `api3`) |
| `/path/to/foo` | `pathToFoo` (camelCase) |
| `-foo-bar` | `FooBar` (kebab → camel) |
| `_foo_bar` | `FooBar` (snake → camel) |
| `{paramId}` | (omitted in name; становится parameter) |
| `?key=val` | (omitted) |
| `/post`/`/get`/`/put` (verb in URL) | sometimes appended (e.g. `apiV1ReplaceMainExitMain`) |

**Verified examples (extracted method dumps):**

```
1/new-cars/filter/brands             → apiNewCarsFilterBrands
1/new-cars/filter/models             → apiNewCarsFilterModels
1/new-cars/filter/apply              → apiNewCarsFilterApply
1/llm/text/beautify/post             → api1LlmTextBeautifyPost
2/dicts/suggest/reg_num/by_photo     → apiDictsSuggestRegNumByPhoto
2/params/suggest                     → suggestParamsApiV2
1/profile/userInfo                   → userInfo (older convention without prefix)
1/replace_main/exit_avito            → apiV1ReplaceMainExitMain
3/nd-trx/search/parameters           → api3NdTrxSearchParamsGet
PUT 4/subscriptions/{filterId}       → subscriptionMobileUpdateV4
GET 5/subscriptions                  → subscriptionsMobileListV2
1/promo/category/tree                → api1PromoCategoryTree
1/promo/category/tree/items          → api1PromoCategoryTreeItems
1/serp/pro/filters/init              → proFiltersInitV1
```

---

## Auto-generated API packages (207 total)

Avito использует Retrofit codegen с naming pattern `api_<version>_<path_with_underscores>`. Для каждого endpoint генерируется package с request DTO + response DTO.

**Path normalization:**
- `_` separates URL path segments
- `__` (double underscore) at start indicates leading `/` in URL (e.g. `1__seller_guide` → `1//seller/guide`)
- Trailing `_get`/`_post`/`_put`/`_delete` may be omitted or kept depending on version

**Examples:**
| Package | URL |
|---|---|
| `api_1_promo_category_tree` | `1/promo/category/tree` |
| `api_1_promo_category_tree_items` | `1/promo/category/tree/items` |
| `api_2_developers_catalog_phone_by_developer_company_group_id_get` | `2/developers/catalog/phone/{developerCompanyGroupId}/get` |
| `api_dicts_suggest_reg_num_by_photo` (no version) | publish-flow dicts |
| `api_dicts_suggest_vin_by_reg_num` | publish-flow VIN suggest |

Полный список 207 packages: `Reverse Avito/findings/raw/api_packages.txt`

---

## Verified Retrofit Api interfaces (key ones for catalog discovery)

### 🎯 `Lcom/avito/android/newcars_mark_model_filter_public/generated/api/NewCarsMarkModelFilterApi;`

**DEX:** classes17 (also stub in classes14)
**Покрывает:** `1/new-cars/filter/{brands,models,apply}`

```kotlin
interface NewCarsMarkModelFilterApi {
    suspend fun apiNewCarsFilterApply(brands: List<...>, models: List<...>): Response
    suspend fun apiNewCarsFilterBrands(): Response
    suspend fun apiNewCarsFilterModels(brandIds: List<...>): Response
}
```

**Это — blueprint для phone-equivalent catalog endpoint.** Если бы phones имели аналогичный specialized API class, его методы выглядели бы как `apiPhonesFilterBrands()` / `apiPhonesFilterModels(brandIds)`. Но такого класса в DEX нет — phones, видимо, используют generic mechanism (см. `06-structured-params-discovery.md` §5).

---

### 🎯 `Lcom/avito/android/saved_searches_core/generated/api/SavedSearchesCoreApi;`

**DEX:** classes14 (stub) + classes18 (full)
**Покрывает:** `4/subscriptions/{filterId}` (PUT), `5/subscriptions` (GET v2 list)

```kotlin
interface SavedSearchesCoreApi {
    suspend fun subscriptionMobileUpdateV4(filterId: Long, body: UpdateSubscriptionRequest): Response
    suspend fun subscriptionsMobileListV2(): Response
}
```

> ⚠ Этот класс declares **только 2 method**. Остальные subscription-операции (POST `4/subscription`, DELETE `2/subscriptions/{id}`, GET `2/subscriptions/{filterId}` deeplink, GET `2/subscriptions/count_with_new_items`) объявлены в **другом** Retrofit interface (легаси, `SavedSearchesApi` без `Core` suffix?) — точное имя класса TBD.

---

### 🎯 `Lcom/avito/android/saved_searches_core/generated/api/subscriptions_mobile_list_v_2/SubscriptionListMobileApi;` [classes18]

⚠ Это **НЕ Retrofit interface** — это **Kotlin data class** (response item из `subscriptionsMobileListV2()`).

**Проверенные поля** (через method extraction):
```kotlin
data class SubscriptionListMobileApi(
    val deepLink: DeepLink,           // ⭐ embedded structured-search deeplink с params[110617]=491590…
    val description: String,
    val editAction: String,
    val hasNewItems: Boolean,
    val id: Long,                      // = filterId
    val openAction: String,
    val pushFrequency: Long,
    val sendEmail: Boolean?,
    val ssid: Long,
    val title: String,
)
```

**Cross-validated против** `DOCS/avito_api_snapshots/autosearches/README.md` — **точное соответствие** ✓

---

### 🎯 `Lcom/avito/android/search/filter/generated/api/FilterApi;` [classes4]

```kotlin
interface FilterApi {
    suspend fun subscriptionsMobileFilter(filterId: Long?): Response
}
```

**Только один метод.** Возвращает `Lcom/avito/android/search/filter/generated/api/subscriptions_mobile_filter/SubscriptionFilterListMobileApi;` — обёртка saved-subscription для UI.

**Гипотеза:** этот endpoint может быть key для catalog discovery — он принимает saved-subscription `filterId` и возвращает full filter taxonomy для категории этой подписки. Если так, то pattern: **сохранить 1 subscription для phones → дёрнуть `subscriptionsMobileFilter(filterId)` → получить таксономию всех phone parameters**.

---

### 🎯 `Lcom/avito/android/category_items_tree/generated/api/CategoryItemsTreeApi;` [classes13, 14]

```kotlin
interface CategoryItemsTreeApi {
    suspend fun api1PromoCategoryTree(...): Response
    suspend fun api1PromoCategoryTreeItems(filterId: Long?, ..., String, String, String): Response
}
```

Покрывает `1/promo/category/tree` + `1/promo/category/tree/items` — **только promo контекст**, не general phone catalog.

---

### 🎯 `Lcom/avito/android/realty_agency/inline_filters_public/generated/api/InlineFiltersApi;` [classes14, 18]

```kotlin
interface InlineFiltersApi {
    suspend fun api1NdTrxLotsSuggestGet(...): Response
    suspend fun api1NdTrxSuggestLocationPost(...): Response
    suspend fun api2NdTrxDevelopmentsSuggestPost(...): Response
}
```

⚠ **Realty-only** (`nd_trx` = new development transactions). Не для phones.

> Phones inline filters (`/api/1/items/profile/search/inline-filters`) — URL string ✓ exists в classes3, но declaring class в этом auto-generated dump НЕ найден.

---

### 🎯 `Lcom/avito/android/remote/user_adverts/generated/api/UserAdvertsApi;` [classes5, 14, 16]

**Содержит критический метод для catalog discovery:**
```kotlin
suspend fun proFiltersInitV1(arg1: String, arg2: String): Response   // = GET /api/1/serp/pro/filters/init
```

**Hypothesis:** аргументы `(categoryId, contextOrToken)`. Возвращает init payload для Avito Pro filters UI — likely full filter taxonomy.

⚠ **Risk:** возможно требует Pro-account (только для sellers). Test plan в `06-structured-params-discovery.md` §5.

---

### 🎯 `Lcom/avito/android/remote/publish/generated/api/PublishApi;` [classes14, 16, 18]

```kotlin
interface PublishApi {
    suspend fun api1DeliveryItemValidationGet(...): Response
    suspend fun api1PublishItemRestrictionCheckGet(...): Response
    suspend fun api2DeliverySubsidySettingsPost(...): Response
    suspend fun api3CpaCreateRequestPost(...): Response
    suspend fun apiDictsSuggestRegNumByPhoto(...): Response          // dicts/suggest/reg_num/by_photo
    suspend fun apiDictsSuggestVinByRegNum(...): Response            // dicts/suggest/vin_by_reg_num
    suspend fun apiPublishSellerAddressList(...): Response
    suspend fun enrichmentFeedbackApiV2(...): Response
    suspend fun estimateEditV4(req: EstimateEditV4ApiRequest): Response  // IMV pricing edit
    suspend fun estimateV4(req: EstimateV4ApiRequest): Response          // IMV pricing
    suspend fun suggestParamsApiV2(req: SuggestApiRequest): Response     // ⭐ 2/params/suggest
    suspend fun v1JobCvLlmWorkPlacesAnalyticSend(...): Response
    suspend fun v1JobCvLoadPreviousResponsibilities(...): Response
    suspend fun v1JobCvSaveAndImproveResponsibilities(...): Response
    suspend fun vacancyMarketSalaryApiV2(...): Response
}
```

`suggestParamsApiV2` — **generic params suggester**. Может быть полезен для catalog discovery если вызвать с правильными ключами.

---

### `Lcom/avito/android/remote/search/generated/api/SearchApi;` [classes12 stub, 14 stub, 16 full]

⚠ В classes16 имеет **только 1 метод**:
```kotlin
suspend fun mainShortVideosOnAppV3(...): Response
```

Multi-DEX stubs в classes12/14 **пусты** (interface declared, methods в classes16). Несмотря на name "SearchApi" — этот класс **НЕ** declares главные search endpoints (`/15/dicts/parameters` etc).

---

### `Lcom/avito/android/developments_agency_search_impl/generated/api/DevelopmentsAgencySearchApi;` [classes14]

```kotlin
interface DevelopmentsAgencySearchApi {
    suspend fun api1NdTrxChatsOpenPost(...): Response
    suspend fun api1NdTrxLocationsByLocationIdManagerGet(locId: Long, ...): Response
    suspend fun api1NdTrxSaveRecentLocationPost(locId: Long, ...): Response
    suspend fun api2NdTrxDevelopmentsSearchGet(...lots of params): Response
    suspend fun api2NdTrxLotsSearchGet(...lots of params): Response
    suspend fun api3NdTrxSearchParamsGet(): Response   // ⭐ search params для realty agency
}
```

`api3NdTrxSearchParamsGet` — **catalog endpoint для realty agency**. Strong template для того как должен выглядеть phones-catalog endpoint.

---

### `Lcom/avito/android/remote/notifications/generated/api/NotificationsApi;` [classes16]

```kotlin
interface NotificationsApi {
    suspend fun apicoNotificationCount(...): Response   // 2/notifications/count
    suspend fun apicoNotificationCountV2(...): Response
    suspend fun apicoNotificationRead(...): Response    // 2/notifications/{id}/read
    suspend fun apicoNotificationSearch(...): Response  // 2/notifications/search
    suspend fun apicoNotificationsSettings(...): Response
    suspend fun apicoNotificationsToken(...): Response  // FCM token reg
    suspend fun apicoSaveNotificationsSettings(...): Response
}
```

Префикс `apico` — необычный (возможно "API content" или generated naming quirk).

---

### `Lcom/avito/android/remote/spare_parts/generated/api/SparePartsApi;` [classes16]

```kotlin
interface SparePartsApi {
    suspend fun getPartCompatibilitiesApiV3(...): Response
    suspend fun getPartCompatibilitiesApiV4(params: ParamsRawParams, ...): Response
}
```

Compatibility lookup для авто запчастей. Аналог "что подходит к моей машине" — отдельный catalog API.

---

### `Lcom/avito/android/replace_main/generated/api/ReplaceMainApi;` [classes16]

```kotlin
interface ReplaceMainApi {
    suspend fun apiV1ReplaceMainExitMain(): Response   // 1/replace_main/exit_avito
    suspend fun apiV1ReplaceMainToggle(): Response     // 1/replace_main/toggle
}
```

Для feature "Замена главной" в profile.

---

### `Lcom/avito/android/llm_impl/generated/api/LlmApi;` [classes16]

```kotlin
interface LlmApi {
    suspend fun api1LlmTextBeautifyPost(...): Response   // 1/llm/text/beautify/post
}
```

Description rewriting в publish flow.

---

### `Lcom/avito/android/messenger/generated/api/MessengerApi;` [classes16]

```kotlin
interface MessengerApi {
    suspend fun apiAutoReplyForMeaninglessMessage(...): Response
    suspend fun getAssistantSettingsDeeplink(...): Response
    suspend fun getChannelsCustomTags(...): Response
    suspend fun getOnboardingLink(...): Response
    suspend fun messengerInformerV1ApiGet(...): Response
    suspend fun setActiveChannelsStatus(...): Response
}
```

Out of scope для catalog discovery — но дополняет наш `01-avito-api.md §B.4` Messenger HTTP REST.

---

### `Lcom/avito/android/remote/profile/generated/api/ProfileApi;` [classes16]

```kotlin
interface ProfileApi {
    suspend fun api2ProfileFinanceGet(...): Response
    suspend fun api3InternalBannerRotationBannersGet(...): Response
    suspend fun socialRedirectV2(...): Response
    suspend fun userInfo(): Response
}
```

`userInfo()` — без префикса (older Retrofit convention).

---

## Ещё интересные Api classes (полный список — 263 шт)

| Класс | Назначение | DEX |
|---|---|---|
| `AccountStorageApi` | Account storage | classes11 |
| `AdvertCollectionApi` | Saved collections (favorites groups) | classes12 |
| `AdvertDetailsApi` | Item details + delivery + cart | classes12 |
| `AiAssistantApi` | AI assistant chat | classes12 |
| `BblApi` (BotBigList?) | classes12 | classes12 |
| `CartSnippetActionsApi` | Cart cart_items_update | classes13 |
| `CharityApi` | Charity feature | classes13 |
| `CheckoutApi` | Checkout flow | classes13 |
| `ConfigApi` | App config | classes3 |
| `CompetitorAnalyticsApi` | Competitor analytics | classes11 |
| `CrmCandidatesApi` | Job CRM candidates (with `apiGetFiltersV5`) | classes15 |
| `CrmPaidCvsApi` | Job paid CVs (with `apiPaidCvGetFilters`, `apiFavoritesCvGetFilters`) | classes15 |
| `DeliveryApi` | Delivery service | classes3 |
| `EarlyAccessApi` | Early access (premium reservation) | classes3 |
| `ExtendedProfileApi` | Extended profile (sellers) | classes11/14 |
| `FavoriteApi` | Favorites (classic) | classes3 |
| `FavoritesApi` | Favorites V2 | classes15 |
| `FavoriteSellersP2PApi` | Subscribed sellers feed | classes12/14 |
| `LogoutApi` | Logout | classes16 |
| `MandatoryVerificationApi` | Mandatory KYC | classes16 |
| `MasterPlanApi` | Master plan (premium) | classes16 |
| `MortgageApi` (+ subforms) | Mortgage flow (5+ classes) | classes17 |
| `NavigationConfigApi` | Navigation config (`1/navigation_config`) | classes17 |
| `NewCarsGetContactsApi` | New cars get contact | classes17 |
| `NewCarsSendLeadApi` | New cars send lead | classes17 |
| `OauthApi` | OAuth flow | classes17 |
| `OnboardingApi` | Onboarding screens | classes16 |
| `PassportLibApi` | Russian passport KYC | classes17 |
| `PersonalSelectionsApi` | Personal selections (recommendations) | classes17 |
| `PhoneProtectionInfoApi` | Phone-protection feature | classes17 |
| `ProfileProApi` | Profile Pro (sellers) | classes17 |
| `RatingAvitoApiGatewayApi` (+ Newbiz) | Rating system | classes18 |
| `ReSellerItemDuplicatesApi` | Reseller item duplicates | classes18 |
| `ReputationApi` | Reputation (with Beduin variant) | classes16 |
| `SafedealItemsApi` | Safe deal items | classes14/16 |
| `SavedSearchesCoreApi` | ⭐ subscriptions | classes18 |
| `SbcApi` | SBC (Sale-By-Content?) | classes18 |
| `SearchPositionApi` | Item search position | classes4 |
| `SellerRoomApi` | Seller room | classes4 |
| `ShortTermRentApi` | STR (short-term rent / Avito Travel) | classes16 |
| `StrSellerOrdersApi` (+ subforms) | STR seller orders | classes18 |
| `TravelSearchApi` | Travel search | classes5/14 |
| `UserAdvertApi` | User advert (with `proFiltersInitV1`) | classes16 |
| `UserAdvertsApi` | User adverts | classes16 |
| `UserAdvertsActionsApi` | User adverts actions | classes16 |
| `VasAutoprolongApi` | VAS auto-prolong | classes6 |
| `VasPerformanceApi` | VAS performance | classes6 |
| `VerificationApi` | Verification | classes6 |
| `VirtualDealRoomApi` (+ 5 subforms) | Virtual deal room | classes6 |
| `VpnCheckApi` | VPN check (probably Avito's anti-VPN) | classes6 |
| `WalletHistoryApi` | Wallet history | classes6 |
| `WalletPageApi` | Wallet page | classes6 |
| `WorkProfileApi` | Work profile | classes6 |

Полный dump: `Reverse Avito/findings/raw/all_api_methods.txt` (1408 строк, 263 классов).

---

## Что НЕ попало в auto-generated dump

| Endpoint URL | URL в DEX? | Auto-gen Api class? | Where? |
|---|---|---|---|
| `15/dicts/parameters` | ✓ classes3 | ❌ NOT FOUND | likely manual/legacy interface, или unused в v222.5 |
| `16/dicts/parameters` | ✓ classes3, 11 | ❌ NOT FOUND | same |
| `2/dicts/parameters/filter` | ✓ classes3 | ❌ NOT FOUND | same |
| `1/dicts/navigation` | ✓ classes3, 18 | ❌ NOT FOUND | same |
| `1/items/profile/search/inline-filters` | ✓ classes3 | ❌ NOT FOUND | same |
| `1/serp/pro/filters/init` | ✓ classes16 | ✓ `UserAdvertsApi.proFiltersInitV1` | classes16 |
| `1/widget/filters/parameters` + `apply` | ✓ classes6 | ❌ NOT FOUND | likely WidgetFiltersApi (legacy) |
| `6/search/parameters` | ✓ classes3 | ❌ NOT FOUND | same |
| `1/items/count` | ✓ classes3, 16 | ❌ NOT FOUND | likely в SearchApi или ItemsApi (legacy) |

**Hypothesis:** legacy/manual Retrofit interfaces используют Avito-specific obfuscated annotation prefix (`@Mg1.f("URL")` etc — see `04-reverse-engineering-howto.md`). Чтобы найти их, нужен **полный jadx decompile** или androguard `Analysis.get_strings().get_xref_from()` (последнее зависает на 12 МБ DEX).

---

## Cross-validation results

Полный test report: `Reverse Avito/findings/raw/test_results.txt`

**Section 1 — Endpoint URL strings:** 40/43 PASS, 3 FAIL
- FAIL: `1/items/inlineFilters/apply`, `1/category/tree/items`, `1/sf/conditions/get` — могут быть renamed/deprecated

**Section 2 — Data class signatures:** 18/18 PASS ✓

**Section 3 — Numeric IDs:**
- `491590` (Apple), `469735` (iPhone 12 Pro Max), `110617`/`110618`/`110680` (param IDs) — **0 hits в DEX as plain text** (server-side only)
- `637640` (locationId Москва) — 446 hits в classes6 (hardcoded в ad targeting JSON)
- `621540` (locationId всей России) — 7 hits

**Section 4 — Predicted method names:** 15/21 found
- ✅ `apiNewCarsFilterBrands/Models/Apply`, `subscriptionMobileUpdateV4`, `subscriptionsMobileListV2/Filter`, `proFiltersInitV1`, `api3NdTrxSearchParamsGet`, `apiDictsSuggestRegNumByPhoto`, `apiDictsSuggestVinByRegNum`, `suggestParamsApiV2`, `api1PromoCategoryTree(Items)`, `userInfo`
- ❌ `apiDictsParameters`, `getDictsParameters`, `dictsParameters`, `apiInlineFilters`, `apiSearchInlineFilters` — **all missing** (`15/dicts/parameters` declaring class TBD)
- ⚠ `getInlineFilters` — найдено в classes3, 14 (но **не в Api class** — likely Kotlin getter, не Retrofit method)
