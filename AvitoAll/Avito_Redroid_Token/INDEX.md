# Navigation Index - Avito Redroid Token

Быстрая навигация по проекту извлечения токенов Avito.

---

## 📖 Документация

- **[README.md](README.md)** - Полная документация проекта
- **[QUICKSTART.md](QUICKSTART.md)** - Быстрый старт за 5 минут
- **[.gitignore](.gitignore)** - Игнорируемые файлы

---

## 🚀 Quick Start Commands

### Первая установка:
```cmd
cd scripts
01_install_docker.bat
02_start_redroid.bat
03_setup_device.bat
04_install_frida.bat
05_install_avito.bat
REM [Авторизоваться в Avito вручную]
06_extract_tokens.bat
```

### Полная автоматизация:
```cmd
cd scripts
07_full_setup.bat
```

### Повторное извлечение токенов:
```cmd
cd scripts
06_extract_tokens.bat
```

---

## 📁 Структура проекта

```
Avito_Redroid_Token/
│
├── 📄 README.md                      # Полная документация
├── 📄 QUICKSTART.md                  # Быстрый старт
├── 📄 INDEX.md                       # Этот файл (навигация)
├── 📄 docker-compose.yml             # Конфигурация Redroid
├── 📄 .gitignore                     # Игнорируемые файлы
│
├── 📂 scripts/                       # BAT скрипты автоматизации
│   ├── 01_install_docker.bat        # Проверка Docker
│   ├── 02_start_redroid.bat         # Запуск контейнера
│   ├── 03_setup_device.bat          # Маскировка устройства
│   ├── 04_install_frida.bat         # Установка Frida Server
│   ├── 05_install_avito.bat         # Установка Avito APK
│   ├── 06_extract_tokens.bat        # Извлечение токенов
│   └── 07_full_setup.bat            # Полная автоматизация
│
├── 📂 automation/                    # Python скрипты
│   ├── extract_tokens.py            # Парсинг токенов из XML
│   └── check_device.py              # Проверка маскировки
│
├── 📂 frida_scripts/                 # Frida скрипты
│   ├── ssl_unpin.js                 # SSL Certificate Unpinning
│   ├── http_capture.js              # Перехват HTTP запросов
│   └── shared_prefs.js              # Чтение SharedPreferences
│
├── 📂 config/                        # Конфигурационные файлы
│   └── build.prop.pixel6            # Build.prop для Pixel 6
│
└── 📂 output/                        # Извлеченные токены
    └── session_*.json               # Файлы с токенами
```

---

## 🔧 Полезные команды

### Docker

```cmd
# Статус контейнеров
docker ps

# Логи Redroid
docker logs avito-redroid -f

# Остановить Redroid
docker-compose stop

# Запустить Redroid
docker-compose up -d

# Удалить Redroid (с данными)
docker-compose down -v

# Выполнить команду в Redroid
docker exec avito-redroid <command>

# Открыть shell в Redroid
docker exec -it avito-redroid sh
```

### ADB (через Docker)

```cmd
# Проверить модель устройства
docker exec avito-redroid getprop ro.product.model

# Список приложений
docker exec avito-redroid pm list packages

# Запустить Avito
docker exec avito-redroid am start -n com.avito.android/.Launcher

# Остановить Avito
docker exec avito-redroid am force-stop com.avito.android

# Сделать скриншот
docker exec avito-redroid screencap -p /sdcard/screen.png
docker cp avito-redroid:/sdcard/screen.png screen.png
```

### Python

```cmd
# Проверить маскировку устройства
python automation\check_device.py

# Извлечь токены из XML вручную
python automation\extract_tokens.py temp_prefs.xml
```

### Просмотр экрана

```cmd
# Вариант 1: scrcpy (рекомендуется)
scrcpy -s 127.0.0.1:5555

# Вариант 2: VNC Viewer
# Подключиться к vnc://127.0.0.1:5900
```

---

## 📊 Проверка состояния

### Проверить Docker:
```cmd
docker --version
docker ps
```

### Проверить Redroid:
```cmd
docker exec avito-redroid getprop sys.boot_completed
# Должно вернуть: 1
```

### Проверить маскировку:
```cmd
python automation\check_device.py
# Должно показать: Pixel 6
```

### Проверить Avito:
```cmd
docker exec avito-redroid pm list packages | findstr avito
# Должно вернуть: package:com.avito.android
```

### Проверить Frida:
```cmd
docker exec avito-redroid ps | findstr frida
# Должно показать процесс frida-server
```

### Проверить токены:
```cmd
dir output
type output\session_*.json
```

---

## 🐛 Troubleshooting

### Docker не запускается
→ См. [QUICKSTART.md](QUICKSTART.md#docker-не-запускается)

### Redroid не стартует
→ См. [QUICKSTART.md](QUICKSTART.md#redroid-не-стартует)

### Не могу подключиться к scrcpy
→ См. [QUICKSTART.md](QUICKSTART.md#не-могу-подключиться-к-scrcpy)

### SharedPreferences пустой
→ См. [QUICKSTART.md](QUICKSTART.md#sharedpreferences-пустой)

### Полный список проблем
→ См. [README.md](README.md#troubleshooting) и [QUICKSTART.md](QUICKSTART.md#troubleshooting)

---

## 🔗 Ссылки

### Внутренние:
- [README.md](README.md) - Полная документация
- [QUICKSTART.md](QUICKSTART.md) - Быстрый старт
- [../Avito_Token_SRV.md](../Avito_Token_SRV.md) - Production развертывание

### Внешние:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Redroid GitHub](https://github.com/remote-android/redroid-doc)
- [Frida Documentation](https://frida.re/docs/home/)
- [scrcpy](https://github.com/Genymobile/scrcpy)
- [APKPure - Avito](https://apkpure.com/avito/com.avito.android)

---

## 📝 Примеры использования

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

print(response.json())
```

### Обновление токена:

```python
def refresh_token(refresh_token):
    url = 'https://api.avito.ru/auth/v1/refresh'
    headers = {
        'Authorization': f'Bearer {refresh_token}',
        'User-Agent': 'Avito/13.28.1 (Android 13; Pixel 6)'
    }
    response = requests.post(url, headers=headers)
    return response.json()

# Использование
new_tokens = refresh_token(session['refresh_token'])
```

---

## 📈 Следующие шаги

1. ✅ **Установка** - Выполните Quick Start
2. ✅ **Извлечение** - Получите первые токены
3. 📝 **Интеграция** - Используйте токены в своем коде
4. 🔄 **Автоматизация** - Настройте автообновление
5. 🚀 **Production** - Разверните на сервере

---

**Время на полную установку: ~10 минут**

**Время на извлечение токенов: ~2 минуты**

---

**Создано с ❤️ и Claude Code**
