# avito-xapi / tests

**Назначение:** Pytest-тесты для всех роутеров и worker-модулей.

**Статус:** working. Все тесты должны проходить без реального Supabase.

---

## Структура

- `conftest.py` — вся тестовая инфраструктура: `make_mock_sb()`, `make_authed_sb()`, `run_request()`, `make_test_jwt()`
- `fixtures/` — JSON-снимки реальных ответов Avito API (calls, channels, messages, search, mock_session). Только данные, без кода
- `test_auth_middleware.py`, `test_sessions.py`, `test_search.py` и др. — покрытие роутеров
- `test_jwt_parser.py`, `test_rate_limiter.py`, `test_token_monitor.py`, `test_ws_manager.py`, `test_session_reader.py` — unit-тесты workers

---

## Запуск

```bash
cd avito-xapi
pytest tests/ -v
pytest tests/test_search.py -v  # отдельный модуль
```

---

## Конвенции

- Все Supabase-вызовы мокируются через `make_authed_sb(*endpoint_data)`. Middleware делает ровно 4 запроса (api_key, tenant, toolkit, update last_used), затем следуют ответы эндпоинта
- `run_request()` — helper, патчит все точки инъекции `get_supabase` сразу и запускает `TestClient`
- `fixtures/` — не трогать, это снимки реальных ответов Avito. CLAUDE.md там не нужен
- Тесты не требуют интернета и реального Supabase
