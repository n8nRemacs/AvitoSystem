# Avito Token Extraction System - Полная документация

## Обзор системы

Система для автоматического извлечения и обновления токенов авторизации Avito с использованием Redroid (Android в Docker контейнере) на удалённом Linux сервере.

### Зачем это нужно

Avito использует JWT токены для API авторизации. Токены:
- **session_token** — живёт 24 часа
- **refresh_token** — живёт ~30 дней
- **fingerprint (fpx)** — генерируется native-библиотекой, невозможно воспроизвести программно

Единственный способ получить валидный fingerprint — извлечь его из работающего приложения Avito.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    Linux Server (Ubuntu 22.04)                   │
│                         109.69.16.95                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Docker Container                         │   │
│  │                   (Redroid)                              │   │
│  │                                                          │   │
│  │   ┌──────────────┐      ┌─────────────────────────┐    │   │
│  │   │ Android 13   │      │ Avito App               │    │   │
│  │   │ (x86_64)     │      │                         │    │   │
│  │   │              │      │ SharedPreferences:      │    │   │
│  │   │ Ports:       │      │ - session (JWT)         │    │   │
│  │   │ - 5555 (ADB) │      │ - refresh_token         │    │   │
│  │   │ - 5900 (VNC) │      │ - fpx (fingerprint)     │    │   │
│  │   └──────────────┘      │ - device_id             │    │   │
│  │                         └─────────────────────────┘    │   │
│  │                                                          │   │
│  │   Volume: redroid_data:/data (персистентный)            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Cron: 0 10 * * * /opt/avito-redroid/auto_refresh_tokens.sh    │
│  Systemd: avito-redroid.service (автозапуск)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ ADB (tcp:5555)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Windows Client                                │
│                                                                  │
│  Tools:                                                          │
│  - ADB (Android SDK)                                            │
│  - scrcpy (просмотр экрана)                                     │
│  - SSH (управление сервером)                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Требования

### Сервер (Linux)

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| CPU | 4 ядра | 6+ ядер |
| RAM | 8 GB | 12+ GB |
| Disk | 20 GB | 50+ GB NVMe |
| Docker | 20.10+ | 24.0+ |

**Критически важно:**
- Ядро Linux с поддержкой `binder` и `ashmem` модулей
- Docker с privileged режимом
- Открытые порты: 5555 (ADB), 5900 (VNC)

**НЕ РАБОТАЕТ на:**
- Windows (Docker Desktop) — нет модулей ядра в WSL2
- macOS — нет поддержки binder

### Клиент (Windows)

- Windows 10/11
- Android SDK Platform Tools (ADB)
- scrcpy (для просмотра экрана)
- SSH клиент

---

## Установка

### 1. Подготовка сервера

```bash
# Подключение
ssh root@109.69.16.95

# Установка Docker (если не установлен)
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Установка зависимостей
apt update
apt install -y python3 python3-pip adb wget unzip

# Установка Frida tools
pip3 install frida-tools
```

### 2. Загрузка модулей ядра

**КРИТИЧНО**: Redroid требует специальные модули ядра Linux.

```bash
# Установка модулей
apt install -y linux-modules-extra-$(uname -r)

# Загрузка модулей
modprobe binder_linux devices="binder,hwbinder,vndbinder"
modprobe ashmem_linux

# Создание binderfs
mkdir -p /dev/binderfs
mount -t binderfs binderfs /dev/binderfs

# Проверка
ls -la /dev/binderfs/
# Должны быть: binder, hwbinder, vndbinder
```

### 3. Создание рабочей директории

```bash
mkdir -p /opt/avito-redroid
cd /opt/avito-redroid
mkdir -p output logs backups
```

### 4. Docker Compose конфигурация

Файл: `/opt/avito-redroid/docker-compose.yml`

