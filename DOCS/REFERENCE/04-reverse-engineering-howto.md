# 04 — Методология реверс-инжиниринга Avito Android

**Создано:** 2026-04-28
**Устройство в наших экспериментах:** OnePlus 8T (LE2115), Android 14, Magisk 30.6
**Версии APK:** 215.1 (основные исследования), 217.2 (fingerprint-анализ), 222.5 (autosearches)

Этот документ — о том **как** проводить реверс, а не о том что открыли. Результаты — в `01-avito-api.md`.

---

## 1. Setup — инструменты и версии

### На хосте (Windows / Linux)

| Инструмент | Версия | Для чего |
|---|---|---|
| **jadx / jadx-gui** | 1.5.4 | Декомпиляция APK → Java/Kotlin. Главный инструмент static analysis |
| **apktool** | 2.9+ | Smali + ресурсы; нужен если хочешь патчить APK (например, `network_security_config.xml`) |
| **ADB** (Android Platform Tools) | свежий | USB debugging, pull файлов, shell-команды |
| **scrcpy** | 2.x | Экран устройства на ПК + удалённый ввод; удобно при навигации по app |
| **frida-tools** (pip) | 17.6.2 | Python-биндинги Frida: `frida`, `frida-ps`, `frida-trace` |
| **mitmproxy** (pip) | 12.2.1 | HTTPS-перехват; работает только при обходе SSL pinning |
| **lief** (pip) | — | Патч нативных `.so` в APK (для Frida Gadget-подхода) |
| **androguard** (pip) | — | Парсинг Manifest из APK; опционально |
| **curl_cffi** (pip) | — | TLS-impersonation при replay запросов |

```bash
pip install frida-tools mitmproxy lief androguard curl_cffi
```

jadx — отдельный download: https://github.com/skylot/jadx/releases (jar или GUI-бандл).

### На устройстве (Android)

| Компонент | Где лежит | Как получить |
|---|---|---|
| **Magisk** | системный уровень | Через recovery или патч `boot.img` |
| **frida-server** (arm64) | `/data/local/tmp/frida-server` | github.com/frida/frida/releases → `frida-server-{ver}-android-arm64.xz` |
| **tcpdump** | `/system/bin/tcpdump` | Обычно предустановлен; или через Termux |

**Никаких специальных APK на устройстве не нужно** для static analysis — только jadx на хосте.

---

## 2. Получение APK

### Вариант A: с устройства напрямую (предпочтительный)

```bash
# Найти путь
adb shell pm path com.avito.android
# -> package:/data/app/~~randomhash==/com.avito.android-somehash/base.apk

adb pull /data/app/~~.../com.avito.android-.../base.apk avito_base.apk
```

Avito поставляется как **split APK**: `base.apk` + несколько `split_*.apk` (config.arm64, config.ru, и т.д.). Для static analysis через jadx достаточно только `base.apk` — он содержит основную логику. Подтверждено на v217.2: `base.apk` = 357 МБ, содержит 17 DEX-файлов.

Если jadx нужен split — можно передать все части сразу (`jadx-gui base.apk split_*.apk`).

### Вариант B: через магазин

Aurora Store (FOSS клиент Play Store) или apkpure.com. Минусы: версия может отставать; apkpure иногда re-sign'ит APK, что ломает signature-check внутри app при переустановке.

### Версии в нашем проекте

