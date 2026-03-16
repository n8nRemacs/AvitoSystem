# 🔐 Avito Token Manager для Android Studio

Полный набор инструментов для извлечения и автоматического обновления токенов Avito через Android Studio эмулятор.

---

## 📁 Структура папки

```
Studio_Token/
├── README.md                    # Этот файл - главная инструкция
├── QUICK_START.md               # Быстрый старт за 5 минут
│
├── scripts/                     # BAT скрипты для автоматизации
│   ├── 01_check_environment.bat # Проверка окружения
│   ├── 02_start_emulator.bat    # Запуск эмулятора
│   ├── 03_mask_device.bat       # Маскировка под Pixel 6
│   ├── 04_install_frida.bat     # Установка Frida Server
│   ├── 05_install_avito.bat     # Установка Avito APK
│   ├── 06_extract_tokens.bat    # Извлечение токенов
│   └── 07_auto_refresh.bat      # Автообновление токенов
│
├── frida_scripts/               # Frida скрипты для hooking
│   ├── ssl_unpin.js             # SSL Unpinning
│   ├── http_capture.js          # Захват HTTP заголовков
│   └── shared_prefs.js          # Чтение SharedPreferences
│
├── output/                      # Результаты извлечения
│   └── session_YYYYMMDD_HHMMSS.json
│
└── logs/                        # Логи работы
    └── token_manager_YYYYMMDD.log
```

---

## 🎯 Назначение

Эта папка содержит **всё необходимое** для работы с токенами Avito:

1. **Извлечение токенов** из авторизованного Avito на эмуляторе
2. **Маскировка устройства** (эмулятор выдает себя за Google Pixel 6)
3. **Автоматическое обновление** токенов через refresh_token
4. **Мониторинг expires_at** и своевременное обновление

---

## ⚡ Быстрый старт (15 минут)

### Предварительные требования

- ✅ Windows 10/11
- ✅ Android Studio установлена
- ✅ Python 3.8+
- ✅ 8GB RAM минимум

### Шаг 1: Проверка окружения

```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token\scripts
01_check_environment.bat
```

### Шаг 2: Создать эмулятор (первый раз)

**Через Android Studio:**
1. Tools → Device Manager → Create Device
2. Device: **Pixel 6**
3. System Image: **Android 13 (API 33), Google APIs** (БЕЗ Play Store!)
4. RAM: 4096 MB, CPU cores: 4
5. Имя: **avito_token_emulator**

### Шаг 3: Запустить эмулятор

```cmd
02_start_emulator.bat
```

Или через Android Studio: Device Manager → avito_token_emulator → ▶️

### Шаг 4: Маскировка (КРИТИЧНО!)

```cmd
03_mask_device.bat
```

Проверит что устройство определяется как "Google Pixel 6".

### Шаг 5: Установить компоненты

```cmd
04_install_frida.bat
05_install_avito.bat
```

### Шаг 6: Авторизоваться в Avito

**ВРУЧНУЮ на эмуляторе:**
1. Открыть Avito
2. Войти (номер телефона + SMS код)
3. Открыть вкладку "Сообщения"

### Шаг 7: Извлечь токены

```cmd
06_extract_tokens.bat
```

**Результат:** `output/session_YYYYMMDD_HHMMSS.json`

### Шаг 8: Автообновление (опционально)

```cmd
07_auto_refresh.bat
```

Токены будут автоматически обновляться каждый час.

---

## 📋 Детальные инструкции

### 1️⃣ Извлечение токенов

После авторизации в Avito на эмуляторе:

```cmd
cd scripts
06_extract_tokens.bat
```

**Что происходит:**
1. ADB подключается к эмулятору
2. Читает файл SharedPreferences Avito
3. Парсит XML → JSON
4. Сохраняет в `output/session_[timestamp].json`

**Результат:**
```json
{
  "session_token": "eyJhbGciOiJIUzUxMiI...",
  "refresh_token": "b026b73d60740b09...",
  "fingerprint": "A2.588e8ee124a2440b...",
  "device_id": "050825b7f6c5255f",
  "remote_device_id": "iv3ik96QMap8lCj_...",
  "user_id": 157920214,
  "user_hash": "9b82afc1ab1e2419...",
  "expires_at": 1769524040,
  "extracted_at": 1769437881
}
```

