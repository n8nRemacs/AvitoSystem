# Quick Start Guide - x86 Development Environment

Быстрый запуск Token Farm на x86/x64 для локальной разработки и тестирования.

## Требования

- **Docker Desktop** (Windows/Mac) или **Docker Engine** (Linux)
- **Python 3.10+**
- **ADB** (Android Debug Bridge) - установи Android Platform Tools
- **Git** (опционально)

## Установка за 5 минут

### Windows

```cmd
# 1. Перейти в папку
cd token-farm-x86

# 2. Запустить скрипт
start.bat

# Готово! Контейнеры запущены.
```

### Linux/Mac

```bash
# 1. Установить зависимости
make install

# 2. Запустить контейнеры
make up

# 3. Подключить ADB
make adb

# Готово!
```

### Ручная установка (любая ОС)

```bash
# 1. Создать .env файл
cp .env.example .env

# 2. Запустить контейнеры
docker-compose up -d

# 3. Подождать 10 секунд

# 4. Подключить ADB
adb connect localhost:5555
adb connect localhost:5556

# 5. Проверить
adb devices
docker-compose ps
```

---

## Проверка установки

### Запустить тесты

```bash
# Python тесты
python test_x86_setup.py

# Unit tests
pytest test_avito_prefs_parser.py -v
```

**Ожидаемый результат:**
```
Test 1: ADB Connection (port 5555)
✅ Connected successfully!

Test 2: Screen Interaction
✅ Tapped at (540, 1200)
✅ Swiped from (540, 1600) to (540, 800)

Test 3: SharedPreferences Parser
✅ Roundtrip successful! All fields match.

Test 4: Mock Active Refresh Logic
✅ Mock refresh simulation completed!

✅ All tests completed!
```

### Проверить контейнеры

```bash
docker-compose ps
```

**Ожидаемый результат:**
```
NAME                STATUS              PORTS
avito-postgres-x86  Up 2 minutes        5432/tcp
redroid-x86-1       Up 2 minutes        0.0.0.0:5555->5555/tcp, 0.0.0.0:5900->5900/tcp
redroid-x86-2       Up 2 minutes        0.0.0.0:5556->5555/tcp, 0.0.0.0:5901->5900/tcp
```

### Проверить ADB

```bash
adb devices
```

**Ожидаемый результат:**
```
List of devices attached
localhost:5555  device
localhost:5556  device
```

---

## Базовое использование

### ADB команды

```bash
# Информация об устройстве
adb -s localhost:5555 shell getprop ro.product.model

# Скриншот
adb -s localhost:5555 exec-out screencap -p > screen.png

# Тап по экрану
adb -s localhost:5555 shell input tap 500 1000

# Свайп (scroll)
adb -s localhost:5555 shell input swipe 540 1600 540 800 300

# Открыть shell
adb -s localhost:5555 shell

# Установить APK
adb -s localhost:5555 install app.apk
```

### Docker команды

```bash
# Посмотреть логи
docker-compose logs -f

# Логи конкретного контейнера
docker-compose logs -f redroid-x86-1

# Зайти в контейнер
docker exec -it redroid-x86-1 sh

# Перезапустить
docker-compose restart

# Остановить
docker-compose down

# Удалить всё (включая данные)
docker-compose down -v
```

### Python тестирование

```python
# test_example.py
import asyncio
from test_x86_setup import SimpleADBController

async def test():
    adb = SimpleADBController(host="localhost", port=5555)
    await adb.connect()

    # Get device info
    model = await adb.get_prop("ro.product.model")
    print(f"Device: {model}")

    # Tap
    await adb.tap(500, 1000)
    print("Tapped!")

asyncio.run(test())
```

---

## Разработка и отладка

### Установить тестовое приложение

Можно установить любой APK для тестирования UI automation:

```bash
# Скачать простой APK (например, калькулятор)
# https://f-droid.org/en/packages/com.simplemobiletools.calculator/

# Установить
adb -s localhost:5555 install calculator.apk

# Запустить
adb -s localhost:5555 shell am start -n com.simplemobiletools.calculator/.MainActivity

# Взаимодействовать
adb -s localhost:5555 shell input tap 500 1000
```

### Тестировать SharedPreferences

```python
from avito_prefs_parser import AvitoSession, generate_session_xml
from datetime import datetime

# Создать тестовую сессию
session = AvitoSession(
    session_token="test_token_123",
    device_id="test_device",
    expires_at=int(datetime.now().timestamp()) + 3600
)

# Сгенерировать XML
xml = generate_session_xml(session)
print(xml)

# Записать в файл
with open("session.xml", "w") as f:
    f.write(xml)

# Загрузить в контейнер
# adb push session.xml /data/local/tmp/
```

### Мониторинг ресурсов

```bash
# CPU/Memory usage
docker stats

# Только контейнеры Token Farm
docker stats redroid-x86-1 redroid-x86-2
```

---

## Частые проблемы

### ADB не подключается

**Проблема:**
```
$ adb connect localhost:5555
failed to connect to localhost:5555
```

**Решение:**
```bash
# 1. Проверить что контейнер запущен
docker-compose ps

# 2. Проверить порты
docker-compose ps | grep 5555

# 3. Перезапустить ADB server
adb kill-server
adb start-server

# 4. Попробовать снова
adb connect localhost:5555
```

### Контейнер не запускается

**Проблема:**
```
Error response from daemon: driver failed
```

**Решение:**
```bash
# 1. Проверить Docker
docker --version
docker ps

# 2. Посмотреть логи
docker-compose logs redroid-x86-1

# 3. Попробовать пересоздать
docker-compose down
docker-compose up -d

# 4. Если не помогает, удалить volumes
docker-compose down -v
docker-compose up -d
```

### Медленная работа

**Проблема:**
Контейнеры тормозят, высокая нагрузка на CPU.

**Решение:**
```yaml
# В docker-compose.yml добавить лимиты:
services:
  redroid-x86-1:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

### Тесты падают

**Проблема:**
```
pytest test_avito_prefs_parser.py
ImportError: No module named 'pytest'
```

**Решение:**
```bash
# Установить зависимости
pip install pytest asyncio httpx

# Или через requirements (если есть)
pip install -r ../token-farm/requirements.txt
```

---

## Следующие шаги

После успешного запуска на x86:

1. ✅ **Тестирование логики** - отладка активного refresh, парсера, UI automation
2. ✅ **Разработка новых фич** - легко тестировать на локальной машине
3. 🚀 **Миграция на ARM** - перенести код в `token-farm/` и развернуть на Hetzner CAX

### Переход на ARM (production)

```bash
# 1. Скопировать код
cp -r token-farm-x86/*.py ../token-farm/

# 2. Использовать ARM docker-compose.yml
cd ../token-farm

# 3. Развернуть на ARM сервере
# (Hetzner CAX, Oracle Ampere, AWS Graviton)

# 4. Запустить с platform: linux/arm64
docker-compose up -d
```

---

## Полезные ссылки

- **Redroid**: https://github.com/remote-android/redroid-doc
- **ADB Commands**: https://developer.android.com/tools/adb
- **Docker Compose**: https://docs.docker.com/compose/
- **Python AsyncIO**: https://docs.python.org/3/library/asyncio.html

---

## Поддержка

Если возникли проблемы:

1. Проверить логи: `docker-compose logs -f`
2. Проверить ADB: `adb devices`
3. Проверить порты: `docker-compose ps`
4. Пересоздать: `docker-compose down -v && docker-compose up -d`

---

**Готово!** Теперь у вас есть рабочее окружение для разработки и тестирования Token Farm на x86. 🎉
