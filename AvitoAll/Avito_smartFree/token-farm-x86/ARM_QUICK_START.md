# ARM Quick Start - Быстрый старт на Hetzner CAX11

Пошаговая инструкция для развертывания на ARM64 сервере после неудачи на x86.

---

## Шаг 1: Создание сервера (2 минуты)

### Hetzner Cloud

1. Зайти на https://console.hetzner.cloud/
2. Создать новый проект "Avito Token Farm"
3. Добавить сервер:
   - **Location:** Nuremberg (или ближайший к России)
   - **Image:** Ubuntu 22.04 ARM64
   - **Type:** CAX11 (2 vCPU, 4GB RAM)
   - **Networking:** IPv4 + IPv6
   - **SSH Key:** Добавить свой публичный ключ
   - **Name:** avito-farm-arm

4. Нажать "Create & Buy now"
5. Дождаться создания (30-60 секунд)
6. Скопировать IP адрес

---

## Шаг 2: Первоначальная настройка (3 минуты)

### Подключиться к серверу

```bash
# Замени IP_ADDRESS на реальный IP
ssh root@IP_ADDRESS
```

### Установить зависимости

```bash
# Обновить систему
apt update && apt upgrade -y

# Установить Docker
apt install -y docker.io docker-compose-v2 git wget curl

# Установить дополнительные kernel модули
apt install -y linux-modules-extra-$(uname -r)

# Загрузить Android модули
modprobe binder_linux devices=binder,hwbinder,vndbinder
modprobe ashmem_linux

# Проверить что модули загружены
lsmod | grep -E 'binder|ashmem'
```

### Настроить автозагрузку модулей

```bash
# Добавить модули в автозагрузку
cat >> /etc/modules << 'EOF'
binder_linux
ashmem_linux
EOF

# Настроить параметры binder
cat > /etc/modprobe.d/binder.conf << 'EOF'
options binder_linux devices=binder,hwbinder,vndbinder
EOF
```

---

## Шаг 3: Загрузка проекта (2 минуты)

### Вариант A: Загрузить с локальной машины (рекомендую)

```powershell
# На Windows (PowerShell)
# Перейти в папку проекта
cd C:\Users\EloWork\Documents\Projects\Reverse\APK\Avito_smartFree

# Загрузить папку token-farm на сервер
scp -r token-farm root@IP_ADDRESS:/root/

# Загрузить APK
scp Avito/avito.apk root@IP_ADDRESS:/tmp/avito.apk
```

### Вариант B: Скачать с x86 сервера

```bash
# На ARM сервере
# Скачать APK с x86 сервера
scp root@85.198.98.104:/tmp/avito_latest.apk /tmp/avito.apk

# Скачать код (если есть на x86)
scp -r root@85.198.98.104:/root/avito-token-farm-x86 /root/token-farm-temp
```

---

## Шаг 4: Настройка Docker (1 минута)

### Создать .env файл

```bash
cd /root/token-farm

cat > .env << 'EOF'
# PostgreSQL
POSTGRES_USER=avito
POSTGRES_PASSWORD=avito_secure_password_change_me
POSTGRES_DB=avito_smartfree

# Token Farm API
FARM_API_KEY=secure_api_key_change_me
LOG_LEVEL=INFO
ENVIRONMENT=production

# Telegram Bot (опционально)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_IDS=your_telegram_id
EOF
```

### Проверить docker-compose.yml

```bash
# Убедиться что используется ARM image
grep "platform:" docker-compose.yml
# Должно быть: platform: linux/arm64
```

---

## Шаг 5: Запуск контейнеров (2 минуты)

```bash
cd /root/token-farm

# Запустить все контейнеры
docker-compose up -d

# Посмотреть логи
docker-compose logs -f redroid-arm-1
# Нажать Ctrl+C когда увидишь "Boot complete"

# Проверить статус
docker-compose ps
```

### Ожидаемый вывод

```
NAME                STATUS              PORTS
avito-postgres      Up 2 minutes        5432/tcp
redroid-arm-1       Up 2 minutes        0.0.0.0:5555->5555/tcp
redroid-arm-2       Up 2 minutes        0.0.0.0:5556->5555/tcp
```

### Проверить что Android загрузился

```bash
# Подождать 30-40 секунд после запуска

# Проверить boot_completed (должен вернуть "1")
docker exec redroid-arm-1 getprop sys.boot_completed

# Проверить system_server (должен работать, НЕ zombie)
docker exec redroid-arm-1 ps -A | grep system_server
```

**✅ Если system_server работает (не zombie) - Android запущен успешно!**

---

## Шаг 6: Установка Avito APK (1 минута)