---

### 2️⃣ Автоматическое обновление токенов

**Запуск в фоновом режиме:**

```cmd
07_auto_refresh.bat
```

**Что делает:**
1. Проверяет `expires_at` каждые 60 минут
2. Если осталось < 2 часов:
   - Обновляет через `refresh_token`
   - Сохраняет новый `session_token`
   - Логирует в `logs/token_manager_[date].log`

**Настройки (в 07_auto_refresh.bat):**
```bat
SET CHECK_INTERVAL=3600      REM Проверять каждый час
SET REFRESH_THRESHOLD=7200   REM Обновлять за 2 часа до истечения
```

---

### 3️⃣ Маскировка устройства

**Зачем:**
Avito детектит эмулятор по Build properties. Без маскировки:
- ❌ Avito видит: "Google sdk_gphone64_x86_64"
- ❌ Уведомление: "Подозрительный вход с нового устройства"

**С маскировкой:**
- ✅ Avito видит: "Google Pixel 6"
- ✅ Уведомление: "Вход с устройства Google Pixel 6"

**Применить:**
```cmd
03_mask_device.bat
```

**Проверить:**
```cmd
adb shell "getprop ro.product.model"
```
Должно вывести: **Pixel 6**

---

### 4️⃣ Использование токенов в коде

**Python пример:**

```python
import json
import requests

# Загрузить последнюю сессию
with open('../output/session_20260126_083000.json', 'r') as f:
    session = json.load(f)

# Заголовки для API запросов
headers = {
    "X-Session": session['session_token'],
    "f": session['fingerprint'],
    "X-DeviceId": session['device_id'],
    "User-Agent": "Avito/13.28.1 (Android 13; Pixel 6)"
}

# Пример: Получить список чатов
response = requests.get(
    "https://api.avito.ru/messenger/v3/channels",
    headers=headers
)

if response.status_code == 200:
    chats = response.json()['channels']
    print(f"Найдено чатов: {len(chats)}")
else:
    print(f"Ошибка: {response.status_code}")
```

---

## 🔧 Настройка и конфигурация

### Изменить имя эмулятора

В файле `scripts/02_start_emulator.bat`:

```bat
SET AVD_NAME=avito_token_emulator
```

Замените на имя вашего AVD.

### Изменить интервал обновления

В файле `scripts/07_auto_refresh.bat`:

```bat
SET CHECK_INTERVAL=3600      REM 1 час = 3600 секунд
SET REFRESH_THRESHOLD=7200   REM 2 часа = 7200 секунд
```

### Путь к Avito APK

В файле `scripts/05_install_avito.bat`:

```bat
SET AVITO_APK=..\avito.apk
```

Укажите путь к вашему APK файлу.

---

## 📊 Мониторинг и логи

### Просмотр логов

```cmd
cd logs
notepad token_manager_20260126.log
```

**Пример лога:**
```
2026-01-26 08:30:00 [INFO] Token Manager started
2026-01-26 08:30:00 [INFO] Checking token expiration...
2026-01-26 08:30:01 [INFO] Token expires in 23.5 hours
2026-01-26 08:30:01 [INFO] Token is fresh, no refresh needed
2026-01-26 09:30:00 [INFO] Checking token expiration...
2026-01-26 09:30:01 [WARNING] Token expires in 1.8 hours!
2026-01-26 09:30:01 [INFO] Starting token refresh...
2026-01-26 09:30:05 [INFO] Token refreshed successfully
2026-01-26 09:30:05 [INFO] New expires_at: 2026-01-27 09:30
```

### Проверить статус токена

```cmd
cd ..
python check_token_status.py
```

Покажет:
- Текущий session_token
- Время до истечения
- Статус (fresh / expiring / expired)

---

## 🚨 Решение проблем

### Проблема: "adb: device unauthorized"

**Решение:**
```cmd
adb kill-server
adb start-server
adb devices
```

