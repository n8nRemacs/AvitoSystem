# Part 5: Token Bridge — План тестирования

## Инструменты

- **pytest**
- **unittest.mock** — мок docker exec, subprocess
- **responses** или **aioresponses** — мок Backend API
- **pytest-cov**

## Структура тестов

```
part5-token-bridge/
└── tests/
    ├── conftest.py              # Фикстуры: mock docker, sample XML
    ├── test_session_reader.py   # Чтение SharedPreferences
    ├── test_jwt_parser.py       # Парсинг JWT
    ├── test_backend_client.py   # HTTP к Backend
    ├── test_bridge.py           # Главный цикл
    └── fixtures/
        ├── preferences.xml      # Пример SharedPreferences XML
        ├── preferences_empty.xml # Пустой XML (нет токенов)
        └── sample_jwt.txt       # Тестовый JWT
```

## Фикстуры

### preferences.xml (тестовый)
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session">eyJhbGciOiJIUzUxMiJ9.eyJleHAiOjk5OTk5OTk5OTksInUiOjEyMzQ1Nn0.sig</string>
    <string name="fpx">A2.test_fingerprint_hex</string>
    <string name="refresh_token">abc123def456</string>
    <string name="device_id">test_device_001</string>
</map>
```

## Unit-тесты

### test_jwt_parser.py
| Тест | Ожидание |
|------|----------|
| Парсинг валидного JWT | exp, user_id корректны |
| JWT с padding-проблемами base64 | Корректный парсинг |
| Невалидный JWT (не 3 части) | None |
| Пустая строка | None |
| `get_expiry()` | Unix timestamp |
| `hours_until_expiry()` — токен свежий | > 0 |
| `hours_until_expiry()` — токен истёк | < 0 |

### test_session_reader.py
| Тест | Ожидание |
|------|----------|
| Парсинг валидного XML | SessionData со всеми полями |
| XML без session токена | None |
| XML без fingerprint | None (fingerprint обязателен) |
| XML с альтернативными именами (token, f) | Корректный fallback |
| Docker exec возвращает ошибку | None, логирование |
| Docker exec — файл не найден | None |
| Пустой XML | None |
| Попытка разных путей SharedPrefs | 3 попытки |

### test_backend_client.py
| Тест | Ожидание |
|------|----------|
| `sync_session()` — 200 | True |
| `sync_session()` — 500 | False, логирование |
| `sync_session()` — сеть недоступна | False, логирование |
| Заголовок X-Api-Key | Присутствует |

### test_bridge.py (главный цикл)
| Тест | Ожидание |
|------|----------|
| Успешное чтение и синхронизация | sync_session вызван |
| Токен не изменился | sync_session НЕ вызван |
| Токен изменился (новый exp) | sync_session вызван |
| exp < now + 7200 (< 2 часов) | Avito запускается (am start) |
| exp < now (истёк) | Avito запускается, ожидание, перечитывание |
| После запуска Avito токен обновился | Синхронизация |
| После запуска Avito токен НЕ обновился | Ошибка в логах |
| Redroid контейнер недоступен | Логирование, пропуск цикла |

## Критерии прохождения

| Критерий | Требование |
|----------|-----------|
| Все тесты зелёные | 100% |
| Покрытие jwt_parser.py | ≥ 95% |
| Покрытие session_reader.py | ≥ 85% |
| Покрытие bridge.py | ≥ 75% |
| Нет обращений к реальному Docker в тестах | 0 |

## Метрики

| Метрика | Цель |
|---------|------|
| Парсинг JWT | < 10 мс |
| Парсинг XML SharedPrefs | < 50 мс |
| Синхронизация на Backend | < 2 сек |
| Обнаружение истечения токена | Корректно в 100% |
| Docker exec latency (реальный) | < 5 сек |
| Время от обновления токена до синхронизации | < 60 сек |

## Запуск

```bash
cd part5-token-bridge
pip install pytest pytest-cov responses
pytest tests/ -v --cov=src --cov-report=term-missing
```
