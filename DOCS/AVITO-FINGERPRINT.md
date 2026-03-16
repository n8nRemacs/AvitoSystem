# Avito Fingerprint Reconnaissance — Results

> **Status:** ЗАПОЛНЕНО — статический анализ APK v217.2 + значения устройства OnePlus 9 (LE2115, Android 14)
>
> **Источники данных:**
> - `fingerprint_analysis.json` — статический анализ DEX-файлов (scan_fingerprint.py)
> - `adb shell` — реальные значения устройства (Build props, Settings, sensors, etc.)
>
> **Примечание:** Runtime-хуки через Frida заблокированы анти-Frida защитой (Cyberity SDK + RootBeer).
> MITM-перехват заблокирован SSL pinning + encrypted DNS. Значения устройства получены напрямую через ADB.

---

## APK Info

| Параметр | Значение |
|----------|----------|
| Package | `com.avito.android` |
| Version | `217.2` |
| Target SDK | 35 (Android 15) |
| Min SDK | 27 (Android 8.1) |
| Total permissions | 55 |
| Fingerprint-relevant permissions | 17 |

---

## Summary

| Category | APIs Found (static) | Confidence | Notes |
|----------|---------------------|------------|-------|
| TelephonyManager | `getDeviceId`, `getImei` | HIGH | Найдены в 6+ DEX-файлах; также `getImeiParameters`, `getImeiFieldId/Value` |
| Settings.Secure | `android_id` | HIGH | Найдены в 6 DEX-файлах; строка `android_id` присутствует повсеместно |
| Build | `MANUFACTURER`, `VERSION.SDK_INT` | HIGH | Явные строки `Build.MANUFACTURER`, `Build.VERSION.SDK_INT` |
| Network/WiFi | `getSSID`, `getBSSID`, `NetworkInterface` | HIGH | WiFi-идентификация + перечисление сетевых интерфейсов |
| Advertising ID | `AdvertisingIdClient`, `getAdvertisingIdInfo` | HIGH | Google GAID + Huawei HMS OAID |
| Location | `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION` | MEDIUM | Permissions есть, runtime вызовы — TODO |
| PackageManager | `getInstalledPackages`, `getInstalledApplications` | HIGH | Перечисление установленных приложений |
| AccountManager | `GET_ACCOUNTS`, `MANAGE_ACCOUNTS` | MEDIUM | Permissions есть; runtime — TODO |
| Sensors | `SensorManager`, `getSensorList` | HIGH | Перечисление датчиков устройства |
| File I/O | `/system/bin/su`, `/system/app/Superuser.apk` | HIGH | Чтение путей для root-детекции |
| Display | `DisplayMetrics`, `densityDpi`, `widthPixels`, `heightPixels` | HIGH | Во всех DEX-файлах; полные метрики экрана |
| System props | `SystemProperties`, `ro.build.*`, `ro.product.*`, `getprop` | HIGH | Чтение build props + vendor-специфичных свойств |
| Runtime.exec | `getprop`, `/system/bin/getprop` | HIGH | Shell-вызов для чтения system properties |
| WebView UA | `getUserAgent`, `getUserAgentString` | HIGH | Явный feature-toggle: `getUserAgentAndFingerprintHeadersInFresco` |
| ContentResolver | `android_id` через Settings.Secure | HIGH | ContentResolver для android_id |
| OpenGL | `GLES20` | MEDIUM | GPU fingerprinting через OpenGL ES 2.0 |
| Hashing | `MessageDigest` (SHA-256) | HIGH | В 10+ DEX-файлах; используется для хеширования device ID |
| Battery | `BatteryManager` | LOW | Одиночное упоминание; может не участвовать в fingerprint |
| Clipboard | `ClipboardManager` | LOW | Широкое использование, но скорее функциональное |
| Timezone/Locale | `TimeZone`, `Locale` | MEDIUM | Везде; участвуют в fingerprint как env-параметры |

---