На эмуляторе появится окно - нажмите "Always allow from this computer".

---

### Проблема: "adb root" не работает

**Причина:** Используется system image с Play Store (нет root).

**Решение:**
1. Удалить текущий AVD
2. Создать новый с **Google APIs** (БЕЗ Play Store!)
3. System Image: `android-33;google_apis;x86_64`

---

### Проблема: SharedPreferences пустой

**Решение:**
```cmd
# Запустить Avito
adb shell "am start -n com.avito.android/.Launcher"

# Подождать 30 секунд (Avito должен загрузиться полностью)

# Проверить что Avito запущен
adb shell "ps | grep avito"

# Попробовать извлечь снова
06_extract_tokens.bat
```

---

### Проблема: Avito все равно детектит эмулятор

**Возможные причины:**
1. GPS координаты (0.0, 0.0)
2. Отсутствие сенсоров
3. Network settings

**Решение:**
1. Применить маскировку: `03_mask_device.bat`
2. Использовать Frida для подмены GPS:
   ```cmd
   frida -U -f com.avito.android -l frida_scripts/gps_mock.js
   ```

---

### Проблема: refresh_token не работает

**Причина:** Токен истёк более 30 дней назад.

**Решение:**
Нужна новая авторизация:
1. Открыть Avito на эмуляторе
2. Выйти из аккаунта
3. Войти заново (номер + SMS код)
4. Извлечь токены: `06_extract_tokens.bat`

---

## 🔄 Workflow для production

### Вариант 1: Локальное обновление

```cmd
# Запустить автообновление в фоне
start /B 07_auto_refresh.bat

# Token Manager работает постоянно
# Токены обновляются автоматически каждые 24 часа
# Файлы сохраняются в output/
```

### Вариант 2: Централизованный сервер

```cmd
# На сервере запустить HTTP API
cd ..
python avito_session_server.py --port 8080

# Токены отправляются на сервер автоматически
# Другие приложения получают токены через API
```

---

## 📚 Дополнительные материалы

### Файлы в этой папке:

- **README.md** - Этот файл (полная инструкция)
- **QUICK_START.md** - Быстрый старт за 5 минут
- **scripts/** - Все BAT скрипты для автоматизации
- **frida_scripts/** - Frida скрипты для hooking
- **output/** - Извлеченные токены (JSON)
- **logs/** - Логи работы Token Manager

### Ссылки на дополнительную документацию:

- **../x86_test/QUICKSTART.md** - Детальное тестирование
- **../x86_test/README.md** - Полная документация эмулятора
- **../Avito_Token_SRV.md** - Docker архитектура для 1000+ клиентов

---

## 🎯 Краткий чеклист

- [ ] Python 3.8+ установлен
- [ ] Android Studio установлена
- [ ] AVD создан (Pixel 6, API 33, Google APIs)
- [ ] Эмулятор запущен
- [ ] `adb root` работает
- [ ] Маскировка применена (`03_mask_device.bat`)
- [ ] Frida Server установлен
- [ ] Avito APK установлен
- [ ] Авторизация в Avito выполнена
- [ ] Токены извлечены (`06_extract_tokens.bat`)
- [ ] Автообновление настроено (`07_auto_refresh.bat`)

---

## ⏱️ Время выполнения

**Первый раз (с настройкой):** ~20 минут
- Создание AVD: 5 минут
- Запуск эмулятора: 3 минуты
- Маскировка + установка: 5 минут
- Авторизация: 3 минуты
- Извлечение токенов: 2 минуты
- Настройка автообновления: 2 минуты

**Повторное извлечение:** ~2 минуты
- Запустить эмулятор: 30 секунд
- Извлечь токены: 30 секунд
- Проверить результат: 30 секунд

---

## 📞 Поддержка

Если возникли проблемы:
1. Проверьте логи в `logs/`
2. Посмотрите раздел "Решение проблем" выше
3. Изучите полную документацию в `../x86_test/README.md`

---

**🚀 Начните с `scripts/01_check_environment.bat` прямо сейчас!**

---

*Версия: 1.0*
*Дата: 2026-01-26*
*Автор: Claude Code*