```yaml
services:
  redroid:
    image: redroid/redroid:13.0.0-latest
    container_name: avito-redroid
    privileged: true
    ports:
      - "5555:5555"
      - "5900:5900"
    volumes:
      - redroid_data:/data
    environment:
      - REDROID_WIDTH=1080
      - REDROID_HEIGHT=2400
      - REDROID_DPI=420
      - REDROID_GPU_MODE=guest
    restart: unless-stopped

volumes:
  redroid_data:
```

### 5. Запуск Redroid

```bash
docker compose up -d

# Ожидание загрузки (30-60 секунд)
sleep 45

# Проверка
docker exec avito-redroid getprop sys.boot_completed
# Должно вернуть: 1
```

### 6. Настройка часового пояса

**⚠️ КРИТИЧЕСКИ ВАЖНО**: Неправильное время = блокировка аккаунта!

```bash
# На сервере
timedatectl set-timezone Europe/Moscow

# В Android
adb connect 127.0.0.1:5555
adb -s 127.0.0.1:5555 shell service call alarm 3 s16 Europe/Moscow
adb -s 127.0.0.1:5555 shell setprop persist.sys.timezone Europe/Moscow

# Проверка (время должно совпадать!)
date
adb -s 127.0.0.1:5555 shell date
```

### 7. Установка Avito APK

```bash
# Скачивание
wget "https://www.avito.st/s/app/apk/avito.apk" -O avito.apk

# Установка
adb -s 127.0.0.1:5555 install avito.apk

# Проверка
adb -s 127.0.0.1:5555 shell pm list packages | grep avito
# Должно вернуть: package:com.avito.android
```

### 8. Установка Frida Server

```bash
# Определение архитектуры
ARCH=$(adb -s 127.0.0.1:5555 shell getprop ro.product.cpu.abi)
# Обычно: x86_64

# Скачивание Frida Server
FRIDA_VERSION="16.6.6"
wget "https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/frida-server-${FRIDA_VERSION}-android-x86_64.xz"
xz -d frida-server-${FRIDA_VERSION}-android-x86_64.xz
mv frida-server-${FRIDA_VERSION}-android-x86_64 frida-server

# Установка на устройство
adb -s 127.0.0.1:5555 push frida-server /data/local/tmp/
adb -s 127.0.0.1:5555 shell chmod +x /data/local/tmp/frida-server

# Запуск
adb -s 127.0.0.1:5555 shell "/data/local/tmp/frida-server -D &"
```

---

## Авторизация в Avito

**Выполняется ВРУЧНУЮ через scrcpy:**

### С Windows клиента:

```cmd
:: Подключение ADB
adb connect 109.69.16.95:5555

:: Запуск scrcpy
scrcpy -s 109.69.16.95:5555
```

### В окне scrcpy:

1. Открыть Avito
2. Нажать "Войти"
3. Ввести номер телефона
4. Ввести SMS код
5. Дождаться входа
6. Открыть вкладку "Сообщения" (активирует токены)

---

## Структура токенов

### SharedPreferences файл

Путь: `/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml`

### Ключевые поля

| Поле | XML name | Описание | Время жизни |
|------|----------|----------|-------------|
| Session Token | `session` | JWT для API | 24 часа |
| Refresh Token | `refresh_token` | Обновление JWT | ~30 дней |
| Fingerprint | `fpx` | Уникальный отпечаток | Постоянный |
| Device ID | `device_id` | ID устройства | Постоянный |
| Remote Device ID | `remote_device_id` | Серверный ID устройства | Постоянный |
| User ID | `profile_id` | ID пользователя | Постоянный |
| User Hash | `profile_hashId` | Хэш пользователя | Постоянный |

### JSON формат экспорта

```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "2f442141d2c9001c4b29c73b7b99943c",
  "fingerprint": "A2.84c6d4a2fa134266bae29d12d21e00f8...",
  "device_id": "8fe96e65f4b2b141",
  "remote_device_id": "vVrrso0GTEY3ExoF...android",
  "user_id": 157920214,
  "user_hash": "9b82afc1ab1e2419981f7a9d9d2b6af9",
  "profile_name": "ИмяПрофиля",
  "email": "email@example.com",
  "expires_at": 1769542184,
  "synced_at": 1769456330
}
```

