# Avito Reverse Engineering - Progress Report

**Дата:** 2026-01-13 (обновлено)
**Цель:** Создание серверного клиента Avito Messenger (аналог Baileys для WhatsApp)

---

## Статус проекта

| Компонент | Статус | Документация |
|-----------|--------|--------------|
| Messenger API (WebSocket) | ✅ Полностью | API_MESSENGER_v2.md |
| Auth API (HTTP) | ✅ Захвачен | API_AUTH.md |
| JWT Token Structure | ✅ Расшифрован | Ниже |
| SSL Pinning Bypass | ✅ Работает | ssl_simple.js |
| HTTP Capture (Frida) | ✅ Работает | http_capture.js |

---

## Что сделано

### 1. Messenger API (WebSocket) - ПОЛНОСТЬЮ ЗАДОКУМЕНТИРОВАН

**Endpoint:** `wss://socket.avito.ru/socket?use_seq=true&app_name=android`

**Протокол:** JSON-RPC 2.0

**Захваченные методы:**
| Метод | Описание |
|-------|----------|
| `avito.getChats.v5` | Список чатов |
| `avito.getChatById.v3` | Чат по ID |
| `messenger.history.v2` | История сообщений |
| `avito.sendTextMessage.v2` | Отправка текста |
| `messenger.sendTyping.v2` | Индикатор набора |
| `messenger.readChats.v1` | Пометить прочитанным |
| `messenger.getUnreadCount.v1` | Счётчик непрочитанных |
| `messenger.quickReplies.v1` | Быстрые ответы |
| `suggest.getMessages` | Подсказки |
| `messenger.getSettings.v2` | Настройки |
| `messenger.getLastActionTimes.v2` | Время действий |
| `avito.getBodyImages` | Изображения |
| `ping` | Keep-alive |

**Push события (Server → Client):**
- `session` - инициализация сессии
- `Message` - новое сообщение
- `ChatTyping` - печатает...
- `ChatRead` - прочитано
- `ChannelUpdate` - обновление канала

**Типы сообщений:**
| type | body поля |
|------|-----------|
| text | text, randomId |
| image | imageId, randomId |
| voice | voiceId, randomId |
| location | lat, lon, title, kind, text |
| file | fileId, name, sizeBytes |

---

### 2. JWT Session Token - СТРУКТУРА РАСШИФРОВАНА

**Алгоритм:** HS512

**Поля payload:**
```json
{
  "exp": 1768313080,           // Expiration (+24h)
  "iat": 1768226680,           // Issued at
  "u": 157920214,              // User ID
  "p": 28109599,               // Profile ID
  "s": "hash.timestamp",       // Session hash
  "h": "base64(<sha1>:<base64(device_id)>)",
  "d": "a8d7b75625458809",     // Device ID
  "pl": "android",             // Platform
  "extra": null
}
```

**Захваченные токены:**
- `sessid` - JWT сессии (24h lifetime)
- `refresh_token` - для обновления сессии
- `phash` - хеш профиля (для API запросов)

---

### 3. Авторизация - ЗАХВАЧЕНА ✅

**Endpoint:** `POST https://app.avito.ru/api/11/auth`

**Что захвачено (2026-01-13):**
- ✅ Auth endpoint и response format
- ✅ JWT session token (HS512)
- ✅ Refresh token
- ✅ User object structure
- ✅ Error response format (неверный пароль)

**Что НЕ захвачено:**
- ❌ Request body format (не удалось прочитать - возможно binary/protobuf)
- ❌ SMS verification endpoint
- ❌ Captcha challenge/response

**Success Response:**
```json
{
  "result": {
    "phash": "add7f675e4dd83c86e25df4b51ff713f",
    "refreshToken": "fd74bc392447ed35a52d6546d0e4034e",
    "session": "eyJhbGciOiJIUzUxMiIs...", // JWT
    "signature": "afafafafafafafafafafafafafafafaf",
    "user": {
      "id": 427999413,
      "name": "mips",
      "phone": "+7***725-37-77",
      "userHashId": "17fa67c42a7531c898da1c4284ccfed4"
    }
  },
  "status": "ok"
}
```

**Заметки:**
- SMS не потребовался (доверенное устройство)
- Header `X-Geo-required: true` может влиять на авторизацию

**Подробная документация:** см. `API_AUTH.md`

**Найденные классы авторизации:**
```
com.avito.android.authorization.auth.AuthActivity
com.avito.android.authorization.login.LoginActivity
com.avito.android.remote.model.LoginResult$Ok
com.avito.android.remote.model.LoginResult$FailedWithMessage
com.avito.android.remote.model.LoginResult$TfaCheckWithPush
com.avito.android.remote.model.LoginResult$PassportBlocked
com.avito.android.remote.model.PhonePretendResult$Ok
com.avito.android.remote.model.AuthResult
com.avito.android.captcha.interceptor.g (HTTP interceptor)
com.vk.id.captcha.* (VK ID интеграция)
```

---

### 4. SSL Pinning Bypass - РЕШЕНО ✅

**Проблема:** Avito использует custom SSL pinning на `app.avito.ru`

