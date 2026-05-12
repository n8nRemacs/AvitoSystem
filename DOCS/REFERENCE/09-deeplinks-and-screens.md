# Avito Mobile App — Deep Links & Screens

**Создано:** 2026-05-08 (перенесено из `Reverse Avito/findings/04-deeplinks-and-screens.md`)
**Источник:** classes*.dex from APK Avito Android v222.5

**Связано:**
- `01-avito-api.md` §B.3 — subscription endpoints (`GET /api/2/subscriptions/{filterId}` returns deepLink)
- `06-structured-params-discovery.md` §1 — известные ID в subscription deeplinks
- `08-data-models.md` — `DeepLink` data class with 96+ subtypes
- Raw scan output: `Reverse Avito/findings/raw/deeplinks_paths.txt`

---

## Distinct deep-link paths (deduped)

После удаления 181 test-fixture instances `1/item/show?...` (одинаковый context tag с image samples), остаётся **5 уникальных** paths:

| Path | Params | Назначение |
|---|---|---|
| `ru.avito://1/item/show` | `context`, `fromPage`, `image`, `itemId` | Open one item by ID |
| `ru.avito://1/beduin/v2/universalPage` | (varies — server-driven) | Server-driven UI page (Beduin engine) |
| `ru.avito://1/beduin/v2/universalPage/bottomSheet` | (varies) | Beduin bottom sheet |
| `ru.avito://1/globalCategories` | `categoryId`, `categoryName` | **Global categories screen** ⭐ — opens filter UI |
| `ru.avito://1/gigger/kyc/esia/webview` | `authUrl` | KYC gov-ID webview |

> ⚠ 96 deeplinks в `Reverse Avito/findings/raw/deeplinks.txt` — это в основном **bundled test fixtures** (sample `item/show` URLs со random `context` tokens used in deeplink-handler unit tests). Реальный deeplink schema — much wider (each Avito screen has its own pattern), но **template strings** (с `{itemId}` etc.) НЕ в DEX — они constructed at runtime из class-based `DeepLink` subtypes.

---

## DeepLink subtypes (96+ классов)

`Lcom/avito/android/deep_linking/links/DeepLink` — base sealed class. Subtypes scattered across DEX, named by screen:

Examples found via class signatures:
- `SearchDeepLink` — для `ru.avito://1/items/search?...` (autosearch deeplink)
- `ItemShowDeepLink` — для `ru.avito://1/item/show?itemId=...`
- `GlobalCategoriesDeepLink` — для `ru.avito://1/globalCategories?...`
- `CategoriesGlobalDeepLink` — variant of above (in `categories_global/` package)
- many more in `category_items_tree/screens/...`

Full DeepLink subtype enumeration не сделана.

---

## Subscription deeplinks (relevant for AvitoSystem)

Главные deep links — это те, что embedded в **subscription `deepLink` field** (returned from `GET /api/2/subscriptions/{filterId}`):

```
ru.avito://1/items/search?categoryId=84
  &geoCoords=55.755814,37.617635
  &locationId=621540
  &params[110617][0]=491590    # brand=Apple
  &params[110618][0]=469735    # model=iPhone 12 Pro Max
  &params[110680]=458500       # condition (TBD value)
  &priceMax=13500
  &priceMin=11000
  &sort=date
  &withDeliveryOnly=1
```

**Structured-search payload.** Метод `SubscriptionListMobileApi.getDeepLink()` возвращает это как `DeepLink` (см. `08-data-models.md` для data class).

---

## Deeplink data flow (inferred)

1. User opens `ru.avito://1/globalCategories?categoryId=84` from another deeplink
2. App resolves to `GlobalCategoriesDeepLink` instance
3. Fetches filter taxonomy для category 84 (via some endpoint — `15/dicts/parameters` candidate? см. `06-structured-params-discovery.md`)
4. Renders filter UI с `ParameterElement` widgets driven by `SimpleParametersTree` / `SelectParameter` data
5. User picks brand=Apple → app POSTs filters → server responds с available models
6. User picks model=iPhone 12 Pro Max → continues filtering
7. User saves search → POST `4/subscription` со всеми params → server returns filterId
8. From now on `GET /api/2/subscriptions/{filterId}` returns the structured deeplink

**The endpoint that returns per-category filter taxonomy** is what we need — это catalog discovery target.

---

## Why deeplinks alone aren't enough

Subscription deeplink содержит IDs (491590=Apple, 469735=iPhone 12 Pro Max), но только **после** того как user manually picks них в UI. Чтобы получить IDs для **любой** iPhone модели, нужен один из:

1. **Subscription mining** — user creates subscription per model в Avito-app; мы extract IDs из каждого deeplink (manual labour) — см. `06-structured-params-discovery.md` §3.A
2. **Catalog endpoint** — single API call returns all brand+model IDs для категории (что `15/dicts/parameters` hypothesized to be) — см. `06-structured-params-discovery.md` §5
3. **mitmproxy** on phone — capture network call when user opens filter UI (most reliable but requires SSL pinning bypass) — см. `04-reverse-engineering-howto.md`

---

## Beduin (server-driven UI)

`ru.avito://1/beduin/v2/universalPage` — точка входа в Avito's **Beduin** UI engine. Server возвращает full UI tree (components, layout, actions) и client renders.

**Implications для catalog discovery:**
- Если filter screens переехали в Beduin, то response от Beduin endpoint **сам по себе содержит filter taxonomy** (не отдельный `dicts/parameters` call)
- Это объяснило бы почему `15/dicts/parameters` (старый API) больше не declared в auto-generated Retrofit interfaces
- Тестовый запрос: `GET /api/.../beduin/v2/universalPage?screen=filters&categoryId=84`

`ReputationApi.reputationV1Beduin(...)` — confirmed Beduin endpoint в `07-retrofit-api-classes.md`.

`SellerRoomApi.getDealBeduin(...)` — другой Beduin endpoint.

---

## Hardcoded location IDs (from DEX cross-validation)

| ID | Location | DEX hits |
|---|---|---|
| `621540` | вся Россия | 7 hits (classes6, 12, 13, 15) |
| `637640` | Москва | 446 hits (classes6 — hardcoded в ad targeting JSON) |

`621540` появляется в:
- `"!falseResult": "621540"` (classes6 — fallback/default location)
- Default location при отсутствии geo-coords

`637640` — главный default для ad-targeting:
- `"locationId": 637640` (classes6 — many JSON snippets)
- `"g_city": 637640, "g_reg": 637640` (classes6 — ad-server params puid21=85, etc)

Подтверждает что Москва — primary market для Avito (как ожидалось).

---

## Mobile vs Web categoryId

**Already documented в `01-avito-api.md` §B.1 + `05-search-query-formation.md`.**

- Mobile API: `categoryId=84` для «Мобильные телефоны»
- Web URL slug: `mobilnye_telefony` → web id `87`
- Это **разные таксономии** — переиспользовать ID нельзя

`84` найден в DEX в массе мест (classes.dex 39 hits, classes11 152 hits, classes6 190 hits). `87` ещё чаще (classes13 676, classes6 511 hits). Оба используются параллельно (для разных endpoints / контекстов).