### JWT структура (session_token)

Payload после декодирования base64:

```json
{
  "exp": 1769542184,
  "iat": 1769455784,
  "u": 157920214,
  "p": 28109599,
  "s": "0d676ed9...",
  "h": "OWRlOTE5...",
  "d": "8fe96e65f4b2b141",
  "pl": "android",
  "extra": null
}
```

| Поле | Описание |
|------|----------|
| exp | Время истечения (Unix timestamp) |
| iat | Время создания |
| u | User ID |
| p | Profile ID |
| s | Session ID |
| d | Device ID |
| pl | Platform |

---

## Файловая структура сервера

```
/opt/avito-redroid/
│
├── docker-compose.yml          # Конфигурация контейнера
├── avito.apk                   # APK файл Avito (~200MB)
├── frida-server                # Frida Server binary (~100MB)
│
├── auto_refresh_tokens.sh      # Скрипт автообновления (cron)
├── export_session.py           # Экспорт токенов в JSON
├── pixel6_mask.js              # Frida скрипт маскировки
│
├── FULL_DOCUMENTATION.md       # Эта документация
├── IMPORTANT_NOTES.md          # Критические заметки
│
├── output/                     # Извлечённые токены
│   ├── session_YYYYMMDD_HHMMSS.json
│   └── latest.json -> ...      # Симлинк на последний
│
├── logs/                       # Логи автообновления
│   └── refresh_YYYYMMDD_HHMMSS.log
│
└── backups/                    # Бэкапы SharedPreferences
    └── prefs_backup_YYYYMMDD_HHMMSS.xml
```

---

## Скрипты

### auto_refresh_tokens.sh

Запускается по cron ежедневно в 10:00 MSK.

**Что делает:**
1. Загружает модули ядра (если нужно)
2. Запускает контейнер (если остановлен)
3. Ждёт загрузки Android
4. Синхронизирует время
5. Запускает Avito (обновляет токены автоматически)
6. Извлекает и сохраняет токены в JSON

### export_session.py

Python скрипт для извлечения токенов из SharedPreferences.

```bash
python3 /opt/avito-redroid/export_session.py > session.json
```

### pixel6_mask.js

Frida скрипт для маскировки устройства под Google Pixel 6.

**Что подменяет:**
- Build.MODEL → "Pixel 6"
- Build.MANUFACTURER → "Google"
- Build.BRAND → "google"
- Build.DEVICE → "oriole"
- SystemProperties.get() для ro.product.*
- Блокирует файлы детекта эмулятора
- TelephonyManager

**Использование:**
```bash
frida -H 127.0.0.1:27042 -l pixel6_mask.js -f com.avito.android --no-pause
```

---

## Автоматизация

### Cron задача

```bash
# Просмотр
crontab -l

# Редактирование
crontab -e

# Текущая настройка
0 10 * * * /opt/avito-redroid/auto_refresh_tokens.sh
```

Формат: `минуты часы день месяц день_недели команда`

Примеры:
- `0 10 * * *` — каждый день в 10:00
- `30 8 * * *` — каждый день в 08:30
- `0 */6 * * *` — каждые 6 часов

### Systemd сервис

Файл: `/etc/systemd/system/avito-redroid.service`

```ini
[Unit]
Description=Avito Redroid Container
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/avito-redroid
ExecStartPre=/sbin/modprobe binder_linux devices="binder,hwbinder,vndbinder"
ExecStartPre=/sbin/modprobe ashmem_linux
ExecStartPre=/bin/mkdir -p /dev/binderfs
ExecStartPre=/bin/mount -t binderfs binderfs /dev/binderfs
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

**Команды:**
```bash
systemctl status avito-redroid
systemctl start avito-redroid
systemctl stop avito-redroid
systemctl restart avito-redroid
systemctl enable avito-redroid   # автозапуск при boot
systemctl disable avito-redroid  # отключить автозапуск
```

---

## Команды

### SSH подключение

```bash
ssh root@109.69.16.95
```

### Docker

```bash
# Статус контейнеров
docker ps

