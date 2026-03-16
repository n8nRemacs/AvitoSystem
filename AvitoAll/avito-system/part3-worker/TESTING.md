# Part 3: Worker (Avito Monitor) — План тестирования

## Инструменты

- **pytest** + **pytest-asyncio** — тесты
- **aioresponses** — мок HTTP-запросов (Avito API, Backend API, OpenRouter)
- **pytest-cov** — покрытие
- **unittest.mock** — моки WebSocket

## Структура тестов

```
part3-worker/
└── tests/
    ├── conftest.py               # Фикстуры: моки API, тестовые данные
    ├── test_backend_client.py    # Клиент к Backend API
    ├── test_avito_api.py         # Клиент к Avito API
    ├── test_analyzer.py          # AI-анализ
    ├── test_auto_message.py      # Автоприветствие
    ├── test_tracker.py           # Дедупликация
    ├── test_worker.py            # Главный цикл
    └── fixtures/
        ├── search_response.json  # Пример ответа Avito /api/11/items
        ├── item_card.json        # Пример карточки товара
        └── item_reserved.json    # Карточка зарезервированного товара
```

## Фикстуры

- `mock_backend` — aioresponses для Backend API (токены, поиски, правила)
- `mock_avito` — aioresponses для Avito API (поиск, карточка)
- `mock_openrouter` — aioresponses для OpenRouter (AI-анализ)
- `sample_session` — валидный объект токенов
- `sample_items` — список тестовых товаров
- `sample_rules` — список тестовых правил

## Unit-тесты

### test_backend_client.py
| Тест | Ожидание |
|------|----------|
| `get_session()` — 200 | Возвращает SessionData |
| `get_session()` — 404 | Возвращает None |
| `get_searches()` — список | Возвращает list[Search] |
| `get_rules()` — список | Возвращает list[Rule] |
| `save_item()` — 200 | True |
| `save_item()` — 500 | False, логирование ошибки |
| `save_dialog()` — 200 | True |
| Заголовок X-Api-Key | Присутствует во всех запросах |

### test_avito_api.py
| Тест | Ожидание |
|------|----------|
| `search()` с фикстурой | Парсит 5+ товаров |
| `search()` — парсинг цены "19 980 ₽" | 19980 |
| `search()` — парсинг цены "5 800 — 9 850 ₽" | 5800 |
| `search()` — фильтрация type != "item" | Виджеты пропущены |
| `search()` — 429 | Пустой список, backoff |
| `search()` — сетевая ошибка | Пустой список, логирование |
| `get_item_card()` — 200 | Возвращает данные карточки |
| `get_item_card()` — 404 | None |
| `is_reserved()` — обычный товар | False |
| `is_reserved()` — зарезервированный | True |
| Заголовки содержат X-Session, f, X-DeviceId | Все присутствуют |
| Rate limiting — 2 запроса подряд | Пауза ≥ 2 сек |
| Токен refresh — exp < now+3600 | Вызывает refresh |

### test_analyzer.py
| Тест | Ожидание |
|------|----------|
| Анализ нормального товара | verdict=OK, score≥7 |
| Товар с "iCloud lock" в описании | verdict=SKIP |
| Товар с "разбит экран" | verdict=SKIP, defects содержит |
| Подозрительно дешёвый | verdict=RISK |
| Пользовательское правило применяется | Правило в system prompt |
| OpenRouter 500 → graceful fallback | verdict=PENDING |
| Таймаут OpenRouter | verdict=PENDING, логирование |
| Максимум 5 фото в запросе | len(images) ≤ 5 |

### test_auto_message.py
| Тест | Ожидание |
|------|----------|
| `send_greeting()` — успех | Возвращает channel_id |
| Повторный greeting тому же item | Пропускает (уже отправлено) |
| Rate limit — 2 сообщения подряд | Пауза ≥ MESSAGE_RATE_LIMIT |
| Мессенджер отключён | None, логирование |
| Ошибка create_chat | None |

### test_tracker.py
| Тест | Ожидание |
|------|----------|
| `filter_new()` — все новые | Возвращает все |
| `filter_new()` — все уже виденные | Пустой список |
| `filter_new()` — частично новые | Только новые |
| Разные query — разные пространства | Не пересекаются |
| `cleanup(max_age_days=0)` | Удаляет все |
| `cleanup(max_age_days=7)` | Оставляет свежие |

### test_worker.py (главный цикл)
| Тест | Ожидание |
|------|----------|
| Цикл с 1 поиском, 2 новых товара | 2 save_item вызова |
| Цикл с 0 поисков | Ничего не делает |
| Товар зарезервирован | Пропущен, не анализируется |
| AI verdict=OK + AUTO_GREET | send_greeting вызван |
| AI verdict=RISK | Нет greeting |
| AI verdict=SKIP | Нет greeting, нет уведомления |
| Нет токенов (404) | Логирование, пропуск цикла |
| Avito 429 | Пропуск, backoff |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все unit-тесты зелёные | 100% |
| Покрытие avito_api.py | ≥ 80% |
| Покрытие analyzer.py | ≥ 70% |
| Покрытие worker.py | ≥ 70% |
| Покрытие tracker.py | ≥ 90% |
| Нет обращений к реальным API в тестах | 0 |

## Метрики

| Метрика | Цель |
|---------|------|
| Парсинг 30 товаров из search response | < 100 мс |
| Один цикл worker (с моками) | < 5 сек |
| AI-анализ (реальный запрос) | < 15 сек |
| Дедупликация 1000 товаров | < 500 мс |
| Rate limit корректен | Пауза 2±0.5 сек |
| Backoff на 429 | 5, 10, 20, 60 сек |

## Запуск

```bash
cd part3-worker
pip install pytest pytest-asyncio pytest-cov aioresponses
pytest tests/ -v --cov=src --cov-report=term-missing
```
