# Avito API Reference

**Компилировано:** 2026-04-28
**Источники:** AVITO-API.md, REVERSE-GUIDE.md, AVITO-FINGERPRINT.md, X-API.md, AvitoAll/API_AUTH.md,
  avito_api_snapshots/autosearches/README.md, avito-xapi/src/workers/base_client.py,
  avito-xapi/src/workers/http_client.py, avito-xapi/src/routers/subscriptions.py

---

## A. Mobile API — базовые параметры

**Base URL:** `https://app.avito.ru/api`

**Протокол:** `curl_cffi` с `impersonate="chrome120"`.
Без TLS-impersonation QRATOR-firewall блокирует запросы (определяет по JA3/JA3S fingerprint).
Нельзя заменить на `httpx` или `aiohttp`.

Источник: `avito-xapi/src/workers/base_client.py:11`

### Обязательные заголовки (все запросы)

```
User-Agent:       AVITO 215.1 (OnePlus LE2115; Android 14; ru)
X-Session:        {JWT_TOKEN}             # HS512, 24h TTL
X-DeviceId:       {device_id}             # 16 hex chars, из SharedPrefs
X-RemoteDeviceId: {remote_device_id}      # base64 строка, из SharedPrefs
f:                {fingerprint}           # A2.{hex 256+ chars}, КРИТИЧНО
X-App:            avito
X-Platform:       android
X-AppVersion:     215.1
Content-Type:     application/json
Cookie:           sessid={JWT}; 1f_uid={uuid}; u={val}; v={timestamp}
X-Date:           {unix_timestamp_seconds}
Accept-Encoding:  zstd;q=1.0, gzip;q=0.8
```

Дополнительные (присутствуют в захваченном трафике):
```
X-Geo:              {lat};{lng};{accuracy};{timestamp}   # опционально
X-Supported-Features: helpcenter-form-46049
AT-v:               1
Schema-Check:       0
```

Откуда берутся значения — см. `02-auth-and-tokens.md §A`.

Источник реализации: `avito-xapi/src/workers/base_client.py:22-43`

### QRATOR Anti-bot защита

Avito использует QRATOR с несколькими уровнями детекции:
1. **TLS Fingerprint (JA3/JA3S)** — порядок и параметры TLS handshake
2. **HTTP/2 Fingerprint** — порядок и параметры HTTP/2 фреймов
3. **Заголовки** — обязательное наличие `f`, `X-DeviceId`, `X-Session`
4. **Паттерны запросов** — timing, частота

Симптом блокировки: HTTP 400 `"Пожалуйста, используйте приложение или авторизуйтесь через avito.ru"`.

При 429: backoff 30 секунд (настраивается через `settings.rate_limit_burst`).

OkHttp Interceptors Chain (из jadx-анализа APK v215.1):
```
1. session_refresh.h      — управление сессией
2. captcha.interceptor.g  — обработка капчи
3. interceptor.Z0         — User-Agent
4. interceptor.g0         — основные заголовки
5. zstd.j                 — zstd сжатие
6. interceptor.x          — certificate pinning
7. interceptor.D          — X-Date заголовок
```

---

## B. Список Endpoints

### B.1 Поиск объявлений

**`GET /api/11/items`** — поиск по параметрам

| Параметр | Тип | Описание |
|---|---|---|
| `query` | string | Поисковый запрос (обязателен, но может быть `" "`) |
| `page` | int | Страница (default 1) |
| `count` | int | Кол-во результатов (max ~30) |
| `locationId` | int | ID региона (621540 = вся Россия, 637640 = Москва) |
| `categoryId` | int | ID категории (84 = Мобильные телефоны) |
| `priceMin` | int | Минимальная цена |
| `priceMax` | int | Максимальная цена |
| `sort` | string | Сортировка (`date`, `price_asc`, `price_desc`) |
| `withDelivery` | bool | Только с Авито Доставкой |
| `params[110617][0]` | string | Structured filter (brand ID, model ID и т.д.) |
| `params_extra` | dict | Любые дополнительные params — передаются через `params_extra` в `search_items()` |