# Логи контейнера
docker logs avito-redroid -f

# Остановка (данные сохранятся)
docker compose -f /opt/avito-redroid/docker-compose.yml stop

# Запуск
docker compose -f /opt/avito-redroid/docker-compose.yml up -d

# Перезапуск
docker compose -f /opt/avito-redroid/docker-compose.yml restart

# Полное удаление БЕЗ данных
docker compose -f /opt/avito-redroid/docker-compose.yml down

# ОПАСНО: Удаление С ДАННЫМИ (потеря авторизации!)
docker compose -f /opt/avito-redroid/docker-compose.yml down -v
```

### ADB

```bash
# Подключение (с сервера)
adb connect 127.0.0.1:5555

# Подключение (с Windows)
adb connect 109.69.16.95:5555

# Список устройств
adb devices

# Выполнить команду в Android
adb -s 127.0.0.1:5555 shell <command>

# Примеры команд
adb -s 127.0.0.1:5555 shell getprop ro.product.model
adb -s 127.0.0.1:5555 shell pm list packages
adb -s 127.0.0.1:5555 shell am start -n com.avito.android/.Launcher
adb -s 127.0.0.1:5555 shell am force-stop com.avito.android
adb -s 127.0.0.1:5555 shell date
adb -s 127.0.0.1:5555 shell getprop persist.sys.timezone
```

### Извлечение токенов

```bash
# Через docker exec (рекомендуется)
docker exec avito-redroid cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml

# Через Python скрипт (форматированный JSON)
python3 /opt/avito-redroid/export_session.py

# Последний сохранённый файл
cat /opt/avito-redroid/output/latest.json
```

### scrcpy (с Windows)

```cmd
:: Установка
winget install Genymobile.scrcpy

:: Или скачать вручную
:: https://github.com/Genymobile/scrcpy/releases

:: Запуск
scrcpy -s 109.69.16.95:5555

:: С ограничением FPS (меньше нагрузка)
scrcpy -s 109.69.16.95:5555 --max-fps 30
```

---

## Клиентская авторизация (noVNC)

Для предоставления клиентам возможности самостоятельной авторизации в Avito используется noVNC — веб-интерфейс для доступа к экрану Android.

### Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Linux Server                                  │
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐    │
│  │  Redroid     │     │  websockify  │     │   Клиент         │    │
│  │  VNC :5900   │────▶│   :6080      │────▶│   Browser/App    │    │
│  │              │     │  (WebSocket) │     │                  │    │
│  └──────────────┘     └──────────────┘     └──────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Установленные компоненты

| Компонент | Порт | Описание |
|-----------|------|----------|
| VNC Server (Redroid) | 5900 | Нативный VNC сервер Android |
| websockify | 6080 | Прокси VNC → WebSocket |
| noVNC | 6080 | Веб-клиент VNC |

### Доступ через браузер

**URL**: `http://109.69.16.95:6080/vnc.html`

**С автоподключением**: `http://109.69.16.95:6080/vnc.html?autoconnect=true&resize=scale`

### Systemd сервис noVNC

Файл: `/etc/systemd/system/novnc.service`

```ini
[Unit]
Description=noVNC WebSocket proxy for Redroid
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
ExecStart=/usr/bin/websockify --web=/usr/share/novnc/ 6080 127.0.0.1:5900
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

**Команды управления:**
```bash
systemctl status novnc
systemctl start novnc
systemctl stop novnc
systemctl restart novnc
```

### Интеграция в мобильное приложение

#### Вариант 1: WebView (простейший)

**iOS (Swift):**
```swift
import WebKit

