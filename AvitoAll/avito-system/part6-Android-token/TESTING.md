# Part 6: Android Token — План тестирования

## Инструменты

- **JUnit 5** — unit-тесты
- **Mockito / MockK** — мок root-команд, OkHttp, Context
- **Robolectric** — Android-компоненты без эмулятора
- **OkHttp MockWebServer** — мок Backend API
- **JaCoCo** — покрытие кода

## Структура тестов

```
part6-Android-token/
└── app/src/test/java/com/avitobridge/
    ├── data/
    │   ├── AvitoSessionReaderTest.kt     # Чтение SharedPrefs через root
    │   ├── SessionDataTest.kt            # JWT-парсинг, модели
    │   ├── PrefsManagerTest.kt           # Настройки
    │   └── ServerApiTest.kt              # HTTP к Backend + Telegram
    ├── service/
    │   ├── SessionMonitorServiceTest.kt  # Foreground Service логика
    │   └── BootReceiverTest.kt           # Автозапуск
    └── fixtures/
        ├── preferences_valid.xml         # Полный XML с токенами
        ├── preferences_minimal.xml       # Только session + fpx
        ├── preferences_empty.xml         # Пустой <map>
        ├── preferences_no_session.xml    # Без токена session
        └── sample_jwt.txt               # Тестовый JWT
```

## Фикстуры

### preferences_valid.xml
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiJ9.eyJleHAiOjk5OTk5OTk5OTksInUiOjEyMzQ1NiwiZCI6InRlc3RfZGV2aWNlIn0.sig</string>
    <string name="fpx">A2.test_fingerprint_hex_value</string>
    <string name="refresh_token">abc123def456</string>
    <string name="device_id">test_device_001</string>
    <string name="remote_device_id">test_remote_device</string>
    <string name="user_hash">test_user_hash_123</string>
    <string name="visitor_id">test_visitor</string>
</map>
```

### preferences_minimal.xml
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiJ9.eyJleHAiOjk5OTk5OTk5OTksInUiOjEyMzQ1Nn0.sig</string>
    <string name="fpx">A2.minimal_fingerprint</string>
</map>
```

## Unit-тесты

### SessionDataTest.kt (JWT-парсинг)

| Тест | Ожидание |
|------|----------|
| `parseJwt()` — валидный JWT | exp, userId корректны |
| `parseJwt()` — JWT с padding-проблемами base64 | Корректный парсинг |
| `parseJwt()` — невалидный JWT (не 3 части) | null |
| `parseJwt()` — пустая строка | null |
| `parseJwt()` — null | null |
| `getExpiry()` — валидный JWT | Unix timestamp |
| `getExpiry()` — JWT без поля exp | null |
| `hoursUntilExpiry()` — свежий токен (exp далеко) | > 0 |
| `hoursUntilExpiry()` — истекший токен | < 0 |
| `hoursUntilExpiry()` — exp через 1 час | ≈ 1.0 |
| Извлечение userId из `u` | Корректный Long |
| Извлечение deviceId из `d` | Корректная строка |
| Извлечение platform из `pl` | "android" |

### AvitoSessionReaderTest.kt

| Тест | Ожидание |
|------|----------|
| Парсинг полного XML (все поля) | SessionData со всеми полями |
| Парсинг минимального XML (session + fpx) | SessionData, остальное null |
| XML без session токена | null |
| XML без fingerprint (fpx) | null |
| XML с fallback именами (`token`, `f`) | Корректный fallback |
| Пустой XML (`<map/>`) | null |
| Некорректный XML | null, без crash |
| Root недоступен (`isRoot = false`) | null, лог ошибки |
| `su -c cat` возвращает пустую строку | null |
| `su -c cat` возвращает ошибку | Попытка следующего пути |
| Попытка 3 путей SharedPrefs | Проход по всем fallback |
| Успех на 2-м пути (первый не найден) | SessionData от 2-го пути |
| `su -mm -c cat` fail → `su -c cat` success | Корректный fallback команд |
| Runtime.exec fallback | SessionData если libsu не работает |
| Cookies (1f_uid, u_cookie, v_cookie) | Извлечены в Map |

### PrefsManagerTest.kt

| Тест | Ожидание |
|------|----------|
| Default значения при первом запуске | serverUrl, apiKey, intervals корректны |
| Сохранение и чтение serverUrl | Значение сохраняется |
| Сохранение и чтение apiKey | Значение сохраняется |
| Сохранение и чтение checkIntervalMinutes | Значение сохраняется |
| Toggle autoSyncEnabled | true → false → true |
| Toggle autoLaunchAvito | true → false → true |
| Кеширование токена | cachedToken сохраняется и читается |
| Кеширование fingerprint | cachedFingerprint сохраняется |
| lastSyncTime обновляется | Корректный timestamp |
| lastSyncStatus | "success" / "error: ..." |
| Telegram settings | botToken, chatId сохраняются |

