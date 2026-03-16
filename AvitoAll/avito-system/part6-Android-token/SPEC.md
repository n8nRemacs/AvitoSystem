# Part 6: Android Token Refresher (Rooted Phone → Backend)

## Обзор

Android-приложение для рутованного смартфона. Читает токены Avito из SharedPreferences через root-доступ, мониторит срок действия, автоматически обновляет и синхронизирует на Backend API.

**Стек:** Kotlin / Android SDK 34 / libsu (root) / OkHttp / Gson
**Пакет:** `com.avitobridge`
**Min SDK:** 26 (Android 8.0)
**Работает на:** рутованный Android-смартфон (Magisk/KernelSU)
**Базовый проект:** `APK/Avito/AvitoSessionManager`

## Отличие от Part 5 (Token Bridge)

| | Part 5: Token Bridge | Part 6: Android Token |
|--|---------------------|----------------------|
| Платформа | Сервер + Redroid (Docker) | Рутованный смартфон |
| Чтение токенов | `docker exec cat` | `su -c cat` (libsu) |
| Обновление токена | `am start` через docker exec | `startActivity()` нативно |
| Развёртывание | Python скрипт | APK (установка на телефон) |
| Интерфейс | Логи в stdout | UI с настройками |
| Автозапуск | systemd | BootReceiver + Foreground Service |
| Уведомления | Нет | Android Notifications + Telegram |

## Структура проекта

```
part6-Android-token/
├── SPEC.md
├── API.md
├── TESTING.md
└── app/
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/avitobridge/
        │   ├── App.kt                        # Application: notification channels
        │   ├── data/
        │   │   ├── AvitoSessionReader.kt     # Чтение SharedPrefs через root
        │   │   ├── PrefsManager.kt           # Настройки приложения
        │   │   ├── SessionData.kt            # Модели + JWT-парсинг
        │   │   └── ServerApi.kt              # HTTP-клиент + Telegram
        │   ├── service/
        │   │   ├── SessionMonitorService.kt  # Foreground Service (мониторинг)
        │   │   └── BootReceiver.kt           # Автозапуск при загрузке
        │   └── ui/
        │       └── MainActivity.kt           # Главный экран
        ├── res/
        │   ├── layout/
        │   │   ├── activity_main.xml         # Основной layout
        │   │   └── dialog_settings.xml       # Диалог настроек
        │   └── values/
        │       ├── colors.xml
        │       ├── strings.xml
        │       └── themes.xml
        └── build.gradle.kts
```

## Компоненты

### AvitoSessionReader.kt

Читает SharedPreferences Avito через root-доступ (libsu).

```kotlin
class AvitoSessionReader(private val context: Context) {

    fun readSession(): SessionData?
    // 1. Проверяет root: Shell.getShell().isRoot
    // 2. Пробует пути SharedPrefs по приоритету
    // 3. Выполняет su -c cat <path>
    // 4. Парсит XML → извлекает токены
    // 5. Парсит JWT → получает exp, user_id
    // 6. Возвращает SessionData или null
}
```

**Пути SharedPreferences (по приоритету):**
```
1. /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
2. /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
3. /data/user_de/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

**Методы чтения файла (fallback):**
1. `Shell.cmd("su -mm -c cat <path>")` — Magisk mount master
2. `Shell.cmd("su -c cat <path>")` — стандартный su
3. `Runtime.getRuntime().exec(arrayOf("su", "-c", "cat <path>"))` — fallback

**XML-маппинг:**

| XML name | SessionData field | Fallback names |
|----------|-------------------|----------------|
| `session` | `sessionToken` | `token` |
| `fpx` | `fingerprint` | `f`, `fingerprint` |
| `fpx_calc_time` | `fingerprintCalcTime` | — |
| `refresh_token` | `refreshToken` | — |
| `device_id` | `deviceId` | — |
| `remote_device_id` | `remoteDeviceId` | — |
| `user_hash` | `userHash` | — |
| `visitor_id` | `visitorId` | — |
| `1f_uid` | `cookies.1f_uid` | — |
| `u_cookie` | `cookies.u` | — |
| `v_cookie` | `cookies.v` | — |

### SessionData.kt

```kotlin
data class SessionData(
    val sessionToken: String,       // JWT (HS512, 24ч)
    val refreshToken: String?,
    val fingerprint: String,        // Заголовок "f" для API
    val deviceId: String?,
    val remoteDeviceId: String?,
    val userId: Long?,              // Из JWT payload → "u"
    val userHash: String?,
    val visitorId: String?,
    val expiresAt: Long?,           // Из JWT payload → "exp"
    val cookies: Map<String, String>
)

// JWT-парсинг без верификации подписи:
fun parseJwt(token: String): Map<String, Any>?
fun getExpiry(token: String): Long?
fun hoursUntilExpiry(token: String): Double
```

**JWT payload:**
```json
{
  "exp": 1770104756,    // Время истечения (unix timestamp)
  "iat": 1770018356,    // Время выдачи
  "u": 157920214,       // User ID
  "p": 28109599,        // Profile ID
  "s": "dd1ce4a4...",   // Session hash
  "h": "NDZkMTc5...",   // Hash (base64)
  "d": "a8d7b756...",   // Device ID
  "pl": "android"       // Платформа
}
```

### PrefsManager.kt

Управление настройками приложения через SharedPreferences (`avito_session_manager`).

```kotlin
class PrefsManager(context: Context) {

    // Настройки сервера
    var serverUrl: String           // Default: "http://155.212.221.189:8080"
    var apiKey: String              // Default: "avito_sync_key_2026"

    // Интервалы
    var checkIntervalMinutes: Int   // Default: 30
    var syncBeforeExpiryHours: Int  // Default: 2