## Tracking SDKs

| SDK | Найден? | DEX-файлы | Детали |
|-----|---------|-----------|--------|
| **AppsFlyer** | YES | classes7.dex | `ro.appsflyer.preinstall.path` — preinstall attribution |
| **Google GAID** | YES | classes6-10, 14 | `AdvertisingIdClient`, `getAdvertisingIdInfo`, permission `AD_ID` |
| **Huawei HMS OAID** | YES | classes8.dex | `com.huawei.hms.ads.identifier.AdvertisingIdClient` |
| **Adjust** | YES | classes11.dex | `adjustId`, `adjust_id` — attribution tracker |
| **MyTracker** | YES | classes7.dex | `MyTrackerRepository`, `InstalledPackagesProvider` |
| **AppMetrica (Yandex)** | YES | classes (multiple) | `appmetrica_device_id_hash`, `appmetrica_gender`, `appmetrica_locks` |
| **Sentry** | YES | classes (multiple) | `io/sentry/android/replay/util/SystemProperties` — replay + crash reporting |
| **VK ID SDK** | YES | classes (multiple) | `getDeviceId$vkid_release`, `getUserAgent$network_release`, `__vk_device_id__` |
| **SberID** | YES | classes (multiple) | `ru.sberbank.mobile.sberid.BIND_PERSONALIZATION_SERVICE` |
| **Google Install Referrer** | YES | classes (multiple) | `com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE` |
| **Google AdServices** | YES | classes (multiple) | `ACCESS_ADSERVICES_ATTRIBUTION`, `ACCESS_ADSERVICES_AD_ID` |
| **Cyberity** | YES | classes (multiple) | `getMetricsScope$cyberity_mobile_sdk_release` — security/fraud SDK |

---

## Detection Mechanisms (Anti-Tamper)

### Root Detection

| Метод | Найден? | DEX-файлы | Детали |
|-------|---------|-----------|--------|
| **RootBeer library** | YES | classes7.dex | `com/scottyab/rootbeer/RootBeerNative`, `com/scottyab/rootbeer/a`, `com/scottyab/rootbeer/b` |
| `isRooted` check | YES | classes7, 9 | `isRooted`, `isRooted1`, `isRooted2` — минимум 2 метода проверки |
| Superuser.apk paths | YES | classes7-9 | Проверяемые пути: |
| | | | `/system/app/Superuser.apk` |
| | | | `/system/app/Superuser/Superuser.apk` |
| | | | `/system/app/SuperSU.apk` |
| su binary paths | YES | classes7-9 | Проверяемые пути: |
| | | | `/system/bin/su` |
| | | | `/su/bin/su` |
| | | | `/system/bin/failsafe/su` |
| | | | `/system/bin/.ext/` (hidden su) |
| | | | `/system/sbin` |
| | | | `/system/bin/which su` |
| `getprop` shell exec | YES | classes7.dex | `/system/bin/getprop` — чтение system props для определения root |
| `/sys/devices/system/cpu` | YES | classes8.dex | Чтение CPU topology (anti-emulator) |
| **DeviceParamsDataProvider** | YES | classes9.dex | `collecting isRooted exception` — Avito-специфичный сборщик параметров устройства |

### Frida Detection

| Метод | Найден? | Детали |
|-------|---------|--------|
| String `frida` | UNCERTAIN | Строка `frida` найдена в 4 DEX-файлах, но контекст показывает ложные срабатывания (TLD `.friday`, день недели `friday`) |
| Прямая детекция Frida-сервера | TODO: runtime sniff needed | Может быть обфусцирована; статический анализ недостаточен |
| Проверка `/proc/self/maps` | TODO: runtime sniff needed | Стандартный метод детекции Frida |
| Проверка открытых портов (27042) | TODO: runtime sniff needed | Стандартный метод детекции Frida |

### Xposed Detection