### ServerApiTest.kt (с MockWebServer)

| Тест | Ожидание |
|------|----------|
| `syncSession()` — 200 OK | Result.success, данные парсятся |
| `syncSession()` — 500 Error | Result.failure |
| `syncSession()` — сеть недоступна | Result.failure |
| `syncSession()` — timeout | Result.failure |
| Заголовок `X-Device-Key` | Присутствует, значение = apiKey |
| Заголовок `Content-Type` | `application/json` |
| Тело запроса содержит все поля | JSON валидный, все поля есть |
| `healthCheck()` — 200 | Result.success(true) |
| `healthCheck()` — 503 | Result.failure |
| `getFullStatus()` — 200 | Парсинг FullStatusResponse |
| `restartMcp()` — 200 | Result.success(true) |
| `pingDevice()` — 200 | Result.success(true) |
| `sendTelegramNotification()` — 200 | Result.success(true) |
| `sendTelegramNotification()` — 401 (bad token) | Result.failure |
| Telegram disabled → не отправлять | Запрос НЕ выполняется |

### SessionMonitorServiceTest.kt

| Тест | Ожидание |
|------|----------|
| Старт сервиса → foreground notification | Notification создана |
| Цикл: токен валиден (> 2ч) | Sync если токен новый |
| Цикл: токен валиден, не изменился | Sync НЕ вызван |
| Цикл: токен скоро истечёт (< 2ч) | WARNING notification + Avito launch |
| Цикл: токен истёк | CRITICAL notification + Avito launch |
| AutoLaunch disabled + токен истекает | Notification есть, Avito НЕ запущен |
| После launch Avito: токен обновился | Sync вызван |
| После launch Avito: токен НЕ обновился | ERROR в логах |
| Notification cooldown (< 1ч) | Повторное уведомление подавлено |
| autoSyncEnabled = false | Sync НЕ вызван |
| Root недоступен | Лог ошибки, сервис продолжает |
| Avito не установлен | Лог ошибки, без crash |

### BootReceiverTest.kt

| Тест | Ожидание |
|------|----------|
| BOOT_COMPLETED + autoSync enabled | Сервис запускается |
| BOOT_COMPLETED + autoSync disabled | Сервис НЕ запускается |
| Другой Intent action | Ничего не происходит |

## Интеграционные тесты

### С реальным Backend (на dev-сервере)

| Тест | Ожидание |
|------|----------|
| Полный цикл: чтение → парсинг → sync | 200 OK, данные на сервере |
| Health check к реальному серверу | 200 OK |
| Full status от реального сервера | Парсинг без ошибок |
| Sync → Telegram notification | Сообщение в Telegram |

### На реальном устройстве

| Тест | Предусловие | Ожидание |
|------|-------------|----------|
| Root-доступ | Magisk установлен | `isRoot = true` |
| Чтение SharedPrefs | Avito авторизован | SessionData ≠ null |
| JWT exp в будущем | Свежий токен | `hoursUntilExpiry > 0` |
| Auto-launch Avito | Avito установлен | Приложение открывается |
| Boot persistence | Перезагрузка | Сервис запускается |
| Foreground notification | Сервис запущен | Уведомление в шторке |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все unit-тесты зелёные | 100% |
| Покрытие SessionData.kt | ≥ 95% |
| Покрытие AvitoSessionReader.kt | ≥ 85% |
| Покрытие ServerApi.kt | ≥ 85% |
| Покрытие SessionMonitorService.kt | ≥ 75% |
| Нет обращений к реальному root в unit-тестах | 0 |
| Нет обращений к реальной сети в unit-тестах | 0 (MockWebServer) |

## Метрики

| Метрика | Цель |
|---------|------|
| Парсинг JWT | < 5 мс |
| Парсинг XML SharedPrefs | < 20 мс |
| Root read (su -c cat) | < 500 мс |
| Синхронизация на Backend | < 3 сек |
| Запуск Avito + ожидание refresh | < 10 сек |
| Foreground Service RAM | < 30 MB |
| Battery impact (30 мин интервал) | < 1% / час |

## Запуск тестов

### Unit-тесты (без устройства)
```bash
cd part6-Android-token
./gradlew testDebugUnitTest
```

### С покрытием
```bash
./gradlew testDebugUnitTest jacocoTestReport
# Отчёт: app/build/reports/jacoco/
```

### На устройстве (instrumented)
```bash
./gradlew connectedDebugAndroidTest
```
