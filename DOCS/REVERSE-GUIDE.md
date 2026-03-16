# Avito Android Reverse Engineering Guide

> **Цель:** Получение fingerprint-данных и перехват трафика приложения Avito Android.
>
> **Устройство:** OnePlus 9 (LE2115), Android 14, Magisk 30.6, root.
>
> **APK:** com.avito.android v217.2, targetSdk 35, minSdk 27.

---

## Оглавление

1. [Инфраструктура и инструменты](#1-инфраструктура-и-инструменты)
2. [Защита Avito — что мешает](#2-защита-avito--что-мешает)
3. [Подход 1: Статический анализ DEX (РАБОТАЕТ)](#3-подход-1-статический-анализ-dex-работает)
4. [Подход 2: Сбор данных через ADB (РАБОТАЕТ)](#4-подход-2-сбор-данных-через-adb-работает)
5. [Подход 3: Frida runtime hooks (ЗАБЛОКИРОВАН)](#5-подход-3-frida-runtime-hooks-заблокирован)
6. [Подход 4: MITM трафика (ЗАБЛОКИРОВАН)](#6-подход-4-mitm-трафика-заблокирован)
7. [Подход 5: Frida Gadget в APK (ЧАСТИЧНО)](#7-подход-5-frida-gadget-в-apk-частично)
8. [Подход 6: tcpdump на устройстве (ЧАСТИЧНО)](#8-подход-6-tcpdump-на-устройстве-частично)
9. [Что делать в следующий раз](#9-что-делать-в-следующий-раз)
10. [Справочник файлов](#10-справочник-файлов)

---

## 1. Инфраструктура и инструменты

### Требования на PC (Windows)

```
pip install frida-tools   # Frida Python bindings (17.6.2)
pip install mitmproxy      # MITM proxy (12.2.1)
pip install scapy           # PCAP анализ (опционально)
pip install androguard      # APK/DEX анализ (опционально)
pip install lief            # ELF/APK патчинг (для Gadget подхода)
pip install cryptography    # Для sign_v2.py
```

### Требования на устройстве

| Компонент | Путь | Как установить |
|-----------|------|----------------|
| Magisk | — | Через recovery/патч boot.img |
| frida-server | `/data/local/tmp/frida-server` | Скачать с github.com/frida/frida/releases (arm64) |
| tcpdump | `/system/bin/tcpdump` | Обычно предустановлен; или `apt install tcpdump` через Termux |
| Root shell | `su` | Через Magisk |

### Установка frida-server

```bash
# Узнать архитектуру
adb shell getprop ro.product.cpu.abi
# -> arm64-v8a

# Скачать frida-server-{version}-android-arm64.xz
# Распаковать и залить:
adb push frida-server /data/local/tmp/
adb shell "su -c 'chmod 755 /data/local/tmp/frida-server'"
```

### Запуск frida-server

```bash
# ВАЖНО: Avito детектит имя процесса "frida-server"
# Переименовать:
adb shell "su -c 'cp /data/local/tmp/frida-server /data/local/tmp/hlpd'"
adb shell "su -c 'chmod 755 /data/local/tmp/hlpd'"

# Запустить:
adb shell "su -c 'nohup /data/local/tmp/hlpd -D > /dev/null 2>&1 &'"

# Проверить:
adb shell "su -c 'pidof hlpd'"
```

> **КРИТИЧНО:** Всегда переименовывать frida-server. Имя `frida-server` детектится.

### ADB подключение

```bash
# Проверить устройство
adb devices
# -> cca17101    device

# USB debugging должен быть включён в Developer Options
# При первом подключении — подтвердить диалог на телефоне
```

---

## 2. Защита Avito — что мешает

### Anti-Frida (АГРЕССИВНАЯ)

Avito использует **Cyberity Mobile SDK** + **RootBeer** для детекции:

| Метод детекции | Описание | Результат |
|----------------|----------|-----------|
| `/proc/self/maps` scan | Ищет строки "frida", "gadget", "gmain" в memory maps | Убивает процесс |
| Port 27042 check | Проверяет стандартный порт Frida | Блокирует |
| Process name scan | Ищет процесс "frida-server" | Детектит |
| `strstr()` scan | Ищет строки "frida-agent", "linjector" в памяти | Детектит |
| Timing check | create_script() занимает >100ms → детект успевает сработать | Connection closed |

**Поведение:** Frida `attach()` успевает подключиться, но `create_script()` вызывает загрузку frida-agent.so → появляется в /proc/self/maps → Avito убивает себя через ~1-2 секунды.

**Доказательство:** Минимальный `send("hello")` один раз сработал (повезло с таймингом), но любой реальный скрипт — `TransportError: the connection is closed`.

### SSL Pinning

| Метод | Описание |
|-------|----------|
| OkHttp3 CertificatePinner | Кастомный pinning сертификатов Avito серверов |
| Network Security Config | `android:networkSecurityConfig` в manifest |
| Cyberity SDK | Дополнительная проверка на уровне SDK |

**Результат:** mitmproxy с системным CA-сертификатом не перехватывает HTTPS.

### Root Detection (RootBeer)

| Проверка | Что ищет |
|----------|---------|
| su binary | `/system/bin/su`, `/su/bin/su`, `/system/bin/failsafe/su`, `/system/bin/.ext/` |
| Superuser.apk | `/system/app/Superuser.apk`, `/system/app/SuperSU.apk` |
| Blacklisted apps | `org.meowcat.edxposed.manager`, `org.creeplays.hack`, `org.mobilism.android` |
| Build props | `ro.debuggable`, `ro.build.tags != release-keys` |
| Native check | RootBeerNative JNI library |

### Encrypted DNS

Avito использует **DNS-over-HTTPS** или **DNS-over-TLS** — стандартные DNS-запросы через порт 53 не показывают домены Avito в tcpdump.

### APK Signature Check

```
appSignatureSha1=673ea7523e1e54c9f4e00743e941916affd0d90f
```

Avito проверяет свою подпись. Перепакованный APK с другой подписью будет отвергнут.

---

## 3. Подход 1: Статический анализ DEX (РАБОТАЕТ)

**Надёжность: 10/10** — работает всегда, не требует запуска приложения.

### Что получаем
- Все используемые fingerprint API (TelephonyManager, Build, Settings.Secure, etc.)
- Tracking SDK (AppsFlyer, GAID, Adjust, AppMetrica, VK ID, etc.)
- HTTP заголовки (X-Device-Fingerprint, X-App-Info, etc.)
- Root/tamper detection механизмы
- Permissions
- Обфусцированные имена классов

### Как запустить

```bash
cd avito-farm-agent

# 1. Положить APK
mkdir -p apk_work
# Скопировать avito.apk в apk_work/
adb shell "pm path com.avito.android"
# -> package:/data/app/.../base.apk
adb pull /data/app/.../base.apk apk_work/avito.apk

# 2. Запустить сканер
pip install androguard  # Для парсинга manifest (опционально)
python scan_fingerprint.py
```

### Скрипт: `scan_fingerprint.py`

Что делает:
1. Открывает APK как ZIP
2. Читает все `classes*.dex` файлы (их ~17 штук)
3. Ищет ~80 строковых паттернов (API имена, хедеры, пути)
4. Извлекает контекст вокруг найденных строк
5. Парсит AndroidManifest.xml через androguard (permissions, SDK versions)
6. Сохраняет в `fingerprint_analysis.json`

### Результат

`fingerprint_analysis.json` (~70KB) — категоризированные находки:
- `apk_info` — permissions, version, SDK
- `fingerprint_apis` — все найденные API
- `tracking_sdks` — SDK трекинга
- `detection_mechanisms` — root/tamper детекция
- `display_info` — экранные API
- `other` — кастомные заголовки

---

## 4. Подход 2: Сбор данных через ADB (РАБОТАЕТ)

**Надёжность: 10/10** — прямое чтение значений с устройства.

### Что получаем
Реальные значения тех же API, которые вызывает Avito. Не runtime-перехват, но те же данные.

### Команды

```bash
# === Build ===
adb shell getprop ro.product.model          # LE2115
adb shell getprop ro.product.manufacturer   # OnePlus
adb shell getprop ro.product.brand          # OnePlus
adb shell getprop ro.product.device         # OnePlus9
adb shell getprop ro.product.name           # OnePlus9
adb shell getprop ro.build.fingerprint      # OnePlus/OnePlus9/...
adb shell getprop ro.hardware               # qcom
adb shell getprop ro.product.board          # lahaina
adb shell getprop ro.build.display.id       # LE2115_14.0.0.1902(EX01)
adb shell getprop ro.build.host             # kvm-slave-build-...
adb shell getprop ro.build.id               # UKQ1.230924.001
adb shell getprop ro.build.type             # user
adb shell getprop ro.build.tags             # release-keys

# === Version ===
adb shell getprop ro.build.version.sdk            # 34
adb shell getprop ro.build.version.release         # 14
adb shell getprop ro.build.version.security_patch  # 2025-04-01
adb shell getprop ro.build.version.incremental     # R.209d31b_1-39324b

# === IDs ===
adb shell settings get secure android_id    # 38cbe2115f76909e

# GAID (нужен root):
adb shell "su -c 'cat /data/data/com.google.android.gms/shared_prefs/adid_settings.xml'"
# -> <string name="adid_key">70101066-0cf5-453b-9c43-ac14b3562a48</string>

# === Screen ===
adb shell wm size       # Physical size: 1080x2400
adb shell wm density    # Physical density: 480

# === Network ===
adb shell "dumpsys wifi | grep 'mWifiInfo' | head -1"
# -> SSID: "MiBeast2G", BSSID: 40:31:3c:d8:b3:cc, MAC: 12:ba:4b:69:31:b2

# === SIM ===
adb shell getprop gsm.sim.operator.alpha     # MegaFon
adb shell getprop gsm.operator.iso-country   # ru
adb shell getprop gsm.sim.operator.numeric   # 25002

# === Timezone/Locale ===
adb shell getprop persist.sys.timezone  # Europe/Samara
adb shell getprop persist.sys.locale    # ru-RU

# === Sensors ===
adb shell "dumpsys sensorservice | head -30"  # 33 h/w sensors

# === GPU ===
adb shell getprop ro.hardware.egl       # adreno
adb shell getprop ro.opengles.version   # 196610 (= ES 3.2)

# === Installed apps ===
adb shell "pm list packages | wc -l"    # 435

# === Accounts ===
adb shell "dumpsys account | grep -c 'Account'"  # 28

# === Vendor-specific (OnePlus/OPLUS) ===
adb shell getprop ro.build.version.oplusrom   # V14.0.0
adb shell getprop ro.oplus.version.my_heytap  # 3.4.5.0...

# === Serial ===
adb shell getprop ro.serialno    # cca17101
```

### Сохранение результатов

Все значения записываются в `DOCS/AVITO-FINGERPRINT.md` в раздел **Device Reference Values**.

---

## 5. Подход 3: Frida runtime hooks (ЗАБЛОКИРОВАН)

**Надёжность: 0/10** — Avito убивает процесс за 1-2 секунды.

### Что пытались

#### 5.1 Attach к работающему Avito

```python
import frida
device = frida.get_usb_device(timeout=10)
session = device.attach(PID)  # OK — подключается
script = session.create_script(code, runtime="v8")  # FAIL — connection closed
```

**Проблема:** `create_script()` загружает frida-agent.so в процесс → появляется в `/proc/self/maps` → Cyberity SDK детектит → `process-terminated`.

#### 5.2 Spawn mode

```python
pid = device.spawn(["com.avito.android"])  # FAIL
```

**Проблема:** `frida.TimedOutError: unexpectedly timed out while waiting for app to launch` или `frida.NotSupportedError: need Gadget to attach on jailed Android`.

#### 5.3 Anti-detect скрипт (anti_detect.js)

Хуки на нативном уровне: `strstr()`, `fgets()`, `connect()`, `popen()` — чтобы скрыть Frida.

**Проблема:** Скрипт не успевает загрузиться раньше, чем детект срабатывает. Anti-detect нужно инъектировать ДО frida-agent, но frida-agent — это и есть механизм инъекции.

#### 5.4 Переименование frida-server

```bash
adb shell "su -c 'cp /data/local/tmp/frida-server /data/local/tmp/hlpd'"
```

**Результат:** Помогает частично — процесс `frida-server` не детектится по имени. Но frida-agent.so всё равно детектится в `/proc/self/maps`.

### Что НЕ пробовали (потенциально может сработать)

| Метод | Сложность | Шанс |
|-------|-----------|------|
| **Shamiko** (Magisk module) | Низкая | Высокий — скрывает root + Frida от конкретных приложений |
| **LSPosed + TrustMeAlready** | Средняя | Высокий — SSL unpin без Frida |
| **Magisk DenyList** | Низкая | Средний — скрывает Magisk от Avito |
| **frida-server с патчем** | Высокая | Средний — пересобрать без характерных строк |
| **Stalker-based inject** | Высокая | Низкий |

### Скрипты

| Файл | Назначение | Статус |
|------|-----------|--------|
| `quick_sniff.js` | Хуки всех fingerprint API (Settings.Secure, TelephonyManager, Build, WiFi, etc.) | Написан, не работает из-за anti-Frida |
| `anti_detect.js` | Хуки strstr/fgets/connect для скрытия Frida | Написан, не успевает загрузиться |
| `ssl_bypass.js` | 10 хуков для обхода SSL pinning (OkHttp, TrustManager, SSLContext, etc.) | Написан, не работает из-за anti-Frida |
| `run_quick_sniff.py` | Python launcher для quick_sniff.js (spawn mode) | Написан |
| `run_mitm.py` | Объединённый launcher: mitmdump + Frida + SSL bypass | Написан |

---

## 6. Подход 4: MITM трафика (ЗАБЛОКИРОВАН)

**Надёжность: 0/10** — SSL pinning + игнорирование прокси.

### Что пытались

#### 6.1 Global HTTP proxy

```bash
adb shell "su -c 'settings put global http_proxy 127.0.0.1:8082'"
adb reverse tcp:8082 tcp:8082
mitmdump --mode regular -p 8082 --set ssl_insecure=true
```

**Результат:** 0 запросов перехвачено. Avito **не использует системный HTTP proxy** для своих запросов (OkHttp напрямую резолвит DNS и подключается).

#### 6.2 Системный CA сертификат

```bash
# Установка mitmproxy CA как системного сертификата
hash=$(openssl x509 -inform PEM -subject_hash_old -in ~/.mitmproxy/mitmproxy-ca-cert.pem | head -1)
adb push ~/.mitmproxy/mitmproxy-ca-cert.pem /data/local/tmp/${hash}.0
adb shell "su -c 'mount -t tmpfs tmpfs /system/etc/security/cacerts'"
adb shell "su -c 'cp /apex/com.android.conscrypt/cacerts/* /system/etc/security/cacerts/'"
adb shell "su -c 'cp /data/local/tmp/${hash}.0 /system/etc/security/cacerts/'"
```

**Результат:** Сертификат установлен, но OkHttp CertificatePinner отвергает его — custom pinning.

#### 6.3 Комбо: Frida SSL bypass + mitmproxy

Идея: Frida загружает ssl_bypass.js (отключает CertificatePinner), потом включаем proxy.

**Результат:** Frida не может загрузить скрипт (см. подход 3).

### Скрипт: `mitm_sniff.py`

Полный pipeline: mitmdump → ADB reverse → Frida spawn/attach → SSL bypass → proxy → анализ.

**Порядок важен:**
1. Запустить mitmdump
2. ADB reverse proxy
3. Запустить/подключиться к Avito (БЕЗ proxy)
4. Загрузить SSL bypass через Frida
5. ПОТОМ включить proxy (`settings put global http_proxy`)
6. Собирать трафик

> **Очистка proxy после работы:**
> ```bash
> adb shell "su -c 'settings put global http_proxy :0'"
> ```
> Если забыть — весь интернет на устройстве перестанет работать!

---

## 7. Подход 5: Frida Gadget в APK (ЧАСТИЧНО)

**Надёжность: 3/10** — APK запускается, но часто крашится.

### Суть

Встроить `libfrida-gadget.so` в APK как зависимость нативной библиотеки. Gadget загружается до Java-кода → хуки устанавливаются раньше anti-Frida.

### Pipeline

```
APK → unzip → patch .so (lief) → add gadget → repack → sign v1 → zipalign → sign v2 → install
```

### Скрипты

| Файл | Описание |
|------|----------|
| `patch_apk.py` | Распаковка APK, патч нативной .so через lief, добавление gadget config |
| `sign_apk.py` | JAR signing (v1) — генерация MANIFEST.MF, CERT.SF, CERT.RSA |
| `zipalign.py` | 4-byte alignment для Android R+ |
| `sign_v2.py` | APK Signature Scheme v2 — чистый Python, без Java/SDK |

### Критические уроки

#### 1. Выбор целевой библиотеки

```python
# ПЛОХО — эта библиотека НЕ загружается при старте:
preferred = ["libandroidx.graphics.path.so"]

# ХОРОШО — загружается при старте:
preferred = ["libcrashlytics.so"]
```

Проверить какие .so загружены: `adb shell "su -c 'cat /proc/PID/maps | grep .so'"`.

#### 2. META-INF/services/ НЕЛЬЗЯ удалять

```python
# ПЛОХО — удаляет ВСЁ, включая ServiceLoader файлы:
shutil.rmtree(meta_inf)

# ХОРОШО — удаляет только подписи:
for f in os.listdir(meta_inf):
    if f.upper() in ("MANIFEST.MF",) or f.upper().endswith((".SF", ".RSA", ".DSA", ".EC")):
        os.remove(os.path.join(meta_inf, f))
```

`META-INF/services/` содержит ServiceLoader конфигурации (kotlinx.coroutines, etc.). Без них — `ClassNotFoundException`.

#### 3. Gadget config: `resume`, НЕ `wait`

```json
{
  "interaction": {
    "type": "listen",
    "address": "0.0.0.0",
    "port": 27042,
    "on_load": "resume"
  }
}
```

`"on_load": "wait"` блокирует UI thread → Android убивает приложение через 5 секунд (ANR).

#### 4. APK Signature Scheme v2 обязателен для Android 14

Android 14 требует v2 подпись. `sign_v2.py` — чистая реализация на Python:
- Chunk-based digest (1MB chunks)
- RSA-PKCS1-v1.5 + SHA-256
- APK Signing Block между ZIP entries и Central Directory

#### 5. Нерешённая проблема: ClassNotFoundException

Перепакованный APK может крашиться с `ClassNotFoundException: android.view.vector`. Причина — нарушение DEX offsets при rezip. **Не решено.**

---

## 8. Подход 6: tcpdump на устройстве (ЧАСТИЧНО)

**Надёжность: 5/10** — видит трафик, но Avito использует encrypted DNS.

### Запуск

```bash
# Текстовый режим (DNS):
adb exec-out "su -c 'tcpdump -i any -nn -l -c 500 port 53 2>/dev/null'" > dns_capture.txt

# Бинарный PCAP (полный трафик):
adb exec-out "su -c 'tcpdump -i any -nn -w - -c 1000 2>/dev/null'" > capture.pcap

# ВАЖНО: использовать exec-out, НЕ "adb shell cat"
# "adb shell cat" повреждает бинарные данные (text mode conversion)
```

### Парсинг PCAP

Link type 276 = **Linux SLL2** (20 bytes header). Парсер в pcap_analysis.json.

### Результаты

- DNS: только 2 запроса (WhatsApp, Fastly CDN) — Avito не использует стандартный DNS
- TLS SNI: `www.ordercountrybrazil.com`, `mqtt-mini.facebook.com` — не Avito
- IP destinations: 149.154.167.41 (Telegram), 176.114.124.5 (возможно Avito), misc

### Вывод

Avito использует **encrypted DNS** (DoH/DoT) → стандартный tcpdump не показывает домены Avito.

---

## 9. Что делать в следующий раз

### Рекомендованный порядок (быстрый результат)

```
1. Статический анализ         — 10 минут, 80% данных
2. ADB сбор данных            — 5 минут, реальные значения
3. Попробовать Shamiko+Frida  — 20 минут, если сработает = 100% данных
4. Если не работает → LSPosed  — 30 минут
```

### Шаг 1: Статический анализ (гарантированно работает)

```bash
# Скачать APK
adb shell "pm path com.avito.android"
adb pull <path> avito-farm-agent/apk_work/avito.apk

# Запустить сканер
cd avito-farm-agent
python scan_fingerprint.py
# -> fingerprint_analysis.json
```

### Шаг 2: ADB данные устройства (гарантированно работает)

Выполнить все команды из [раздела 4](#4-подход-2-сбор-данных-через-adb-работает). Заполнить `DOCS/AVITO-FINGERPRINT.md`.

### Шаг 3: Shamiko (НЕ ПРОБОВАЛИ — высокий шанс)

```bash
# 1. Скачать Shamiko: github.com/LSPosed/LSPosed.github.io/releases
# (или альтернативу для Magisk 30.6+)

# 2. Установить Magisk module
adb push Shamiko-xxx.zip /sdcard/
# -> Magisk app → Modules → Install from storage → Shamiko

# 3. Добавить Avito в Magisk DenyList
adb shell "su -c 'magisk --denylist add com.avito.android'"

# 4. Перезагрузить
adb reboot

# 5. Проверить — Avito не видит root
# 6. Запустить frida-server (переименованный!)
adb shell "su -c 'nohup /data/local/tmp/hlpd -D > /dev/null 2>&1 &'"

# 7. Подключить Frida
python run_quick_sniff.py  # или quick_sniff.js через frida CLI
```

**Почему это должно сработать:** Shamiko скрывает Magisk, root и Zygisk от приложений в DenyList. Если Avito не видит root → RootBeer не срабатывает → Cyberity SDK может не запускать anti-Frida проверки (или запускать менее агрессивные).

### Шаг 4: LSPosed + TrustMeAlready (если Shamiko не помог)

```bash
# 1. Установить LSPosed (Zygisk)
# github.com/LSPosed/LSPosed

# 2. Установить модуль TrustMeAlready или SSLUnpinning
# → Активировать для com.avito.android

# 3. Это обходит SSL pinning БЕЗ Frida
# → mitmproxy будет перехватывать трафик
```

### Чеклист "всё работает"

- [ ] ADB видит устройство (`adb devices`)
- [ ] Root доступ (`adb shell "su -c 'whoami'"` → `root`)
- [ ] frida-server запущен (`adb shell "su -c 'pidof hlpd'"`)
- [ ] Avito запущен (`adb shell "pidof com.avito.android"`)
- [ ] Frida видит процесс: `python -c "import frida; d=frida.get_usb_device(); print([p for p in d.enumerate_processes() if p.pid == PID])"`
- [ ] ВАЖНО: Avito отображается как "Авито" (кириллица), НЕ "com.avito.android" в Frida

### Известные ловушки

| Проблема | Решение |
|----------|---------|
| `frida.ProcessNotFoundError` при attach | Frida ищет по имени "com.avito.android", но процесс называется "Авито". Использовать PID: `device.attach(PID)` |
| `frida.TransportError: connection closed` | Anti-Frida detection. Нужен Shamiko или другой bypass |
| `frida.TimedOutError` при spawn | Global HTTP proxy мешает запуску. Убрать proxy: `settings put global http_proxy :0` |
| `frida.NotSupportedError: need Gadget` | frida-server не запущен или упал. Перезапустить |
| `frida.ServerNotRunningError` | frida-server упал. Проверить `pidof hlpd`, перезапустить |
| MITM 0 requests | Avito игнорирует global proxy + SSL pinning. Нужен Frida SSL bypass или LSPosed |
| tcpdump no Avito DNS | Encrypted DNS (DoH/DoT). Не решается tcpdump |
| APK install: `NO_CERTIFICATES` | Нужна v2 подпись. Использовать `sign_v2.py` |
| APK install: `UPDATE_INCOMPATIBLE` | Другая подпись. `adb uninstall com.avito.android` перед установкой |
| APK crash: `ClassNotFoundException` | META-INF/services/ удалён. Исправить patch_apk.py и sign_apk.py |
| APK crash: kotlinx.coroutines | То же — META-INF/services/ |
| Proxy забыли выключить | `adb shell "su -c 'settings put global http_proxy :0'"` |

---

## 10. Справочник файлов

### Frida скрипты (JavaScript)

| Файл | Размер | Описание | Статус |
|------|--------|----------|--------|
| `quick_sniff.js` | 11K | Хуки 15+ API категорий (Settings.Secure, TelephonyManager, Build, WiFi, Display, ContentResolver, PackageManager, Sensors, GAID, System.getProperty, Runtime.exec, File.exists, WebView UA, Location, AccountManager, OkHttp headers) | Готов, заблокирован anti-Frida |
| `ssl_bypass.js` | 7K | 10 хуков SSL: OkHttp3 CertificatePinner, TrustManagerImpl, SSLContext.init, HostnameVerifier, NetworkSecurityConfig, Conscrypt, WebViewClient, TrustManagerFactory, Apache HTTP | Готов |
| `anti_detect.js` | 6K | Нативные хуки: strstr(), fgets(), connect(), popen() — скрытие Frida от /proc/self/maps, port scan, string scan | Готов, не успевает загрузиться |
| `sniff_fingerprint.js` | 24K | Расширенный сниффер (из ранней версии) | Готов |
| `grab_token.js` | 8K | Перехват access/refresh токенов | Готов |
| `spoof_fingerprint.js` | 9K | Подмена fingerprint значений | Готов |

### Python скрипты

| Файл | Описание | Статус |
|------|----------|--------|
| `scan_fingerprint.py` | Статический анализ DEX → JSON | **РАБОТАЕТ** |
| `run_quick_sniff.py` | Frida spawn + quick_sniff.js (45-60s collection) | Готов, заблокирован |
| `run_mitm.py` | Полный pipeline: mitmdump + Frida + SSL bypass + анализ | Готов, заблокирован |
| `mitm_sniff.py` | Альтернативный MITM pipeline с addon | Готов, заблокирован |
| `patch_apk.py` | APK распаковка + Frida Gadget injection через lief | Работает (но APK крашится) |
| `sign_apk.py` | JAR signing (v1) | Работает |
| `sign_v2.py` | APK Signature Scheme v2 (pure Python) | Работает |
| `zipalign.py` | ZIP alignment (4 bytes) | Работает |

### Данные

| Файл | Описание |
|------|----------|
| `fingerprint_analysis.json` | 70K — результат статического анализа |
| `pcap_analysis.json` | 1.5K — анализ сетевого трафика |
| `dns_capture.txt` | 36K — DNS-запросы (текст) |
| `avito_clean.pcap` | 490K — PCAP (binary, SLL2 link type 276) |
| `config.json` | Конфигурация farm agent |

### Документация

| Файл | Описание |
|------|----------|
| `DOCS/AVITO-FINGERPRINT.md` | Полный отчёт: API, значения, SDK, detection |
| `DOCS/REVERSE-GUIDE.md` | Этот документ |
