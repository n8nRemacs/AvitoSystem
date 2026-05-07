# Search Query Formation — Web URL → Mobile API

**Создано:** 2026-05-07
**Обновлено:** 2026-05-07 — добавлены эмпирические находки по QRATOR и categoryId
**Назначение:** как корректно конвертировать поисковый URL из браузера Avito в запрос к Avito mobile API так, чтобы получать **те же** результаты что показывает Avito-app, а не fuzzy-text мусор.

---

## ⚡ Эмпирические находки 2026-05-07 (live curl tests)

Прямые тесты `curl_cffi chrome120` против `https://app.avito.ru/api/11/items` со свежим JWT через
SOCKS5-туннель (155.212.217.226 = phone-IP):

| Параметр запроса | HTTP status | Что в body |
|---|---|---|
| `query=test` (без categoryId) | **200** | count=28296, real listings — есть |
| `query="Iphone 12 Pro Max"` (без categoryId) | **200** | count=12808, в первой выдаче iPhone 17 Pro Max и др. реальные iPhone'ы |
| `query=...&categoryId=84` (mobile id) | **403** | `{"too-many-requests": "Доступ с вашего IP-адреса временно ограничен"}` |
| `query=...&categoryId=87` (web id) | **403** | то же |
| `query=...&categoryId=84&params[110617][0]=491590&params[110618][0]=469735` | **403** | то же |
| `query=...&category_id=84` (snake_case) | **403** | то же |
| `/15/items?...` (любой вариант) | **403** | `/15` — другой эндпоинт, наш токен туда не пускают |
| Структурный запрос с deeplink-style params БЕЗ query | **403** | без полного set'а structured params Avito отклоняет |

**Выводы:**
1. **`categoryId` любого значения на `/11/items` без полного structured-params set'а → QRATOR 403.** Это не cooldown, это детект «бот-формат запроса». Даже с правильным mobile-id `84` и парой brand/model (но без всех нужных фильтров категории).
2. **`/11/items` без categoryId — нормальная text-search**, отдаёт реальные iPhone'ы. Для V1 fuzzy-text+post-filter это рабочий путь.
3. **`/15/items` — другой контракт**, наш токен/набор headers'ов туда не подходит.
4. **Avito-app шлёт `categoryId` ТОЛЬКО** когда у него есть полный набор structured params (brand+model+state+etc.) — это subscription-deeplink контекст. Передавать `categoryId` голым без brand/model — антипаттерн, который QRATOR ловит.

### Минимальный фикс для прямого `search_items()`

В `avito-xapi/src/workers/http_client.py:170-220` дропнуть `categoryId` из URL params для не-subscription запросов. Subscription flow (вариант B ниже) шлёт categoryId через `params_extra=` уже с brand+model id'ами и работает.

---

## ⚡ Эмпирические находки 2026-05-07 (QRATOR per-(token, IP) binding)

Подтверждённая дублирующая корреляция:

| origin IP | new token (родился на phone-IP) | old token (прожил сутки на VPS-IP) |
|---|---|---|
| VPS 81.200.119.132 (direct egress) | 403 captcha | 200 OK |
| ru-vpn 155.212.217.226 (= phone outbound) | 200 OK | 403 captcha |

**Толкование:** QRATOR (firewall Avito) хранит trust-score per **(JWT, IP)**. JWT, выпущенный для Avito-app на телефоне, валиден ТОЛЬКО с того IP, на котором телефон сидит в инете в момент его выпуска. Использовать этот же JWT с другого IP = 403 captcha-challenge с первого запроса. После 2-3 captcha-403'ов токен залочивается на all-IP в QRATOR (нужен cooldown ~30-60 мин или новый токен).

**Архитектурное следствие:** все исходящие запросы к Avito из xapi должны выходить с того IP, на котором живёт Avito-app. У нас:
- VPS 81.200.119.132 → ssh -D 172.18.0.1:1081 → ru-vpn 155.212.217.226 → Avito
- systemd unit: `/etc/systemd/system/avito-vpn-tunnel.service` (Restart=always)
- env: `AVITO_SOCKS_PROXY=socks5h://172.18.0.1:1081` в `/opt/avito-system/.env`
- `avito-xapi/src/workers/base_client.py` читает env и пробрасывает `proxies=` в `curl_cffi.Session`