| Метод | Найден? | Детали |
|-------|---------|--------|
| String `xposed` | UNCERTAIN | Найдена в 6 DEX-файлах, но контекст показывает UI-термины (`ExposedDropdownMenu`, `exposed` AB-тесты) |
| `org.meowcat.edxposed.manager` | YES | classes7.dex — прямая проверка пакета EdXposed Manager в списке установленных приложений |
| Проверка hooks | TODO: runtime sniff needed | Может проверять наличие Xposed hooks через reflection |

### Hack-app Detection (package blacklist)

Из контекста `getInstalledPackages` и `xposed` видно, что проверяются:
- `org.meowcat.edxposed.manager` — EdXposed Manager
- `org.creeplays.hack` — hack-утилита
- `org.mobilism.android` — пиратский маркет

---

## Detailed Results

### TelephonyManager

| Method | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|--------|---------|-----------|----------------------|-------|
| `getDeviceId()` | YES | classes, 10, 13, 14, 6, 7 | Blocked (API 29+, targetSdk 35) | IMEI deprecated; `getDeviceId failed` — обработка SecurityException |
| `getImei()` | YES | classes10, 16, 17 | Blocked (API 29+) | `getImeiParameters`, `getImeiFieldId`, `getImeiFieldValue` — парсинг IMEI |
| `getSubscriberId()` | PROBABLE | — | Blocked (API 29+) | IMSI; статически не обнаружен явно, но SDK pattern |
| `getSimSerialNumber()` | PROBABLE | — | Blocked (API 29+) | Статически не обнаружен явно |
| `getLine1Number()` | PROBABLE | — | Blocked (API 29+) | Статически не обнаружен явно |
| `getNetworkOperator()` | YES | classes8, 9 | `25002` (MegaFon) | MCC+MNC |
| `getNetworkOperatorName()` | YES | classes8, 9 | `MegaFon` | Carrier name |
| `getSimOperator()` | PROBABLE | — | `25002` | Статически не обнаружен явно |
| `getNetworkCountryIso()` | YES | classes8, 9 | `ru` | Country ISO |
| `getSimCountryIso()` | PROBABLE | — | `ru` | |

### Settings.Secure

| Key | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `android_id` | YES | classes6-10, 17 | `38cbe2115f76909e` | Основной ID; feature toggle: `androidVersionSignal` |
| `development_settings_enabled` | YES | context strings | `0` (выключено) | Anti-tamper check |

### Build Fields

| Field | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-------|---------|-----------|----------------------|-------|
| `MANUFACTURER` | YES | classes9 | `OnePlus` | Явная строка `Build.MANUFACTURER: ` в логах |
| `VERSION.SDK_INT` | YES | classes4, 9 | `34` (Android 14) | Явная строка `Build.VERSION.SDK_INT: ` |
| `MODEL` | PROBABLE | — | `LE2115` | Стандартный fingerprint-сигнал |
| `BRAND` | PROBABLE | — | `OnePlus` | |
| `DEVICE` | PROBABLE | — | `OnePlus9` | |
| `PRODUCT` | PROBABLE | — | `OnePlus9` | |
| `FINGERPRINT` | PROBABLE | — | `OnePlus/OnePlus9/OnePlus9:14/UKQ1.230924.001/...` | Full build fingerprint string |
| `HARDWARE` | PROBABLE | — | `qcom` | Qualcomm SoC |
| `BOARD` | PROBABLE | — | `lahaina` | Snapdragon 888 platform |
| `DISPLAY` | PROBABLE | — | `LE2115_14.0.0.1902(EX01)` | |
| `HOST` | PROBABLE | — | `kvm-slave-build-s-system-07262362` | Build server |
| `ID` | PROBABLE | — | `UKQ1.230924.001` | |
| `TYPE` | PROBABLE | — | `user` | |
| `TAGS` | PROBABLE | — | `release-keys` | |
| `SERIAL` | PROBABLE | — | `cca17101` | Deprecated but still readable via root |
| `VERSION.RELEASE` | PROBABLE | — | `14` | |
| `VERSION.SECURITY_PATCH` | PROBABLE | — | `2025-04-01` | |
| `VERSION.INCREMENTAL` | PROBABLE | — | `R.209d31b_1-39324b` | |