let webView = WKWebView()
let url = URL(string: "http://109.69.16.95:6080/vnc.html?autoconnect=true&resize=scale")!
webView.load(URLRequest(url: url))
```

**Android (Kotlin):**
```kotlin
val webView = WebView(context)
webView.settings.javaScriptEnabled = true
webView.loadUrl("http://109.69.16.95:6080/vnc.html?autoconnect=true&resize=scale")
```

#### Вариант 2: Нативные VNC библиотеки

| Платформа | Библиотека | Лицензия |
|-----------|------------|----------|
| iOS | PulseVNC | MIT |
| Android | bVNC | GPL |
| Flutter | flutter_vnc_viewer | MIT |
| React Native | react-native-vnc | MIT |

### API для клиентской авторизации

Рекомендуемый flow для продакшена:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Backend API                                   │
├─────────────────────────────────────────────────────────────────────┤
│  POST /auth/session/start                                           │
│    → Запускает Redroid контейнер для клиента                        │
│    → Возвращает: { vnc_url, session_id, timeout }                   │
│                                                                     │
│  GET /auth/session/{id}/status                                      │
│    → Проверяет статус авторизации                                   │
│    → Возвращает: { authorized: bool, user_id }                      │
│                                                                     │
│  POST /auth/session/{id}/complete                                   │
│    → Извлекает токены, останавливает контейнер                      │
│    → Сохраняет токены в БД                                          │
│    → Возвращает: { success, user_id }                               │
└─────────────────────────────────────────────────────────────────────┘
```

**Клиентский flow:**
1. Клиент нажимает "Привязать Avito" в приложении
2. App → `POST /auth/session/start`
3. Открывается WebView/VNC с экраном Avito
4. Клиент вводит: телефон → SMS код → капча (если есть)
5. App → `POST /auth/session/complete`
6. Токены сохранены на сервере, клиент авторизован

---

## Умное обновление токенов (Smart Refresh)

### Принцип работы

Токены Avito обновляются **автоматически внутри приложения**, когда оно запущено. Для минимизации ресурсов сервера используется "умное" обновление:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Timeline обновления токена                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Token expires: 22:29:44                                             │
│                                                                      │
│  22:27:00  ─────▶  Cron запускает smart_refresh.sh                  │
│            │                                                         │
│  22:27:05  │       Загрузка модулей ядра (если нужно)               │
│            │                                                         │
│  22:27:10  │       docker compose up -d                              │
│            │                                                         │
│  22:27:30  │       Ожидание загрузки Android (~20 сек)              │
│            │                                                         │
│  22:28:00  │       Синхронизация времени                            │
│            │                                                         │
│  22:29:34  │       Запуск Avito (за 10 сек до истечения)            │
│            │                                                         │
│  22:29:44  │       ═══ TOKEN EXPIRES ═══                            │
│            │       Avito автоматически обновляет токен               │
│            │                                                         │
│  22:30:00  │       Извлечение нового токена                          │
│            │                                                         │
│  22:30:05  │       Сохранение в output/latest.json                  │
│            │                                                         │
│  22:30:10  ─────▶  docker compose stop (экономия ресурсов)          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Почему так работает

1. **Контейнер не держим постоянно** — экономия RAM и CPU
2. **Запускаем заблаговременно** — контейнер грузится ~20-30 сек
3. **Avito запускаем за 10 сек до истечения** — токен обновится автоматически
4. **После обновления гасим** — до следующего раза

### Скрипт smart_refresh.sh

Файл: `/opt/avito-redroid/smart_refresh.sh`

