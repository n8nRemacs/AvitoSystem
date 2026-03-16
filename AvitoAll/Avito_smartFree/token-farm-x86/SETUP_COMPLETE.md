# Token Farm x86 - Setup Complete ✅

x86 Development окружение полностью настроено и готово к использованию!

## 📦 Что создано

### Структура проекта

```
token-farm-x86/
├── docker-compose.yml           # x86 конфигурация (2-3 контейнера)
├── .env.example                 # Шаблон переменных окружения
├── README.md                    # Полная документация
├── QUICKSTART.md                # Быстрый старт за 5 минут
├── start.bat                    # Windows quick start script
├── Makefile                     # Команды для разработки (Linux/Mac)
├── avito_prefs_parser.py        # Парсер SharedPreferences (copied from ARM)
├── test_avito_prefs_parser.py   # Unit tests (copied from ARM)
├── test_x86_setup.py            # Integration tests для x86
└── scripts/
    └── (empty - cleanup script не нужен для x86)
```

### Docker конфигурация

**Контейнеры:**
- ✅ PostgreSQL 15 (база данных)
- ✅ Redroid x86 #1 (OnePlus 9 profile) - порт 5555
- ✅ Redroid x86 #2 (Samsung S21 profile) - порт 5556
- ✅ Redroid x86 #3 (Google Pixel 6 profile) - порт 5557 (опционально)

**Отличия от ARM версии:**
- ❌ НЕТ `platform: linux/arm64` (использует host архитектуру)
- ✅ `ro.secure=0` и `ro.debuggable=1` для отладки
- ✅ Меньше контейнеров для экономии ресурсов (2 вместо 5)
- ✅ Опциональный API сервер через `--profile api`

---

## 🚀 Быстрый запуск

### Windows

```cmd
cd token-farm-x86
start.bat
```

### Linux/Mac

```bash
cd token-farm-x86
make up
make adb
make test
```

### Проверка

```bash
# Статус контейнеров
docker-compose ps

# ADB устройства
adb devices

# Запуск тестов
python test_x86_setup.py
```

---

## ✅ Что можно тестировать

### 1. ADB Communication
```python
from test_x86_setup import SimpleADBController

adb = SimpleADBController("localhost", 5555)
await adb.connect()
model = await adb.get_prop("ro.product.model")
# Output: OnePlus LE2115
```

### 2. UI Automation
```python
# Tap, swipe, scroll
await adb.tap(500, 1000)
await adb.swipe(540, 1600, 540, 800, 300)
```

### 3. SharedPreferences Parser
```python
from avito_prefs_parser import AvitoSession, generate_session_xml

session = AvitoSession(session_token="test", device_id="123")
xml = generate_session_xml(session)
# Generates valid Android SharedPreferences XML
```

### 4. Mock Active Refresh Logic
```python
# Симуляция активного обновления токенов
# Без реального Avito, но тестирует логику
```

### 5. Scheduler Logic
```python
# Тестирование обнаружения истекающих токенов
# Тестирование очереди задач
# Тестирование параллельной обработки
```

---

## ❌ Что НЕ работает на x86

1. **Реальное Avito приложение**
   - libfp.so обнаружит x86 CPU
   - Fingerprint генерация не пройдет проверку
   - Avito заблокирует аккаунт

2. **Anti-emulator bypass**
   - Build properties не помогут на x86
   - CPU detection всегда покажет emulator

3. **Production токены**
   - Даже если получить токен, он будет невалиден

**Для production используй `token-farm/` (ARM версия)!**

---

## 📝 Примеры использования

### Тест 1: Проверка ADB подключения

```bash
# Подключиться
adb connect localhost:5555

# Получить информацию
adb shell getprop ro.product.manufacturer
# Output: OnePlus

adb shell getprop ro.product.model
# Output: LE2115

adb shell getprop ro.build.version.release
# Output: 12
```

### Тест 2: UI Automation

```bash
# Тап по центру экрана
adb shell input tap 540 1200

# Scroll вниз
adb shell input swipe 540 1600 540 800 300

# Ввод текста
adb shell input text "Hello"

# Нажать Back
adb shell input keyevent 4
```

### Тест 3: SharedPreferences

```python
# test_prefs.py
from avito_prefs_parser import *
from datetime import datetime

# Создать сессию
session = AvitoSession(
    session_token="eyJ.test.token",
    device_id="device_123",
    fingerprint="A2.fingerprint_456",
    expires_at=int(datetime.now().timestamp()) + 86400
)

# Сгенерировать XML
xml = generate_session_xml(session)
print(xml)

# Парсить обратно
parsed = parse_session_xml(xml)
assert parsed.session_token == session.session_token
print("✅ Roundtrip success!")
```