APK-файлы **не хранятся** в активном repo (большие, gitignored). Извлекаются по необходимости через `adb pull` либо `aurora store`. Архивные копии — в `_archive/avito-farm-agent/apk_work/` (после cleanup'а).
Артефакты от 222.5 (autosearches реверс) — временная папка `%TEMP%/avito_apk/`, не коммитятся.

---

## 3. Static analysis с jadx

**Надёжность: 10/10 — работает всегда, не требует запущенного приложения.**

### Запуск

```bash
# GUI:
jadx-gui avito_base.apk
# CLI (без UI, для grep):
jadx -d output_dir avito_base.apk
```

jadx декомпилирует все `classes*.dex` в Java. На 17 DEX-файлах — несколько минут. Результат: `output_dir/sources/` с Java-файлами.

### Где искать endpoints: Retrofit interfaces

Это главный источник. Avito строит HTTP-клиент на Retrofit2 + OkHttp. В jadx tree ищи файлы с именами вида `*Api.java`, `*Service.java`, `*Interface*.java`. Аннотации обфусцированы, но паттерн сохраняется.

Пример из v222.5 — интерфейс `ou0.InterfaceC46814a`:
```java
// @PUT("4/subscriptions/{filterId}")
@Mg1.p("4/subscriptions/{filterId}")
@Mg1.k({"X-Geo-required: true"})
// suspend fun update(@Path filterId: Long, @Body request: ...)
TypedResult update(@Mg1.s("filterId") long filterId, @Mg1.a SubscriptionMobileUpdateV4Request body);
```

**Таблица алиасов Retrofit в Avito APK v222.5:**

| Avito alias | Retrofit standard |
|---|---|
| `@Mg1.f("path")` | `@GET` |
| `@Mg1.o("path")` | `@POST` |
| `@Mg1.p("path")` | `@PUT` |
| `@Mg1.b("path")` | `@DELETE` |
| `@Mg1.s("name")` | `@Path` |
| `@Mg1.t("name")` | `@Query` |
| `@Mg1.a` | `@Body` |
| `@Mg1.c("name")` | `@Field` |
| `@Mg1.e` | `@FormUrlEncoded` |

Алиасы меняются от версии к версии — проверяй при каждом новом реверсе.

### Поиск через jadx-gui

Используй `View → Search` (`Ctrl+F`). Полезные запросы:

```
BaseUrl        # находит класс с base URL
https://app    # находит все URL
Bearer         # auth
X-Session      # header names
X-DeviceId
AvitoApi       # сервис-классы
subscriptions  # конкретный path
items/search   # search endpoint
```

### OkHttp interceptors

Interceptors — это где добавляются заголовки и обрабатываются ошибки. Из jadx найдены следующие (цепочка в порядке выполнения):

```
session_refresh.h      — управление сессией
captcha.interceptor.g  — обработка капчи
interceptor.Z0         — User-Agent
interceptor.g0         — основные заголовки (X-DeviceId, X-Session, f, и т.д.)
zstd.j                 — zstd сжатие
interceptor.x          — certificate pinning (com.avito.android.remote.interceptor.x)
interceptor.D          — X-Date заголовок
```

### SharedPreferences keys (для token extraction)

Из static analysis — ключи хранения токенов:

```
session           → JWT сессии
fpx               → fingerprint (A2.{hex})
refresh_token     → refresh token
device_id         → 16 hex chars
remote_device_id  → base64 строка
user_hash         → 32 hex chars
1f_uid, u_cookie, v_cookie → cookies
```

Путь к файлу: `/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml`

### Полезные пакеты в jadx tree

Пакеты, которые просматривали чаще всего:
- `com.avito.android.remote.*` — HTTP-клиент, interceptors, модели
- `com.avito.android.remote_device_id.*` — вычисление device ID
- `com.avito.android.authorization.*` — auth flow
- `com.avito.android.saved_searches.*` — autosearch/subscription
- `ou0.*`, `mu0.*`, `pu0.*` — обфусцированные Retrofit-интерфейсы (имена меняются от версии)

Скрипт для автоматического поиска по DEX-строкам: `avito-farm-agent/scan_fingerprint.py`.

---

## 4. Dynamic analysis — устройство

### Подготовка устройства

1. **USB debugging:** Settings → About Phone → нажать Build Number 7 раз → Developer Options → USB Debugging ✓
2. Подключить по USB, на устройстве подтвердить fingerprint хоста.

```bash
adb devices   # убедиться что устройство видно
# cca17101    device
```

3. **Magisk root:** нужен для чтения SharedPreferences Avito и запуска frida-server. Без root — только static analysis.

### Чтение значений устройства через ADB (работает всегда)

Можно получить реальные значения тех же полей, что Avito собирает в fingerprint, без запуска app:

```bash
adb shell getprop ro.product.model           # LE2115
adb shell getprop ro.product.manufacturer    # OnePlus
adb shell getprop ro.build.fingerprint       # OnePlus/OnePlus9/...
adb shell settings get secure android_id     # 38cbe2115f76909e
adb shell wm size                            # Physical size: 1080x2400
adb shell wm density                         # Physical density: 480
# GAID (нужен root):
adb shell "su -c 'cat /data/data/com.google.android.gms/shared_prefs/adid_settings.xml'"
```

Полный набор команд — в `DOCS/AVITO-FINGERPRINT.md` (раздел "Device Reference Values").

### Чтение токенов через ADB (нужен root)

```bash
adb shell "su -c 'cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml'"
# Или стандартный путь:
adb shell "su -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml'"
```

---

## 5. Frida — что работает, что заблокировано

### Запуск frida-server (переименовать обязательно)

```bash
# Avito детектит имя процесса "frida-server" — всегда переименовывать:
adb shell "su -c 'cp /data/local/tmp/frida-server /data/local/tmp/hlpd'"
adb shell "su -c 'chmod 755 /data/local/tmp/hlpd'"
adb shell "su -c 'nohup /data/local/tmp/hlpd -D > /dev/null 2>&1 &'"
adb shell "su -c 'pidof hlpd'"   # проверить что запущен
```

### Что Avito детектит (Cyberity SDK + RootBeer)

| Метод детекции | Результат |
|---|---|
| Scan `/proc/self/maps` на строки "frida", "gadget" | Убивает процесс |
| Проверка порта 27042 | Блокирует |
| Поиск процесса с именем "frida-server" | Детектит → переименование обходит |
| Timing: `create_script()` занимает >100ms | Connection closed |

**Итог:** `device.attach(PID)` успевает сработать, но `create_script()` загружает `frida-agent.so` → появляется в `/proc/self/maps` → Avito убивает себя через 1-2 секунды. Spawn mode аналогично не работает.

Один раз `send("hello")` сработал (повезло с таймингом). Любой реальный скрипт — `TransportError: the connection is closed`.

### Что НЕ пробовали (потенциально работает)

| Метод | Сложность | Оценка шанса |
|---|---|---|
| **Shamiko** (Magisk module) | Низкая | Высокий — скрывает root + Frida от конкретных приложений |
| **LSPosed + TrustMeAlready** | Средняя | Высокий — SSL unpin без Frida |
| **Magisk DenyList** | Низкая | Средний |

Shamiko: скачать с github.com/LSPosed/LSPosed.github.io/releases, установить как Magisk module, добавить Avito в DenyList:
```bash
adb shell "su -c 'magisk --denylist add com.avito.android'"
adb reboot
```

### Frida Gadget в APK (частично работает)

Встроить `libfrida-gadget.so` в APK как зависимость нативной библиотеки. Gadget загружается до Java-кода → хуки раньше anti-Frida. Pipeline: `patch_apk.py` → `sign_apk.py` (v1) → `zipalign.py` → `sign_v2.py` (обязателен для Android 14).

Проблема: APK крашится с `ClassNotFoundException` из-за нарушения DEX offsets при rezip. Не решено.

Скрипты в `avito-farm-agent/`: `patch_apk.py`, `sign_apk.py`, `sign_v2.py`, `zipalign.py`.

**Критические уроки при Gadget-подходе:**
- Целевая `.so` должна загружаться при старте: `libcrashlytics.so` работает, `libandroidx.graphics.path.so` нет.
- Не удалять `META-INF/services/` целиком — там ServiceLoader конфиги (kotlinx.coroutines). Удалять только `*.SF`, `*.RSA`, `*.DSA`.
- Gadget config: `"on_load": "resume"`, не `"wait"` — иначе ANR через 5 секунд.

---

## 6. MITM трафика — почему не работает

**MITM через mitmproxy: заблокировано.**

Avito не использует системный HTTP proxy (`OkHttp` напрямую резолвит DNS). Установка mitmproxy CA как системного сертификата не помогает — `OkHttp CertificatePinner` отвергает. Encrypted DNS (DoH/DoT) — домены Avito не видны в tcpdump через порт 53.

tcpdump на устройстве работает, но показывает только TLS рукопожатие без расшифровки, и Avito-домены не разрезолвятся в стандартный DNS.

Полная документация попыток — в `DOCS/REVERSE-GUIDE.md`.

---

## 7. Наш фактический workflow (без Frida)

Это рабочий путь для получения новых endpoints. Подтверждён на autosearches-реверсе (v222.5, апрель 2026).

### Шаг 1: Статический анализ в jadx

```
jadx-gui avito_base.apk
```

Найти фичу в UI → по названию (например "Сохранённые поиски") найти пакет (`saved_searches`) → найти Retrofit-интерфейс → выписать путь, HTTP-метод, параметры, response-модель.

Для autosearches: интерфейс `ou0.InterfaceC46814a` → `@PUT("4/subscriptions/{filterId}")`.

Для массового поиска endpoint-кандидатов — скрипт `AvitoAll/autosearch_capture.js` и `find_retrofit.py`.

### Шаг 2: Capture токенов с устройства

```bash
adb shell "su -c 'cat /data/user/0/com.avito.android/shared_prefs/com.avito.android_preferences.xml'"
```

Или через `register_clone_session.py` (читает SharedPreferences, парсит XML, отправляет на xapi):
```bash
# В repo: scripts/register_clone_session.py
python scripts/register_clone_session.py
```

### Шаг 3: Replay через curl_cffi

```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session(impersonate="chrome120")
resp = session.get(
    "https://app.avito.ru/api/5/subscriptions",
    headers={
        "User-Agent": "AVITO 222.5 (OnePlus LE2115; Android 14; ru)",
        "X-Session": JWT_TOKEN,
        "X-DeviceId": device_id,
        "X-RemoteDeviceId": remote_device_id,
        "f": fingerprint,
        "X-App": "avito",
        "X-Platform": "android",
        "X-AppVersion": "222.5",
        ...
    }
)
```

**Обязателен `curl_cffi` с `impersonate="chrome120"`.** Без него QRATOR блокирует по JA3/JA3S TLS fingerprint. `requests`, `httpx`, `aiohttp` — все получают HTTP 400.

Реализация заголовков: `avito-xapi/src/workers/base_client.py:22-43`.

### Шаг 4: Добавить в xapi или avito-mcp

Если endpoint подтверждён — добавить в `avito-xapi/src/routers/` или `avito-monitor/avito_mcp/tools/`.

---

## 8. Подводные камни и quirks

### QRATOR

Срабатывает на паттерны запросов, не только на rate. Эмпирически: burst из 14 запросов за 5 секунд к `/subscriptions` вызвал бан аккаунта (сессия A, апрель 2026). Текущие настройки: `1 RPS, burst 3`. Симптом бана: HTTP 403 или временная деактивация аккаунта Avito.

### Anti-fraud per-account

Avito отслеживает поведение per-account. Нехарактерные паттерны (burst запросов, несоответствие device_id и fingerprint) вызывают бан. Каждый токен следует использовать только с тем device_id и fingerprint, с которым был получен.

### TLS-fingerprint requirement

Без `curl_cffi(impersonate="chrome120")` — 400 или 403 на любом endpoint. Это фиксированное требование, не зависит от версии app.

### Fingerprint header `f`

Формат: `A2.{256+ hex символов}`. Генерируется нативной библиотекой `com.avito.security.libfp.FingerprintService` с VM-обфускацией. **Программно сгенерировать невозможно** — только захватить с реального устройства через SharedPreferences (ключ `fpx`). Frida-hook дал бы доступ к генерации, но Frida заблокирован. Значение живёт долго — можно переиспользовать.

### Версия приложения в заголовках

`User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)` — сейчас жёстко задана в `base_client.py:APP_VERSION`. При обновлении APK на устройстве нужно проверить, не изменился ли набор обязательных заголовков и не появились ли новые поля в сессии.

### device_id vs remote_device_id

Разные сущности, оба хранятся в SharedPreferences:
- `device_id` — 16 hex chars, простой идентификатор устройства
- `remote_device_id` — длинная base64 строка, генерируется через `/api/1/visitorGenerate`, синхронизируется с сервером Avito

### Avito обновляет токены автоматически

JWT живёт 24 часа. Avito-app при запуске сам обновляет через refresh_token. Алгоритм обновления — запустить `adb shell am start -n com.avito.android/.MainActivity`, подождать 30 секунд, перечитать SharedPreferences.

### Encrypted DNS

Avito использует DoH/DoT. Домены Avito не разрезолвятся через стандартный DNS (порт 53). tcpdump показывает IP без имён.

---

## 9. Quick start — новый endpoint за один сеанс

**Цель:** открыть один ранее неизвестный endpoint, проверить live.

1. Открой jadx-gui с `avito_base.apk` нужной версии.
2. Найди UI-фичу которая вызывает нужный endpoint. Нажми на неё в app + посмотри в jadx какой пакет отвечает за эту фичу.
3. Найди Retrofit-интерфейс в этом пакете. Выпиши: HTTP-метод (`@Mg1.f/o/p/b`), путь, параметры (`@Mg1.s/t/a`), response-класс.
4. Возьми живой токен из SharedPreferences (`adb shell su -c cat ...`).
5. Сделай replay через `curl_cffi`:
   ```python
   from curl_cffi import requests as curl_requests
   s = curl_requests.Session(impersonate="chrome120")
   r = s.get("https://app.avito.ru/api/{version}/{path}", headers=build_headers(token))
   print(r.status_code, r.json())
   ```
6. Если 403 — проверить: TLS impersonation включён? Все обязательные заголовки есть? `f` не пустой? `X-Date` свежий?
7. Если 429 — ждать 30 секунд, не retry в цикле.
8. После подтверждения — добавить в `avito-xapi/src/routers/` или `avito-monitor/avito_mcp/tools/`.

---

## 10. Что НЕ работает (зафиксировано)

| Подход | Статус | Причина |
|---|---|---|
| Frida attach к com.avito.android | Заблокирован | Cyberity SDK детектит frida-agent.so в /proc/self/maps через 1-2 сек |
| Frida spawn mode | Заблокирован | TimedOutError или NotSupportedError |
| mitmproxy перехват HTTPS | Заблокирован | App игнорирует system proxy; OkHttp CertificatePinner |
| Генерация fingerprint программно | Невозможно | Нативная библиотека с VM-обфускацией, Frida недоступен |
| Веб-API через мобильную auth | Не работает | Разные наборы endpoints (`www.avito.ru` vs `app.avito.ru`) |
| `requests` / `httpx` / `aiohttp` | Блокируется | Неверный TLS fingerprint → QRATOR 400 |
| Создание нового fingerprint из нуля | Не исследовано | Нет runtime-доступа к генерации; нужен Frida или перехват с нового устройства |
| Авторизация через `/api/11/auth` программно | Не работает | QRATOR + firebase token + CAPTCHA |

**Важная хронология:** до 2026-Q1 Frida работал в ранних экспериментах (ArchiveAll/AvitoAll — `ssl_simple.js` и `http_capture.js` были рабочими). В версиях APK 215+ Cyberity SDK агрессивно блокирует.

---

## Ссылки

- `01-avito-api.md` — все известные endpoints, заголовки, структура JWT
- `02-auth-and-tokens.md` — lifecycle токенов, ban detection, multi-account
- `03-android-setup.md` — физическая инфраструктура (OnePlus, Magisk, ADB)
- `DOCS/avito_api_snapshots/autosearches/README.md` — пример полного реверса (subscriptions v222.5)
- `avito-farm-agent/` — все Frida-скрипты (js) и Python-инструменты реверса
- `AvitoAll/PROGRESS_REPORT.md` — дневник ранних экспериментов (2026-01)
