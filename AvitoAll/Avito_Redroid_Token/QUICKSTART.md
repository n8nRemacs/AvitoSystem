# Quick Start Guide - Avito Redroid Token Extraction

Быстрый запуск системы извлечения токенов Avito на базе Redroid.

---

## 5-минутная установка

### Шаг 1: Установите Docker Desktop

Скачайте и установите: https://www.docker.com/products/docker-desktop/

**Важно**: Включите WSL 2 backend во время установки.

### Шаг 2: Запустите все скрипты по порядку

Откройте командную строку в папке `Avito_Redroid_Token` и выполните:

```cmd
cd scripts

REM 1. Проверка Docker (1 минута)
01_install_docker.bat

REM 2. Запуск Redroid (2-3 минуты при первом запуске)
02_start_redroid.bat

REM 3. Настройка устройства как Pixel 6 (30 секунд)
03_setup_device.bat

REM 4. Установка Frida Server (1 минута)
04_install_frida.bat

REM 5. Установка Avito APK (1 минута)
05_install_avito.bat
```

### Шаг 3: Авторизуйтесь в Avito

**ВАЖНО: Этот шаг делается ВРУЧНУЮ**

1. Установите scrcpy для просмотра экрана Android:
   ```cmd
   winget install scrcpy
   ```

2. Подключитесь к Redroid:
   ```cmd
   scrcpy --serial 127.0.0.1:5555
   ```

3. В окне Avito:
   - Введите номер телефона
   - Введите код из SMS
   - Дождитесь входа
   - Откройте вкладку "Сообщения"

### Шаг 4: Извлеките токены

После успешной авторизации:

```cmd
REM 6. Извлечение токенов (10 секунд)
06_extract_tokens.bat
```

Токены будут сохранены в `output\session_YYYYMMDD_HHMMSS.json`

---

## Что дальше?

### Использование токенов в Python:

```python
import json
import requests

# Загрузить токены
with open('output/session_20260126_120000.json') as f:
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

chats = response.json()
print(f"Found {len(chats)} chats")
```

### Автоматическое обновление токенов:

```python
def refresh_token(refresh_token):
    """Обновить session_token через refresh_token"""
    url = 'https://api.avito.ru/auth/v1/refresh'
    headers = {
        'Authorization': f'Bearer {refresh_token}',
        'User-Agent': 'Avito/13.28.1 (Android 13; Pixel 6)'
    }

    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to refresh: {response.text}")

# Использование
new_tokens = refresh_token(session['refresh_token'])
session['session_token'] = new_tokens['access_token']
```

---

## Повторное извлечение токенов

Когда токены истекут (обычно через 30 дней):

```cmd
cd scripts

REM Запустить Redroid если остановлен
02_start_redroid.bat

REM Извлечь токены (если уже авторизованы)
06_extract_tokens.bat
```

Если нужна новая авторизация:

1. Запустите Avito: `docker exec avito-redroid am start -n com.avito.android/.Launcher`
2. Откройте scrcpy: `scrcpy -s 127.0.0.1:5555`
3. Авторизуйтесь заново
4. Запустите `06_extract_tokens.bat`

---

## Проверка состояния

### Проверить что Redroid работает:

```cmd
docker ps
```

Должен быть `avito-redroid` со статусом `Up`

### Проверить маскировку устройства:

```cmd
python automation\check_device.py
```

Должно показать:
```
Model: Pixel 6
Manufacturer: Google
Brand: google
Device: oriole
```

### Проверить что Avito установлен:

```cmd
docker exec avito-redroid pm list packages | findstr avito
```

Должно вернуть: `package:com.avito.android`

### Проверить токены:

```cmd
dir output
```

Должны быть файлы `session_*.json`

---

## Остановка и удаление

### Остановить Redroid (сохранить данные):

```cmd
docker-compose stop
```

### Удалить Redroid (удалить все данные):

```cmd
docker-compose down -v
```

### Запустить заново:

```cmd
scripts\02_start_redroid.bat
```

Данные авторизации сохраняются в Docker volume, поэтому после перезапуска не нужно авторизовываться заново (если не удалили volume с `-v`).

---

## Troubleshooting

### Docker не запускается

**Проблема**: `Cannot connect to Docker daemon`

**Решение**:
1. Запустите Docker Desktop из меню Пуск
2. Дождитесь зеленого значка в трее
3. Повторите команду

### Redroid не стартует

**Проблема**: Container exits immediately

**Решение**:
```cmd
docker logs avito-redroid
docker-compose down -v
docker-compose up -d
```

### Не могу подключиться к scrcpy

**Проблема**: `scrcpy: error: Could not connect to...`

**Решение**:
```cmd
REM Перезапустить ADB сервер
adb kill-server
adb start-server

REM Подключиться к Redroid
adb connect 127.0.0.1:5555

REM Проверить
adb devices

REM Запустить scrcpy
scrcpy -s 127.0.0.1:5555
```

### SharedPreferences пустой

**Проблема**: `Cannot read SharedPreferences` или `SharedPreferences is empty`

**Решение**:
1. Убедитесь что авторизованы в Avito
2. Откройте вкладку "Сообщения"
3. Подождите 30-60 секунд
4. Повторите `06_extract_tokens.bat`

---

## Полезные команды

### Посмотреть логи Redroid:

```cmd
docker logs avito-redroid -f
```

### Выполнить команду в Redroid:

```cmd
docker exec avito-redroid <command>
```

Примеры:
```cmd
REM Проверить модель устройства
docker exec avito-redroid getprop ro.product.model

REM Список установленных приложений
docker exec avito-redroid pm list packages

REM Запустить Avito
docker exec avito-redroid am start -n com.avito.android/.Launcher

REM Сделать скриншот
docker exec avito-redroid screencap -p /sdcard/screen.png
docker cp avito-redroid:/sdcard/screen.png .
```

### Открыть shell в контейнере:

```cmd
docker exec -it avito-redroid sh
```

---

## Дальнейшие шаги

1. **Автоматизация**: См. `automation/` для Python скриптов
2. **API примеры**: См. README.md раздел "Использование токенов"
3. **Масштабирование**: См. README.md раздел "Масштабирование (ферма токенов)"
4. **Production**: См. `Avito_Token_SRV.md` для развертывания на сервере

---

**Время на полную установку: ~10 минут**

**Время на извлечение токенов (после установки): ~2 минуты**
