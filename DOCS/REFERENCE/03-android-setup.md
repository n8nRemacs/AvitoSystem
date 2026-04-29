# Android Device Setup Reference

**Компилировано:** 2026-04-28
**Источники:** CONTINUE.md §3, token_farm_system.md, AVITO-FINGERPRINT.md,
  REVERSE-GUIDE.md, AvitoAll/AvitoSessionManager/README.md,
  account-pool-design.md §3.D10-D15, §7.5

---

## A. Аппаратная база

**Устройство:** OnePlus 8T (LE2115)
- CPU: Snapdragon 865
- RAM: 12 GB
- Storage: 256 GB (~300-500 MB на Android-user-профиль)
- Android: 14 (API 34)
- Root: Magisk 30.6
- ADB serial: `110139ce`

**Концепция:** Одно физическое устройство с N Android-users. Каждый user — изолированная файловая система, отдельная копия Avito-app со своими токенами. Для Avito anti-fraud = разные устройства (разный device_id).

---

## B. Android Multi-User (System Clone)

### B.1 Как работает

Android поддерживает множественные user profiles на уровне ОС. Файловая система каждого user физически изолирована:

```
/data/user/0/com.avito.android/   ← основной пользователь (user 0)
/data/user/10/com.avito.android/  ← System Clone (user 10) — наш Clone-аккаунт
/data/user/N/com.avito.android/   ← потенциальные будущие аккаунты
```

Данные между users не пересекаются: токены, SharedPreferences, БД — всё отдельно.

### B.2 Создание нового Android-user

```bash
adb shell pm create-user "clone_account_name"
# → Success: created user id 10
```

По умолчанию Android ограничивает число users до 4-5. Снятие лимита:
```bash
adb shell "su -c 'setprop fw.max_users 100'"
adb shell "su -c 'echo fw.max_users=100 >> /system/build.prop'"
```

### B.3 Установка приложений в System Clone

```bash
# Установить Avito в user 10 (должен быть уже установлен в user 0)
adb shell pm install-existing --user 10 com.avito.android

# Установить AvitoSessionManager APK в user 10
adb shell pm install-existing --user 10 com.avitobridge.sessionmanager
```

### B.4 Переключение foreground-пользователя

```bash
adb -s 110139ce shell am switch-user 10   # перейти в user 10
adb -s 110139ce shell am get-current-user  # проверить текущего
```

**Важно:** NotificationListener в неактивном (background) user может тормозиться Android Doze.
Рекомендуется раз в день-два открывать clone-пространство вручную (переключиться в foreground) на минуту — NL «прогревается».

Это же делает `device_switcher.switch_to()` перед refresh-командой (8 сек sleep после switch).

Источник реализации: `account-pool-design.md §7.5`

---

## C. Magisk Root Grant per-Android-User

### C.1 Формула UID

```
UID = androidUserId * 100000 + appId
```

Примеры для AvitoSessionManager (appId=10296):
- user 0: UID = `0 * 100000 + 10296 = 10296`
- user 10: UID = `10 * 100000 + 10296 = 1010296`

### C.2 Выдача root grant

```bash
# Выдать root AvitoSessionManager в user 10
adb -s 110139ce shell "su -c 'magisk --sqlite \"INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (1010296, 2, 0, 1, 1)\"'"

# policy=2 означает GRANT (постоянно, until=0)
```

Проверить все гранты:
```bash
adb -s 110139ce shell "su -c 'magisk --sqlite \"SELECT * FROM policies\"'"
```

Источник: `CONTINUE.md §3`

---

## D. NotificationListener Access

AvitoSessionManager должен быть registered как NotificationListener, чтобы ловить push-уведомления Avito (через которые он триггерится на чтение SharedPrefs).

```bash
# Выдать NL-access в конкретном Android-user
adb -s 110139ce shell "su -c 'settings --user 10 put secure enabled_notification_listeners com.avitobridge.sessionmanager/com.avitobridge.service.AvitoNotificationListener'"
```

Проверить:
```bash
adb -s 110139ce shell "settings --user 10 get secure enabled_notification_listeners"
```

