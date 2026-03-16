# Avito SmartFree - Техническое Задание v2.0

**Дата:** 2026-01-25
**Статус:** В реализации
**Приоритет:** Критичный

---

## 🎯 Цель проекта

SaaS платформа для интеграции Avito Messenger с Telegram без необходимости физических устройств клиентов.

### Ключевое отличие от v1:
- ❌ **Не копируем** данные с телефонов клиентов
- ✅ **Генерируем** fingerprint в Redroid эмуляторах на ARM сервере
- ✅ **Обходим** anti-emulator проверки Avito
- ✅ **Автоматически обновляем** токены через активную имитацию пользователя

---

## 🏗️ Архитектура

```
┌──────────────────────────────────────────────────────┐
│         Token Farm (ARM Server - Hetzner CAX)        │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Redroid Container Pool (1-100 контейнеров)    │ │
│  │                                                │ │
│  │  Каждый контейнер:                             │ │
│  │  - Android 12 (замаскирован под OnePlus 9)    │ │
│  │  - Avito app установлен                        │ │
│  │  - Генерирует валидный fingerprint             │ │
│  │  - Обновляет токены автоматически              │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Refresh Scheduler                             │ │
│  │                                                │ │
│  │  - Мониторинг истечения токенов                │ │
│  │  - Запуск Avito за 1 мин до истечения         │ │
│  │  - Активная имитация пользователя              │ │
│  │  - Проверка обновления каждые 15-20 сек       │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Token Farm API (FastAPI)                      │ │
│  │  - REST API для управления аккаунтами          │ │
│  │  - Prometheus metrics                          │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
                          │
                          ▼ WebSocket
┌──────────────────────────────────────────────────────┐
│              MCP Server (VPS)                        │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  MCP Manager                                   │ │
│  │  - WebSocket pool (1000 соединений)           │ │
│  │  - Роутинг Avito ↔ Telegram                   │ │
│  │  - Auto-reconnect при обновлении токенов       │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Telegram Bot                                  │ │
│  │  - Команды: /chats, /select, /history         │ │
│  │  - Пересылка сообщений                         │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 🔑 Ключевые компоненты

### 1. Redroid Маскировка (КРИТИЧНО!)

**Задача:** Обмануть `libfp.so` anti-emulator проверки

**Реализация:**
```yaml
# docker-compose.yml
services:
  redroid-1:
    image: redroid/redroid:12.0.0-latest
    platform: linux/arm64  # ARM обязательно!
    privileged: true
    command: >
      androidboot.redroid_gpu_mode=guest
      ro.product.manufacturer=OnePlus
      ro.product.model=LE2115
      ro.hardware=qcom
      ro.kernel.qemu=0
      ro.build.fingerprint=OnePlus/OnePlus9/OnePlus9:13/TP1A.220905.001/R.202402a5:user/release-keys
    volumes:
      - ./scripts/cleanup_emulator.sh:/system/bin/cleanup.sh
```

**Init скрипт:**
```bash
#!/system/bin/sh
# cleanup_emulator.sh

# Удаляем эмуляторные device nodes
rm -f /dev/socket/qemud
rm -f /dev/qemu_pipe
rm -f /dev/goldfish*
rm -f /sys/qemu_trace

# Даём системе загрузиться
sleep 5
```

**Проверки которые должны пройти:**
- `Build.FINGERPRINT` не содержит "generic", "emulator"
- `Build.MANUFACTURER` не "unknown"
- `SystemProperties.get("ro.kernel.qemu")` = "0"
- `/dev/qemu_pipe` не существует
- ARM CPU в `/proc/cpuinfo`

---

### 2. Активное Обновление Токенов

**Проблема:** Токен обновляется ТОЛЬКО после истечения

**Решение:** Запускаем Avito заранее и имитируем активность до обновления

**Алгоритм:**
```python
# active_token_refresh.py

async def active_token_refresh(account_id: UUID) -> bool:
    """
    Активное обновление токена

    Timeline:
    11:59 - Запуск (за 1 мин до истечения)
    12:00 - Токен истекает
    12:00:15 - Токен обновляется (Avito автоматически)
    12:00:20 - Сохраняем и останавливаем

    Downtime: 0 секунд!
    """

    # 1. Запустить Avito
    await adb.shell("am start com.avito.android/.MainActivity")
    await asyncio.sleep(3)

    old_expiry = account.expires_at

    # 2. Цикл имитации до обновления токена
    for round in range(30):  # Макс 10 минут

        # Имитация пользователя
        actions = random.sample([
            scroll_feed,
            open_messages,
            open_profile,
            http_api_ping,
        ], k=2)

        for action in actions:
            await action(adb, account)
            await asyncio.sleep(random.uniform(1, 3))

        # Проверка обновления
        new_session = await read_prefs(adb)

        if new_session['expires_at'] > old_expiry:
            logger.info(f"✓ Token refreshed after {round + 1} rounds")
            await save_to_db(account_id, new_session)
            await notify_mcp(account_id, new_session)
            break

        # Пауза перед следующим раундом
        await asyncio.sleep(15)

    # 3. Остановить Avito
    await adb.shell("am force-stop com.avito.android")
```

**UI Automation функции:**
```python
async def scroll_feed(adb: ADBController):
    """Свайп по ленте"""
    size = await adb.get_screen_size()
    await adb.shell(f"input swipe {size.width//2} {size.height*2//3} {size.width//2} {size.height//3} 300")

