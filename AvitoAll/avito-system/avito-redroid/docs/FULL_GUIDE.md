# Avito Redroid Masked: Полный гайд

## Оглавление

1. [Обзор системы](#обзор-системы)
2. [Архитектура](#архитектура)
3. [Как выбирается устройство](#как-выбирается-устройство)
4. [Что маскируется](#что-маскируется)
5. [Процесс запуска контейнера](#процесс-запуска-контейнера)
6. [Установка и деплой](#установка-и-деплой)
7. [Управление устройством](#управление-устройством)
8. [Работа с Avito](#работа-с-avito)
9. [Извлечение токенов](#извлечение-токенов)
10. [Troubleshooting](#troubleshooting)

---

## Обзор системы

**Avito Redroid Masked** — это Docker-контейнер с Android 13, который при первом запуске автоматически маскируется под случайное реальное устройство из базы GSMArena (~4000+ устройств).

### Зачем это нужно?

Avito и другие приложения детектят эмуляторы по:
- Системным свойствам (`ro.kernel.qemu`, `ro.hardware`)
- Fingerprint устройства
- Наличию файлов эмулятора (`/dev/qemu_pipe`)
- Нереалистичным названиям устройств ("sdk_gphone64_x86_64")

Наша система:
1. Выбирает реальное устройство из GSMArena
2. Генерирует все системные свойства как у реального устройства
3. Удаляет файлы и свойства, выдающие эмулятор
4. Сохраняет идентичность между перезапусками

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PostgreSQL (85.198.98.104:5433)                  │
│                    Таблица: zip_gsmarena_raw                        │
│                    ~4000+ реальных устройств                        │
│                                                                     │
│  Поля: brand, model_name, chipset, cpu, os, release_year           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ SQL запрос с фильтрами
                                 │ ORDER BY RANDOM() LIMIT 1
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     device_profile_gen.py                           │
│                                                                     │
│  1. Подключается к БД                                               │
│  2. Фильтрует: год >= 2021, бренды, не бюджетные                   │
│  3. Выбирает случайное устройство                                   │
│  4. Генерирует codename, fingerprint, build info                    │
│  5. Сохраняет в /data/device_profile.json                          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ JSON профиль
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      build_prop_gen.py                              │
│                                                                     │
│  Генерирует build.prop с 100+ свойствами:                          │
│  - ro.product.* (model, brand, device, manufacturer)                │
│  - ro.build.* (fingerprint, id, version)                           │
│  - ro.hardware, ro.board.platform                                   │
│  - Anti-emulator: ro.kernel.qemu=0, ro.debuggable=0                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Redroid Container                              │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ 02_cleanup   │  │ 01_apply     │  │    Android 13          │   │
│  │ _emu.sh      │  │ _mask.sh     │  │                        │   │
│  │              │  │              │  │  • Avito видит:        │   │
│  │ Удаляет:     │  │ Применяет:   │  │    Samsung Galaxy S23  │   │
│  │ /dev/qemu*   │  │ setprop ...  │  │    (или другое)        │   │
│  │ /dev/gold*   │  │              │  │                        │   │
│  └──────────────┘  └──────────────┘  └────────────────────────┘   │
│                                                                     │
│  Volume: /data (профиль + данные Avito сохраняются)                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Как выбирается устройство

### Источник данных

База данных PostgreSQL содержит ~4000+ устройств, спарсенных с GSMArena:

```
Host: 85.198.98.104
Port: 5433
Database: postgres
Table: zip_gsmarena_raw
```

### Поля в БД

| Поле | Пример | Использование |
|------|--------|---------------|
| `brand` | Samsung | ro.product.brand |
| `model_name` | Galaxy S23 | ro.product.model |
| `chipset` | Snapdragon 8 Gen 2 | Определение hardware (qcom/mtk/exynos) |
| `cpu` | Octa-core | Информационно |
| `os` | Android 13, One UI 5.1 | Парсинг версии Android |
| `release_year` | 2023 | Фильтрация по году |

### Критерии фильтрации

```python
# SQL запрос в device_profile_gen.py
SELECT brand, model_name, chipset, cpu, os, release_year
FROM zip_gsmarena_raw
WHERE
    brand IN ('Samsung', 'Xiaomi', 'Google', 'OnePlus', 'Oppo',
              'Realme', 'Huawei', 'Vivo', 'Honor', 'Motorola')
    AND release_year >= 2021           -- Android 11+
    AND os LIKE '%Android%'            -- Только Android
    AND model_name NOT LIKE '%Lite%'   -- Исключить бюджетные
    AND model_name NOT LIKE '%Go%'
    AND model_name NOT LIKE '%Mini%'
ORDER BY RANDOM()
LIMIT 1
```

### Почему эти критерии?

| Критерий | Причина |
|----------|---------|
| Год >= 2021 | Android 11+ для совместимости с современными приложениями |
| Популярные бренды | Наиболее распространены в России, меньше подозрений |
| Исключение Lite/Go | Бюджетные модели имеют характерные паттерны |
| Android only | Исключить iOS-устройства из выдачи |

### Генерация codename

Для каждого бренда есть база известных codenames:

```python
DEVICE_CODENAMES = {
    'Samsung': {
        'Galaxy S23': {'device': 'dm1q', 'product': 'dm1qxx', 'hardware': 'qcom'},
        'Galaxy S22': {'device': 'r0q', 'product': 'r0qxx', 'hardware': 'qcom'},
        ...
    },
    'Google': {
        'Pixel 8': {'device': 'shiba', 'product': 'shiba', 'hardware': 'gs201'},
        'Pixel 7': {'device': 'panther', 'product': 'panther', 'hardware': 'gs101'},
        ...
    },
    'Xiaomi': {
        'Xiaomi 13': {'device': 'fuxi', 'product': 'fuxi', 'hardware': 'qcom'},
        ...
    }
}
```

Если устройство не найдено в базе codenames, генерируется по правилам бренда:

```python
# Samsung: sm + число + q
device = f"sm{random.randint(100, 999)}q"  # например: sm847q

# Xiaomi: названия природы
device = random.choice(['jasmine', 'violet', 'lavender', ...])

# Google: названия животных
device = random.choice(['panther', 'cheetah', 'lynx', ...])
```

---

## Что маскируется

### 1. Product Properties (Идентификация устройства)

```properties
# Основные свойства продукта
ro.product.model=Galaxy S23              # Название модели
ro.product.brand=Samsung                 # Бренд
ro.product.name=dm1qxx                   # Продукт (для OTA)
ro.product.device=dm1q                   # Codename устройства
ro.product.manufacturer=samsung          # Производитель
ro.product.board=qcom                    # Платформа

# Дублирование для разных разделов (system, vendor, odm)
ro.product.system.model=Galaxy S23
ro.product.vendor.model=Galaxy S23
ro.product.odm.model=Galaxy S23
```

### 2. Build Properties (Информация о сборке)

```properties
ro.build.id=TP1A.220624.014              # Build ID
ro.build.display.id=S911BXXU2AWA1        # Отображаемый номер сборки
ro.build.version.sdk=33                   # SDK версия (Android 13 = 33)
ro.build.version.release=13               # Версия Android
ro.build.version.security_patch=2024-10-01  # Патч безопасности
ro.build.type=user                        # Тип сборки (не debug!)
ro.build.tags=release-keys                # Теги сборки
```

### 3. Fingerprint (Критически важно!)

Fingerprint — это строка, уникально идентифицирующая сборку. Формат:

```
brand/product/device:version/build_id/build_number:type/tags
```

Пример для Samsung Galaxy S23:
```
samsung/dm1qxx/dm1q:13/TP1A.220624.014/S911BXXU2AWA1:user/release-keys
```

Свойства fingerprint:
```properties
ro.build.fingerprint=samsung/dm1qxx/dm1q:13/TP1A.220624.014/S911BXXU2AWA1:user/release-keys
ro.bootimage.build.fingerprint=...  # То же самое
ro.vendor.build.fingerprint=...     # То же самое
ro.system.build.fingerprint=...     # То же самое
```

### 4. Hardware Properties

```properties
ro.hardware=qcom                    # Платформа (qcom/mtk/exynos/gs201)
ro.hardware.chipname=qcom           # Имя чипа
ro.board.platform=qcom              # Платформа платы
```

Определение hardware по чипсету:
| Чипсет содержит | Hardware |
|-----------------|----------|
| Snapdragon, Qualcomm | qcom |
| Dimensity, Helio, MediaTek | mtk |
| Exynos | exynos |
| Tensor, Google | gs201 |
| Kirin, HiSilicon | kirin |

### 5. Anti-Emulator Properties

```properties
# Скрытие эмулятора
ro.kernel.qemu=0                    # НЕ QEMU
ro.kernel.android.qemud=0           # Нет QEMU демона
ro.kernel.qemu.gles=0               # Нет QEMU графики

# Сервисы эмулятора остановлены
init.svc.qemu-props=stopped
init.svc.goldfish-setup=stopped
init.svc.goldfish-logcat=stopped

# Boot состояние (как на реальном устройстве)
ro.boot.verifiedbootstate=green     # Verified boot пройден
ro.boot.flash.locked=1              # Загрузчик заблокирован
ro.boot.vbmeta.device_state=locked  # Устройство заблокировано
```

### 6. Security Properties

```properties
ro.secure=1                         # Secure mode включён
ro.adb.secure=1                     # ADB требует авторизацию
ro.debuggable=0                     # Debug отключён (production)
ro.allow.mock.location=0            # Фейковая локация запрещена
ro.oem_unlock_supported=0           # OEM unlock не поддерживается
```

### 7. Удаляемые файлы эмулятора

```bash
# Device файлы QEMU/Goldfish
/dev/qemu_pipe
/dev/goldfish_pipe
/dev/goldfish_address_space
/dev/goldfish_sync
/dev/socket/qemud

# Системные файлы
/sys/qemu_trace
/system/lib/libc_malloc_debug_qemu.so
/system/lib64/libc_malloc_debug_qemu.so

# Бинарники эмулятора (переименовываются)
/system/bin/qemu-props → qemu-props.disabled
/system/bin/goldfish-setup → goldfish-setup.disabled
```

---

## Процесс запуска контейнера

### Последовательность действий

```
docker compose up
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ entrypoint.sh                                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [1/5] Проверка профиля устройства                          │
│        │                                                     │
│        ├─ Файл существует? (/data/device_profile.json)      │
│        │   ├─ ДА → Использовать существующий                │
│        │   └─ НЕТ → Генерировать новый                      │
│        │            │                                        │
│        │            ├─ Есть DB_PASSWORD?                    │
│        │            │   ├─ ДА → Запрос к GSMArena БД        │
│        │            │   └─ НЕТ → Fallback (Samsung S23)     │
│        │            │                                        │
│        │            └─ Сохранить в /data/device_profile.json│
│        │                                                     │
│  [2/5] Генерация build.prop                                 │
│        python3 build_prop_gen.py --profile ... --output ... │
│        │                                                     │
│  [3/5] Подготовка cleanup скрипта                           │
│        chmod +x /system/etc/init.d/02_cleanup_emu.sh        │
│        │                                                     │
│  [4/5] Установка переменных окружения                       │
│        DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_DPI           │
│        │                                                     │
│  [5/5] Запуск Android                                        │
│        exec /init "$@"                                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Android Init (/init)                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  → Загрузка ядра                                            │
│  → Монтирование /system, /data                              │
│  → Выполнение init.d скриптов:                              │
│      │                                                       │
│      ├─ 01_apply_mask.sh                                    │
│      │   Читает device_profile.json                         │
│      │   Применяет setprop для всех свойств                 │
│      │                                                       │
│      ├─ 02_cleanup_emu.sh                                   │
│      │   Удаляет /dev/qemu*, /dev/goldfish*                 │
│      │   Устанавливает ro.kernel.qemu=0                     │
│      │   Отключает эмуляторные сервисы                      │
│      │                                                       │
│      └─ 03_start_services.sh                                │
│          Настраивает ADB (порт 5555)                        │
│          Создаёт /data/ready (статус файл)                  │
│                                                              │
│  → Запуск Android Framework                                  │
│  → Запуск Launcher                                           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
   Android Ready!
   ADB: порт 5555
```

### Пример профиля устройства

```json
{
  "brand": "Samsung",
  "model": "Galaxy S23",
  "device": "dm1q",
  "product": "dm1qxx",
  "manufacturer": "samsung",
  "hardware": "qcom",
  "chipset": "Snapdragon 8 Gen 2",
  "cpu": "Octa-core",
  "android_version": "13",
  "sdk_version": "33",
  "build_id": "TP1A.220624.014",
  "build_number": "S911BXXU2AWA1",
  "security_patch": "2024-10-01",
  "fingerprint": "samsung/dm1qxx/dm1q:13/TP1A.220624.014/S911BXXU2AWA1:user/release-keys",
  "release_year": 2023,
  "source": "gsmarena_db"
}
```

---

## Установка и деплой

### Требования к серверу

| Компонент | Требование |
|-----------|------------|
| OS | Linux (Ubuntu 20.04+, Debian 11+) |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| RAM | 4GB минимум |
| CPU | 4 cores рекомендуется |
| Kernel modules | binder_linux, ashmem_linux |

### Шаг 1: Подготовка сервера

```bash
# Установка Docker (если не установлен)
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Загрузка kernel modules для Redroid
modprobe binder_linux devices="binder,hwbinder,vndbinder"
modprobe ashmem_linux

# Проверка
lsmod | grep binder
lsmod | grep ashmem
```

Для автозагрузки модулей при старте:
```bash
echo "binder_linux" >> /etc/modules-load.d/redroid.conf
echo "ashmem_linux" >> /etc/modules-load.d/redroid.conf

# Параметры binder
echo 'options binder_linux devices="binder,hwbinder,vndbinder"' > /etc/modprobe.d/redroid.conf
```

### Шаг 2: Копирование файлов

```bash
# Копировать на сервер
scp -r avito-redroid/ root@your-server:/opt/

# Или клонировать из git
git clone <repo> /opt/avito-redroid
```

### Шаг 3: Настройка

```bash
cd /opt/avito-redroid

# Создать .env с паролем БД
echo "DB_PASSWORD=Mi31415926pSss!" > .env

# Проверить права
chmod +x entrypoint.sh
chmod +x init.d/*.sh
chmod +x scripts/*.py
```

### Шаг 4: Сборка образа

```bash
docker compose build
```

Процесс сборки:
1. Скачивает базовый образ `redroid/redroid:13.0.0-latest`
2. Устанавливает Python 3, pip, curl, jq
3. Устанавливает psycopg2-binary
4. Копирует скрипты маскировки
5. Копирует init.d скрипты
6. Устанавливает entrypoint

### Шаг 5: Запуск

```bash
# Запуск в фоне
docker compose up -d

# Просмотр логов
docker compose logs -f

# Проверка статуса
docker compose ps
```

### Шаг 6: Проверка

```bash
# Подключение по ADB
adb connect localhost:5555

# Проверка маскировки
adb shell getprop ro.product.model
adb shell getprop ro.product.brand
adb shell getprop ro.build.fingerprint
adb shell getprop ro.kernel.qemu
```

---

## Управление устройством

### Просмотр текущего профиля

```bash
# JSON формат
docker exec avito-redroid cat /data/device_profile.json

# Красивый вывод
docker exec avito-redroid cat /data/device_profile.json | jq .

# Только основные поля
docker exec avito-redroid cat /data/device_profile.json | jq '{brand, model, fingerprint}'
```

### Смена устройства

```bash
# Удалить профиль
docker exec avito-redroid rm /data/device_profile.json

# Перезапустить контейнер (получит новое случайное устройство)
docker compose restart

# Проверить новое устройство
docker exec avito-redroid cat /data/device_profile.json | jq '{brand, model}'
```

### Принудительный выбор бренда

```bash
# Остановить контейнер
docker compose down

# Запустить с указанием бренда
docker compose run --rm avito-redroid \
  python3 /opt/masking/device_profile_gen.py \
    --db-host 85.198.98.104 \
    --db-port 5433 \
    --db-user postgres \
    --db-password "Mi31415926pSss!" \
    --db-name postgres \
    --brand Google \
    --output /data/device_profile.json

# Запустить контейнер
docker compose up -d
```

### Просмотр логов маскировки

```bash
docker exec avito-redroid cat /data/masking.log
```

### Проверка всех свойств

```bash
# Все product свойства
adb shell getprop | grep ro.product

# Все build свойства
adb shell getprop | grep ro.build

# Проверка qemu (должно быть пусто или 0)
adb shell getprop | grep qemu

# Проверка secure
adb shell getprop ro.secure        # 1
adb shell getprop ro.debuggable    # 0
```

---

## Работа с Avito

### Установка Avito

```bash
# Скачать APK (получить актуальную ссылку с apkpure/apkmirror)
wget -O avito.apk "https://..."

# Установить
adb install avito.apk
```

### Первый запуск

1. Открыть Avito
2. Войти по номеру телефона (SMS)
3. Разрешить все запрашиваемые permissions
4. Перейти в "Сообщения" (активирует WebSocket)
5. Подождать 30 секунд

### Проверка определения устройства

В приложении Avito:
1. Профиль → Настройки → О приложении
2. Или: Профиль → Помощь → Написать в поддержку

Avito покажет модель устройства — должна соответствовать профилю.

### Что видит Avito

| Параметр | Значение из профиля |
|----------|---------------------|
| Модель | Galaxy S23 (ro.product.model) |
| Производитель | Samsung (ro.product.manufacturer) |
| Версия Android | 13 (ro.build.version.release) |
| Fingerprint | samsung/dm1qxx/dm1q:13/... |

---

## Извлечение токенов

### Автоматическое извлечение

```bash
# Из контейнера
docker exec avito-redroid python3 /opt/masking/extract_tokens.py

# Результат в
cat output/tokens/latest.json
```

### Ручное извлечение

```bash
# Получить root
adb root

# Скопировать SharedPreferences
adb pull /data/data/com.avito.android/shared_prefs/ ./prefs/

# Найти токены
grep -r "eyJ" ./prefs/  # JWT токены начинаются с eyJ
```

### Формат токенов

```json
{
  "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "abc123...",
  "fingerprint": "device_fingerprint_hash",
  "device_id": "android_device_id",
  "user_id": 123456789,
  "expires_at": 1735689600,
  "expires_date": "2025-01-01T00:00:00",
  "extracted_at": 1706400000,
  "extracted_date": "2024-01-28T00:00:00"
}
```

### Использование токенов

Токены можно использовать для API запросов:

```bash
curl -H "Authorization: Bearer $SESSION_TOKEN" \
     -H "X-Device-Fingerprint: $FINGERPRINT" \
     https://api.avito.ru/...
```

---

## Troubleshooting

### Контейнер не запускается

**Проблема:** `Error: binder not found`

```bash
# Решение: загрузить kernel modules
modprobe binder_linux devices="binder,hwbinder,vndbinder"
modprobe ashmem_linux
```

**Проблема:** `Permission denied`

```bash
# Контейнер должен запускаться с privileged
# Проверить docker-compose.yml:
privileged: true
```

### Не подключается к БД

**Проблема:** `Database connection failed`

Контейнер автоматически использует fallback профиль (Samsung Galaxy S23).

```bash
# Проверить подключение
docker exec avito-redroid python3 -c "
import psycopg2
conn = psycopg2.connect(
    host='85.198.98.104',
    port=5433,
    user='postgres',
    password='Mi31415926pSss!',
    database='postgres'
)
print('OK')
"
```

### Avito всё ещё детектит эмулятор

```bash
# 1. Проверить qemu свойства
adb shell getprop | grep qemu
# Должно быть пусто или 0

# 2. Проверить файлы эмулятора
adb shell ls /dev/qemu* 2>&1
# Должно быть "No such file"

# 3. Проверить fingerprint
adb shell getprop ro.build.fingerprint
# Должен быть реалистичный

# 4. Проверить логи маскировки
docker exec avito-redroid cat /data/masking.log
```

### ADB не подключается

```bash
# Проверить порт
docker compose ps
# Должен быть 0.0.0.0:5555->5555/tcp

# Проверить firewall
ufw allow 5555

# Перезапустить ADB
adb kill-server
adb connect localhost:5555
```

### Токены не извлекаются

```bash
# 1. Проверить установку Avito
adb shell pm list packages | grep avito

# 2. Проверить авторизацию
adb shell ls /data/data/com.avito.android/shared_prefs/

# 3. Убедиться что есть root
adb root
adb shell ls /data/data/com.avito.android/
```

---

## Приложение: Таблица свойств

### Все маскируемые свойства

| Свойство | Описание | Пример значения |
|----------|----------|-----------------|
| ro.product.model | Модель | Galaxy S23 |
| ro.product.brand | Бренд | Samsung |
| ro.product.name | Имя продукта | dm1qxx |
| ro.product.device | Codename | dm1q |
| ro.product.manufacturer | Производитель | samsung |
| ro.product.board | Плата | qcom |
| ro.build.id | Build ID | TP1A.220624.014 |
| ro.build.display.id | Номер сборки | S911BXXU2AWA1 |
| ro.build.version.sdk | SDK | 33 |
| ro.build.version.release | Android | 13 |
| ro.build.version.security_patch | Патч | 2024-10-01 |
| ro.build.type | Тип | user |
| ro.build.tags | Теги | release-keys |
| ro.build.fingerprint | Fingerprint | samsung/dm1qxx/... |
| ro.hardware | Hardware | qcom |
| ro.kernel.qemu | QEMU флаг | 0 |
| ro.secure | Secure mode | 1 |
| ro.debuggable | Debug | 0 |
| ro.boot.verifiedbootstate | Verified boot | green |
| ro.boot.flash.locked | Bootloader | 1 |

---

*Документ создан: 2026-01-28*