```bash
# Проверить что APK есть
ls -lh /tmp/avito.apk
# Должен быть ~200 MB

# Скопировать APK в контейнер
docker cp /tmp/avito.apk redroid-arm-1:/tmp/

# Установить через package manager
docker exec redroid-arm-1 sh -c 'pm install -r /tmp/avito.apk'

# Проверить установку
docker exec redroid-arm-1 sh -c 'pm list packages | grep avito'
# Вывод: package:com.avito.android

# Узнать версию
docker exec redroid-arm-1 sh -c 'dumpsys package com.avito.android | grep versionName'
```

**✅ Если видишь "package:com.avito.android" - APK установлен!**

---

## Шаг 7: Инжект session data (3 минуты)

### Подготовить session XML

```bash
# Создать Python скрипт для генерации XML
cat > /root/generate_session.py << 'PYTHON_EOF'
import sys
sys.path.append('/root/token-farm')

from avito_prefs_parser import AvitoSession, generate_session_xml

# Real session data (из avito_session_final.json)
session = AvitoSession(
    session_token="YOUR_SESSION_TOKEN_HERE",  # JWT токен из avito_session_final.json
    refresh_token="YOUR_REFRESH_TOKEN_HERE",
    fingerprint="YOUR_FINGERPRINT_HERE",  # Реальный fpx из session data
    device_id="YOUR_DEVICE_ID_HERE",
    remote_device_id="YOUR_REMOTE_DEVICE_ID_HERE",
    user_id=YOUR_USER_ID,  # Integer
    user_hash="YOUR_USER_HASH_HERE",
    expires_at=1800000000  # Far future for testing
)

xml = generate_session_xml(session)
print(xml)
PYTHON_EOF

# Сгенерировать XML
python3 /root/generate_session.py > /tmp/avito_session.xml

# Проверить что XML создан
cat /tmp/avito_session.xml | head -20
```

### Инжектировать в контейнер

```bash
# Скопировать XML в контейнер
docker cp /tmp/avito_session.xml redroid-arm-1:/tmp/

# Установить в нужное место с правильными правами
docker exec redroid-arm-1 sh -c '
    # Создать папку shared_prefs если нет
    mkdir -p /data/data/com.avito.android/shared_prefs

    # Скопировать XML
    cp /tmp/avito_session.xml /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml

    # Получить UID приложения
    APP_UID=$(stat -c "%u" /data/data/com.avito.android)

    # Установить права доступа
    chown -R ${APP_UID}:${APP_UID} /data/data/com.avito.android/shared_prefs
    chmod 660 /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml

    # Проверить
    ls -la /data/data/com.avito.android/shared_prefs/
'

# Проверить содержимое
docker exec redroid-arm-1 sh -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml | head -30'
```

**✅ Если видишь XML с fingerprint - session data инжектирована!**

---

## Шаг 8: Первый запуск Avito (2 минуты)

### Запустить приложение

```bash
# Запустить Avito
docker exec redroid-arm-1 sh -c 'am start -n com.avito.android/.main.MainActivity'

# Подождать 5 секунд
sleep 5

# Сделать скриншот
docker exec redroid-arm-1 sh -c 'screencap -p' > /tmp/avito_screen.png

# Скачать скриншот на локальную машину
# На ARM сервере:
# Готово, теперь скачай на Windows
```

### Скачать скриншот (на Windows)

```powershell
scp root@IP_ADDRESS:/tmp/avito_screen.png ./avito_first_launch.png
```

**Открой `avito_first_launch.png` и проверь:**
- ✅ Приложение открылось (не краш, не черный экран)
- ✅ Нет запроса авторизации (если session data работает)
- ✅ Видно главный экран или профиль пользователя

### Если требуется авторизация

Если скриншот показывает экран входа - нужна ручная авторизация:

```bash
# 1. Посмотреть скриншот, найти где поле ввода номера
# 2. Тап на поле (координаты зависят от UI)
docker exec redroid-arm-1 sh -c 'input tap 540 800'

# 3. Ввести номер
docker exec redroid-arm-1 sh -c 'input text "+7XXXXXXXXXX"'

# 4. Тап на кнопку "Далее"
docker exec redroid-arm-1 sh -c 'input tap 540 1200'

# 5. Получить SMS код (проверь телефон)
# 6. Ввести код
docker exec redroid-arm-1 sh -c 'input text "1234"'  # Замени на реальный код

# 7. После авторизации извлечь новую session
docker exec redroid-arm-1 sh -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml' > /tmp/new_session.xml
```

---

## Шаг 9: Тест активного refresh (5 минут)

### Создать тестовый скрипт