async def open_messages(adb: ADBController):
    """Тап на Сообщения"""
    await adb.shell("input tap 650 2300")  # Координаты для 1080x2400

async def http_api_ping(adb: ADBController, account: Account):
    """HTTP запрос к Avito API"""
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://app.avito.ru/api/1/messenger/getUnreadCount",
            headers=build_headers(account),
            json={}
        )
```

---

### 3. Refresh Scheduler

**Задача:** Мониторинг и автоматический refresh

**Алгоритм:**
```python
# refresh_scheduler.py

async def token_refresh_daemon():
    """Главный цикл мониторинга"""

    while True:
        now = time.time()

        # Получить аккаунты где токен истекает через < 2 минуты
        accounts = await db.execute("""
            SELECT a.*, s.expires_at
            FROM accounts a
            JOIN sessions s ON s.account_id = a.id
            WHERE s.is_active = true
            AND s.expires_at < :threshold
            AND a.status NOT IN ('refreshing', 'error')
            ORDER BY s.expires_at ASC
        """, {"threshold": now + 120})

        logger.info(f"Found {len(accounts)} accounts needing refresh")

        # Запускаем refresh для каждого (параллельно до 10)
        tasks = []
        for account in accounts:
            task = asyncio.create_task(
                active_token_refresh(account.id)
            )
            tasks.append(task)

            if len(tasks) >= 10:
                await asyncio.gather(*tasks)
                tasks = []

        if tasks:
            await asyncio.gather(*tasks)

        # Проверяем каждые 30 секунд
        await asyncio.sleep(30)
```

---

### 4. MCP Manager интеграция

**Задача:** Связать Avito WebSocket и Telegram Bot

**Архитектура:**
```python
# mcp_manager.py

class MCPManager:
    """Управление WebSocket соединениями"""

    def __init__(self):
        self.clients: Dict[UUID, AvitoClient] = {}
        self.telegram_bot = TelegramBot()

    async def start_client(self, account_id: UUID):
        """Запустить WebSocket для аккаунта"""
        account = await db.get_account(account_id)
        session = await db.get_active_session(account_id)

        client = AvitoClient(
            session_token=session.session_token,
            device_id=account.device_id,
            fingerprint=account.fingerprint,
            user_hash=account.user_hash
        )

        # Callback для входящих сообщений
        client.on_message = lambda msg: self.handle_avito_message(account_id, msg)

        await client.connect()
        self.clients[account_id] = client

    async def handle_avito_message(self, account_id: UUID, msg: dict):
        """Обработка входящего сообщения из Avito"""

        # Найти Telegram пользователей для этого аккаунта
        telegram_users = await db.get_telegram_users_for_account(account_id)

        # Отправить в Telegram
        for user in telegram_users:
            await self.telegram_bot.send_message(
                user.telegram_id,
                format_avito_message(msg)
            )

    async def send_to_avito(self, account_id: UUID, channel_id: str, text: str):
        """Отправка сообщения в Avito"""
        client = self.clients.get(account_id)
        if client:
            await client.send_message(channel_id, text)

    async def update_session(self, account_id: UUID, new_session: dict):
        """Обновление токена - переподключение WebSocket"""

        # Отключить старый клиент
        if account_id in self.clients:
            await self.clients[account_id].disconnect()
            del self.clients[account_id]

        # Создать новый с обновлённым токеном
        await self.start_client(account_id)
```

---

## 📋 План реализации (Этапы)

### ✅ Этап 0: Подготовка (выполнено)
- [x] Изучение проекта
- [x] Анализ TODO
- [x] Создание ТЗ
- [x] Планирование задач

### 🔄 Этап 1: Core функциональность (1-2 дня)
1. ⏳ Настройка Redroid маскировки
2. ⏳ Парсер Avito XML
3. ⏳ UI Automation в ADBController
4. ⏳ Активное обновление токенов
5. ⏳ Refresh Scheduler

### 🔄 Этап 2: Интеграция (1 день)
6. ⏳ MCP Manager ↔ Telegram Bot
7. ⏳ Init скрипт для контейнеров

### 🔄 Этап 3: Тестирование (1-2 дня)
8. ⏳ Развёртывание на ARM сервере
9. ⏳ E2E тест полного цикла
10. ⏳ Нагрузочное тестирование

### 🔄 Этап 4: Production (1 день)
11. ⏳ Метрики и мониторинг
12. ⏳ Документация
13. ⏳ CI/CD

**Общая оценка:** 5-7 дней

---

## 🎯 Критерии успеха

### MVP (Минимум для запуска):
- ✅ Redroid запускается на ARM и обходит anti-emulator проверки
- ✅ Avito app генерирует валидный fingerprint в контейнере
- ✅ Токены обновляются автоматически каждые 24 часа
- ✅ Downtime при обновлении < 30 секунд
- ✅ MCP Server пересылает сообщения Avito ↔ Telegram

### Production Ready:
- ✅ Поддержка 100+ аккаунтов на одном сервере
- ✅ Метрики и алерты
- ✅ Health checks и auto-recovery
- ✅ Документация для развёртывания
- ✅ E2E тесты

---

## 🚀 Следующий шаг

**Начинаем с Задачи #1:** Настройка Redroid для обхода anti-emulator проверок

Создаём `docker-compose.yml` с правильными build properties и init скриптом.