### System Properties (ro.build.*, ro.product.*, etc.)

| Property | Найден? | DEX-файлы | Назначение |
|----------|---------|-----------|------------|
| `ro.build.date.utc` | YES | classes.dex | Дата сборки прошивки |
| `ro.build.freeme.label` | YES | classes6, 7 | Freeme OS detection |
| `ro.build.version.emui` | YES | classes6, 7 | Huawei EMUI version detection |
| `ro.build.version.oneui` | YES | classes6, 7 | Samsung OneUI version detection |
| `ro.build.version.opporom` | YES | classes6, 7 | OPPO ColorOS version detection |
| `ro.build.version.ark` | YES | classes7 | Huawei ARK compiler detection |
| `ro.build.characteristics` | YES | classes7 | Device characteristics (tablet, etc.) |
| `ro.build.hw_emui_api_level` | YES | classes7 | Huawei EMUI API level |
| `ro.miui.ui.version` | YES | classes6 | Xiaomi MIUI version detection |
| `ro.product.locale` | YES | classes7 | Device locale |
| `ro.product.locale.region` | YES | classes7 | Device region |
| `ro.hw.country` | YES | classes7 | Huawei country code |
| `ro.debuggable` | YES | classes7 | Debug build detection (anti-tamper) |
| `ro.appsflyer.preinstall.path` | YES | classes7 | AppsFlyer preinstall attribution path |
| `EMUI_SDK_INT` | YES | classes7 | EMUI SDK level (via SystemProperties) |

**Vendor OS Detection:** Avito определяет тип ОС/оболочки (EMUI, OneUI, MIUI, ColorOS, FreemeOS, ARK) через system properties. Это влияет на fingerprint.

### Network / WiFi

| API | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `WifiInfo.getSSID()` | YES | classes7-9 | `"MiBeast2G"` | Имя WiFi-сети |
| `WifiInfo.getBSSID()` | YES | classes7-8 | `40:31:3c:d8:b3:cc` | MAC роутера |
| `WifiInfo.getMacAddress()` | PROBABLE | — | `12:ba:4b:69:31:b2` | Randomized MAC (Android 10+) |
| `WifiInfo.getIpAddress()` | PROBABLE | — | `192.168.31.37` | Local IP |
| `WifiInfo.getLinkSpeed()` | PROBABLE | — | `173 Mbps` | |
| `WifiInfo.getFrequency()` | PROBABLE | — | `2417 MHz` | 2.4GHz band |
| `NetworkInterface.getNetworkInterfaces()` | YES | classes8-9 | wlan0, rmnet_data+ | Перечисление сетевых интерфейсов |
| Permission `ACCESS_WIFI_STATE` | YES | manifest | — | |
| Permission `ACCESS_NETWORK_STATE` | YES | manifest | — | |

### Advertising / Tracking IDs

| API | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `AdvertisingIdClient.getAdvertisingIdInfo()` | YES | classes6-8, 10, 14 | `70101066-0cf5-453b-9c43-ac14b3562a48` | Google GAID |
| `isLimitAdTrackingEnabled()` | YES | — | `false` | Ad tracking разрешён |
| Huawei HMS `AdvertisingIdClient` | YES | classes8 | N/A (не HMS-устройство) | Huawei OAID для HMS-устройств |
| `adjust_id` / `adjustId` | YES | classes11 | Generated at runtime | Adjust attribution ID |
| `appmetrica_device_id_hash` | YES | multiple | Generated at runtime | Yandex AppMetrica device hash |
| `__vk_device_id__` | YES | multiple | Generated at runtime | VK SDK device ID |
| Permission `AD_ID` | YES | manifest | — | `com.google.android.gms.permission.AD_ID` |
| Permission `ACCESS_ADSERVICES_AD_ID` | YES | manifest | — | Android Privacy Sandbox AD_ID |
| Permission `ACCESS_ADSERVICES_ATTRIBUTION` | YES | manifest | — | Android Privacy Sandbox Attribution |