```bash
cat > /root/test_refresh.py << 'PYTHON_EOF'
import asyncio
import subprocess
from datetime import datetime

async def shell(cmd):
    """Execute command in container"""
    proc = await asyncio.create_subprocess_shell(
        f'docker exec redroid-arm-1 sh -c "{cmd}"',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode().strip()

async def test_refresh():
    print("=" * 60)
    print("Avito Active Refresh Test")
    print("=" * 60)

    # Получить текущую session
    print("\n[1] Reading current session...")
    xml = await shell("cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml")

    if '<string name="fpx">' in xml:
        print("✅ Fingerprint found in session")
        # Извлечь fpx
        import re
        fpx_match = re.search(r'<string name="fpx">(.*?)</string>', xml)
        if fpx_match:
            fpx = fpx_match.group(1)
            print(f"   Fingerprint: {fpx[:50]}...")
    else:
        print("❌ No fingerprint in session!")
        return

    # Запустить Avito
    print("\n[2] Starting Avito...")
    await shell("am start -n com.avito.android/.main.MainActivity")
    await asyncio.sleep(5)
    print("✅ Avito started")

    # Симулировать активность
    print("\n[3] Simulating user activity (scrolling)...")
    for i in range(3):
        print(f"   Round {i+1}/3: Scrolling...")
        await shell("input swipe 540 1600 540 800 300")
        await asyncio.sleep(3)

    print("✅ Activity simulation complete")

    # Остановить Avito
    print("\n[4] Stopping Avito...")
    await shell("am force-stop com.avito.android")
    print("✅ Avito stopped")

    # Проверить session после
    print("\n[5] Checking session after activity...")
    xml_after = await shell("cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml")

    if xml == xml_after:
        print("⚠️  Session unchanged (may need real API calls)")
    else:
        print("✅ Session updated!")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_refresh())
PYTHON_EOF

# Запустить тест
python3 /root/test_refresh.py
```

**✅ Если видишь "Fingerprint found" и "Test complete" - базовая функциональность работает!**

---

## Шаг 10: Проверка (чек-лист)

Убедись что всё работает:

- [ ] ✅ `docker exec redroid-arm-1 getprop sys.boot_completed` возвращает `1`
- [ ] ✅ `docker exec redroid-arm-1 ps -A | grep system_server` показывает работающий процесс (НЕ zombie)
- [ ] ✅ `docker exec redroid-arm-1 pm list packages | grep avito` показывает `package:com.avito.android`
- [ ] ✅ SharedPreferences содержит fingerprint
- [ ] ✅ Avito запускается без ошибок
- [ ] ✅ Скриншот показывает нормальный UI (не краш)

**Если все чекбоксы ✅ - развертывание успешно! Можно переходить к интеграции.**

---

## 🆘 Troubleshooting

### Контейнер не запускается

```bash
# Проверить логи
docker logs redroid-arm-1

# Проверить модули ядра
lsmod | grep -E 'binder|ashmem'

# Перезагрузить модули
modprobe -r binder_linux ashmem_linux
modprobe binder_linux devices=binder,hwbinder,vndbinder
modprobe ashmem_linux
```

### system_server падает (как на x86)

```bash
# Это НЕ должно произойти на ARM, но если случилось:

# Проверить tombstones
docker exec redroid-arm-1 ls -la /data/tombstones/

# Проверить логи
docker exec redroid-arm-1 logcat -d | grep -E 'FATAL|system_server'

# Попробовать другой образ
# В docker-compose.yml изменить:
# image: redroid/redroid:11.0.0-latest
```

### APK не устанавливается

```bash
# Проверить что файл не поврежден
md5sum /tmp/avito.apk

# Попробовать установить с флагом -t (test APK)
docker exec redroid-arm-1 pm install -r -t /tmp/avito.apk

# Проверить логи установки
docker exec redroid-arm-1 logcat -d | grep PackageManager
```

### Session data не инжектируется

```bash
# Проверить права доступа
docker exec redroid-arm-1 ls -la /data/data/com.avito.android/shared_prefs/

# Проверить UID приложения
docker exec redroid-arm-1 stat -c "%u:%g" /data/data/com.avito.android

# Установить права вручную
docker exec redroid-arm-1 sh -c '
    chown 10001:10001 /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
    chmod 660 /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
'
```

---

## 📞 Следующие шаги после успешного запуска

1. **Протестировать token refresh** - убедиться что expires_at обновляется
2. **Проверить API запросы** - fingerprint должен работать
3. **Настроить Token Refresh Scheduler** - автоматическое обновление
4. **Интегрировать Telegram Bot** - управление через Telegram
5. **Настроить мониторинг** - Prometheus + Grafana (опционально)

**Подробный план:** см. `X86_DEPLOYMENT_SUMMARY.md`

---

**Время развертывания:** 15-20 минут
**Дата:** 25 января 2026
**Следующий файл:** `X86_DEPLOYMENT_SUMMARY.md` (полная документация)