```bash
#!/bin/bash

# ============================================
# Smart Token Refresh Script
# ============================================
# Запускает контейнер, ждёт нужного времени,
# запускает Avito для обновления токена,
# извлекает токен и останавливает контейнер.
# ============================================

LOG_DIR="/opt/avito-redroid/logs"
OUTPUT_DIR="/opt/avito-redroid/output"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/refresh_${TIMESTAMP}.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd /opt/avito-redroid

# 1. Загрузка модулей ядра
log "Loading kernel modules..."
modprobe binder_linux devices="binder,hwbinder,vndbinder" 2>/dev/null
modprobe ashmem_linux 2>/dev/null
mkdir -p /dev/binderfs
mount -t binderfs binderfs /dev/binderfs 2>/dev/null

# 2. Запуск контейнера
log "Starting Redroid container..."
docker compose up -d

# 3. Ожидание загрузки Android
log "Waiting for Android boot..."
for i in {1..60}; do
    BOOT=$(docker exec avito-redroid getprop sys.boot_completed 2>/dev/null)
    if [ "$BOOT" = "1" ]; then
        log "Android booted successfully"
        break
    fi
    sleep 1
done

# 4. Синхронизация времени
log "Syncing timezone..."
docker exec avito-redroid service call alarm 3 s16 Europe/Moscow
docker exec avito-redroid setprop persist.sys.timezone Europe/Moscow

# 5. Получение времени истечения токена
PREFS=$(docker exec avito-redroid cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml 2>/dev/null)
SESSION=$(echo "$PREFS" | grep -oP '(?<=name="session">)[^<]+')

if [ -n "$SESSION" ]; then
    # Декодируем JWT и получаем exp
    PAYLOAD=$(echo "$SESSION" | cut -d'.' -f2 | base64 -d 2>/dev/null)
    EXPIRES=$(echo "$PAYLOAD" | grep -oP '"exp":\K[0-9]+')

    if [ -n "$EXPIRES" ]; then
        LAUNCH_TIME=$((EXPIRES - 10))
        NOW=$(date +%s)
        WAIT_SECONDS=$((LAUNCH_TIME - NOW))

        if [ $WAIT_SECONDS -gt 0 ]; then
            log "Token expires at $(date -d @$EXPIRES '+%Y-%m-%d %H:%M:%S')"
            log "Waiting $WAIT_SECONDS seconds before launching Avito..."
            sleep $WAIT_SECONDS
        fi
    fi
fi

# 6. Запуск Avito
log "Launching Avito..."
docker exec avito-redroid am start -n com.avito.android/.Launcher

# 7. Ожидание обновления токена
log "Waiting for token refresh..."
sleep 30

# 8. Извлечение токена
log "Extracting new token..."
python3 /opt/avito-redroid/export_session.py > "${OUTPUT_DIR}/session_${TIMESTAMP}.json"
ln -sf "session_${TIMESTAMP}.json" "${OUTPUT_DIR}/latest.json"

# 9. Проверка нового токена
NEW_EXPIRES=$(cat "${OUTPUT_DIR}/latest.json" | grep -oP '"expires_at":\s*\K[0-9]+')
if [ -n "$NEW_EXPIRES" ]; then
    log "New token expires at $(date -d @$NEW_EXPIRES '+%Y-%m-%d %H:%M:%S')"
fi

# 10. Остановка контейнера
log "Stopping container..."
docker compose stop

log "Done!"
```

### Настройка Cron

**Текущая конфигурация:**

Токен истекает в **22:29:44**, cron запускается за 2-3 минуты до этого:

```bash
# Просмотр crontab
crontab -l

# Текущая задача (запуск в 22:27)
27 22 * * * /opt/avito-redroid/smart_refresh.sh >> /opt/avito-redroid/logs/cron.log 2>&1
```

**Формат cron:**
```
┌───────────── минуты (0-59)
│ ┌───────────── часы (0-23)
│ │ ┌───────────── день месяца (1-31)
│ │ │ ┌───────────── месяц (1-12)
│ │ │ │ ┌───────────── день недели (0-7, 0 и 7 = воскресенье)
│ │ │ │ │
│ │ │ │ │
* * * * * команда
```

### Расчёт времени запуска cron

```
Token expires:     22:29:44
Container boot:    ~30 sec
Android boot:      ~20 sec
Sync + prepare:    ~10 sec
Buffer:            ~60 sec
─────────────────────────────
Total:             ~2 minutes before expiry

Cron time = 22:29 - 2 min = 22:27
```

