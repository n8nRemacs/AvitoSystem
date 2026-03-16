# Avito Token Extraction with Redroid

Система автоматического извлечения токенов Avito с использованием Redroid (Android в Docker контейнере).

## ⚠️ КРИТИЧНО: Синхронизация времени

**Неправильное время вызывает блокировку при входе и обновлении токенов!**

```bash
# Сервер - установить Moscow timezone
timedatectl set-timezone Europe/Moscow

# Android - синхронизировать часовой пояс
adb shell service call alarm 3 s16 Europe/Moscow
adb shell setprop persist.sys.timezone Europe/Moscow

# Проверка (время должно совпадать!)
date && adb shell date
```

---

## Почему Redroid?

### Преимущества перед эмулятором:
- ✅ **Нативная маскировка**: Build.prop меняется навсегда, не нужен Frida для подмены
- ✅ **Нет детектов эмулятора**: Redroid - это контейнер, а не emulator
- ✅ **Root доступ**: Полный контроль над системой
- ✅ **Производительность**: x86_64 native, быстрый запуск (~10 сек)
- ✅ **Масштабируемость**: Легко запустить 10-100 экземпляров

---

## Быстрый старт

### 1. Установить Docker Desktop
```cmd
scripts\01_install_docker.bat
```

### 2. Запустить Redroid контейнер
```cmd
scripts\02_start_redroid.bat
```

### 3. Настроить устройство как Pixel 6
```cmd
scripts\03_setup_device.bat
```

### 4. Установить Avito
```cmd
scripts\05_install_avito.bat
```

### 5. Извлечь токены
```cmd
scripts\06_extract_tokens.bat
```

---

## Структура проекта

```
Avito_Redroid_Token/
├── docker-compose.yml           # Конфигурация Redroid
├── Dockerfile                   # Кастомный образ
├── scripts/
│   ├── 01_install_docker.bat    # Проверка Docker Desktop
│   ├── 02_start_redroid.bat     # Запуск контейнера
│   ├── 03_setup_device.bat      # Маскировка под Pixel 6
│   ├── 04_install_frida.bat     # Frida Server
│   ├── 05_install_avito.bat     # Установка APK
│   ├── 06_extract_tokens.bat    # Извлечение токенов
│   └── 07_full_setup.bat        # Полная автоматизация
├── frida_scripts/
│   ├── http_capture.js          # Перехват HTTP
│   ├── shared_prefs.js          # Чтение SharedPreferences
│   └── ssl_unpin.js             # SSL Unpinning
├── automation/
│   ├── extract_tokens.py        # Извлечение токенов
│   └── check_device.py          # Проверка маскировки
└── output/
    └── session_*.json           # Извлеченные токены
```

---

## Требования

### Системные требования:
- **OS**: Windows 10/11 Pro или Enterprise (для Hyper-V)
- **RAM**: Минимум 8 GB (рекомендуется 16 GB)
- **CPU**: 4 ядра (рекомендуется 6+)
- **Disk**: 20 GB свободного места

### Software:
- Docker Desktop for Windows
- Python 3.9+
- ADB (Android Debug Bridge)

---

## Детальная инструкция

### Шаг 1: Установка Docker Desktop

1. Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Установите с настройками по умолчанию
3. Включите WSL 2 backend (рекомендуется)
4. Перезагрузите компьютер

**Проверка:**
```cmd
docker --version
docker-compose --version
```

### Шаг 2: Запуск Redroid

**Автоматически:**
```cmd
scripts\02_start_redroid.bat
```

**Вручную:**
```cmd
docker-compose up -d
```

Redroid запустится с:
- Android 13 (API 33)
- ADB на порту 5555
- GPU rendering
- Root доступ

**Проверка:**
```cmd
adb connect 127.0.0.1:5555
adb devices
```

Должно показать:
```
127.0.0.1:5555  device
```

### Шаг 3: Маскировка под Google Pixel 6

Скрипт автоматически изменит `build.prop`:

```cmd
scripts\03_setup_device.bat
```

**Что меняется:**
```properties
ro.product.model=Pixel 6
ro.product.manufacturer=Google
ro.product.brand=google
ro.product.device=oriole
ro.product.name=oriole
ro.build.fingerprint=google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys
```

**Проверка:**
```cmd
adb shell getprop ro.product.model
# Должно вернуть: Pixel 6
```

### Шаг 4: Установка Frida Server

```cmd
scripts\04_install_frida.bat
```

Frida нужен только для извлечения токенов, НЕ для маскировки устройства.

**Проверка:**
```cmd
frida-ps -H 127.0.0.1:5555
```

### Шаг 5: Установка Avito APK

Поместите `avito.apk` в корень папки `Avito_Redroid_Token/`, затем:

```cmd
scripts\05_install_avito.bat
```

**Или скачайте вручную:**
1. Откройте: https://apkpure.com/avito/com.avito.android
2. Скачайте последнюю версию (~200 MB)
3. Сохраните как: `Avito_Redroid_Token\avito.apk`

### Шаг 6: Авторизация в Avito

**ВАЖНО: Выполняется ВРУЧНУЮ**