Ответ (ключевые поля):
```json
{
  "result": {
    "items": [
      {
        "type": "item",
        "value": {
          "id": "7867391303",
          "title": "iPhone 12 Pro, 128 ГБ",
          "price": {"current": "15 000 ₽"},
          "galleryItems": [{"value": {"678x678": "https://..."}}],
          "isDeliveryAvailable": true,
          "sellerInfo": {"userKey": "abc123"}
        }
      }
    ],
    "totalCount": 150,
    "mainCount": 150
  }
}
```

**ВАЖНО:** Мобильный API (11/items) принимает только **structured params** (`categoryId`, `params[…]`), но НЕ `f=` blob из веб-URL. Веб и мобильный API — разные бэкенды. Передача веб-URL без structured params даёт fuzzy-match с посторонними лотами.

Используется в: `avito-xapi/src/workers/http_client.py:170`, `avito-monitor/avito_mcp/integrations/xapi_client.py:88`

Наш endpoint: `GET /api/v1/search/items` (xapi)

---

### B.2 Карточка объявления

**`GET /api/19/items/{item_id}`** — детали лота

Используется в: `avito-xapi/src/workers/http_client.py:224`

Ответ содержит полное описание, все фото, информацию о продавце. Точный формат ответа не задокументирован в старых файлах — помечено как `TODO: перехватить через Frida при открытии объявления`.

Наш endpoint: `GET /api/v1/search/items/{id}` (xapi)

---

### B.3 Сохранённые поиски (Autosearches / Subscriptions)

Avito называет их `subscriptions` в mobile API, `autosearch` в веб-интерфейсе.
Идентификатор: `filterId` (Long).

Источник реверса: статический анализ Avito-app v222.5 (jadx), APK `base.apk` 357 МБ.
Источник: `DOCS/avito_api_snapshots/autosearches/README.md`

---

**`GET /api/5/subscriptions`** — список autosearches пользователя  ✅ live-validated

Без параметров. Возвращает все сохранённые поиски залогиненного юзера.

Ответ:
```json
{
  "success": {
    "items": [
      {
        "id": 264239719,         // filterId (Long)
        "ssid": 459778524,       // вторичный id
        "title": "IPhone 12 pro max",
        "description": "Все регионы, Телефоны, Производитель: Apple, ...",
        "deepLink": "",
        "editAction": "ru.avito://1/searchSubscription/show?categoryId=84&...",
        "openAction": "ru.avito://1/searchSubscription/open?...",
        "hasNewItems": false,
        "pushFrequency": 0       // 0=no push, 1=push enabled
      }
    ]
  }
}
```

**Важно:** `description` — только human-readable текст. Structured params отсутствуют. Для точной выдачи нужен следующий endpoint.

Используется в: `avito-xapi/src/workers/http_client.py:235`, `avito-xapi/src/routers/subscriptions.py:59`

---

**`GET /api/2/subscriptions/{filterId}`** — deeplink с точными search params  ✅ live-validated

Это ключевой endpoint для polling без мусора (ADR-011).

Ответ:
```json
{
  "status": "ok",
  "result": {
    "deepLink": "ru.avito://1/items/search?categoryId=84&geoCoords=55.755814,37.617635&locationId=621540&params[110617][0]=491590&params[110618][0]=469735&priceMax=13500&priceMin=11000&sort=date&withDeliveryOnly=1"
  }
}
```

Парсим query-string из deepLink → кормим в `search_items()` через `params_extra`:
```python
# avito-xapi/src/routers/subscriptions.py:36-55
def _parse_deeplink_to_search_params(deeplink: str) -> dict[str, Any]:
    parts = urlsplit(deeplink)
    qs = parts.query or deeplink.split("?", 1)[1]
    raw = parse_qs(qs, keep_blank_values=True)
    # Flatten singletons, keep bracket keys as-is
```

Используется в: `avito-xapi/src/workers/http_client.py:253`, `avito-xapi/src/routers/subscriptions.py:75`

---

**`GET /api/subscriptions/{filter_id}/items`** — items через xapi  ✅

Наш xapi endpoint. Под капотом: `get_subscription_deeplink(filter_id)` → parse → `search_items(**params)`.
Отдаёт точно такую же выдачу как Avito-веб показывает пользователю в autosearch — без fuzzy-match мусора.

Используется в: `avito-xapi/src/routers/subscriptions.py:115`, `avito-monitor/avito_mcp/integrations/xapi_client.py`

