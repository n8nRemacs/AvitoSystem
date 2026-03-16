# Avito System — Мастер-план тестирования

## Стратегия

Каждая часть тестируется **изолированно** (unit + integration с моками), затем проводится **сквозное тестирование** всей системы.

## Уровни тестирования

```
┌─────────────────────────────────────────────────┐
│ E2E (сквозные)                                  │
│ Полный цикл: поиск → анализ → уведомление      │
│ Файл: TESTING.md (этот файл)                    │
├─────────────────────────────────────────────────┤
│ Integration (между компонентами)                │
│ Backend ↔ Worker, Backend ↔ Messenger и т.д.    │
│ Файл: TESTING.md                                │
├─────────────────────────────────────────────────┤
│ Unit (внутри компонента)                        │
│ Каждая часть: partN-*/TESTING.md                │
│ Моки вместо внешних зависимостей                │
└─────────────────────────────────────────────────┘
```

## Общие критерии готовности (Definition of Done)

Часть считается готовой когда:
- [ ] Все unit-тесты проходят
- [ ] Все integration-тесты с моками проходят
- [ ] Покрытие тестами ≥ 70% для бизнес-логики
- [ ] Нет критических ошибок при запуске
- [ ] .env.example заполнен и задокументирован
- [ ] SPEC.md соответствует реализации

## Общие метрики проекта

| Метрика | Цель | Критично |
|---------|------|----------|
| Unit-тесты проходят | 100% green | Да |
| Покрытие бизнес-логики | ≥ 70% | Да |
| Время запуска Backend | < 3 сек | Нет |
| Время ответа API (p95) | < 200 мс | Да |
| Worker: цикл поиска | < 30 сек на запрос | Да |
| Frontend: загрузка страницы | < 2 сек | Нет |
| E2E: от появления товара до уведомления | < 3 мин | Да |
| Token Bridge: синхронизация | < 10 сек | Да |
| Android Token: root read | < 500 мс | Да |
| Messenger: WebSocket connect | < 3 сек | Да |
| Messenger: send_rpc latency | < 500 мс | Да |
| Uptime Backend | 99.5% | Да |

---

## Сквозные тесты (E2E)

### E2E-1: Полный цикл мониторинга

**Предусловия:** Все серверные части запущены (1-5 или 1+6), токены валидны, есть активный поиск.

**Шаги:**
1. Через веб-панель создать поиск: `iPhone 12 Pro, 10000-20000, доставка`
2. Worker подхватывает поиск в следующем цикле
3. Worker находит товары через Avito API
4. Worker проверяет карточку (не зарезервирован)
5. Worker отправляет на AI-анализ
6. Worker сохраняет результат в Backend
7. Telegram Bot отправляет уведомление
8. Если OK — приветствие продавцу через Messenger (Part 7)

**Критерий:** Уведомление в Telegram получено ≤ 3 минут от появления товара.

### E2E-2: Фильтрация зарезервированного

**Шаги:**
1. Worker находит товар
2. Карточка товара показывает "зарезервирован"
3. Товар не проходит AI-анализ, не отправляется уведомление

**Критерий:** Зарезервированные товары отсутствуют в результатах (`GET /api/v1/items`).

### E2E-3: Обновление токенов (Redroid)

**Шаги:**
1. JWT-токен истекает (exp < now)
2. Token Bridge (Part 5) запускает Avito в Redroid
3. Avito обновляет токен
4. Bridge извлекает новый токен и отправляет на Backend
5. Worker и Messenger получают новый токен и продолжают работу

**Критерий:** Перерыв мониторинга ≤ 5 минут при обновлении токена.

### E2E-4: Обновление токенов (Android)

**Шаги:**
1. JWT-токен близок к истечению (< 2 часов)
2. Android Token (Part 6) запускает Avito через startActivity
3. Avito обновляет токен
4. APK перечитывает SharedPreferences и синхронизирует на Backend
5. Worker и Messenger получают новый токен

**Критерий:** Обновление автоматическое, без ручного вмешательства. Foreground notification показывает статус.

### E2E-5: Управление через веб-панель

**Шаги:**
1. Создать поиск через веб-панель
2. Убедиться что он появился в `GET /api/v1/searches`
3. Выключить поиск (enabled=false)
4. Worker перестаёт искать по этому запросу
5. Удалить поиск
6. Результаты остаются в истории

**Критерий:** Все CRUD-операции отрабатывают корректно, Worker реагирует на изменения.

### E2E-6: Полный цикл мессенджера

**Шаги:**
1. Worker находит товар с вердиктом OK
2. Messenger создаёт чат через `chatCreateByItemId`
3. Messenger отправляет приветствие через `sendTextMessage`
4. Продавец отвечает → WebSocket push event `Message`
5. Event handler сохраняет ответ в Backend
6. Telegram Bot уведомляет о новом сообщении

**Критерий:** Сообщение от продавца видно в Backend и Telegram ≤ 30 сек.

### E2E-7: Real-time диалог через Messenger

**Шаги:**
1. Messenger подключается по WebSocket
2. Получает список чатов (getChats.v5)
3. Получает историю конкретного чата (history.v2)
4. Отправляет typing indicator
5. Отправляет текстовое сообщение
6. Получает push event с ответом
7. Помечает чат как прочитанный

