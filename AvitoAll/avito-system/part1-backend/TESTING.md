# Part 1: Backend API — План тестирования

## Инструменты

- **pytest** + **pytest-asyncio** — тесты
- **httpx** — async HTTP клиент для тестов FastAPI
- **pytest-cov** — покрытие

## Структура тестов

```
part1-backend/
└── tests/
    ├── conftest.py            # Фикстуры: test app, test DB, test client
    ├── test_health.py
    ├── test_sessions.py
    ├── test_searches.py
    ├── test_rules.py
    ├── test_items.py
    ├── test_dialogs.py
    ├── test_stats.py
    └── test_auth.py
```

## Фикстуры (conftest.py)

- `test_db` — SQLite in-memory, таблицы создаются заново для каждого теста
- `test_app` — FastAPI app с подменённой БД
- `client` — httpx.AsyncClient к test_app
- `auth_headers` — `{"X-Api-Key": "test_key"}`

## Unit-тесты

### test_health.py
| Тест | Ожидание |
|------|----------|
| `GET /health` | 200, `{"status": "ok"}` |
| `GET /health` без авторизации | 200 (health без auth) |

### test_auth.py
| Тест | Ожидание |
|------|----------|
| Запрос без `X-Api-Key` | 401 |
| Запрос с неверным ключом | 401 |
| Запрос с верным ключом | 200 |

### test_sessions.py
| Тест | Ожидание |
|------|----------|
| `POST /api/v1/sessions` с валидными данными | 200, `success: true` |
| `POST /api/v1/sessions` без session_token | 422 (validation error) |
| `POST /api/v1/sessions` повторный — обновляет, не дублирует | 200, 1 запись в БД |
| `GET /api/v1/session` при наличии токенов | 200, полный объект |
| `GET /api/v1/session` при пустой БД | 404 |
| `POST` с истёкшим JWT — сохраняет (bridge отвечает за валидность) | 200 |

### test_searches.py
| Тест | Ожидание |
|------|----------|
| `POST /api/v1/searches` с query | 200, объект с id |
| `POST` без query | 422 |
| `GET /api/v1/searches` — пустой список | 200, `[]` |
| `GET` после создания 3 поисков | 200, 3 элемента |
| `GET ?enabled=true` фильтр | только enabled поиски |
| `PUT /api/v1/searches/{id}` обновить цену | 200, обновлённые поля |
| `PUT` несуществующего id | 404 |
| `DELETE /api/v1/searches/{id}` | 200, не найден повторно |
| `DELETE` несуществующего | 404 |

### test_rules.py
| Тест | Ожидание |
|------|----------|
| При инициализации есть предустановленные правила | ≥ 6 правил с is_preset=true |
| `POST /api/v1/rules` пользовательское | 200, is_preset=false |
| `PUT` выключить предустановленное | 200, enabled=false |
| `DELETE` предустановленного | 400/403 (запрещено) |
| `DELETE` пользовательского | 200 |
| `GET ?enabled=true` | только включённые |

### test_items.py
| Тест | Ожидание |
|------|----------|
| `POST /api/v1/items` сохранить товар | 200 |
| `POST` дубликат (тот же id) — перезаписывает | 200, 1 запись |
| `GET /api/v1/items` список | 200, сортировка по found_at DESC |
| `GET ?verdict=OK` фильтр | только OK |
| `GET ?search_id=1` фильтр | только из поиска 1 |
| `GET /api/v1/items/{id}` | 200, полный объект |
| `GET` несуществующего | 404 |
| `GET /api/v1/items/new?since=...` | только новые после timestamp |
| Пагинация `?limit=10&offset=0` | корректное количество |

### test_dialogs.py
| Тест | Ожидание |
|------|----------|
| `POST /api/v1/dialogs` | 200, channel_id |
| `POST` дубликат channel_id | 409 или update |
| `GET /api/v1/dialogs` | 200, список |
| `GET ?status=greeted` | фильтр по статусу |
| `PUT /api/v1/dialogs/{ch}` смена статуса | 200 |
| `PUT` невалидный статус | 400 |
| Допустимые переходы: new→greeted→replied→deal→shipped→done | все работают |

### test_stats.py
| Тест | Ожидание |
|------|----------|
| `GET /api/v1/stats` пустая БД | 200, нули |
| После добавления данных | корректные счётчики |
| `token_valid` при наличии токена | true/false в зависимости от exp |
| `items_by_verdict` | правильная группировка |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все тесты зелёные | 100% |
| Покрытие бизнес-логики (routers/) | ≥ 80% |
| Покрытие models.py | ≥ 90% |
| Время выполнения всех тестов | < 10 сек |
| Нет flaky-тестов | 0 |

## Метрики

| Метрика | Как измеряется | Цель |
|---------|---------------|------|
| Время ответа API | httpx response time | p95 < 100 мс |
| Корректность CRUD | assert на каждую операцию | 100% |
| Валидация входных данных | 422 на невалидные запросы | 100% |
| Авторизация | 401 без ключа на всех /api/v1/* | 100% |
| Целостность БД | FK constraints, уникальность | нет ошибок |

## Запуск

```bash
cd part1-backend
pip install pytest pytest-asyncio pytest-cov httpx
pytest tests/ -v --cov=src --cov-report=term-missing
```
