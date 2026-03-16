# Avito Session Manager

Android приложение для автоматического захвата и синхронизации сессии Avito с сервером.

## Требования

- Android устройство с **ROOT доступом** (Magisk)
- Установленное приложение Avito (авторизованное)
- Android 8.0+ (API 26+)

## Функции

### 1. Чтение сессии
Читает данные сессии из SharedPreferences Avito через root:
- JWT токен (sessid) - время жизни 24 часа
- Fingerprint (заголовок `f`) - критически важен для API
- Device ID, User ID, cookies, refresh_token

### 2. Синхронизация с сервером
Два режима:
- **Ручной** - кнопка "Sync Now"
- **Автоматический** - синхронизирует за N часов до истечения токена

### 3. Авто-обновление токена
Когда токен скоро истекает:
- **Auto-launch Avito** - автоматически открывает Avito для обновления токена
- **Notify on expiry** - показывает уведомление с напоминанием
- Можно включить оба варианта одновременно

### 4. Фоновый мониторинг
Foreground Service который:
- Периодически проверяет состояние токена (настраиваемый интервал)
- Показывает время до истечения в формате `Xh Ym`
- Автоматически синхронизирует при приближении к истечению
- Показывает уведомление со статусом

### 5. Управление MCP ботом
- Просмотр статуса MCP (Telegram бота) на сервере
- Кнопка "Restart MCP" для перезапуска бота

## Установка

### Сборка (Windows)
```bash
cd AvitoSessionManager
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
gradlew.bat assembleDebug
```

APK будет в `app/build/outputs/apk/debug/app-debug.apk`

### Установка на устройство
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Настройки

| Настройка | Описание | По умолчанию |
|-----------|----------|--------------|
| **Server URL** | Адрес сервера для синхронизации | `http://155.212.221.189:8080` |
| **API Key** | Ключ авторизации устройства | `avito_sync_key_2026` |
| **Check interval** | Как часто проверять токен (минуты) | `30` |
| **Sync before expiry** | За сколько часов до истечения синхронизировать | `2` |
| **Auto-sync** | Включить автоматическую синхронизацию | `ON` |
| **Auto-launch Avito** | Запускать Avito при истечении токена | `ON` |
| **Notify on expiry** | Показывать уведомление при истечении | `ON` |

## API сервера

### POST /api/v1/sessions
Приложение отправляет сессию на сервер:

```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "fd74bc392447ed35a52d6546d0e4034e",
  "fingerprint": "A2.a541fb18def1032c...",
  "device_id": "a8d7b75625458809",
  "remote_device_id": "kSCwY4Kj4HUf...android",
  "user_id": 157920214,
  "user_hash": "4c48533419806d790635e8565693e5c2",
  "expires_at": 1768379484,
  "cookies": {"1f_uid": "uuid", "u": "string", "v": "timestamp"},
  "synced_at": 1768293084
}
```

Headers:
- `Content-Type: application/json`
- `X-Device-Key: {API_KEY}`

### GET /api/v1/full-status
Получение полного статуса сервера (токен + MCP бот)

### POST /api/v1/mcp/restart
Перезапуск MCP бота (требует API Key)

## Структура проекта

```
app/src/main/java/com/avitobridge/
├── App.kt                        # Application, notification channel
├── data/
│   ├── PrefsManager.kt           # Настройки приложения (SharedPreferences)
│   ├── SessionData.kt            # Модели данных, JWT парсер, форматирование времени
│   ├── AvitoSessionReader.kt     # Чтение SharedPreferences Avito через root (libsu)
│   └── ServerApi.kt              # HTTP клиент (OkHttp), TelegramNotifier
├── service/
│   ├── SessionMonitorService.kt  # Foreground сервис мониторинга
│   └── BootReceiver.kt           # Автозапуск при загрузке устройства
└── ui/
    └── MainActivity.kt           # Главный экран с UI
```

## Как работает

```
┌─────────────────────────────────────────────────────────────┐
│                    Android Device (Rooted)                   │
│                                                              │
│  ┌──────────────────┐        ┌─────────────────────────┐   │
│  │   Avito App      │◄──────►│  AvitoSessionManager    │   │
│  │   (Official)     │  root  │                         │   │
│  │                  │  read  │  • SessionMonitorService│   │
│  │  SharedPrefs:    │        │  • Auto-launch Avito    │   │
│  │  - session (JWT) │        │  • Notifications        │   │
│  │  - fpx           │        │  • Server sync          │   │
│  │  - device_id     │        └───────────┬─────────────┘   │
│  └──────────────────┘                    │                  │
└──────────────────────────────────────────┼──────────────────┘
                                           │ HTTPS POST
                                           ▼
                              ┌─────────────────────────┐
                              │   Server (:8080)        │
                              │                         │
                              │  • Saves session JSON   │
                              │  • Restarts MCP bot     │
                              └─────────────────────────┘
```

1. **AvitoSessionReader** читает файл через `su -c cat`:
   `/data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml`

2. Парсит XML и извлекает:
   - `session` - JWT токен
   - `fpx` - fingerprint
   - `device_id`, `user_hash_id`, `refresh_token` и др.

3. **SessionMonitorService** периодически:
   - Читает текущую сессию
   - Проверяет время до истечения
   - При приближении к истечению: уведомление и/или запуск Avito
   - Отправляет на сервер если нужно

4. При получении новой сессии сервер:
   - Сохраняет в `avito_session_new.json`
   - Перезапускает MCP бот (`systemctl restart avito-bridge`)

## Важно

- Приложение Avito должно быть авторизовано
- Avito само обновляет токен каждые 24 часа при запуске
- Наше приложение только **читает** данные, не модифицирует
- Fingerprint генерируется native-библиотекой Avito, невозможно воспроизвести

## Troubleshooting

### "No root access"
- Проверить что Magisk установлен и работает
- Предоставить root доступ приложению в Magisk → Superuser
- Попробовать переустановить приложение

### "Failed to read session"
- Проверить что Avito установлен и авторизован
- Открыть Avito хотя бы раз после установки
- Проверить путь: `/data/user/0/com.avito.android/shared_prefs/`

### "Sync failed"
- Проверить настройки сервера (URL, API Key)
- Проверить сетевое подключение
- Проверить что сервер доступен: `curl http://SERVER:8080/health`

### Token не обновляется
- Открыть Avito вручную - токен обновится автоматически
- Включить "Auto-launch Avito" в настройках
- Проверить что Avito не в фоновых ограничениях Android

## Зависимости

```kotlin
// Root access
implementation("com.github.topjohnwu.libsu:core:5.2.2")
implementation("com.github.topjohnwu.libsu:service:5.2.2")

// Networking
implementation("com.squareup.okhttp3:okhttp:4.12.0")
implementation("com.google.code.gson:gson:2.10.1")

// Android
implementation("androidx.core:core-ktx:1.12.0")
implementation("androidx.work:work-runtime-ktx:2.9.0")
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
```

---

*Версия: 1.1*
*Обновлено: 2026-01-14*