**Решение (ssl_simple.js):**
1. `TrustManagerImpl.verifyChain` - bypass системной проверки
2. `SSLContext.init` - подмена TrustManager
3. `OkHttp CertificatePinner.check` - bypass OkHttp pinning
4. `com.avito.android.remote.interceptor.x` - bypass Avito custom interceptor

**Найденные классы pinning:**
- `com.avito.android.remote.interceptor.x` (CertificatePinningInterceptorImpl)
- `com.avito.android.remote.interceptor.C34315x` (альтернативное имя)
- `com.avito.android.certificate_pinning.b`
- `com.avito.android.remote.error.ApiError$CertificatePinningError`

---

### 5. Технические проблемы (обновлено)

| Проблема | Причина | Статус |
|----------|---------|--------|
| ~~OkHttp hooks не работают~~ | ~~Классы obfuscated~~ | ✅ РЕШЕНО - OkHttp не обфусцирован |
| ~~HTTP body не захватывается~~ | ~~SSL pinning~~ | ✅ РЕШЕНО - Frida capture |
| Request body не читается | okio.Buffer проблема | ⏳ В работе |
| mitmproxy proxy не работает | App игнорирует system proxy | ❌ Отказались |

---

## Следующие шаги

### ФАЗА 1: Исследование триггеров авторизации

**Цель:** Понять, что вызывает SMS/Captcha/простой вход

| # | Эксперимент | Ожидание | Статус |
|---|-------------|----------|--------|
| 1 | Вход с того же device + того же IP | Без SMS, без captcha | ✅ Подтверждено |
| 2 | Вход с нового device_id (generate UUID) | SMS? | ⏳ |
| 3 | Вход с другого IP (VPN) | Captcha? | ⏳ |
| 4 | Вход после очистки данных приложения | SMS + Captcha? | ⏳ |
| 5 | Вход с refresh_token | Без SMS (обновление сессии) | ⏳ |
| 6 | Несколько попыток входа подряд | Rate limit → Captcha → IP ban | ⏳ |

**Подтверждённые гипотезы:**
- ✅ Доверенное устройство = вход без SMS

---

### ФАЗА 2: Решение проблемы HTTP capture - ЗАВЕРШЕНА ✅

**Выбранное решение: Frida OkHttp hooks**

mitmproxy НЕ сработал:
- ❌ App игнорирует system proxy
- ❌ SSL pinning на app.avito.ru даже с CA cert

**Работающее решение:**
1. ✅ Frida ssl_simple.js - bypass SSL pinning
2. ✅ Frida http_capture.js - capture HTTP через OkHttp hooks
3. ✅ Захвачен auth flow без proxy

---

### ФАЗА 3: Документирование Auth API - ЧАСТИЧНО ✅

**Захвачено:**
```
POST /api/11/auth
  Headers: X-Geo-required: true
  Body: (не удалось захватить)
  Response: { session, refreshToken, phash, user }
```