### Изменение времени cron

Если токен начнёт истекать в другое время:

```bash
# Посмотреть текущее время истечения
cat /opt/avito-redroid/output/latest.json | jq .expires_at
# Перевести в читаемое время
date -d @<timestamp>

# Изменить cron (вычесть 2-3 минуты от времени истечения)
crontab -e
# Изменить строку: MM HH * * * /opt/avito-redroid/smart_refresh.sh ...
```

### Мониторинг работы cron

```bash
# Последний лог обновления
tail -f /opt/avito-redroid/logs/cron.log

# Все логи обновлений
ls -la /opt/avito-redroid/logs/

# Проверить что cron работает
grep CRON /var/log/syslog | tail -20

# Текущий токен и время истечения
cat /opt/avito-redroid/output/latest.json | jq '{expires: .expires_at, expires_human: (.expires_at | todate)}'
```

---

## Использование токенов в API

### Python пример

```python
import json
import requests

# Загрузка токенов
with open('session.json') as f:
    session = json.load(f)

# Заголовки для API
headers = {
    'Authorization': f'Bearer {session["session_token"]}',
    'X-Device-Id': session['device_id'],
    'f': session['fingerprint'],
    'User-Agent': 'Avito/216.0 (Android 13; Pixel 6)'
}

# Пример: получение чатов
response = requests.get(
    'https://api.avito.ru/messenger/v3/channels',
    headers=headers
)
print(response.json())
```

### Обновление токена через API

```python
def refresh_session(refresh_token):
    url = 'https://api.avito.ru/auth/v1/refresh'
    headers = {
        'Authorization': f'Bearer {refresh_token}',
        'User-Agent': 'Avito/216.0 (Android 13; Pixel 6)'
    }
    response = requests.post(url, headers=headers)
    return response.json()

# Использование
new_tokens = refresh_session(session['refresh_token'])
session['session_token'] = new_tokens['access_token']
```

---

## Troubleshooting

### Redroid не запускается (exit code 129)

**Причина**: Не загружены модули ядра

**Решение**:
```bash
modprobe binder_linux devices="binder,hwbinder,vndbinder"
modprobe ashmem_linux
mkdir -p /dev/binderfs
mount -t binderfs binderfs /dev/binderfs
docker compose restart
```

### Android не загружается (boot_completed пустой)

**Причина**: Проблема с конфигурацией или ресурсами

**Решение**:
```bash
docker logs avito-redroid
docker compose down
docker compose up -d
sleep 60
docker exec avito-redroid getprop sys.boot_completed
```

### Avito требует повторную авторизацию

**Причины**:
1. Неправильное время на устройстве
2. Удалён Docker volume (`docker compose down -v`)
3. Истёк refresh_token (~30 дней без использования)

**Решение**:
```bash
# Проверить время
date && adb -s 127.0.0.1:5555 shell date

# Синхронизировать
timedatectl set-timezone Europe/Moscow
adb -s 127.0.0.1:5555 shell service call alarm 3 s16 Europe/Moscow
```

### Токены не обновляются автоматически

**Причина**: Avito должен быть **запущен** для обновления токенов

**Решение**:
```bash
adb -s 127.0.0.1:5555 shell am start -n com.avito.android/.Launcher
sleep 30
python3 /opt/avito-redroid/export_session.py
```

### scrcpy не подключается

**Решение**:
```bash
# На сервере - перезапуск ADB
adb kill-server
adb start-server
adb connect 127.0.0.1:5555

# Проверить firewall
ufw allow 5555/tcp
ufw allow 5900/tcp
```

### "Device offline" в ADB

**Решение**:
```bash
adb disconnect 127.0.0.1:5555
sleep 2
adb connect 127.0.0.1:5555
adb devices
```

---

## Важные заметки

### ⚠️ Синхронизация времени (КРИТИЧНО!)

**Avito блокирует запросы с неправильным временем!**

