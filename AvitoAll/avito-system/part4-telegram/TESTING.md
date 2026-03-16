# Part 4: Telegram Bot — План тестирования

## Инструменты

- **pytest** + **pytest-asyncio**
- **aiogram.testing** — тестирование хендлеров без реального Telegram API
- **aioresponses** — мок Backend API
- **pytest-cov**

## Структура тестов

```
part4-telegram/
└── tests/
    ├── conftest.py            # Фикстуры: mock bot, mock backend
    ├── test_handlers.py       # Обработчики команд
    ├── test_notifier.py       # Цикл уведомлений
    ├── test_backend_client.py # HTTP к Backend
    └── test_access.py         # Контроль доступа
```

## Unit-тесты

### test_access.py
| Тест | Ожидание |
|------|----------|
| Пользователь в whitelist | Доступ разрешён |
| Пользователь не в whitelist | Сообщение "Нет доступа" |
| Пустой whitelist | Доступ всем |

### test_handlers.py
| Тест | Ожидание |
|------|----------|
| `/start` | Приветственное сообщение с помощью |
| `/add iPhone 12 Pro 10000-25000 доставка` | POST search, ответ "Поиск добавлен" |
| `/add` без аргументов | Ответ "Укажите запрос" |
| `/add iPhone 12 Pro 5000-3000` | Ошибка "min > max" |
| `/list` с 3 поисками | Список из 3 строк |
| `/list` без поисков | "Нет активных поисков" |
| `/remove 1` | DELETE search, ответ "Удалён" |
| `/remove 999` | Ошибка "Не найден" |
| `/status` | Статистика (из stats endpoint) |
| `/stop` | Все поиски disabled |

### test_notifier.py
| Тест | Ожидание |
|------|----------|
| Новый товар с verdict=OK | Отправлено сообщение с ✅ |
| Новый товар с verdict=RISK | Отправлено сообщение с ⚠️ |
| Товар с verdict=SKIP | Не отправлено |
| Нет новых товаров | Ничего не отправлено |
| Backend недоступен | Логирование, пропуск |
| Формат сообщения | Содержит: название, цену, AI-оценку, ссылку |
| Товар с greeted=true | Содержит "Приветствие отправлено" |

### test_backend_client.py
| Тест | Ожидание |
|------|----------|
| `get_searches()` | Список |
| `create_search()` | Объект с id |
| `delete_search()` | True |
| `get_new_items()` | Список товаров |
| `get_stats()` | Объект статистики |
| Backend 500 | None / пустой список |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все тесты зелёные | 100% |
| Покрытие handlers.py | ≥ 80% |
| Покрытие notifier.py | ≥ 80% |
| Нет обращений к реальному Telegram API | 0 |
| Парсинг `/add` команды | Все варианты корректны |

## Метрики

| Метрика | Цель |
|---------|------|
| Парсинг `/add` с ценой и доставкой | Корректный в 100% случаев |
| Формирование уведомления | < 100 мс |
| Цикл notifier | Интервал ± 5 сек |
| Обработка недоступности Backend | Graceful, без crash |

## Запуск

```bash
cd part4-telegram
pip install pytest pytest-asyncio pytest-cov aioresponses
pytest tests/ -v --cov=src --cov-report=term-missing
```
