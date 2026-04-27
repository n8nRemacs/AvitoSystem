# tenant-auth / tests

**Назначение:** Pytest-тесты сервиса аутентификации.

**Статус:** WIP. Минимальное покрытие (health, auth flow, jwt_service).

---

## Файлы

- `conftest.py` — фикстуры: mock Supabase, тестовые пользователи
- `test_health.py` — проверка `/health`
- `test_auth.py` — регистрация, OTP flow, получение токенов
- `test_jwt_service.py` — создание и валидация JWT

---

## Запуск

```bash
cd tenant-auth
pytest tests/ -v
```