### Тест 4: Mock Refresh

```bash
python test_x86_setup.py
# Запустит полную симуляцию активного refresh
# Покажет что логика работает корректно
```

---

## 🔧 Development Workflow

### Типичный workflow:

1. **Запустить контейнеры**
   ```bash
   make up  # или start.bat
   ```

2. **Подключить ADB**
   ```bash
   make adb
   ```

3. **Разработка кода**
   - Редактировать Python файлы
   - Тестировать локально

4. **Запустить тесты**
   ```bash
   make test      # Integration tests
   make test-unit # Unit tests
   ```

5. **Отладка**
   ```bash
   make logs      # Посмотреть логи
   make shell     # Зайти в контейнер
   make screen    # Сделать скриншот
   ```

6. **Когда всё работает - мигрировать на ARM**
   ```bash
   cp *.py ../token-farm/
   # Развернуть на ARM сервере
   ```

---

## 🎯 Следующие шаги

### На x86 (development):

- [x] ✅ Базовая настройка контейнеров
- [x] ✅ ADB подключение
- [x] ✅ Парсер SharedPreferences
- [x] ✅ UI Automation тестирование
- [ ] 🔄 Установить тестовый APK и протестировать UI automation
- [ ] 🔄 Полное покрытие unit tests
- [ ] 🔄 Mock сервер для Avito API (опционально)

### На ARM (production):

- [ ] ⏳ Task #7: Init скрипт setup_container.py
- [ ] ⏳ Task #6: Тестирование на ARM сервере (Hetzner CAX)
- [ ] ⏳ Task #5: Интеграция с Telegram Bot и MCP
- [ ] ⏳ Task #9: Метрики Prometheus
- [ ] ⏳ Task #11: E2E тесты

---

## 📚 Документация

- **QUICKSTART.md** - Быстрый старт за 5 минут
- **README.md** - Полная документация x86 версии
- **../token-farm/TECHNICAL_SPEC.md** - Техническая спецификация (ARM)
- **Makefile** - Список всех команд (make help)

---

## 🐛 Troubleshooting

### Контейнер не запускается
```bash
docker-compose down -v
docker-compose up -d
docker-compose logs -f
```

### ADB не подключается
```bash
adb kill-server
adb start-server
adb connect localhost:5555
```

### Python модули не найдены
```bash
pip install pytest asyncio httpx
```

### Полная переустановка
```bash
make clean        # Удалить всё
make install      # Установить заново
make up           # Запустить
make test         # Проверить
```

---

## 💡 Tips & Tricks

### 1. Быстрое переключение между контейнерами
```bash
# Алиасы в ~/.bashrc или ~/.zshrc
alias adb1='adb -s localhost:5555'
alias adb2='adb -s localhost:5556'
alias adb3='adb -s localhost:5557'

# Использование
adb1 shell input tap 500 1000
adb2 shell getprop ro.product.model
```

### 2. Автоматический reconnect ADB
```bash
# reconnect.sh
#!/bin/bash
for port in 5555 5556 5557; do
    adb connect localhost:$port
done
adb devices
```

### 3. Мониторинг в реальном времени
```bash
# Terminal 1: Логи
docker-compose logs -f

# Terminal 2: ADB logcat
adb logcat

# Terminal 3: Resource monitor
watch -n 1 docker stats
```

---

## ✅ Checklist перед миграцией на ARM

Перед развертыванием на ARM сервере убедись:

- [ ] Все unit tests проходят (`make test-unit`)
- [ ] Integration tests работают (`make test`)
- [ ] ADB подключение стабильно
- [ ] UI automation работает корректно
- [ ] Парсер SharedPreferences работает с реальными XML
- [ ] Mock refresh logic работает
- [ ] Нет hardcoded localhost/x86 зависимостей
- [ ] Код портабелен (работает на любой архитектуре)

---

## 🎉 Готово!

x86 Development окружение готово к использованию!

**Что дальше:**

1. Запусти тесты: `python test_x86_setup.py`
2. Поэкспериментируй с ADB
3. Разработай новые фичи
4. Когда всё работает - миграция на ARM

**Для production используй:**
- `../token-farm/` - ARM версия
- Развертывание на Hetzner CAX / Oracle Ampere
- Реальное Avito приложение

---

*Created: 2026-01-25*
*Version: x86 Development Build*