**Критерий:** Все операции без ошибок, WebSocket keepalive стабилен ≥ 30 мин.

### E2E-8: IP-телефония

**Предусловия:** Part 7 с call_tracking_enabled=true, есть история звонков.

**Шаги:**
1. Запросить историю звонков за период
2. Скачать запись звонка (MP3)
3. Проверить что файл валидный

**Критерий:** История загружена, запись скачана и воспроизводится.

---

## Интеграционные тесты

### INT-1: Backend ↔ Worker

| Тест | Что проверяет |
|------|--------------|
| Worker получает токены | `GET /api/v1/session` → 200 с валидным JWT |
| Worker получает поиски | `GET /api/v1/searches?enabled=true` → список |
| Worker получает правила | `GET /api/v1/rules?enabled=true` → список |
| Worker сохраняет товар | `POST /api/v1/items` → 200, товар в БД |
| Worker создаёт диалог | `POST /api/v1/dialogs` → 200, диалог в БД |

### INT-2: Backend ↔ Frontend

| Тест | Что проверяет |
|------|--------------|
| Список поисков | Страница /searches загружает данные |
| CRUD поисков | Создание, редактирование, удаление работают |
| Список правил | Предустановленные правила отображаются |
| Результаты | Товары с вердиктами отображаются |
| Диалоги | Список диалогов с сообщениями |
| Статистика | /status показывает актуальные данные |

### INT-3: Backend ↔ Telegram

| Тест | Что проверяет |
|------|--------------|
| /add создаёт поиск | POST /api/v1/searches вызывается |
| /list показывает поиски | GET /api/v1/searches возвращает данные |
| Уведомления | GET /api/v1/items/new возвращает новые товары |

### INT-4: Backend ↔ Token Bridge (Part 5)

| Тест | Что проверяет |
|------|--------------|
| Синхронизация | POST /api/v1/sessions → 200, токены в БД |
| Перезапись | Повторный POST обновляет, не дублирует |
| Валидация | POST с невалидным JWT → 400 |

### INT-5: Backend ↔ Android Token (Part 6)

| Тест | Что проверяет |
|------|--------------|
| Синхронизация (X-Device-Key) | POST /api/v1/sessions → 200 |
| Health check | GET /health → 200 |
| Full status | GET /api/v1/full-status → парсинг без ошибок |
| Device ping | POST /api/v1/devices/ping → 200 |
| MCP restart | POST /api/v1/mcp/restart → 200 |

### INT-6: Backend ↔ Messenger (Part 7)

| Тест | Что проверяет |
|------|--------------|
| Получение токенов | GET /api/v1/session → SessionData с fingerprint |
| Сохранение диалога | POST /api/v1/dialogs → 200 |
| Сохранение сообщения | POST /api/v1/messages → 200 |
| Обновление диалога | PUT /api/v1/dialogs/{id} → 200 |

### INT-7: Messenger ↔ Avito WebSocket

| Тест | Что проверяет |
|------|--------------|
| Connect с id_version=v2 | Session init получен |
| getChats.v5 | Список каналов |
| history.v2 | Сообщения чата |
| sendTextMessage.v2 | Сообщение отправлено |
| Push event Message | Входящее сообщение получено |
| Ping keepalive | Соединение стабильно 30+ мин |
| Reconnect после обрыва | Автоматическое переподключение |

### INT-8: Messenger ↔ Avito HTTP REST

| Тест | Что проверяет |
|------|--------------|
| getChannels (category=1) | Список каналов |
| getUserVisibleMessages | Сообщения с body.text.text |
| sendTextMessage | Сообщение отправлено |
| Пагинация (>30 каналов) | hasMore + sortingTimestamp |
| TLS impersonation | curl_cffi chrome120 |

---

## Матрица тестов по частям

| Часть | Unit-тесты | Файл |
|-------|-----------|------|
| Part 1: Backend | API endpoints, models, DB | `part1-backend/TESTING.md` |
| Part 2: Frontend | Components, API calls | `part2-frontend/TESTING.md` |
| Part 3: Worker | Avito API, analyzer, tracker | `part3-worker/TESTING.md` |
| Part 4: Telegram | Commands, notifications | `part4-telegram/TESTING.md` |
| Part 5: Token Bridge | XML parsing, JWT, docker exec | `part5-token-bridge/TESTING.md` |
| Part 6: Android Token | Root read, JWT, OkHttp, Service | `part6-Android-token/TESTING.md` |
| Part 7: Messenger | WS client, HTTP client, events | `part7-messager/TESTING.md` |

## Запуск всех тестов

```bash
# Unit-тесты всех Python-частей
for part in part1-backend part3-worker part4-telegram part5-token-bridge part7-messager; do
  echo "=== $part ===" && cd $part && pytest tests/ -v && cd ..
done

# Frontend тесты
cd part2-frontend && npm test

# Android тесты (unit, без устройства)
cd part6-Android-token && ./gradlew testDebugUnitTest

# Android тесты (на устройстве)
cd part6-Android-token && ./gradlew connectedDebugAndroidTest
```