- Сервер и Android должны быть в **одном часовом поясе**
- Рекомендуется: `Europe/Moscow`
- Проверять перед каждой операцией с токенами

```bash
# Проверка
date && adb -s 127.0.0.1:5555 shell date
# Время должно совпадать!
```

### ⚠️ Маскировка устройства

Redroid определяется как эмулятор (`redroid13_x86_64`).

Avito видит название устройства при входе и записывает в историю.

Для новых авторизаций использовать Frida маскировку **ДО** входа:
```bash
frida -H 127.0.0.1:27042 -l pixel6_mask.js -f com.avito.android --no-pause
```

### ⚠️ Docker Volume

Данные Avito хранятся в Docker volume `avito-redroid_redroid_data`.

**НЕ УДАЛЯЙТЕ volume без бэкапа!**

```bash
# ОПАСНО - удалит все данные авторизации!
docker compose down -v

# Безопасно - данные сохранятся
docker compose down
docker compose stop
```

### ⚠️ Fingerprint (fpx)

Fingerprint генерируется **native-библиотекой** Avito.

**Невозможно:**
- Сгенерировать программно
- Перенести на другое устройство
- Восстановить после удаления данных

При потере fingerprint — нужна новая авторизация.

---

## Переменные и конфигурация

### Docker Compose environment

| Переменная | Значение | Описание |
|------------|----------|----------|
| REDROID_WIDTH | 1080 | Ширина экрана |
| REDROID_HEIGHT | 2400 | Высота экрана |
| REDROID_DPI | 420 | Плотность пикселей |
| REDROID_GPU_MODE | guest | Режим GPU (guest/host/auto) |

### Сетевые порты

| Порт | Протокол | Описание |
|------|----------|----------|
| 5555 | TCP | ADB (Android Debug Bridge) |
| 5900 | TCP | VNC Server (Redroid) |
| 6080 | TCP | noVNC (веб-доступ к VNC) |
| 27042 | TCP | Frida Server |

### Пути на сервере

| Путь | Описание |
|------|----------|
| /opt/avito-redroid | Рабочая директория |
| /var/lib/docker/volumes/avito-redroid_redroid_data | Docker volume |
| /etc/systemd/system/avito-redroid.service | Systemd сервис |

### Часовой пояс

**Обязательно**: `Europe/Moscow` (или другой, но одинаковый на сервере и Android)

---

## Версии ПО (на момент настройки)

| Компонент | Версия |
|-----------|--------|
| Ubuntu | 22.04.5 LTS |
| Kernel | 5.15.0-164-generic |
| Docker | 29.1.5 |
| Docker Compose | v5.0.2 |
| Redroid | 13.0.0-latest (Android 13) |
| Frida | 16.6.6 |
| Avito APK | 216.0 (январь 2026) |
| Python | 3.10+ |

---

## Текущая конфигурация

| Параметр | Значение |
|----------|----------|
| **Сервер** | 109.69.16.95 |
| **Пользователь** | root |
| **Рабочая директория** | /opt/avito-redroid |
| **Часовой пояс** | Europe/Moscow |
| **Аккаунт Avito** | РемАкс (dk@remacs.ru) |
| **User ID** | 157920214 |

### Сервисы

| Сервис | Статус | Описание |
|--------|--------|----------|
| avito-redroid.service | enabled | Автозапуск контейнера при boot |
| novnc.service | enabled | Веб-доступ к экрану Android |

### Cron задачи

| Время | Команда | Описание |
|-------|---------|----------|
| 22:27 * * * | smart_refresh.sh | Умное обновление токена |

### URL доступа

| Назначение | URL |
|------------|-----|
| noVNC (браузер) | http://109.69.16.95:6080/vnc.html |
| noVNC (autoconnect) | http://109.69.16.95:6080/vnc.html?autoconnect=true&resize=scale |
| VNC (native) | vnc://109.69.16.95:5900 |
| ADB | 109.69.16.95:5555 |

---

*Документация создана: 2026-01-26*
*Последнее обновление: 2026-01-27*
