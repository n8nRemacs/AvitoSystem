# Avito Auth API

**Дата:** 2026-01-13
**Захвачено через:** Frida HTTP hooks

---

## Endpoints

### 1. Auth Suggest (получение доступных методов авторизации)

**Endpoint:** `GET https://app.avito.ru/api/1/auth/suggest`

**Query params:**
- `hashUserIds[0]` - хеш устройства/пользователя
- `key` - API ключ (опционально)

**Response:**
```json
{
  "result": {
    "socials": [
      {"provider": "vk-id", "status": "visible"},
      {"provider": "esia-id", "status": "visible"},
      {"provider": "ok", "status": "visible"},
      {"provider": "gp", "status": "disabled", "userDialog": {...}}
    ]
  },
  "status": "ok"
}
```

---

### 2. Авторизация (основной endpoint)

**Endpoint:** `POST https://app.avito.ru/api/11/auth`

**Headers (из анализа OkHttp интерцепторов):**

| Header | Источник | Значение |
|--------|----------|----------|
| `User-Agent` | V0.java (UserAgentHeaderProviderImpl) | `AVITO {version} ({manufacturer} {model}; Android {ver}; {locale})` |
| `X-DeviceId` | X.java (FixedDeviceIdHeaderProvider) | 16 hex chars (e.g., `a8d7b75625458809`) |
| `X-Platform` | C14429a.java (AndroidXPlatformProvider) | `android` |
| `X-App` | C34290k.java (AppHeaderProvider) | `avito` |
| `X-AppVer` | b.java (AppVersionHeaderProvider) | App version (e.g., `118.8`) |
| `X-Date` | A.java (DateHeaderProviderImpl) | Unix timestamp in seconds |
| `Accept-Language` | C34280f.java (AcceptLanguageInterceptorImpl) | `ru-RU` |
| `X-Geo-required` | Retrofit annotation | `true` (для auth endpoint) |
| `X-Session` | G0.java (SessionHeaderProviderImpl) | JWT токен (после авторизации) |
| `X-Geo` | C34275c0.java (GeoHeaderProviderImpl) | `lat;lng;accuracy;timestamp` (опционально) |
| `Content-Type` | | `application/x-www-form-urlencoded` |

**ПОЛНЫЕ ЗАГОЛОВКИ (захвачены через Frida 2026-01-13):**

```
User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)
X-Supported-Features: helpcenter-form-46049
X-App: avito
X-DeviceId: a8d7b75625458809
X-Geo: 46.360889;48.047291;100;1768295137
Schema-Check: 0
f: A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01c...
X-Platform: android
X-RemoteDeviceId: kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBc...android
AT-v: 1
Accept-Encoding: zstd;q=1.0, gzip;q=0.8
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
Content-Length: 304
Host: app.avito.ru
Connection: Keep-Alive
Cookie: 1f_uid=...; u=...
X-Date: 1768295320
```

### Критический заголовок `f` (Fingerprint)

**Источник:** `com.avito.security.libfp.FingerprintService` (нативная библиотека)

**Формат:** `A2.<hex_signature>` (256+ символов)

**Генерация:**
```java
FingerprintService.init(context);
String fp = fingerprintService.calculateFingerprintV2(timestamp);
```

**Хранение:** SharedPreferences ключ `"fpx"`

**ВАЖНО:** Без этого заголовка запрос будет отклонён QRATOR!

**Request body:** (из jadx декомпиляции InterfaceC34258d.java)
```
Content-Type: application/x-www-form-urlencoded

login=+7XXXXXXXXXX
password=xxxxx
token=<firebase_push_token>
provider=<optional>
isSandbox=false
suggestKey=<optional>
src=<optional>
fid=<tracker_uid>
```

**Параметры:**
| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| login | да | Телефон (+7...) или email |
| password | да | Пароль |
| token | да | Firebase push token |
| provider | нет | Провайдер (для social login) |
| isSandbox | да | false для production |
| suggestKey | нет | Ключ от предыдущего входа |
| src | нет | Источник авторизации |
| fid | да | Tracker/fingerprint UID |

**Success Response:**
```json
{
  "result": {
    "phash": "add7f675e4dd83c86e25df4b51ff713f",
    "refreshToken": "fd74bc392447ed35a52d6546d0e4034e",
    "session": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjgzNzk0ODQsImlhdCI6MTc2ODI5MzA4NCwidSI6NDI3OTk5NDEzLCJwIjozNTQyMzExODcsInMiOiIyMWZiZTE3ZTNlNWJlNmMwNzdmNDYzYjRjMzYzNDU4Zi4xNzY4MjkzMDg0IiwiaCI6IlptRTJObUUzWVdWa05EUTFOakE0TlROaFlqRXpNemsyWkdOak5EWmlNamhqTkRabE0yWTFNVHBaVkdoclRqSkpNMDVVV1hsT1ZGRXhUMFJuZDA5UiIsImQiOiJhOGQ3Yjc1NjI1NDU4ODA5IiwicGwiOiJhbmRyb2lkIiwiZXh0cmEiOm51bGx9.iOXYyV5CfXze95hHWso3wHso5Pk8KW7QoXnO-LM4GmZtvkKBKchp0j7_1JQMVOnIpCS-pVh__cZXIs00lPUFZA",
    "signature": "afafafafafafafafafafafafafafafaf",
    "user": {
      "avatar": {
        "128x128": "https://static.avito.ru/stub_avatars/M/14_128x128.png",
        ...
      },
      "id": 427999413,
      "isLegalPerson": false,
      "isPro": false,
      "metroId": 0,
      "name": "mips",
      "phone": "+7***725-37-77",
      "registrationTime": 1768226296,
      "type": {"code": "private", "title": "Частное лицо"},
      "userHashId": "17fa67c42a7531c898da1c4284ccfed4"
    }
  },
  "status": "ok"
}
```