### Display / Screen

| API | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `DisplayMetrics` | YES | ВСЕ DEX | — | Основной класс метрик экрана |
| `densityDpi` | YES | classes (11 файлов) | `480` (xxhdpi) | Плотность экрана |
| `widthPixels` | YES | classes (14 файлов) | `1080` | Ширина (FHD+) |
| `heightPixels` | YES | classes (16 файлов) | `2400` | Высота (FHD+) |
| `density` | PROBABLE | — | `3.0` | density = densityDpi / 160 |
| `xdpi` / `ydpi` | PROBABLE | — | ~480.0 | Physical DPI |
| `getMetrics()` | YES | classes6-9, 17 | — | Получение Display Metrics |
| `getRearDisplayMetrics()` | YES | context | N/A (не foldable) | Foldable-устройства |

### OpenGL / GPU

| API | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `GLES20` | YES | classes, 6-9 | — | OpenGL ES 2.0 |
| `GL_RENDERER` | PROBABLE | — | `Adreno (TM) 660` | Qualcomm Adreno GPU |
| `GL_VENDOR` | PROBABLE | — | `Qualcomm` | GPU vendor |
| `GL_VERSION` | PROBABLE | — | `OpenGL ES 3.2` (ro.opengles.version=196610) | ES 3.2 |
| EGL impl | PROBABLE | — | `adreno` (ro.hardware.egl) | |

### Sensors

| API | Найден? | DEX-файлы | Значение (OnePlus 9) | Notes |
|-----|---------|-----------|----------------------|-------|
| `SensorManager` | YES | classes, 6-9, 15 | — | Доступ к сенсорам |
| `getSensorList()` | YES | classes9 | **33 hardware sensors** | Уникальный набор для модели |
| Accelerometer | — | — | `icm4x6xx` (TDK-Invensense) | |
| Gyroscope | — | — | `icm4x6xx` (TDK-Invensense) | |
| Magnetometer | — | — | `mmc56x3x` (memsic) | |
| Light sensor | — | — | `tcs3701` (ams AG) | |
| Proximity | — | — | `stk33502` (oplus) | |
| Permission `USE_BIOMETRIC` | YES | manifest | — | Биометрия |
| Permission `USE_FINGERPRINT` | YES | manifest | — | Deprecated |

### Hashing (Device ID Processing)

| API | Найден? | DEX-файлы | Notes |
|-----|---------|-----------|-------|
| `MessageDigest` | YES | 10+ DEX-файлов | SHA-256, MD5 |
| `MessageDigest.SHA-256` | YES | explicit string | Явное использование SHA-256 для хеширования |
| `getDeviceIdHash` | YES | classes6, 7 | Avito хеширует device ID перед отправкой |
| `resettable_device_id_hash` | YES | Firebase Analytics | Firebase analytics device ID hash |
| `appmetrica_device_id_hash` | YES | AppMetrica | AppMetrica device ID hash |

### Installed Apps Check

| API | Найден? | DEX-файлы | Notes |
|-----|---------|-----------|-------|
| `getInstalledPackages()` | YES | classes7 | Перечисление всех установленных пакетов |
| `getInstalledApplications()` | YES | classes9 | Перечисление всех установленных приложений |
| `getInstallerPackageName()` | YES | classes7 | Откуда установлено приложение (Play Store / RuStore / APK) |

Черный список пакетов (обнаруженные):
- `org.meowcat.edxposed.manager` — EdXposed
- `org.creeplays.hack` — hack tool
- `org.mobilism.android` — pirated apps market

### File I/O (Root-related paths)

