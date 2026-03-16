# 📑 Навигация по Studio_Token

Быстрый доступ ко всем файлам и инструкциям.

---

## 📚 Документация

| Файл | Описание | Время чтения |
|------|----------|--------------|
| **README.md** | Полная инструкция со всеми деталями | 15 минут |
| **QUICK_START.md** | Быстрый старт за 5 минут | 2 минуты |
| **INDEX.md** | Этот файл - навигация | 1 минута |

---

## 🔧 BAT Скрипты (scripts/)

Запускать по порядку:

| Скрипт | Назначение | Время выполнения |
|--------|-----------|------------------|
| **01_check_environment.bat** | Проверка Python, Frida, ADB, Android SDK | 30 сек |
| **02_start_emulator.bat** | Запуск эмулятора avito_token_emulator | 2-3 минуты |
| **03_mask_device.bat** | Маскировка под Pixel 6 (КРИТИЧНО!) | 30 сек |
| **04_install_frida.bat** | Установка Frida Server на эмулятор | 1 минута |
| **05_install_avito.bat** | Установка Avito APK | 30 сек |
| **06_extract_tokens.bat** | Извлечение токенов в JSON | 1 минута |
| **07_auto_refresh.bat** | Автообновление токенов (daemon) | Постоянно |

---

## 🐍 Python Утилиты

| Файл | Назначение | Использование |
|------|-----------|---------------|
| **check_token_status.py** | Проверить статус токенов (expires_at) | `python check_token_status.py` |
| **check_device_info.py** | Проверить Build properties устройства | `python check_device_info.py` |

---

## 🎣 Frida Скрипты (frida_scripts/)

| Скрипт | Назначение |
|--------|-----------|
| **ssl_unpin.js** | SSL Unpinning для перехвата HTTPS |
| **http_capture.js** | Захват HTTP заголовков (токены, fingerprint) |
| **shared_prefs.js** | Мониторинг SharedPreferences (где хранятся токены) |

**Использование:**
```cmd
frida -U -f com.avito.android -l frida_scripts/ssl_unpin.js --no-pause
```

---

## 📁 Папки результатов

| Папка | Содержимое |
|-------|-----------|
| **output/** | Извлеченные токены (session_YYYYMMDD_HHMMSS.json) |
| **logs/** | Логи Token Manager (token_manager_YYYYMMDD.log) |

---

## ⚡ Быстрые команды

### Первый запуск (полная настройка):

```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token\scripts

01_check_environment.bat
REM Создать AVD через Android Studio GUI
02_start_emulator.bat
03_mask_device.bat
04_install_frida.bat
05_install_avito.bat
REM Авторизоваться в Avito вручную на эмуляторе
06_extract_tokens.bat
```

**Время: ~20 минут**

---

### Повторное извлечение токенов:

```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token\scripts

02_start_emulator.bat
06_extract_tokens.bat
```

**Время: ~2 минуты**

---

### Проверить статус текущих токенов:

```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token

python check_token_status.py
```

Покажет:
- Время до истечения
- Статус (valid / expiring / expired)
- Рекомендации по действиям

---

### Запустить автообновление:

```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token\scripts

07_auto_refresh.bat
```

Токены будут обновляться автоматически каждый час.

---

## 🎯 Типичные сценарии использования

### Сценарий 1: Извлечь токены для разработки

1. Запустить эмулятор: `02_start_emulator.bat`
2. Извлечь токены: `06_extract_tokens.bat`
3. Использовать файл из `output/` в коде

---

### Сценарий 2: Настроить автообновление для production

1. Выполнить полную настройку (см. выше)
2. Запустить daemon: `07_auto_refresh.bat`
3. Токены обновляются автоматически

---

### Сценарий 3: Проверить почему токен не работает

1. Проверить статус: `python check_token_status.py`
2. Если EXPIRED - извлечь новый: `06_extract_tokens.bat`
3. Проверить маскировку: `python check_device_info.py`

---

## 📖 Дополнительные материалы

### В этой папке:
- README.md - Полная документация
- QUICK_START.md - Быстрый старт

### В родительских папках:
- **../x86_test/QUICKSTART.md** - Тестирование эмулятора
- **../x86_test/README.md** - Полная документация эмулятора
- **../Avito_Token_SRV.md** - Docker архитектура для 1000+ клиентов

---

## ❓ Решение проблем

| Проблема | Решение |
|----------|---------|
| "adb: device unauthorized" | `adb kill-server && adb start-server` |
| "adb root" не работает | Использовать Google APIs image (не Play Store) |
| SharedPreferences пустой | Убедиться что Avito авторизован |
| Avito детектит эмулятор | Запустить `03_mask_device.bat` |
| Токен expired | Извлечь новый: `06_extract_tokens.bat` |

Подробное решение проблем: **README.md** раздел "Решение проблем"

---

## 🔗 Быстрые ссылки

- [Python скачать](https://www.python.org/)
- [Android Studio скачать](https://developer.android.com/studio)
- [Frida релизы](https://github.com/frida/frida/releases)
- [Avito API документация](../API_FINAL.md)

---

**Начните с README.md для полной инструкции!**

---

*Последнее обновление: 2026-01-26*
