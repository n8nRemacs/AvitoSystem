# Token Farm x86 - Development/Testing Version

Версия Token Farm для тестирования на x86/x64 серверах и локальных машинах.

## ⚠️ Важно

**Эта версия НЕ подходит для production!**

Avito `libfp.so` **обнаружит эмулятор** на x86 архитектуре, даже с правильными build properties.

### Для чего эта версия:

✅ **Локальная разработка и отладка**
- Тестирование логики активного refresh
- Отладка ADBController и UI automation
- Проверка парсера SharedPreferences
- Разработка scheduler логики

✅ **Быстрое прототипирование**
- Запуск на обычном ПК/ноутбуке
- Быстрый старт контейнеров (секунды вместо минут)
- Легкий доступ к ADB для отладки

✅ **Обучение и демонстрация**
- Показ архитектуры системы
- Демонстрация работы с несколькими контейнерами

❌ **НЕ для production:**
- libfp.so обнаружит x86 CPU
- Авито заблокирует аккаунты при попытке использования
- Fingerprint генерация не будет валидной

---

## Отличия от ARM версии

| Параметр | ARM (production) | x86 (dev) |
|----------|------------------|-----------|
| Platform | `linux/arm64` | host (x86_64) |
| CPU detection | Проходит ✅ | Не проходит ❌ |
| Build properties | Критичны | Необязательны |
| Скорость запуска | ~60 сек | ~10 сек |
| Anti-emulator bypass | Работает | Не работает |
| Для чего | Production | Development |

---

## Быстрый старт

### 1. Установка

```bash
cd token-farm-x86

# Создать .env файл
cp .env.example .env

# Отредактировать настройки
nano .env
```

### 2. Запуск

```bash
# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs -f
```

### 3. Подключение по ADB

```bash
# Контейнер 1
adb connect localhost:5555

# Контейнер 2
adb connect localhost:5556

# Проверка
adb devices
```

### 4. Тестирование

```bash
# Запустить тесты парсера
python -m pytest test_avito_prefs_parser.py -v

# Тестовый refresh (симуляция)
python test_active_refresh.py
```

---

## Структура

```
token-farm-x86/
├── docker-compose.yml       # x86 конфигурация (без platform: arm64)
├── .env.example             # Шаблон переменных окружения
├── scripts/
│   └── cleanup_emulator.sh  # Init скрипт (опционален для x86)
├── avito_prefs_parser.py    # Парсер SharedPreferences (идентичен ARM)
├── active_refresh.py        # Активное обновление (идентично ARM)
├── farm_manager.py          # Менеджер контейнеров (идентичен ARM)
├── test_*.py                # Unit tests
└── README.md                # Этот файл
```

---

## Что можно тестировать

### ✅ Работает на x86:

1. **ADB подключение и команды**
   ```bash
   adb shell getprop ro.product.model
   adb shell input tap 500 1000
   adb shell pm list packages
   ```

2. **Парсер SharedPreferences**
   ```python
   from avito_prefs_parser import parse_session_xml
   session = parse_session_xml(xml_content)
   print(session.session_token)
   ```

3. **UI Automation**
   ```python
   adb = ADBController(host="localhost", port=5555)
   await adb.scroll_feed()
   await adb.open_messages()
   ```

4. **Логика Refresh Scheduler**
   ```python
   # Проверка обнаружения истекающих токенов
   # Проверка очереди задач
   # Проверка параллельной обработки
   ```

### ❌ НЕ работает на x86:

1. **Реальное Avito приложение**
   - libfp.so обнаружит x86 CPU
   - Fingerprint генерация не пройдет проверку

2. **Production токены**
   - Даже если получить токен, Avito заблокирует

3. **Anti-emulator bypass**
   - Build properties не помогут на x86

---

## Тестирование без Avito

Можно тестировать всю логику с mock данными:

```python
# test_active_refresh.py
from avito_prefs_parser import AvitoSession
from active_refresh import ActiveTokenRefresh
from farm_manager import ADBController

async def test_refresh_logic():
    # Mock session
    session = AvitoSession(
        session_token="mock_token_123",
        device_id="device_456",
        expires_at=int(time.time()) + 60
    )

    # Test ADB controller
    adb = ADBController(host="localhost", port=5555)
    await adb.connect()

    # Test actions (работают на любом Android!)
    await adb.scroll_feed()
    await adb.tap(500, 1000)

    # Test session injection
    await adb.set_avito_session(session)

    # Test session extraction
    extracted = await adb.get_avito_session()
    assert extracted.session_token == session.session_token
```

---

## Миграция на ARM

Когда код протестирован на x86:

1. Скопировать файлы в `token-farm/` (ARM версия)
2. Изменить `docker-compose.yml`:
   - Добавить `platform: linux/arm64`
   - Изменить build properties на реальные устройства
3. Развернуть на Hetzner CAX или Oracle Ampere
4. Протестировать с реальным Avito

---

## Полезные команды

### Docker

```bash
# Пересоздать контейнеры
docker-compose down && docker-compose up -d

# Удалить все данные
docker-compose down -v

# Зайти в контейнер
docker exec -it redroid-x86-1 sh

# Посмотреть логи конкретного контейнера
docker-compose logs -f redroid-x86-1
```

### ADB

```bash
# Список устройств
adb devices

# Подключение
adb connect localhost:5555

# Shell
adb -s localhost:5555 shell

# Установить APK (для тестирования любого Android app)
adb -s localhost:5555 install app.apk

# Скриншот
adb -s localhost:5555 exec-out screencap -p > screen.png

# Логи
adb -s localhost:5555 logcat
```

### Python тесты

```bash
# Все тесты
pytest -v

# Конкретный тест
pytest test_avito_prefs_parser.py::TestAvitoSession -v

# С coverage
pytest --cov=. --cov-report=html
```

---

## Troubleshooting

### Контейнер не запускается

```bash
# Проверить логи
docker-compose logs redroid-x86-1

# Проверить что Redroid image скачан
docker images | grep redroid

# Скачать вручную
docker pull redroid/redroid:12.0.0-latest
```

### ADB не подключается

```bash
# Проверить что порт открыт
docker-compose ps

# Попробовать другой порт
adb connect localhost:5556

# Убить adb server и перезапустить
adb kill-server
adb start-server
```

### Медленная работа

```bash
# Ограничить ресурсы контейнера
# В docker-compose.yml:
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 4G
```

---

## Что дальше?

После отладки на x86:

1. ✅ Код работает - миграция на ARM
2. ⚙️ Добавить setup_container.py (Task #7)
3. 🧪 E2E тесты (Task #11)
4. 📊 Метрики Prometheus (Task #9)
5. 🚀 Deploy на Hetzner CAX

---

*Версия: x86 Development Build*
*Для production используйте `token-farm/` (ARM)*