| Path | Проверяется? | Notes |
|------|-------------|-------|
| `/system/app/Superuser.apk` | YES | Root indicator |
| `/system/app/Superuser/Superuser.apk` | YES | Root indicator (newer) |
| `/system/app/SuperSU.apk` | YES | SuperSU root |
| `/system/bin/su` | YES | su binary |
| `/su/bin/su` | YES | Alternate su path |
| `/system/bin/failsafe/su` | YES | Failsafe su |
| `/system/bin/.ext/` | YES | Hidden su directory |
| `/system/bin/which su` | YES | which check for su |
| `/system/sbin` | YES | Alternate su location |
| `/system/bin/getprop` | YES | System property reader |
| `/sys/devices/system/cpu` | YES | CPU topology (anti-emulator) |

---

## HTTP Headers (Fingerprint Transport)

| Header | Найден? | DEX | Назначение |
|--------|---------|-----|------------|
| **`X-Device-Fingerprint`** | YES | classes9 | **Основной fingerprint-хедер** — содержит хеш устройства |
| `X-App-Info` | YES | classes9 | Информация о приложении (версия, build) |
| `X-Client-Id` | YES | classes9 | Идентификатор клиента |
| `X-Mob-App` | YES | classes9 | Тип мобильного приложения |
| `X-Mob-App-Framework` | YES | classes9 | Framework приложения |
| `X-Debug` | YES | classes9 | Debug flag |
| `X-Image-Id` | YES | classes9 | Image identification |
| `X-Applicant-Id` | YES | classes9 | Applicant identification |
| `X-Access-Token` | YES | classes9 | Токен авторизации |
| `User-Agent` | YES | multiple | Feature toggle: `getUserAgentAndFingerprintHeadersInFresco` |

**Ключевой вывод:** Feature toggle `getUserAgentAndFingerprintHeadersInFresco` указывает, что User-Agent и fingerprint передаются вместе, в том числе в запросах на загрузку изображений через Fresco.

---

## Device ID System

Avito использует собственную систему `remote_device_id`:

| Компонент | Класс (обфусцированный) | Notes |
|-----------|------------------------|-------|
| Domain logic | `com.avito.android.remote_device_id.domain.a` | |
| Domain logic | `com.avito.android.remote_device_id.domain.b` | |
| Domain logic | `com.avito.android.remote_device_id.domain.e` | С вложенным классом `e$a` |
| Domain logic | `com.avito.android.remote_device_id.domain.g` | С вложенным классом `g$a` |
| Background task | `com.avito.android.remote_device_id.task.background...` | Фоновое обновление device ID |
| Provider | `deviceIdProvider` | DI-компонент для device ID |
| Storage | `deviceIdStorage` / `DeviceIdStorage` | Хранение device ID на устройстве |
| Hash | `getDeviceIdHash()` | SHA-256 хеш device ID |
| DB table | `device_id_info` | Локальная SQLite-таблица |

**Ключевой вывод:** `remote_device_id` — это не просто `android_id`, а вычисляемый Avito-идентификатор, вероятно составленный из нескольких сигналов и синхронизируемый с сервером.

---

## Permissions (Fingerprint-Relevant)

| Permission | Для чего |
|------------|---------|
| `READ_PHONE_STATE` | IMEI, IMSI, phone number, network info |
| `ACCESS_FINE_LOCATION` | GPS coordinates |
| `ACCESS_COARSE_LOCATION` | Network-based location |
| `ACCESS_WIFI_STATE` | WiFi SSID, BSSID, MAC |
| `ACCESS_NETWORK_STATE` | Network type, connectivity |
| `BLUETOOTH` | Bluetooth MAC, paired devices |
| `BLUETOOTH_CONNECT` | Bluetooth device names |
| `NFC` | NFC presence |
| `CAMERA` | Camera specs (resolution, etc.) |
| `ACCESS_MEDIA_LOCATION` | EXIF location from photos |
| `USE_BIOMETRIC` | Biometric hardware presence |
| `USE_FINGERPRINT` | Fingerprint sensor presence (deprecated API) |
| `AD_ID` (`com.google.android.gms.permission`) | Google Advertising ID |
| `ACCESS_ADSERVICES_AD_ID` | Android Privacy Sandbox AD_ID |
| `ACCESS_ADSERVICES_ATTRIBUTION` | Android Privacy Sandbox Attribution |
| `GET_ACCOUNTS` | Google account list |
| `READ_CONTACTS` | Contacts (possible social graph) |

