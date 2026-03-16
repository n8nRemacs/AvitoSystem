# Next Steps - ОБНОВЛЕНО 25.01.2026

## ❌ x86 Deployment ПРОВАЛЕН

**Критическая проблема:** Redroid не работает стабильно на x86 архитектуре.

**Что было сделано:**
1. ✅ Kernel модули binder/ashmem установлены и загружены
2. ✅ Docker контейнеры запускаются (Android 11 и 12 протестированы)
3. ✅ Avito APK загружен (205 MB)
4. ✅ Session data с реальным fingerprint подготовлена
5. ✅ SharedPreferences parser тесты пройдены (17/17)
6. ✅ Код полностью готов к переносу на ARM

**Почему не работает:**
- ❌ system_server крашится при загрузке Android
- ❌ Boot loop - перезапуски каждые 5 секунд
- ❌ Без system_server нет PackageManager/ActivityManager
- ❌ Невозможно установить или запустить APK
- ❌ Это известная проблема Redroid на x86 (GitHub Issue #418)

**Подробности:** см. `X86_DEPLOYMENT_SUMMARY.md`

---

## 🚀 СЛЕДУЮЩИЙ ШАГ: Переход на ARM64

### Рекомендуемое решение: Hetzner CAX11

### Вариант A: Автоматическая установка (если есть прямая ссылка)

Если есть прямая ссылка на Avito APK, используй:

```bash
ssh root@85.198.98.104 "wget -O /tmp/avito_latest.apk 'DIRECT_LINK' && cd /root/avito-token-farm-x86 && bash install_avito.sh"
```

### Вариант B: Ручная установка (рекомендую)

#### Шаг 1: Скачай APK

**Источники:**
- APKMirror: https://www.apkmirror.com/apk/avito/avito/
- APKPure: https://apkpure.com/ru/avito/com.avito.android

**Важно:** Скачивай базовый APK (~80-100 MB), не XAPK bundle!

#### Шаг 2: Загрузи на сервер

```powershell
# В PowerShell/CMD (папка с APK)
scp com.avito.android*.apk root@85.198.98.104:/tmp/avito_latest.apk
```

#### Шаг 3: Установи

```bash
ssh root@85.198.98.104
cd /root/avito-token-farm-x86
bash install_avito.sh
```

Подробная инструкция: см. `MANUAL_AVITO_INSTALL.md`

---

## 📱 После установки APK

### 1. Запустить приложение

```bash
ssh root@85.198.98.104

# Запустить Avito
docker exec redroid-x86-1 sh -c "am start -n com.avito.android/.main.MainActivity"

# Сделать скриншот
docker exec redroid-x86-1 sh -c "screencap -p" > /tmp/screen.png

# Скачать скриншот
scp root@85.198.98.104:/tmp/screen.png ./avito_screen.png
```

### 2. Пройти авторизацию

**Понадобится:**
- Номер телефона (Россия)
- SMS код подтверждения

**Процесс:**
1. Открой скриншот `avito_screen.png`
2. Посмотри где поле ввода номера
3. Используй UI automation для ввода:

```bash
# Координаты зависят от UI Avito
# Пример: тап на поле номера
docker exec redroid-x86-1 sh -c "input tap 540 800"

# Ввод номера (пример)
docker exec redroid-x86-1 sh -c "input text '+79123456789'"

# Тап на кнопку "Далее"
docker exec redroid-x86-1 sh -c "input tap 540 1200"

# Ввод SMS кода (после получения)
docker exec redroid-x86-1 sh -c "input text '1234'"
```

**Альтернатива (VNC):**
- Подключись через VNC Viewer к `85.198.98.104:5900`
- Пройди авторизацию вручную через GUI

### 3. Извлечь session data

После успешной авторизации:

```bash
# Проверить что SharedPreferences созданы
docker exec redroid-x86-1 sh -c "ls -la /data/data/com.avito.android/shared_prefs/"

# Прочитать session file
docker exec redroid-x86-1 sh -c "cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml"

# Сохранить в файл
docker exec redroid-x86-1 sh -c "cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml" > /tmp/avito_session.xml

# Скачать на компьютер
scp root@85.198.98.104:/tmp/avito_session.xml ./avito_session.xml
```

### 4. Парсинг данных

Используй наш парсер:

```bash
cd /root/avito-token-farm-x86

# Создай скрипт
cat > parse_session.py << 'EOF'
from avito_prefs_parser import parse_session_xml
import sys

with open('/tmp/avito_session.xml', 'r') as f:
    xml = f.read()

session = parse_session_xml(xml)
if session:
    print(f"Session Token: {session.session_token[:50]}...")
    print(f"Fingerprint: {session.fingerprint}")
    print(f"Device ID: {session.device_id}")
    print(f"User Hash: {session.user_hash}")
    print(f"Expires at: {session.expires_at}")
    print(f"Time until expiry: {session.time_until_expiry()}s")
else:
    print("Failed to parse session")
EOF

python3 parse_session.py
```

---

## 🔄 Тестирование активного обновления

После получения session token:

### 1. Подготовка

```bash
cd /root/avito-token-farm-x86

# Создать тестовый скрипт для активного refresh
cat > test_active_refresh_real.py << 'EOF'
import asyncio
import sys
import time
from datetime import datetime
from avito_prefs_parser import parse_session_xml

# Simplified ADB controller using docker exec
class DockerADB:
    def __init__(self, container="redroid-x86-1"):
        self.container = container

    async def shell(self, cmd):
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self.container, "sh", "-c", cmd,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    async def get_session(self):
        xml = await self.shell("cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml")
        if xml and '<map>' in xml:
            return parse_session_xml(xml)
        return None

    async def start_avito(self):
        await self.shell("am start -n com.avito.android/.main.MainActivity")

    async def stop_avito(self):
        await self.shell("am force-stop com.avito.android")

    async def swipe(self, x1, y1, x2, y2, duration=300):
        await self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")

async def test_active_refresh():
    print("="*60)
    print("Active Token Refresh Test")
    print("="*60)

    adb = DockerADB()

    # Get current session
    print("\n[1] Reading current session...")
    session = await adb.get_session()
    if not session:
        print("❌ No session found. Authorize first!")
        return

    print(f"✅ Session found")
    print(f"   Token: {session.session_token[:50]}...")
    print(f"   Fingerprint: {session.fingerprint[:30]}...")
    print(f"   Expires in: {session.time_until_expiry()}s")

    # Check if token is about to expire
    time_left = session.time_until_expiry()
    if time_left > 600:  # More than 10 minutes
        print(f"\n⚠️  Token expires in {time_left}s ({time_left//60} minutes)")
        print("   For testing, you can manually expire the token or wait")
        print("   Simulating refresh anyway...")

    # Start Avito
    print("\n[2] Starting Avito app...")
    await adb.start_avito()
    await asyncio.sleep(5)
    print("✅ Avito started")

    # Simulate user activity
    print("\n[3] Simulating user activity...")
    for i in range(3):
        print(f"   Round {i+1}: Scrolling feed...")
        await adb.swipe(540, 1600, 540, 800, 300)
        await asyncio.sleep(2)

        # Check for token update
        new_session = await adb.get_session()
        if new_session and new_session.expires_at != session.expires_at:
            print(f"✅ Token refreshed!")
            print(f"   Old expiry: {session.expires_at}")
            print(f"   New expiry: {new_session.expires_at}")
            break

    # Stop Avito
    print("\n[4] Stopping Avito...")
    await adb.stop_avito()

    print("\n" + "="*60)
    print("✅ Test complete!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_active_refresh())
EOF

# Запустить тест
python3 test_active_refresh_real.py
```

---

## 📊 Ожидаемый результат

После всех шагов у нас будет:

1. ✅ Установленный Avito APK
2. ✅ Успешная авторизация
3. ✅ Извлеченные данные:
   - Session token (JWT)
   - Fingerprint (header 'f')
   - Device ID, User Hash
   - Refresh token
4. ✅ Протестированный активный refresh
5. ✅ Подтверждение что на x86 все работает

---

## ⚠️ Важные заметки

### Что работает на x86:
- ✅ UI automation
- ✅ Session extraction
- ✅ Active refresh logic
- ✅ Token monitoring

### Что НЕ работает на x86:
- ❌ **Fingerprint генерация** - libfp.so обнаружит x86 CPU
- ❌ **Production использование** - Avito может заблокировать

### Поэтому x86 для:
- ✅ Разработки и отладки
- ✅ Тестирования логики
- ✅ Прототипирования

### Для production:
- 🚀 Миграция на ARM (Hetzner CAX / Oracle Ampere)
- 🚀 Task #6: Тестирование на реальном ARM сервере

---

## 🆘 Если что-то не работает

**APK не устанавливается:**
- Проверь размер файла (должен быть 80-100 MB)
- Проверь что это базовый APK, не XAPK
- Попробуй другой источник (APKMirror или APKPure)

**Авторизация не проходит:**
- Сделай скриншот и посмотри UI
- Используй VNC для ручной авторизации
- Проверь логи: `docker exec redroid-x86-1 logcat | grep -i avito`

**Session не извлекается:**
- Проверь что авторизация завершена
- Проверь путь к SharedPreferences
- Убедись что есть root доступ

---

---

## 📋 Краткий план на ARM

**1. Создать Hetzner CAX11:**
- Цена: €4.49/мес
- 2 ARM cores, 4GB RAM
- Ubuntu 22.04 ARM64

**2. Установка (5-10 минут):**
```bash
# Kernel модули
apt install linux-modules-extra-$(uname -r)
modprobe binder_linux devices=binder,hwbinder,vndbinder
modprobe ashmem_linux

# Docker
apt install docker.io docker-compose-v2

# Загрузить token-farm/
# Запустить: docker-compose up -d
```

**3. Avito APK:**
```bash
# APK готов: /tmp/avito_latest.apk (на старом сервере)
# Или локально: c:/Users/EloWork/Documents/Projects/Reverse/APK/Avito/avito.apk
scp avito.apk root@ARM_SERVER:/tmp/
docker exec redroid-arm-1 pm install -r /tmp/avito.apk
```

**4. Session инжект:**
- Fingerprint готов: `A2.a541fb18def1032c46e8ce9356bf78870fa9c764...`
- Credentials: +79171708077 / Mi31415926pSss!
- Сгенерировать XML и скопировать в SharedPreferences

**5. Тестирование:**
- Запустить Avito
- Проверить token refresh
- Убедиться что fingerprint работает

**Подробный план:** `X86_DEPLOYMENT_SUMMARY.md` (раздел "План действий на будущее")

---

**❗ ВАЖНО:** НЕ ТОРОПИТЬСЯ. У нас нет кучи попыток, аккаунт могут заблокировать.