**Когда это сломается:**
- ru-vpn IP сменится → весь pool токенов мгновенно тухнет, нужны новые JWT
- Avito-app на телефоне переключится на другой VPN-выход → правим SOCKS_PROXY на новый IP
- QRATOR изменит rules

См. memory `reference_qrator_token_ip_binding.md` для дублирующей фиксации.

---

## TL;DR корня проблемы

Avito имеет **два разных search backend'а**:

| Что использует | Какой endpoint | Какие фильтры | Качество результатов |
|---|---|---|---|
| **Браузер (web)** | URL вида `/all/.../iphone_12_pro_max-ASgB...?f=AS...&pmin=...` | base64 protobuf token `f=AS...` декодит сервер | Точное (Avito декодит token на бэке) |
| **Avito-app (mobile)** | `GET /15/items` или `/11/items` | structured query `params[110617][0]=491590&params[110618][0]=469735&priceMin=...` | Точное (вход уже структурирован) |
| **Наш xapi сейчас** | `/api/v1/search/items?query=...&category_id=...` (free-text + categoryId) | extracted из URL slug: `query="Iphone 12 Pro Max"`, `categoryId=87` | **Fuzzy → мусор** (формы для склейки стекла, рюмки Beluga, чайники) |

**Корень:** наш URL parser извлекает только текстовый brand+model из slug-а и dropит весь structured filter `f=AS...`. Avito mobile-API без structured params отдаёт fuzzy-результаты.

---

## Доступные пути исправления (3 варианта)

### Вариант A — декодить web URL filter blob (`f=ASgB...`) → structured params

**Идея:** распаковать base64 protobuf и получить из него `params[110617][0]=491590` напрямую без захода в Avito-app.

