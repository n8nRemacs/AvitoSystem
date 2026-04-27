# AvitoAll — Research Archive

**Назначение:** Сборная папка с research-наработками по реверс-инжинирингу Avito: Frida-скрипты, mitmproxy, Android-приложения для захвата токенов, DEX/SO-бинарники из APK, старая версия архитектуры системы.

**Статус:** archive / research — это НЕ рабочий проект, а накопленные исследования. Новый проект V1 — в `avito-xapi/`.

**Стек/технологии:** Python, JavaScript (Frida), Kotlin (Android), Docker (Redroid), ADB, jadx.

## Карта подпапок

| Папка | Что это | Статус |
|-------|---------|--------|
| `avito-system/` | Старая архитектура (7 частей): backend/frontend/worker/telegram/token-bridge/android/messenger | archive, только документация |
| `Avito_smartFree/` | SaaS-версия для 1000+ клиентов: token-farm (Redroid) + MCP-сервер | prototype, незавершён |
| `AvitoSessionManager/` | Kotlin Android-приложение: чтение сессии из SharedPrefs Avito через root | working code |
| `Avito_Redroid_Token/` | Инструкция и скрипты для извлечения токенов через Redroid (Docker Android) | working |
| `Studio_Token/` | То же, но через Android Studio эмулятор вместо Redroid | working, дубликат темы |
| `dex_extract/` | 17 DEX-файлов из APK Avito (classes.dex … classes17.dex) | binary archive |
| `lib_extract/` | SO-файлы: `libgtc4core.so`, `libsigner.so` — нативные библиотеки из APK | binary archive |
| `jadx_tool/` | Бинарник jadx (деобфускатор DEX) — инструмент для работы с DEX | tool |

## Root-level файлы

- `API_AUTH.md`, `API_MESSENGER.md`, `API_MESSENGER_v2.md`, `API_FINAL.md` — задокументированные эндпоинты Avito (auth, WebSocket/JSON-RPC, HTTP REST), захваченные через Frida
- `TECHNICAL_SPECIFICATION.md` — архитектура "Avito Bridge" (Android app + session server + Telegram бот)
- `PROGRESS_REPORT.md` — дневник реверс-инжиниринга: что захвачено, что не работает
- `Avito_Token_SRV.md` — гайд по деплою на сервер
- `*.js` (~30 файлов) — Frida-скрипты разных версий (SSL bypass, HTTP capture, WS capture, FCM, fingerprint, headers)
- `*.py` (~40 файлов) — Python-скрипты: auth клиенты, session manager, telegram bridge, тесты API
- `avito_session*.json` — реальные захваченные сессии (с живыми токенами в прошлом)
- `avito-bridge.service` — systemd unit для Telegram-бота

## Что полезно для V1

1. **API_AUTH.md + API_MESSENGER_v2.md** — задокументированные заголовки, структура JWT, WebSocket JSON-RPC методы, список перехватчиков OkHttp. Прямой референс для avito-xapi.
2. **ssl_simple.js** — рабочий SSL pinning bypass (4 стратегии), нужен для отладки через Frida.
3. **http_capture.js** — рабочий захват HTTP через OkHttp hooks (sync + async), нужен для исследования новых эндпоинтов.
4. **fcm_capture.js** — захват FCM push-уведомлений + WebSocket, полезен для понимания push-событий.
5. **avito-system/contracts/** — JSON-схемы сущностей (session, search, item, rule) — можно взять как основу для моделей V1.
6. **avito-system/part3-worker/SPEC.md** — детальное ТЗ воркера мониторинга (алгоритм, классы, Avito API параметры). Прямой reference для V1 worker.
7. **AvitoSessionManager/** — готовый Kotlin APK для чтения сессии с рут-телефона через libsu. Рабочий, можно использовать as-is.
8. **Avito_smartFree/shared/utils.py** — утилиты: `build_avito_headers()`, `parse_jwt()`, `generate_device_id()`, `RateLimiter` — готовые к портированию в avito-xapi.

## Что НЕ использовать

- `dex_extract/` и `lib_extract/` — бинарники для ручного анализа через jadx, не трогать
- `Studio_Token/` — дубликат `Avito_Redroid_Token/` (та же задача, другой инструмент)
- `*.py` в корне (avito_auth.py, avito_auth_v2.py и т.д.) — экспериментальные попытки авторизации, QRATOR блокирует
- `avito_session*.json` — реальные сессии, токены давно истекли
- `Avito_smartFree/` — незавершённый SaaS-прототип, компоненты изолированы, SMS-регистрация не реализована

## Ссылки

- Активный проект V1: `../avito-xapi/`
- ТЗ V1: `../DOCS/TZ_Avito_Monitor_V1.md`
- `avito-system/` — подробнее в `avito-system/CLAUDE.md`