    // Флаги
    var autoSyncEnabled: Boolean    // Default: true
    var autoLaunchAvito: Boolean    // Default: true
    var notifyOnExpiry: Boolean     // Default: true

    // Telegram
    var telegramEnabled: Boolean    // Default: false
    var telegramBotToken: String
    var telegramChatId: String

    // Кешированная сессия
    var cachedToken: String?
    var cachedFingerprint: String?
    var cachedExpiry: Long
    var lastSyncTime: Long
    var lastSyncStatus: String
}
```

### ServerApi.kt

HTTP-клиент для Backend API и Telegram.

```kotlin
class ServerApi(private val prefs: PrefsManager) {

    // Backend API
    fun syncSession(session: SessionData): Result<SyncResponse>
    fun healthCheck(): Result<Boolean>
    fun getFullStatus(): Result<FullStatusResponse>
    fun restartMcp(): Result<Boolean>
    fun pingDevice(battery: Int, avitoRunning: Boolean): Result<Boolean>

    // Telegram
    fun sendTelegramNotification(message: String): Result<Boolean>
}
```

### SessionMonitorService.kt

Foreground Service для фонового мониторинга.

```kotlin
class SessionMonitorService : Service() {

    // Цикл мониторинга (каждые checkIntervalMinutes):
    // 1. Проверить root-доступ
    // 2. Проверить установлен ли Avito
    // 3. Прочитать сессию через AvitoSessionReader
    // 4. Кешировать локально
    // 5. Проверить время до истечения
    //    ├─ > syncBeforeExpiryHours → sync если токен изменился
    //    ├─ 0 < hours < syncBeforeExpiryHours → запустить Avito, ждать 5с, перечитать
    //    └─ ≤ 0 (истёк) → запустить Avito, ждать, перечитать, логировать ошибку
    // 6. Синхронизировать на Backend
    // 7. Обновить уведомление
}
```

**Foreground Notification:**
- Channel: `session_monitor` (LOW importance)
- Показывает текущий статус: "Ready", "Checking...", "Token valid (12.5h)", "Token expired!"
- Action: "Sync Now" — немедленная синхронизация

**Expiry Notification:**
- Priority: HIGH
- Cooldown: 1 час между уведомлениями
- Action: открыть Avito для ручного обновления

### BootReceiver.kt

```kotlin
class BootReceiver : BroadcastReceiver() {
    // Слушает: android.intent.action.BOOT_COMPLETED
    // Если autoSyncEnabled → запускает SessionMonitorService
}
```

### MainActivity.kt

UI с 5 карточками:

```
┌────────────────────────────────┐
│  Server Status                 │
│  Token: ✅ Valid (12.5h left)  │
│  MCP Bot: 🟢 Running          │
│  [Refresh] [Restart MCP]      │
├────────────────────────────────┤
│  Device Session                │
│  Token: eyJhbG...  [Copy]     │
│  Fingerprint: A2.a541...      │
│  Expires: 2026-02-07 14:30    │
│  [Read Session]                │
├────────────────────────────────┤
│  Sync Status                   │
│  Last sync: 5 min ago ✅       │
│  [Sync Now]                    │
├────────────────────────────────┤
│  Settings                      │
│  Auto-sync: ✅  Auto-launch: ✅│
│  Notify: ✅     Telegram: ❌   │
│  [Settings]                    │
├────────────────────────────────┤
│  Service                       │
│  Status: 🟢 Running           │
│  [Start] [Stop]               │
└────────────────────────────────┘
```

## Permissions (AndroidManifest.xml)

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
```

## Зависимости (build.gradle.kts)

```kotlin
// Root access
implementation("com.github.topjohnwu.libsu:core:5.2.2")
implementation("com.github.topjohnwu.libsu:service:5.2.2")

// HTTP
implementation("com.squareup.okhttp3:okhttp:4.12.0")
implementation("com.google.code.gson:gson:2.10.1")

// Android
implementation("androidx.work:work-runtime-ktx:2.9.0")
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
implementation("com.google.android.material:material:1.11.0")
```

## Настройка

### Первоначальная

1. Собрать APK:
   ```bash
   cd part6-Android-token
   ./gradlew assembleRelease
   ```
2. Установить на рутованный телефон:
   ```bash
   adb install app/build/outputs/apk/release/app-release.apk
   ```
3. Открыть AvitoSessionManager
4. Settings → указать Server URL и API Key
5. Нажать "Read Session" → проверить что токен читается
6. Нажать "Start Service" → запустить мониторинг

### Требования к устройству

- Android 8.0+ (API 26+)
- Root-доступ (Magisk / KernelSU)
- Установлен Avito (авторизован по SMS)
- Стабильный интернет

## Обновление токенов

```
Токен живёт 24 часа.

Мониторинг каждые 30 минут:
├─ > 2 часов осталось → sync если токен новый
├─ 0-2 часа осталось:
│   └─ Запустить Avito (startActivity)
│   └─ Подождать 5 сек
│   └─ Перечитать SharedPreferences
│   └─ Если exp обновился → синхронизировать
└─ Истёк:
    └─ Запустить Avito
    └─ Подождать 5 сек
    └─ Перечитать
    └─ Если обновился → sync
    └─ Если нет → HIGH notification + Telegram alert
```

## Интеграция с Part 5

Part 5 и Part 6 — взаимозаменяемы. Оба отправляют токены на один Backend API.

- **Part 5** — для серверного Redroid (Docker), без UI, Python
- **Part 6** — для реального телефона, с UI и уведомлениями, Kotlin

Можно использовать оба одновременно (разные аккаунты Avito), Backend принимает сессии от любого источника.