**Что есть:**
- `_is_filter_token` в `avito-monitor/app/services/url_parser.py:101-110` — детектит token (исправлен 2026-05-07: mixed-case + digit, чтобы не ловить slug'и типа `iphone_12_pro_max`)
- Token извлекается + строкой выкидывается. Декодирование **не реализовано**.

**Что нужно:**
- **Protobuf schema** — Avito не публикует. Реверс через jadx (find класс который сериализует filter) + Frida hook'и. Не делалось.
- **Brand/model ID maps** — в `DOCS/avito_api_snapshots/phone_catalog.xml` есть **только текстовые названия** 524 брендов + 16'149 моделей, **без числовых ID**. ID'ы (491590=Apple, 469735=iPhone 12 Pro Max) приходят только из mobile API ответов (`/2/subscriptions/{filterId}.deepLink`).

**Цена:** 8-15 часов реверса. Высокая хрупкость — Avito может менять token формат.

**Когда брать:** если автономность важнее цены reverse-engineering'а.

---

### Вариант B — Subscription flow (текущая правильная архитектура)

**Идея:** юзер сохраняет поиск в Avito-app как «🔔 autosearch» → наш xapi `GET /5/subscriptions` импортирует список subscription_id'ов и `GET /2/subscriptions/{filterId}.deepLink` для каждого получает уже-декодированный `params[110617][0]=491590&params[110618][0]=469735&priceMin=11000&priceMax=13500&...`.

**Что есть:**
- `avito-xapi/src/routers/subscriptions.py:65-84` — `_parse_deeplink_to_search_params()` парсит deeplink в dict готовый к передаче в `/15/items` через `params_extra=`.
- `avito-xapi/src/routers/subscriptions.py:152-228` — `get_subscription_items()` endpoint полный flow.
- `avito-monitor/app/services/autosearch_sync.py` — импорт subscriptions с Avito + auto-создание SearchProfile с `import_source='autosearch_sync'`, `avito_autosearch_id=...`, `owner_account_id=...`
- Polling Task 3 (commit `5e2d0b2`, 2026-05-06) — owner-aware claim для autosearch профилей; `fetch_subscription_items(int(profile.avito_autosearch_id))`
- Live-validated пример deeplink с реальными ID:
  ```
  ru.avito://1/items/search?categoryId=84&geoCoords=55.755814,37.617635
    &locationId=621540&params[110617][0]=491590&params[110618][0]=469735
    &params[110680]=458500&priceMax=13500&priceMin=11000&sort=date&withDeliveryOnly=1
  ```
  - `categoryId=84` — Мобильные телефоны (mobile API использует другой ID чем web `87` — see B.1 ниже)
  - `params[110617][0]=491590` — Производитель = Apple
  - `params[110618][0]=469735` — Модель = iPhone 12 Pro Max
  - `params[110680]=458500` — состояние/пробег parameter
  - `priceMin/priceMax`, `withDeliveryOnly`, `sort=date`

**Что нужно от юзера:**
- В Avito-app под `157920214`: «🔔 сохранить поиск» с фильтрами model + цена
- В нашем UI: кнопка «Sync autosearches» (`POST /search-profiles/sync`)
- Polling автоматически берёт subscription_id

**Чего сейчас не хватает:**
- Свежий JWT (TTL > 30 минут) — без него `GET /5/subscriptions` Avito 403'ит. Сейчас все наши JWT expire через 7-15 минут и не обновляются автоматически (см. §refresh-gap ниже)
- Робастный **pull-based refresh-flow** чтобы JWT всегда был свежим (см. backlog).

**Цена:** ничего нового реализовывать не надо — flow уже зашиплен. Нужно только починить refresh-flow + manual setup в Avito-app.

**Когда брать:** **рекомендуется как primary path**.

---

### Вариант C — capture mobile-app traffic через rooted phone (mitm)

**Идея:** настроить mitmproxy/Frida на phone'е (OnePlus 8T `110139ce`, root через Magisk) → перехватить **реальные** запросы Avito-app к `/15/items` со structured `params[...]` → дамп в JSON → подставлять как ground truth для нашего xapi.

**Что есть в репе:**
- `DOCS/REFERENCE/04-reverse-engineering-howto.md` — методология (jadx + curl_cffi + Frida + QRATOR обходы)
- `DOCS/REFERENCE/03-android-setup.md` — Magisk + ADB + System Clone
- `avito-farm-agent/` — Python+JS Frida агент для перехвата токенов (есть pinning bypass в `frida_scripts/`). Можно расширить hook'ом на `okhttp3.Request.Builder.url()` чтобы дампить URL+headers+params каждого запроса.
- **БЫЛИ предыдущие capture'ы** (юзер: «мы это уже делали»), но в репе артефакты не нашлись — могут быть в локальных temp'ах ноута или удалены.

**Что нужно:**
- Запустить mitmproxy с Magisk-trusted CA на phone'е
- Открыть Avito-app, сохранить поиск iPhone 12 Pro Max, открыть его → mitm перехватит `GET /15/items?params[110617][0]=491590&params[110618][0]=469735&...`
- Дампить `params[*]` как JSON (можно прямо в БД)
- В polling.py сделать поле `profile.avito_search_params` (JSONB), polling передаёт его в `params_extra=` для search/items

**Цена:** 2-4 часа (если mitm setup ещё работает на phone)

**Когда брать:** если хочется **точно** видеть что Avito-app отправляет — для построения параметр-id mapping table или дебага одного конкретного запроса.

---

## Параметр-ID'ы (известные)

Mobile API использует numeric parameter IDs. Известно:

| ID | Параметр | Значение пример |
|---|---|---|
| 110617 | Производитель (brand) | 491590 = Apple |
| 110618 | Модель (model) | 469735 = iPhone 12 Pro Max |
| 110680 | Состояние/пробег | 458500 (TBD) |
| (categoryId top-level) | Категория | mobile=`84`, web=`87` |

Полный список параметр-id'ов и их допустимые значения **не задокументирован**. Получаются только через subscription deeplink или mobile traffic capture.

### Mobile vs Web categoryId

В mobile API `categoryId=84` для «Мобильные телефоны». В web URL slug `mobilnye_telefony` маппится на `87`. Это **разные таксономии**:
- `_CATEGORY_SLUG_TO_ID` в `avito-monitor/avito_mcp/tools/search.py:20-27` мапит web slug → web id (87 для phones)
- mobile использует `84` для тех же phones

**Bug в текущем коде:** при URL-based polling мы шлём `category_id=87` (web id) в mobile API endpoint `/15/items` который ожидает `84`. Это объясняет часть фрустрации Avito search'а — он матчит **не ту категорию**. Нужен либо отдельный mapping web_id→mobile_id, либо взять categoryId из deeplink (Subscription flow всё это делает).

---

## Refresh-flow gap (блокер для всех 3 вариантов)

JWT для Avito mobile-API имеет TTL = 24 часа. Avito **403'ит запросы с TTL < ~30 минут** — заставляет клиентов refresh заранее.

**Текущая модель (push-only):**
- Avito-app сам refresh'ит JWT когда видит near-expiry
- APK `com.avitobridge.sessionmanager` ловит push-notification от Avito-app и POST'ит свежий JWT в наш xapi `/api/v1/sessions`
- **Проблема:** Avito-app рефрешит JWT **молча**, без push-notification, при internal-trigger'е (открытие приложения, action). APK ничего не ловит → у нас остаётся stale JWT → Avito 403.

**Реально работающий trigger refresh flow для phone:**
1. **Logout/login full-flow в Avito-app** — Avito-app **обязательно** показывает push-notification при поступлении нового JWT после login → APK перехватит → POST к xapi.
2. Просто «открыть Avito-app» — refresh может произойти молча, push не гарантирован.

**Долгосрочное решение (план):** pull-based refresh-flow — xapi помечает `refresh_requested_at` на account когда видит TTL<30min, APK пуллит endpoint `GET /api/v1/sessions/refresh-pending` каждые 60s, читает SharedPrefs Avito-app `/data/user/{X}/com.avito.android/shared_prefs/com.avito.android_preferences.xml`, POST'ит свежий JWT либо `POST /refresh-failed` если SharedPrefs тоже expired → xapi шлёт TG алерт.

Estimate: ~10ч (xapi 4ч + APK 4ч + TG/e2e 1ч + deploy 1ч).

---

## Что было исправлено сегодня (2026-05-07)

Коммиты на main, все деплоено:

| SHA | Что |
|---|---|
| `3cca3d0` | url_parser: filter token regex tighter — не ловит lowercase model slug'и (`iphone_12_pro_max` больше не считается filter token'ом, brand/model теперь корректно extract'ятся) |
| `4a0e67a` | xapi: `QueryBuilder.gt/gte/lt/lte` — было пропущено в кастомном httpx wrapper'е, Task 1 предикат крашился AttributeError |
| `042faf1` | xapi `POST /sessions`: свежая сессия flip'ит state from `cooldown`/`needs_refresh`/`waiting_refresh` → `active` (раньше только `waiting_refresh`) |
| `dc91ce5` | (1) xapi search.py: surface upstream Avito 4xx as same status (раньше всё было 500). (2) polling.py: post-filter listings'ов по brand+model tokens (отбрасывает мусор) + self-heal `parsed_brand/parsed_model` re-parse on-the-fly. |
| `a0f4bd2` | UI: timestamps в browser-local TZ через `<time data-utc>` + js converter в base.html |
| `804bc57` | (Merge) Account pool hardening A+B+C: liveness predicate, cooldown auto-recovery, owner-aware claim |

---

## Где ещё посмотреть

| Файл | Что |
|---|---|
| `DOCS/REFERENCE/01-avito-api.md` §B (lines 76-118) | mobile search endpoints `/11/items`, `/15/items`; их params |
| `DOCS/avito_api_snapshots/autosearches/README.md` | реверс `/2/subscriptions/{filterId}` с live-validated deeplink-примером |
| `DOCS/avito_api_snapshots/phone_catalog.xml` (6.8 МБ) | 524 brand + 16K model — names only, no IDs |
| `DOCS/REFERENCE/04-reverse-engineering-howto.md` | методология реверса (jadx + Frida + curl_cffi + QRATOR) |
| `avito-monitor/app/services/url_parser.py` | существующий URL parser (web → текстовые поля) |
| `avito-xapi/src/routers/subscriptions.py:65-84` | `_parse_deeplink_to_search_params()` готовый |
| `avito-monitor/app/services/autosearch_sync.py` | autosearch import flow |
| `avito-monitor/avito_mcp/tools/search.py:20-42` | `_CATEGORY_SLUG_TO_ID` + `_BRAND_CATEGORY_MODEL_HINT` |

---

## Action items для следующей сессии

1. **Починить refresh-flow** — без свежих JWT нельзя пройти ни один из 3 вариантов. Pull-based flow detailed выше. **Блокер для всего остального.**
2. **Subscription flow end-to-end** — после refresh-flow юзер создаёт autosearch в Avito-app → sync импортирует → polling работает с точными `params[brand][model]`.
3. **Вариант C (mitm capture)** — опционально, для построения brand/model ID mapping (если хочется sometime поддержать URL-based профили без subscription).
4. **Web vs mobile categoryId** — добавить `_WEB_TO_MOBILE_CATEGORY` mapping в search.py, либо дропать `category_id` из URL-based search и полагаться только на text query до получения structured params.
