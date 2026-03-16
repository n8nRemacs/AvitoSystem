# Контракты API — Avito System

Эта папка содержит JSON-схемы для всех сущностей системы. Все части проекта используют эти схемы как единый источник правды.

## Схемы

| Файл | Описание |
|------|----------|
| `session.schema.json` | Токены авторизации Avito (JWT, refresh, fingerprint) |
| `search.schema.json` | Поисковый запрос (query, цена, доставка, регион) |
| `item.schema.json` | Найденный товар + результат AI-анализа |
| `rule.schema.json` | AI красный флаг (общий для всех поисков) |

## API Endpoints (Backend :8080)

### Токены
| Метод | Путь | Описание | Кто вызывает |
|-------|------|----------|--------------|
| `POST` | `/api/v1/sessions` | Синхронизация токенов | token-bridge |
| `GET` | `/api/v1/session` | Получить актуальные токены | worker |

### Поиски
| Метод | Путь | Описание | Кто вызывает |
|-------|------|----------|--------------|
| `GET` | `/api/v1/searches` | Список поисков | frontend, worker, telegram |
| `POST` | `/api/v1/searches` | Создать поиск | frontend, telegram |
| `PUT` | `/api/v1/searches/{id}` | Обновить поиск | frontend |
| `DELETE` | `/api/v1/searches/{id}` | Удалить поиск | frontend, telegram |

### AI-правила
| Метод | Путь | Описание | Кто вызывает |
|-------|------|----------|--------------|
| `GET` | `/api/v1/rules` | Список правил | frontend, worker |
| `POST` | `/api/v1/rules` | Создать правило | frontend |
| `PUT` | `/api/v1/rules/{id}` | Обновить правило | frontend |
| `DELETE` | `/api/v1/rules/{id}` | Удалить правило | frontend |

### Результаты (товары)
| Метод | Путь | Описание | Кто вызывает |
|-------|------|----------|--------------|
| `GET` | `/api/v1/items` | Список найденных товаров | frontend, telegram |
| `GET` | `/api/v1/items/{id}` | Детали товара | frontend |
| `POST` | `/api/v1/items` | Сохранить найденный товар | worker |
| `GET` | `/api/v1/items/new` | Новые товары (для Telegram) | telegram |

### Диалоги
| Метод | Путь | Описание | Кто вызывает |
|-------|------|----------|--------------|
| `GET` | `/api/v1/dialogs` | Список диалогов | frontend, telegram |
| `GET` | `/api/v1/dialogs/{id}` | Детали диалога | frontend |
| `POST` | `/api/v1/dialogs` | Создать диалог | worker |
| `PUT` | `/api/v1/dialogs/{id}` | Обновить статус | frontend, telegram |

### Система
| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Healthcheck |
| `GET` | `/api/v1/stats` | Статистика |

## Авторизация

Все запросы к Backend API: заголовок `X-Api-Key: <ключ из .env>`