**TODO:**
- [ ] Захватить request body (login/password format)
- [ ] Найти POST /api/*/auth/refresh endpoint
- [ ] Найти SMS verification endpoint
- [ ] Найти captcha endpoint

---

### ФАЗА 4: Python клиент авторизации

```python
class AvitoAuth:
    def login_with_phone(self, phone: str) -> AuthState:
        """Начать авторизацию по номеру телефона"""
        pass

    def verify_sms(self, code: str) -> Session:
        """Подтвердить SMS код"""
        pass

    def solve_captcha(self, solution: dict) -> AuthState:
        """Решить капчу (slider puzzle)"""
        pass

    def refresh_session(self, refresh_token: str) -> Session:
        """Обновить сессию без SMS"""
        pass

    def restore_session(self, sessid: str) -> bool:
        """Восстановить сессию из сохранённого токена"""
        pass
```

---

## Файлы проекта

```
APK/Avito/
├── API_MESSENGER_v2.md          # Документация Messenger API
├── API_AUTH.md                  # Документация Auth API (NEW!)
├── avito_session.json           # Первая захваченная сессия
├── avito_session_new.json       # Новая сессия с полной структурой
├── ssl_simple.js                # Frida: SSL pinning bypass (РАБОТАЕТ!)
├── http_capture.js              # Frida: HTTP capture через OkHttp (РАБОТАЕТ!)
├── auth_full_capture.js         # Frida: базовый capture
├── auth_targeted_hooks.js       # Frida: целевые hooks auth
├── auth_captcha_hooks.js        # Frida: hooks для captcha
├── auth_registration_capture.js # Frida: регистрация
├── fcm_capture.js               # Frida: push notifications
├── avito_messenger_client.py    # Python: Messenger клиент (WIP)
├── avito_session_manager.py     # Python: Session manager (WIP)
├── example_bot.py               # Python: пример бота (WIP)
├── output/                      # jadx decompiled APK
└── PROGRESS_REPORT.md           # Этот файл
```

---

## Приоритеты (обновлено)

1. ~~**HIGH:** Захватить HTTP auth flow через mitmproxy~~ ✅ СДЕЛАНО (через Frida)
2. **HIGH:** Захватить request body для auth endpoint
3. **HIGH:** Понять триггеры SMS/Captcha
4. **MEDIUM:** Реализовать refresh_token flow
5. ~~**MEDIUM:** Документировать Auth API~~ ✅ СДЕЛАНО (API_AUTH.md)
6. **LOW:** Исследовать VK ID интеграцию

---

## Вопросы для исследования

1. Можно ли авторизоваться только с refresh_token (без SMS)?
2. Как долго живёт refresh_token?
3. Что хранится в SharedPreferences для "запоминания" устройства?
4. Как работает slider captcha (алгоритм решения)?
5. Есть ли rate limits на API?

---

---

## Архитектурные решения

### Решение капчи - WebSocket мост

```
┌─────────────┐    WebSocket    ┌─────────────┐    HTTP/WS    ┌─────────┐
│   Клиент    │ ◄────────────► │   Сервер    │ ◄──────────► │  Avito  │
│  (браузер)  │                │  (Python)   │   proxy IP   │   API   │
└─────────────┘                └─────────────┘              └─────────┘
```

**Flow:**
1. Сервер получает капчу от Avito
2. Отправляет клиенту через WebSocket (картинка + UI)
3. Клиент решает капчу в браузере
4. Отправляет результат на сервер
5. Сервер завершает авторизацию

**Альтернатива:** Telegram бот для получения решения капчи

### IP стратегия - фиксированный прокси

```
Клиент ──► Сервер ──► Прокси (фиксированный IP) ──► Avito
```

**Почему фиксированный IP лучше ротации:**
- Стабильность = доверие от Avito
- Корпоративные подсети = много пользователей на одном IP (норма)
- Если IP забанят → меняем прокси, аккаунт не страдает
- Ротация IP = подозрительное поведение = триггер защиты

### Итоговая архитектура

```
┌────────────────────────────────────────────────────────┐
│                     СЕРВЕР                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ AvitoClient  │  │ AuthManager  │  │ CaptchaProxy │  │
│  │  (messenger) │  │ (tokens)     │  │ (to user)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│          │                │                 │          │
│          └────────────────┼─────────────────┘          │
│                           │                            │
│                    ┌──────▼──────┐                     │
│                    │ HTTP Proxy  │ (фиксированный IP)  │
│                    └──────┬──────┘                     │
└───────────────────────────┼────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   Avito API   │
                    └───────────────┘
```

**Компоненты:**
- `AvitoClient` - WebSocket клиент для Messenger API
- `AuthManager` - управление токенами (sessid, refresh_token)
- `CaptchaProxy` - проксирование капчи пользователю для решения
- `HTTP Proxy` - фиксированный IP для всех запросов к Avito

---

## Оценка рисков

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| API изменится | Низкая | Высокое | Мониторинг, версионирование |
| IP бан | Средняя | Низкое | Смена прокси |
| Капча усложнится | Низкая | Среднее | Пользователь решает вручную |
| Аккаунт бан | Низкая | Высокое | Лимиты запросов, человекоподобное поведение |

---

---

## Сессия 2026-01-13 (продолжение)

### Анализ OkHttp Interceptors - ЗАВЕРШЁН ✅

**Найдены все HTTP заголовки:**

| Header | Класс | Значение |
|--------|-------|----------|
| User-Agent | V0.java | `AVITO 118.8 (OnePlus LE2115; Android 14; ru_RU)` |
| X-DeviceId | X.java | 16 hex chars |
| X-Platform | C14429a.java | `android` |
| X-App | C34290k.java | `avito` |
| X-AppVer | b.java | `118.8` |
| X-Date | A.java | Unix timestamp (секунды) |
| Accept-Language | C34280f.java | `ru-RU` |
| X-Session | G0.java | JWT токен |
| X-Geo | C34275c0.java | `lat;lng;acc;ts` |

### QRATOR Protection - ПРОБЛЕМА ❌

**Проблема:** QRATOR детектирует Python клиент по TLS fingerprint:
- Даже с правильными заголовками получаем HTTP 400
- Сообщение: "Пожалуйста, используйте приложение или авторизуйтесь через avito.ru"
- Аккаунт временно заблокирован после нескольких попыток

**Попытки:**
1. `httpx` с HTTP/2 - не работает
2. `curl_cffi` с `impersonate="okhttp4_android_13"` - не работает

**Вывод:** TLS fingerprint Python/curl отличается от Android OkHttp

### Созданные файлы

- `avito_auth.py` - первая версия auth клиента
- `avito_auth_v2.py` - версия с curl_cffi и всеми заголовками
- `capture_final_request.js` - Frida для захвата финальных headers
- `capture_headers_v2.js` - улучшенный capture script

### Следующие шаги

1. **Дождаться разблокировки аккаунта** (несколько часов)
2. **Захватить реальные headers через mitmproxy** с телефона
3. **Попробовать Appium** для автоматизации реального APK
4. **Исследовать прямое проксирование** через телефон (adb forward)

---

*Текущий статус: Аккаунт временно заблокирован из-за попыток с неправильным TLS fingerprint. Ждём разблокировки.*