1. Откройте scrcpy для просмотра экрана:
   ```cmd
   scrcpy -s 127.0.0.1:5555
   ```

2. Или используйте VNC: `vnc://127.0.0.1:5900`

3. Откройте Avito на устройстве

4. Авторизуйтесь:
   - Введите номер телефона
   - Введите SMS код
   - Дождитесь входа в аккаунт

5. Откройте вкладку "Сообщения" (чтобы токены сохранились)

### Шаг 7: Извлечение токенов

После авторизации:

```cmd
scripts\06_extract_tokens.bat
```

Токены будут сохранены в `output\session_YYYYMMDD_HHMMSS.json`

**Формат:**
```json
{
  "session_token": "eyJhbGci...",
  "refresh_token": "b026b73d...",
  "fingerprint": "A2.588e8ee...",
  "device_id": "050825b7f6c5255f",
  "user_id": 157920214,
  "expires_at": 1769524040,
  "extracted_at": 1769437881,
  "device_info": {
    "model": "Pixel 6",
    "manufacturer": "Google",
    "brand": "google"
  }
}
```

---

## Полная автоматизация

Все шаги одной командой:

```cmd
scripts\07_full_setup.bat
```

Скрипт выполнит:
1. ✅ Проверку Docker
2. ✅ Запуск Redroid
3. ✅ Настройку устройства
4. ✅ Установку Frida
5. ✅ Установку Avito
6. ⚠️ Остановится для ручной авторизации
7. ✅ Извлечение токенов

---

## Использование токенов

### Python пример:

```python
import json
import requests

# Загрузить токены
with open('output/session_20260126_210000.json', 'r') as f:
    session = json.load(f)

# API запрос
headers = {
    'X-Session': session['session_token'],
    'f': session['fingerprint'],
    'User-Agent': 'Avito/13.28.1 (Android 13; Pixel 6)'
}

response = requests.get(
    'https://api.avito.ru/messenger/v3/channels',
    headers=headers
)

print(response.json())
```

### Обновление токена:

```python
import requests

refresh_url = 'https://api.avito.ru/auth/v1/refresh'
headers = {
    'Authorization': f'Bearer {session["refresh_token"]}',
    'User-Agent': 'Avito/13.28.1 (Android 13; Pixel 6)'
}

response = requests.post(refresh_url, headers=headers)
new_session = response.json()
```

---

## Масштабирование (ферма токенов)

Для запуска нескольких экземпляров используйте `docker-compose.scale.yml`:

```cmd
docker-compose -f docker-compose.scale.yml up -d --scale avito-redroid=5
```

Это создаст 5 независимых Android устройств на портах:
- 5555, 5556, 5557, 5558, 5559

Каждое устройство:
- Независимая авторизация
- Свои токены
- Свой device_id

---

## Troubleshooting

### Docker не запускается

**Проблема:** Docker Desktop не стартует

**Решение:**
1. Включите Virtualization в BIOS
2. Включите Hyper-V в Windows Features
3. Включите WSL 2:
   ```cmd
   wsl --install
   wsl --set-default-version 2
   ```

### ADB не подключается

**Проблема:** `adb connect 127.0.0.1:5555` зависает

**Решение:**
```cmd
adb kill-server
adb start-server
adb connect 127.0.0.1:5555
```

### Redroid не стартует

**Проблема:** Container exits immediately

**Решение:**
```cmd
docker logs avito-redroid
docker-compose down -v
docker-compose up -d
```

### Avito показывает "sdk_gphone"

**Проблема:** Устройство не замаскировано

**Решение:**
1. Проверьте build.prop:
   ```cmd
   adb shell cat /system/build.prop | grep ro.product.model
   ```

2. Если неправильно, пересоздайте контейнер:
   ```cmd
   docker-compose down -v
   scripts\03_setup_device.bat
   ```

### Токены не извлекаются

**Проблема:** SharedPreferences пустой

**Решение:**
1. Убедитесь что авторизовались в Avito
2. Откройте вкладку "Сообщения" в приложении
3. Подождите 30 секунд
4. Повторите извлечение

---

## Production deployment

Для продакшн развертывания на VPS:

1. **Ubuntu 20.04+ сервер** с Docker
2. **Systemd service** для автозапуска
3. **Nginx reverse proxy** для API
4. **Supervisor** для управления процессами
5. **Monitoring** (Prometheus + Grafana)

См. `Avito_Token_SRV.md` для детальной инструкции.

---

## Безопасность

### Рекомендации:

1. **Храните токены в безопасности**
   - Используйте environment variables
   - Никогда не коммитьте в Git
   - Шифруйте на диске

2. **Ротация токенов**
   - Обновляйте через refresh_token каждые 24 часа
   - Следите за expires_at

3. **Rate limiting**
   - Не делайте слишком много запросов
   - Используйте задержки между операциями

4. **User-Agent**
   - Используйте актуальную версию Avito
   - Меняйте периодически

---

## Контакты и поддержка

- **Issues**: GitHub Issues
- **Документация**: README.md, QUICKSTART.md
- **Примеры**: automation/ папка

---

## License

MIT License - используйте свободно

---

**Создано с ❤️ и Claude Code**