**Error Response (неверный пароль):**
```json
{
  "result": {
    "messages": {
      "password": "Неправильный пароль"
    }
  },
  "status": "incorrect-data"
}
```

---

### 3. TFA/SMS верификация

**Endpoint:** `POST https://app.avito.ru/api/2/tfa/auth`

**Request body:**
```
Content-Type: application/x-www-form-urlencoded

code=123456
flow=sms|push
fid=<tracker_uid>
```

**Параметры:**
| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| code | да | SMS код |
| flow | да | Тип TFA (sms/push) |
| fid | да | Tracker UID |

---

### 4. JWT Session Token Structure

**Алгоритм:** HS512

**Payload (decoded):**
```json
{
  "exp": 1768379484,           // Expiration (+24h)
  "iat": 1768293084,           // Issued at
  "u": 427999413,              // User ID
  "p": 354231187,              // Profile ID
  "s": "21fbe17e3e5be6c077f463b4c363458f.1768293084",  // Session hash
  "h": "ZmE2NmE3YWVkNDQ1NjA4NTNhYjEzMzk2ZGNjNDZiMjhjNDZlM2Y1MTpZVGhrTjJJMzU5UWxORkV4T1JnZDBR",
  "d": "a8d7b75625458809",      // Device ID
  "pl": "android",              // Platform
  "extra": null
}
```

---

### 4. Дополнительные endpoints

**Visitor Generate:**
```
POST https://app.avito.ru/api/1/visitorGenerate

Response:
{
  "result": {
    "visitor": "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android"
  },
  "status": "ok"
}
```

**Notifications Token:**
```
POST https://app.avito.ru/api/3/notifications/token

Response:
{"success":{"result":{"success":true}}}
```

---

## Токены для API

| Токен | Описание | Использование |
|-------|----------|---------------|
| `session` | JWT токен сессии (24h) | Header `X-Session`, Cookie `sessid` |
| `refreshToken` | Для обновления сессии | POST /api/*/auth/refresh |
| `phash` | Хеш профиля | Query param в API запросах |
| `signature` | Подпись (всегда "afaf...") | Для верификации |

---

## Заметки

1. **SMS не требовался** - авторизация прошла только по паролю (возможно из-за доверенного устройства)
2. **X-Geo-required: true** - header указывает что геолокация может влиять на авторизацию
3. **Request body не удалось захватить** - возможно используется binary/protobuf формат

---

---

## QRATOR Anti-Bot Protection

### Проблема

Avito использует QRATOR DDoS/Anti-Bot защиту которая детектирует:
1. **TLS Fingerprint (JA3/JA3S)** - отпечаток TLS handshake
2. **HTTP/2 Fingerprint** - порядок и параметры HTTP/2 frames
3. **Заголовки** - порядок и наличие всех required headers
4. **Request timing** - паттерны запросов

### Симптомы блокировки

- HTTP 400 с сообщением "Пожалуйста, используйте приложение или авторизуйтесь через avito.ru"
- Временная блокировка аккаунта после нескольких попыток

### Подходы к обходу

1. **TLS Impersonation** (текущий подход - не работает полностью)
   - `curl_cffi` с `impersonate="okhttp4_android_13"`
   - Проблема: fingerprint всё равно отличается от реального OkHttp

2. **mitmproxy + реальное устройство**
   - Настроить прокси на телефоне
   - Захватить точный трафик
   - Replay через тот же прокси

3. **Appium + реальный APK**
   - Автоматизация реального приложения через Appium
   - Самый надёжный, но медленный

4. **Frida + Socket proxy**
   - Хукать сокеты напрямую для replay

5. **Модификация APK**
   - Patch APK чтобы использовать свой backend
   - Сложно из-за обфускации

### OkHttp Interceptors Chain

```
1. session_refresh.h      - Session management
2. captcha.interceptor.g  - Captcha handling
3. interceptor.F          - Response body processing
4. session_refresh.d      - Session refresh
5. interceptor.Z0         - User-Agent
6. interceptor.f          - Accept-Language
7. interceptor.v0         - Server time
8. interceptor.O0         - Supported features
9. interceptor.g0         - Headers (main)
10. zstd.j                - Zstd compression
11. L40.a                 - Unknown
12. quic.u                - QUIC protocol
13. Zl0.e                 - Unknown
14. interceptor.x         - Certificate pinning
15. interceptor.J         - Exception catching
16. quic.c                - QUIC
[Network Interceptors]
17. interceptor.D         - Date header
```

---

## TODO

- [x] Захватить request body для POST /api/11/auth (найдено в jadx)
- [x] Найти endpoint для SMS верификации (POST /api/2/tfa/auth)
- [x] Проанализировать все OkHttp interceptors
- [x] Найти все HTTP headers
- [ ] Захватить финальные headers через Frida
- [ ] Обойти QRATOR protection
- [ ] Протестировать refresh token flow
- [ ] Найти endpoint для капчи
