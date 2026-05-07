# ТЗ: AvitoBridge Phone Proxy V1

**Статус:** черновик 2026-05-07. Не реализовано. Pre-condition для start: текущий ssh -D + ru-vpn архитектура работает 1+ неделю и есть наблюдаемые причины эскалации.

**Назначение:** Расширение существующего APK `com.avitobridge.sessionmanager` так, чтобы наш xapi мог проксировать выбранные запросы к Avito **через сам телефон** — выходить с реальным OkHttp TLS-fingerprint Avito-app, наследовать сессионные cookies, не зависеть от внешних SOCKS5-туннелей.

**Не назначение V1:**
- НЕ заменяем pool/state machine — это остаётся в xapi
- НЕ переносим UI/scheduler/LLM на телефон
- НЕ строим mitm/reverse-engineering — мы пишем СВОИ запросы, просто отправляем их с телефона

---

## 1. Motivation — когда это понадобится

`DOCS/REFERENCE/05-search-query-formation.md` + memory `reference_qrator_token_ip_binding.md` подтвердили эмпирически, что Avito QRATOR делает per-(token, IP) trust-binding. Текущее решение ssh -D через ru-vpn:

| Свойство | ssh -D (есть) | Phone Bridge (это ТЗ) |
|---|---|---|
| Outbound IP | 155.212.217.226 | 155.212.217.226 (тот же телефон → ru-vpn) |
| **TLS fingerprint** | curl_cffi chrome120 | **OkHttp Android — байт-в-байт как Avito-app** |
| HTTP/2 SETTINGS frame | chrome120 | OkHttp |
| Cookies от Avito (_avisc, и т.д.) | не наследуем | можно зеркалить из Avito-app |
| Resilience к смене VPN-IP | руками править systemd | автоматически (телефон сам в инете) |
| Зависимость от внешнего сервиса | ru-vpn должен жить | только сам телефон + linkup-канал |

**Сигналы к старту реализации:**
- Через 7-14 дней работы ssh -D токены начинают периодически 403'ить (значит QRATOR детектит chrome120-vs-OkHttp diff)
- Avito выпускает новую версию приложения и наш chrome120-fingerprint начинает палиться
- Поднимется потребность подмешивать `_avisc`/`1f_uid` cookies для проходимости captcha-challenges

Без любого из этих сигналов V1 phone-bridge — over-investment. ssh -D достаточно.

---

## 2. Архитектура

### 2.1 Высокоуровневая схема

```
                                                               ┌─────────────┐
                                                               │  Avito API  │
                                                               │ app.avito.ru│
                                                               └──────▲──────┘
                                                                      │ OkHttp TLS
┌──────────────┐  HTTPS  ┌─────────────────┐  WebSocket  ┌────────────┴────┐
│ avito-xapi   │────────►│  link-up server │◄═══════════►│ AvitoBridge APK │
│ (VPS Beget)  │         │   (на VPS)      │             │  на телефоне    │
└──────────────┘         └─────────────────┘             └─────────────────┘
       │                                                          │
       │                                                          ▼
       │                                            читает SharedPrefs Avito-app
       │                                            (session_token, fingerprint, ...)
       │
       └─ feature flag AVITO_BRIDGE_ENABLED:
             true  → запросы через phone bridge (этот TZ)
             false → текущий путь (curl_cffi + ssh -D)  -- по умолчанию
```

### 2.2 Поток одного запроса

1. Polling worker / MCP вызывает `AvitoHttpClient.search_items(...)` в xapi
2. xapi видит `AVITO_BRIDGE_ENABLED=true` → строит abstract Avito-request (URL, headers, params, body)
3. Сериализует в JSON, отправляет на `link-up server` (внутри xapi или отдельный сервис)
4. link-up server по persistent WebSocket к подключённому телефону пересылает запрос
5. APK на телефоне получает запрос, делает реальный OkHttp-вызов к Avito с этими headers (плюс наследует CookieJar)
6. Получает ответ, упаковывает (status, headers, body, время) → отправляет обратно по WS
7. xapi возвращает результат вызывающему коду

### 2.3 Connectivity: APK-инициированный WebSocket

**Выбор:** outbound persistent WS из APK к VPS. NAT-friendly, не требует пробрасывать порты.