---

## Build Signature

Из контекста строк:

```
appSignatureSha1=673ea7523e1e54c9f4e00743e941916affd0d90f
appLocales=ru
buildType=releaseRuStore
isRelease=true
isDebuggable=false
```

Avito проверяет свою собственную подпись APK (`appSignatureSha1`). Это anti-tamper: если APK пересобрать, подпись изменится.

---

## Conclusions

### Minimum spoof set (для Token Farm)

На основе статического анализа:

1. **MUST SPOOF (критично для fingerprint):**
   - `android_id` — основной persistent ID
   - `device_id` / `remote_device_id` — Avito-специфичный вычисляемый ID
   - `deviceIdHash` — SHA-256 хеш device ID
   - `Build.MANUFACTURER` — производитель
   - `Build.VERSION.SDK_INT` — версия Android
   - `Build.MODEL`, `BRAND`, `DEVICE`, `PRODUCT` — TODO: подтвердить runtime
   - `DisplayMetrics` (densityDpi, widthPixels, heightPixels) — метрики экрана
   - `AdvertisingIdClient.getAdvertisingIdInfo()` — Google GAID
   - `User-Agent` заголовок
   - `X-Device-Fingerprint` заголовок — **главный fingerprint-хедер**
   - `TimeZone`, `Locale` — часовой пояс и язык
   - `appSignatureSha1` — подпись APK (нельзя менять, иначе tamper detection)

2. **SHOULD SPOOF (влияют на уникальность):**
   - `TelephonyManager.getDeviceId()` / `getImei()` — IMEI
   - `WifiInfo.getSSID()` / `getBSSID()` — WiFi-сеть
   - `NetworkInterface.getNetworkInterfaces()` — MAC-адреса
   - `SensorManager.getSensorList()` — список сенсоров (определяет модель)
   - `GLES20` GPU info — GPU renderer string
   - System properties: `ro.build.*`, `ro.product.*`, `ro.miui.ui.version`, etc.
   - `getInstalledPackages()` — список установленных приложений

3. **OPTIONAL (низкий приоритет):**
   - `BatteryManager` — уровень заряда
   - `ClipboardManager` — скорее функциональный, не fingerprint
   - `adjustId` — Adjust tracker (отдельный от device fingerprint)

4. **MUST BYPASS (anti-tamper):**
   - RootBeer (`com.scottyab.rootbeer`) — скрыть root
   - `isRooted` / `isRooted1` / `isRooted2` — все три метода проверки
   - Su binary path checks — скрыть файлы su
   - Blacklisted packages (`edxposed.manager`, `creeplays.hack`, `mobilism.android`) — скрыть из `getInstalledPackages`
   - `ro.debuggable` — вернуть `0`
   - `development_settings_enabled` — вернуть `0`
   - APK signature check — сохранить оригинальную подпись

### Implications for `spoof_fingerprint.js`

- **Per-profile values (уникальные для каждого аккаунта):**
  - `android_id`
  - `device_id` / `remote_device_id`
  - GAID (`AdvertisingIdInfo`)
  - IMEI (`getDeviceId`, `getImei`)
  - `deviceIdHash`
  - `X-Device-Fingerprint` header value

- **Per-device values (уникальные для каждого "устройства", можно шарить между аккаунтами):**
  - `Build.*` fields (MODEL, MANUFACTURER, BRAND, etc.)
  - `DisplayMetrics` (densityDpi, widthPixels, heightPixels)
  - `SensorManager.getSensorList()` result
  - `GLES20` GPU info
  - System properties (`ro.build.*`, `ro.product.*`)
  - `User-Agent` string
  - WiFi SSID / BSSID
  - Installed packages list
  - `TimeZone` / `Locale`