---

**`GET /api/2/subscriptions/count_with_new_items`** — счётчик новых  ✅ live-validated

```json
{"result": {"count": 5}, "status": "ok"}
```

---

**`PUT /api/4/subscriptions/{filterId}`** — обновить настройки подписки  (из jadx)

Body (`pu0.d`):
```json
{
  "emailFrequency": "instant"|"daily"|"weekly"|null,
  "isEmailEnabled": true|false|null,
  "isPushAllowed": true|false|null,
  "isPushEnabled": true|false|null,
  "title": "iPhone 12 Pro Max"
}
```

Ответ: `{"id": 12345678, "searchSubscriptionAction": "avito://..."}`. Не нужен в V1.

---

**`POST /api/4/subscription`** — создать подписку (form-encoded)  (из jadx)

Не нужен в V1 (мы только зеркалим Avito→нас, не создаём на Avito).

---

**`DELETE /api/2/subscriptions/{subscriptionId}`** — удалить подписку  (литерал из DEX)

Не нужен в V1.

---

### B.4 Мессенджер HTTP REST

Base URL: `https://app.avito.ru/api/1/messenger/`
Авторизация: полный набор заголовков (раздел A).
Rate limit: ~2 секунды между запросами, 429 → backoff 30 сек.

| Endpoint | Метод | Что делает |
|---|---|---|
| `/getChannels` | POST | Список чатов. `category=1` (все). `category=0` → 500! |
| `/getUserVisibleMessages` | POST | История сообщений канала |
| `/sendTextMessage` | POST | Отправить текст (`idempotencyKey=uuid-v4`) |
| `/getChannelById` | POST | Один канал по ID |
| `/readChats` | POST | Пометить прочитанным (`channelIds: [...]`) |
| `/typing` | POST | Индикатор набора |
| `/createItemChannel` | POST | Создать чат по itemId |
| `/createUserChannel` | POST | Создать чат по userHash |
| `/getUnreadCount` | POST | Счётчик непрочитанных |

**Важная ловушка:** Текст сообщения в HTTP REST — `body.text.text` (двойная вложенность).
В WebSocket push — `body.text` (одинарная). Разные форматы!

Источник реализации: `avito-xapi/src/workers/http_client.py:14-124`

---

### B.5 Мессенджер WebSocket JSON-RPC

**WS URL:** `wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}`

КРИТИЧНО: без `id_version=v2` и `my_hash_id` → `Forbidden (-32043)`.

Ping каждые 25 сек: `{"method": "ping", "params": {}}`.

Ключевые методы:
- `avito.getChats.v5` — список чатов
- `avito.sendTextMessage.v2` — отправка
- `messenger.history.v2` — история
- `messenger.readChats.v1` — прочитать

Push-события от сервера: `Message`, `ChatTyping`, `ChatRead`, `ChannelUpdate`, `MessageDelete`.

Источник: `DOCS/AVITO-API.md` Блок 3-4.

---

### B.6 Авторизация (для справки, мы НЕ используем)

**`POST /api/11/auth`** — логин через пароль (form-urlencoded)

```
login=+7XXXXXXXXXX&password=xxxxx&token=<firebase>&isSandbox=false&fid=<tracker_uid>
```

ВНИМАНИЕ: дополнительно защищён QRATOR, требует firebase token. Мы НЕ используем этот endpoint — вместо этого извлекаем токены из SharedPreferences через root.

Источник: `DOCS/AVITO-API.md` Блок 1, `AvitoAll/API_AUTH.md`.

---

### B.7 Call Tracking (IP-телефония)

Base URL: `https://www.avito.ru/web/1/calltracking-pro/`
Авторизация: только cookie `sessid` (без fingerprint `f`).

- `POST /history` — история звонков (dateFrom, dateTo, limit, offset)
- `GET /audio?historyId={id}` — скачать MP3 записи

Источник реализации: `avito-xapi/src/workers/http_client.py:128-166`

---

## C. Catalog Endpoints (Official API)

**Base URL:** `https://api.avito.ru`
**Auth:** OAuth2 client_credentials (Bearer token), не реверс-инжиниринг.

Использовалось для снятия snapshots в 2026-04-25. В V1 **не используется**.