Альтернативы (отвергнуты):
- ADB-туннель USB ↔ Linux-host: телефон у пользователя дома, VPS в Beget. Не сходится физически.
- WireGuard / Tailscale: добавляет ещё один компонент сети, при отключении подложки бьёт всю систему.
- HTTPS short-poll (как было в старом `device_commands`): поднимает latency, нагружает мобильный трафик.

WS преимущества: tunable keep-alive, low latency, естественный backpressure.

---

## 3. Android-сторона (расширение APK `com.avitobridge.sessionmanager`)

### 3.1 Зависимости

- Kotlin + Coroutines (уже в APK)
- OkHttp (уже в APK для push-handler'ов) — **используем same Client как для Avito-выхода**
- ktor-client-cio (или okhttp WebSocket) — для WS-канала к VPS
- kotlinx.serialization-json — сериализация запросов/ответов

### 3.2 Module структура

```
app/src/main/java/com/avitobridge/proxy/
  ProxyClient.kt          — WS-клиент, reconnect, auth
  AvitoForwarder.kt       — выполнение AvitoRequest на устройстве, сборка ответа
  CookieStore.kt          — глобальный CookieJar для Avito-домена (+ опц. чтение из Avito-app)
  SharedPrefsReader.kt    — чтение JWT/fingerprint/device_id из Avito-app prefs (через root)
  models/AvitoRequest.kt  — DTO: method, url, headers, body, timeout
  models/AvitoResponse.kt — DTO: status, headers, body (base64 если binary), elapsed
```

### 3.3 WS-канал

- URL: `wss://${VPS_HOST}/api/v1/bridge/ws`
- Auth: `Authorization: Bearer ${BRIDGE_TOKEN}` (значение в `BuildConfig` или SharedPrefs)
- Reconnect: exponential back-off 1s → 30s, jitter ±20%
- Heartbeat: ping/pong каждые 25с
- Max-frame: 1 MB (item-detail body может быть тяжёлым, особенно с `images`)
- Out-of-order safe: каждый запрос имеет `requestId` (UUID), ответы коррелируются по нему

### 3.4 OkHttp-клиент для Avito-стороны

```kotlin
val avitoClient = OkHttpClient.Builder()
    .connectTimeout(15.seconds)
    .readTimeout(30.seconds)
    .cookieJar(avitoCookieJar)        // делим один Jar
    .followRedirects(true)
    .protocols(listOf(Protocol.HTTP_2, Protocol.HTTP_1_1))  // как Avito-app
    .build()
```

CookieJar инициализируем при старте APK из Avito-app's WebKit cookie store (`/data/data/com.avito.android/...`) — так подмешиваем `_avisc`, `1f_uid`, `u`, `v`, любые сервисные.

### 3.5 SharedPrefs read

Уже реализовано в существующем APK (NotificationListener читает токены). Расширяем читателя на остальные ключи:
- `session_token` (уже)
- `refresh_token` (уже)
- `fingerprint` / `fpx` (новый — для подмеса в `f` header)
- `device_id` (уже)
- `remote_device_id` (новый)

Все значения экспонируются через локальный API APK для proxy-handler'а.

### 3.6 Endpoint handler (логика на ws-сообщение)

Псевдокод:
```kotlin
suspend fun handle(req: AvitoRequest): AvitoResponse {
    val builder = Request.Builder()
        .url(req.url)
        .method(req.method, req.body?.toRequestBody())
    req.headers.forEach { (k, v) -> builder.header(k, v) }
    
    // Inject session bits ТОЛЬКО если они помечены sentinel'ом
    // ${SESSION_TOKEN}, ${FINGERPRINT}, ${DEVICE_ID}, ${REMOTE_DEVICE_ID}
    // Это позволяет xapi'ю делать запросы за разные account-pool slots
    val resolved = resolveSentinels(req, sessionFor(req.accountId))
    
    val resp = avitoClient.newCall(resolved).execute()
    return AvitoResponse(
        status = resp.code,
        headers = resp.headers.toMap(),
        body = resp.body?.bytes()?.toBase64() ?: "",
        elapsed = resp.receivedResponseAtMillis - resp.sentRequestAtMillis,
    )
}
```

**Замечание:** xapi присылает sentinels (`${SESSION_TOKEN}` и т.д.), а APK подставляет реальные значения из SharedPrefs. Это исключает передачу JWT по WS — наш WS-канал безопасен, но это лишняя страховка от логов.

---

## 4. Транспортный routing (transport selection per operation)

Не каждый запрос к Avito должен идти одним и тем же путём. У нас три эффективных канала, каждый со своим scope, латентностью и риск-профилем:

| Канал | TLS/JA3 | Auth | Что умеет | Latency | Risk |
|---|---|---|---|---|---|
| **A. curl_cffi + ssh -D** | chrome120 impersonation | reversed JWT (mobile) | Всё mobile API | 200-400ms | средний (chrome120 ≠ OkHttp) |
| **B. Phone Bridge (этот ТЗ)** | реальный OkHttp Android | reversed JWT (mobile) | Всё mobile API | 400-800ms | низкий (неотличимо от Avito-app) |
| **C. Official Avito Business API** | стандартный TLS | OAuth2 client_credentials | Только свои объявления, свой messenger, статистика, autoload | 100-300ms | минимальный (это легальный путь) |

### 4.1 Routing matrix

| Операция | Primary | Fallback | Замечание |
|---|---|---|---|
| `search_items()` (чужие лоты) | A или B | — | Чисто mobile, official не умеет search чужих |
| `get_item_details()` (чужой лот) | A или B | — | Mobile only |
| `get_subscription_items()` (свои autosearches) | A или B | — | Mobile only |
| `list_subscriptions()` (свои autosearches) | A или B | — | Mobile only (через mobile API возвращает structured deeplink) |
| `list_own_items()` (наши объявления, V2) | **C** | A или B | Official по дефолту — он чище |
| `update_own_item()` (V2 autoload) | **C** | — | Только official |
| `get_own_stats()` (V2) | **C** | — | Только official |
| `send_message()` (own messenger, V2) | **C** | A или B | Official предпочтителен, но не везде покрывает |
| `get_messenger_channels()` (V1 monitoring) | A или B | — | Mobile reverse используется сейчас |

### 4.2 Реализация routing'а

В `AvitoHttpClient` каждый метод декларирует preferred transport через декоратор/атрибут:

```python
class AvitoHttpClient:
    @transport_pref(primary="reverse", fallback=None)
    async def search_items(...): ...

    @transport_pref(primary="official", fallback="reverse")
    async def list_own_items(...): ...
```

`base_client.py` resolver выбирает реальный класс:
- `reverse` → `AVITO_BRIDGE_ENABLED=true` ? PhoneBridgeClient : CurlCffiClient
- `official` → `OfficialAvitoClient` (новый, обёртка над `api.avito.ru` с OAuth2)

### 4.3 Official API client (отдельный)

`avito-xapi/src/workers/official_client.py`:

```python
class OfficialAvitoClient:
    BASE_URL = "https://api.avito.ru"

    def __init__(self, client_id, client_secret):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._token_exp = 0

    async def _ensure_token(self):
        if self._token and time.time() < self._token_exp - 60:
            return
        # POST /token, grant=client_credentials, save bearer + expires_in
        ...

    async def list_own_items(self, ...):
        await self._ensure_token()
        return await self._get("/core/v1/items", ...)

    async def get_own_stats(self, item_id, date_from, date_to):
        await self._ensure_token()
        return await self._get(f"/stats/v1/accounts/.../items/{item_id}/", ...)
```

Credentials живут в `.env`:
```
AVITO_OFFICIAL_CLIENT_ID=
AVITO_OFFICIAL_CLIENT_SECRET=
```
(Уже есть в нашем `.env` локально, надо перенести в production `/opt/avito-system/.env`.)

### 4.4 Per-tenant override

Routing matrix — глобальный default. Per-tenant override может в будущем понадобиться (например, для тестов на конкретном профиле). В V1 не делаем — глобально через env.

---

## 5. xapi-сторона (детали реализации reverse-channels)

### 5.1 Новый клиент

`avito-xapi/src/workers/phone_bridge_client.py`:

```python
class PhoneBridgeClient(AvitoHttpClient):
    """Заменяет curl_cffi-based AvitoHttpClient. Совместимая сигнатура,
    под капотом — отправка запроса на phone bridge.
    """
    def __init__(self, session_data, ws_send, ...): ...

    async def _do_request(self, method, url, **kwargs):
        req_id = str(uuid4())
        msg = {"requestId": req_id, "method": method, "url": url,
               "headers": self._sentinel_headers(), "body": kwargs.get("body")}
        await self.ws_send(msg)
        resp = await self._await_response(req_id, timeout=30)
        return _to_curl_cffi_compatible(resp)
```

`_sentinel_headers()` ставит `X-Session: ${SESSION_TOKEN}`, `f: ${FINGERPRINT}`, и т.д. — APK сам подставит реальные значения.

### 5.2 Link-up server

Сначала встраиваем в существующий xapi (FastAPI WebSocket route `/api/v1/bridge/ws`). По мере роста — выделяем в отдельный сервис.

Ответственность:
- Принимает WS-соединения от APK
- Аутентифицирует bearer token
- Хранит in-memory mapping `account_id → connected_phone_ws`
- Реализует request/response correlation: `dict[requestId, asyncio.Future]`
- Метрики: round-trip-ms по 50/95/99 percentile, error rate, reconnect rate

### 5.3 Feature flag

В `.env`:
```
AVITO_BRIDGE_ENABLED=false      # default
AVITO_BRIDGE_TOKEN=             # bearer для APK ↔ link-up auth
```

В `base_client.py` (вместо текущего AVITO_SOCKS_PROXY-only пути):
```python
if os.environ.get("AVITO_BRIDGE_ENABLED") == "true":
    return PhoneBridgeClient(...)
elif (proxy := os.environ.get("AVITO_SOCKS_PROXY")):
    return CurlCffiClient(impersonate="chrome120", proxies={...})
else:
    return CurlCffiClient(impersonate="chrome120")
```

Это позволяет на лету переключаться: ssh -D ↔ phone bridge ↔ direct, без рестарта (env update + container restart).

---

## 6. Безопасность

- **WS Auth:** bearer-token (random 32 hex). Хранится в `BuildConfig` APK (read-only) и в `.env` VPS.
- **TLS:** WS over HTTPS (wss://). Сертификат VPS — Caddy/Let's Encrypt.
- **Sentinels:** session_token / fingerprint **не передаются** по WS — APK сам резолвит. Защита от утечки в логах link-up server.
- **CookieJar:** хранится только на телефоне, не утекает в xapi.
- **APK request validation:** APK проверяет, что входящий URL начинается с `https://app.avito.ru/api/` — защита от использования APK как general-purpose proxy.
- **Per-account scoping:** сообщение от xapi содержит `accountId`; APK выбирает правильную сессию из своего prefs-store. Если accountId неизвестен → reject.

---

## 7. Резильентность

| Сценарий | Поведение |
|---|---|
| APK теряет связь с VPS | exponential back-off, link-up server marks bridge as offline, xapi падает на ssh -D fallback (если AVITO_BRIDGE_REQUIRE=false) или 503 |
| Авито возвращает 403/captcha | APK прокидывает наверх как обычный response, state machine xapi реагирует штатно |
| APK crash | systemd-style restart на стороне Android (foreground service) — auto-restart |
| Phone reboot | foreground service с MANIFEST_PERMISSION_FOREGROUND_SERVICE_DATA_SYNC + START_STICKY |
| OOM-kill | как выше + persistent notification (иконка в шторке, чтобы Android не убивал) |
| Слишком много pending request'ов | cap на queue size в xapi (50), новые запросы отклоняются с 503 |

---

## 8. Migration path

**Phase 0 — текущее (есть):**
- ssh -D + curl_cffi chrome120 + ru-vpn
- AVITO_SOCKS_PROXY=socks5h://172.18.0.1:1081

**Phase 1 — реализация phone bridge (этот TZ):**
- APK side: HTTP-клиент + WS + sentinel resolver
- xapi side: PhoneBridgeClient + link-up route
- env: AVITO_BRIDGE_ENABLED=false (build-only, без рантайм-эффекта)

**Phase 2 — soak обоих путей в параллель:**
- На один профиль включаем `AVITO_BRIDGE_ENABLED=true`, остальные на ssh -D
- Сравниваем 2-3 дня: error rate, latency, missing-listings, captcha rate
- Метрики смотрим в `profile_runs` + Telegram alerts

**Phase 3 — переключение всего polling'а на bridge:**
- AVITO_BRIDGE_ENABLED=true, AVITO_SOCKS_PROXY оставляем как fallback
- Если 7 дней OK — фиксируем как primary

**Phase 4 — отказ от ssh -D (опционально):**
- Удалить systemd unit, вернуть curl_cffi-direct как dev-only
- Снизить операционную сложность

---

## 9. Оценка трудозатрат (часы кодинга)

### MVP — Phase 1

| Блок | Часы |
|---|---|
| Android: WS-клиент + auth + reconnect | 1.5 |
| Android: AvitoForwarder с OkHttp + sentinel resolver | 2 |
| Android: расширение SharedPrefsReader | 0.5 |
| Android: CookieJar (читать из Avito-app webview cookies) | 1.5 |
| Android: foreground service + manifest + battery exemption | 1 |
| xapi: PhoneBridgeClient (наследует AvitoHttpClient) | 1.5 |
| xapi: link-up FastAPI WebSocket route + correlation map | 1.5 |
| xapi: feature flag в base_client.py | 0.3 |
| Тесты: unit на sentinel resolver, end-to-end на 1 endpoint | 1.5 |
| Smoke на проде (1 endpoint, шкала «работает/нет») | 0.5 |
| **Sub-total bridge** | **~11ч** |
| OfficialAvitoClient (OAuth2 + 2-3 endpoint'а: own_items, own_stats) | 2 |
| @transport_pref decorator + resolver в base_client | 1 |
| **Итого MVP** | **~14ч** |

Plus hidden:
- Build APK release (signing): 0.5ч
- Соак Phase 2: реальные часы не идут в эстимейт (фоновый watch)
- Если CookieJar inheritance окажется сложным (SSL pinning Avito-app-webview) — +2-3ч

Реальный ожидаемый диапазон: **10-18ч**.

---

## 10. Open questions

1. **CookieJar from Avito-app**: насколько просто читать `/data/data/com.avito.android/app_webview/Cookies` (sqlite)? Если просто — выигрываем `_avisc` обмен. Если требует mitm — отказываемся, обходимся empty Jar.
2. **Multi-account на одном устройстве**: `b5cbf28b` и `14acfef4` — нам в pool два, у нас на телефоне одна Avito-app. Может ли APK хранить/жонглировать сессиями двух аккаунтов? Решение: SharedPrefs-only multi-account уже задумано — кладём JWT в наш prefs, не в Avito-app's.
3. **Cellular vs WiFi**: если телефон уйдёт с домашнего WiFi на cellular, IP сменится → токены протухнут. Решение: APK обнаруживает смену сети → принудительный refresh токена (триггер на xapi).
4. **Avito update break**: новая версия Avito-app может изменить SharedPrefs-ключи. Решение: APK логирует ключи на старте, alert в TG если ожидаемый ключ отсутствует.
5. **Производительность**: phone-WS-roundtrip vs ssh-D-direct — ожидаем +200-400ms latency. Acceptable для polling раз в 5 мин, неприемлемо для realtime messaging (V2 scope).

---

## 11. Decision triggers / Out of scope

**В V1 НЕ входит:**
- Messaging (real-time chat) через bridge — V2 (другая частота, другие требования)
- Multi-device pool (несколько телефонов) — V2 (нужен load balancer перед link-up)
- Auto-discovery подключённых телефонов — V2 (заводим вручную)
- Захват trace/HAR из Avito-app для dev (V2)

**Решение делать V1**: сигнал что ssh -D не справляется (см. §1). До этого — этот документ остаётся черновиком.

---

## 12. Связанные документы

- `DOCS/REFERENCE/02-auth-and-tokens.md` — детали JWT/refresh/SharedPrefs ключи
- `DOCS/REFERENCE/04-reverse-engineering-howto.md` — как читать SharedPrefs Avito-app, Frida-методы
- `DOCS/AVITO-FINGERPRINT.md` — устройство `f` blob, почему его нельзя сгенерировать
- `DOCS/REFERENCE/05-search-query-formation.md` — root cause search query problem
- `c:/Users/EloNout/.claude/projects/C--Projects-Sync-AvitoSystem/memory/reference_qrator_token_ip_binding.md` — emp.findings 05-07
- `DOCS/DECISIONS.md` — потенциальный ADR-012 на основании этого TZ

---

## 13. Sign-off

Автор: 2026-05-07 черновик в ходе сессии.
Pre-implementation review: при сигнале к старту (см. §1) ревью у заказчика.