**Известный quirk:** Background NL может зевнуть push при Android Doze. Фактически наблюдали на практике.

Источник: `CONTINUE.md §3`

---

## E. AvitoSessionManager APK — как работает

Package: `com.avitobridge.sessionmanager`
Версия исходника: 1.1 (2026-01-14)
Стек: Kotlin, Android SDK 26+, libsu (root), OkHttp 4, WorkManager

### E.1 Что делает

1. Слушает push-уведомления Avito через NotificationListener
2. При получении push (login/refresh event) — читает SharedPreferences Avito через root
3. Парсит XML, извлекает `session`, `fpx`, `device_id`, `remote_device_id`, `refresh_token`, cookies
4. POST `/api/v1/sessions` на xapi с полученными данными

### E.2 Критическое ограничение

**AvitoSessionManager НЕ читает SharedPreferences самостоятельно при старте.**
Он триггерится только push-уведомлением от Avito-app. Если push пропущен (NL-доступ выдан после login) — токен не зарегистрируется автоматически.

**Workaround:** Прямой `cat` SharedPreferences через root + POST на xapi.

```python
# scripts/register_clone_session.py
# Читает /data/user/10/com.avito.android/shared_prefs/com.avito.android_preferences.xml
# Парсит XML, POSTит в xapi /api/v1/sessions
# Токены не печатает в stdout
```

### E.3 Где хранятся prefs самого APK

```
/data/data/com.avitobridge.sessionmanager/shared_prefs/avito_session_manager.xml
```

Per-Android-user:
```
/data/user/N/com.avitobridge.sessionmanager/shared_prefs/...
```

### E.4 Конфигурация (настраивается в UI)

| Настройка | Описание | По умолчанию |
|---|---|---|
| Server URL | xapi base URL | `http://155.212.221.189:8080` |
| API Key | `X-Api-Key` для xapi | `avito_sync_key_2026` |
| Check interval | Как часто проверять токен | 30 мин |
| Sync before expiry | За сколько часов до истечения sync | 2 ч |

### E.5 Сборка APK

```bash
cd AvitoAll/AvitoSessionManager
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
gradlew.bat assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
adb install -r app-debug.apk
```

---

## F. Avito-app SharedPreferences — где живут токены

**Путь (per-Android-user):**
```
/data/user/{androidUserId}/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

Fallback пути (из более ранних версий):
```
/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
/data/user_de/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml
```

Формат XML:
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...</string>
    <string name="fpx">A2.a541fb18def1032c46e8ce9...</string>
    <string name="refresh_token">5c5b31d4b70e997ac188ad7723b395b4</string>
    <string name="device_id">a8d7b75625458809</string>
    <string name="remote_device_id">kSCwY4Kj4HUfwZHG...</string>
    <string name="user_hash">9b82afc1ab1e2419981f7a9d9d2b6af9</string>
    <long name="fpx_calc_time" value="1768297821046" />
</map>
```

Чтение через root:
```bash
adb -s 110139ce shell "su -c 'cat /data/user/10/com.avito.android/shared_prefs/com.avito.android_preferences.xml'"
```

Дополнительные прefs-файлы (альтернативные хранилища в старых версиях, проверять при проблемах):
```
/data/data/com.avito.android/shared_prefs/avito_auth_v2.xml
/data/data/com.avito.android/shared_prefs/auth_prefs.xml
/data/data/com.avito.android/shared_prefs/secure_prefs.xml
```

---

## G. ADB из LXC-контейнера

xapi работает в Proxmox LXC. Телефон подключён USB к хосту Proxmox и прокинут в LXC.

### G.1 LXC Config (Proxmox)

```
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir
```

Монтируется весь `/dev/bus/usb` (не один node) — это позволяет hot-plug новых телефонов без перезапуска контейнера.

Источник: `account-pool-design.md §7.5`

### G.2 Установка ADB в LXC

```bash
apt-get install android-tools-adb
adb start-server
adb devices   # должны быть видны все подключённые телефоны
```