| Endpoint | Что | Файл snapshot |
|---|---|---|
| `GET /autoload/v1/user-docs/tree` | Полное дерево категорий | `DOCS/avito_api_snapshots/categories_tree.json` |
| `GET /autoload/v1/user-docs/node/{slug}/fields` | Поля категории для autoload | `fields_mobilnye_telefony.json` и др. |

XML-каталоги (требуют RU IP, QRATOR):
- `phone_catalog.xml` (6.8 МБ) — 524 бренда, 16149 моделей телефонов
- `tablets.xml` (2 МБ) — 486 брендов, 7391 модель
- `brendy_fashion.xml` (336 КБ) — 7522 fashion-бренда

Структура телефонного каталога: `Vendor → Model → MemorySize → Color → RamSize`.

**Важное ограничение:** Официальный API даёт поля для autoload (размещения объявлений), но НЕ полный список фильтров поиска. Числовых `categoryId` нет — только строковые slug'и.

Источник: `DOCS/avito_api_snapshots/README.md`

---

## D. Official Avito Business API

В V1 **не используется**. Credentials хранятся в `.env` для V2.

Официальный API (`api.avito.ru`) покрывает:
- Свои объявления (`/core/v1/items`) — ТОЛЬКО свои, не чужие
- Статистика, баланс, услуги продвижения
- Мессенджер (официально, V2)
- Autoload taxonomy

**Поиск чужих объявлений доступен ТОЛЬКО через реверс mobile API.**

Источник: `DOCS/DECISIONS.md` ADR-003.

---

## E. Rate Limiting (наша конфигурация)

Текущие настройки xapi (по состоянию на 2026-04-28):
- `rate_limit_rps = 1.0` (1 запрос/сек к Avito)
- `rate_limit_burst = 3`
- Backoff при 429: 30 сек

Реализация: `avito-xapi/src/workers/rate_limiter.py` (TokenBucket)

**Эмпирический лимит:** 14 запросов к `/N/subscriptions` за 5 сек → ban аккаунта.
Источник: `CONTINUE.md §3` (инцидент 2026-04-28).

---

## F. Fingerprint — структура и невозможность генерации

Заголовок `f`:
- Формат: `A2.{256+ hex символов}`
- Хранение: SharedPreferences ключ `fpx`
- Генерация: нативная библиотека `com.avito.security.libfp.FingerprintService` (VM-обфускация)
- **Невозможно сгенерировать программно** — только извлечь с рутованного устройства

Что Avito собирает в fingerprint (статический анализ APK v217.2):
- `android_id` (Settings.Secure)
- `Build.MANUFACTURER`, `Build.VERSION.SDK_INT`, `Build.MODEL`, `FINGERPRINT` и др.
- `WifiInfo.getSSID()`, `getBSSID()`
- `DisplayMetrics` (densityDpi, widthPixels, heightPixels)
- `AdvertisingIdClient.getAdvertisingIdInfo()` (Google GAID)
- `SensorManager.getSensorList()` (33 датчика на OnePlus)
- `getInstalledPackages()` — список установленных приложений
- System props: `ro.build.*`, `ro.product.*`, vendor-специфичные (MIUI, EMUI, OneUI)

Anti-tamper: RootBeer (root detection), Cyberity SDK (anti-Frida), APK signature check.

Источник: `DOCS/AVITO-FINGERPRINT.md`

---

## G. Реверс-инжиниринг — статус методов

| Метод | Статус | Что получили |
|---|---|---|
| Статический анализ DEX (jadx) | РАБОТАЕТ | Endpoint strings, Retrofit annotations, HTTP headers |
| ADB сбор данных | РАБОТАЕТ | Реальные значения device properties |
| Frida runtime hooks | ЗАБЛОКИРОВАН | Anti-Frida: Cyberity SDK + RootBeer убивают процесс за 1-2 сек |
| MITM (mitmproxy) | ЗАБЛОКИРОВАН | SSL pinning (OkHttp CertificatePinner) + encrypted DNS |
| Frida Gadget в APK | ЧАСТИЧНО | APK запускается, но крашится (ClassNotFoundException) |
| tcpdump | ЧАСТИЧНО | Видит трафик, но Avito использует DoH/DoT |

Источник: `DOCS/REVERSE-GUIDE.md`