- **Shared values OK (одинаковые для всех):**
  - `BatteryManager` values
  - `ClipboardManager` (не трогать)

- **Special attention (critical anti-tamper):**
  - **RootBeer native library** (`RootBeerNative`) — использует JNI, нужен отдельный Frida-хук для native-уровня
  - **Cyberity SDK** (`cyberity_mobile_sdk_release`) — security/fraud detection SDK, может детектить Frida на native уровне
  - **APK signature** (`appSignatureSha1=673ea7523e1e54c9f4e00743e941916affd0d90f`) — не менять APK
  - **Multiple root check methods** (`isRooted`, `isRooted1`, `isRooted2`) — нужно перехватить все три
  - **Feature toggle system** — Avito использует feature toggles (например `getDeviceId` как toggle Feature), поведение может меняться server-side

---

## Device Reference Values (OnePlus 9 / LE2115)

| Category | Key | Value |
|----------|-----|-------|
| **Build** | MODEL | `LE2115` |
| | MANUFACTURER | `OnePlus` |
| | BRAND | `OnePlus` |
| | DEVICE | `OnePlus9` |
| | PRODUCT | `OnePlus9` |
| | FINGERPRINT | `OnePlus/OnePlus9/OnePlus9:14/UKQ1.230924.001/R.209d31b_1-39324b:user/release-keys` |
| | HARDWARE | `qcom` |
| | BOARD | `lahaina` |
| | DISPLAY | `LE2115_14.0.0.1902(EX01)` |
| | HOST | `kvm-slave-build-s-system-07262362` |
| | ID | `UKQ1.230924.001` |
| | TYPE | `user` |
| | TAGS | `release-keys` |
| | SERIAL | `cca17101` |
| **Version** | SDK_INT | `34` |
| | RELEASE | `14` |
| | SECURITY_PATCH | `2025-04-01` |
| | INCREMENTAL | `R.209d31b_1-39324b` |
| **IDs** | android_id | `38cbe2115f76909e` |
| | GAID | `70101066-0cf5-453b-9c43-ac14b3562a48` |
| | limitAdTracking | `false` |
| **Screen** | Resolution | `1080x2400` |
| | DensityDpi | `480` (xxhdpi) |
| | Density | `3.0` |
| **Network** | WiFi SSID | `"MiBeast2G"` |
| | WiFi BSSID | `40:31:3c:d8:b3:cc` |
| | WiFi MAC | `12:ba:4b:69:31:b2` (randomized) |
| | Local IP | `192.168.31.37` |
| | Link Speed | `173 Mbps` |
| | Frequency | `2417 MHz` |
| **SIM** | Operator | `MegaFon` (25002) |
| | Country | `ru` |
| **Locale** | Timezone | `Europe/Samara` |
| | Locale | `ru-RU` |
| | Product locale | `en-US` |
| **GPU** | EGL | `adreno` |
| | GL ES version | `3.2` (196610) |
| **Sensors** | Total | 33 hardware sensors |
| **Apps** | Installed | 435 packages |
| **Accounts** | Total | 28 accounts |
| **OnePlus** | OplusROM | `V14.0.0` |
| | HeyTap | `3.4.5.0.2025031801000130448133` |
| | OTA | `LE2115_11.H.29_3290_202510271426` |
| **Root** | su path | `/product/bin/su` |
| | Magisk | `30.6` |
| | frida-server | `/data/local/tmp/frida-server` |

---

## Raw Data

- Статический анализ: `avito-farm-agent/fingerprint_analysis.json`
- Данные устройства: собраны через `adb shell getprop`, `dumpsys`, `settings`
- PCAP анализ: `avito-farm-agent/pcap_analysis.json`