### G.3 Работа с несколькими телефонами

```bash
adb devices
# → 110139ce   device
# → ABC123DEF  device   (будущий 2-й OnePlus)

adb -s 110139ce shell am switch-user 10
adb -s ABC123DEF shell am switch-user 0
```

Каждый физический device идентифицируется по ADB serial. В `avito_accounts.phone_serial` хранится этот serial.

---

## H. DeviceSwitcher — архитектура

`avito-xapi/src/workers/device_switcher.py` (новый компонент, план из account-pool-design.md):

```python
class DeviceSwitcher:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}  # per-phone lock

    async def switch_to(self, phone_serial: str, target: int) -> None:
        async with self._lock_for(phone_serial):
            if await self.current_user(phone_serial) == target:
                return
            # adb -s {phone_serial} shell am switch-user {target}
            # ждать current_user == target до 5 сек

    async def health(self, phone_serial: str) -> bool:
        # adb -s {phone_serial} get-state == 'device'
```

Параллелизм: switch на разных `phone_serial` не блокирует друг друга — разные locks.
Это критично при 2 OnePlus — refresh обоих аккаунтов может идти параллельно.

---

## I. Известные Quirks и Проблемы

### I.1 NotificationListener Background Freeze

NL в фоновом Android-user может пропускать push-уведомления из-за Android Doze.

**Mitigation:**
- `device_switcher.switch_to(phone_serial, android_user_id)` + 8 сек sleep перед каждой refresh-командой
- Периодически (раз в день) открывать clone-пространство вручную

### I.2 Avito Anti-Fraud Per-Account

Бан — per-account, не per-IP. Эмпирически подтверждено.
Защита: pool аккаунтов с round-robin + cooldown ratchet.

### I.3 System Clone Login Loss

System Clone может потерять Avito-логин при системных обновлениях Android.
При этом нужен ручной re-login и повторная регистрация сессии через register_clone_session.py.

### I.4 Token Refresh Race

`POST /api/v1/sessions` деактивирует все прежние активные сессии аккаунта.
При параллельных попытках refresh — last-write-wins (допустимо).

### I.5 APK Timeout → Dead State

Если AvitoSessionManager не ответил за 5 минут после refresh-команды:
```
account.state = dead
TG-alert: "Account {nickname} (Android-user {N}) не получил refresh за 5 минут. Открой вручную или проверь APK."
```

Ручное восстановление: открыть Android-user N в foreground → Avito-app → ждать refresh push → APK сам зарегистрирует сессию. Если не сработало — `register_clone_session.py`.

---

## J. Полезные команды

```bash
# ADB путь (Windows, к конкретному serial)
ADB="C:/Users/EloNout/AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v3.3.4/adb.exe"

# Все root grants
$ADB -s 110139ce shell "su -c 'magisk --sqlite \"SELECT * FROM policies\"'"

# Выдать grant (пример для новой установки SessionManager в user N)
# Сначала узнать appId: adb shell pm dump com.avitobridge.sessionmanager | grep userId
# UID = N * 100000 + appId
$ADB -s 110139ce shell "su -c 'magisk --sqlite \"INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (<UID>, 2, 0, 1, 1)\"'"

# NotificationListener в user N
$ADB -s 110139ce shell "su -c 'settings --user 10 put secure enabled_notification_listeners com.avitobridge.sessionmanager/com.avitobridge.service.AvitoNotificationListener'"

# Переключить foreground user
$ADB -s 110139ce shell am switch-user 10

# Зарегистрировать сессию напрямую из SharedPrefs
python scripts/register_clone_session.py

# Вручную запросить refresh через xapi
ssh homelab "curl -s -H 'X-Api-Key: test_dev_key_123' -H 'Content-Type: application/json' \
  -d '{\"command\":\"refresh_token\",\"payload\":{\"timeout_sec\":90,\"prev_exp\":0},\"issued_by\":\"manual\"}' \
  -X POST http://127.0.0.1:8080/api/v1/devices/me/commands"
```

Источник: `CONTINUE.md §5`
