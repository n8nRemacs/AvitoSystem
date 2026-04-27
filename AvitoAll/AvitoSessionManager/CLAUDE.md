# AvitoSessionManager — Android Root App

**Назначение:** Kotlin-приложение для рут-телефона: читает сессию Avito из SharedPreferences через `su -c cat`, мониторит истечение JWT и синхронизирует токены на сервер.

**Статус:** working — компилируемый и рабочий APK.

**Стек/технологии:** Kotlin, Android SDK 26+, libsu (root), OkHttp 4, Foreground Service, WorkManager.

## Что внутри

```
app/src/main/java/com/avitobridge/
├── data/
│   ├── AvitoSessionReader.kt  — чтение XML SharedPrefs через root (libsu)
│   ├── SessionData.kt         — модель данных + JWT-парсер + форматирование времени
│   ├── PrefsManager.kt        — настройки приложения
│   └── ServerApi.kt           — OkHttp HTTP-клиент для sync на сервер
├── service/
│   ├── SessionMonitorService.kt — Foreground Service, периодическая проверка
│   └── BootReceiver.kt          — автозапуск при загрузке
└── ui/
    └── MainActivity.kt          — UI: статус, кнопки sync/MCP restart
```

**Читаемые поля из SharedPrefs Avito:**
`session` (JWT), `fpx` (fingerprint), `device_id`, `user_hash_id`, `refresh_token`, cookies.

**Путь к файлу:** `/data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml`

**API сервера:** `POST /api/v1/sessions` с заголовком `X-Device-Key`.

## Что полезно для V1

Готовый APK для получения токенов с реального телефона. Если используется как источник токенов в V1 — можно установить as-is. `SessionData.kt` содержит рабочий JWT-парсер для Kotlin.

Сборка: `gradlew.bat assembleDebug` (требует JAVA_HOME на Android Studio JBR).

## Что НЕ использовать

README.md уже есть (`README.md`). Не дублировать архитектуру — она описана там же и в `TECHNICAL_SPECIFICATION.md` родительской папки.

## Ссылки

- `../TECHNICAL_SPECIFICATION.md` — детальная архитектура всей системы Avito Bridge
- `../avito-system/part6-Android-token/` — аналогичная задача в старой архитектуре (только SPEC.md)
