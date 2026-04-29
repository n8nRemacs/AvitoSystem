# tenant-auth

**Назначение:** Отдельный микросервис аутентификации тенантов. Регистрация/вход через OTP (email, SMS, Telegram, VK, WhatsApp), выдача JWT access + refresh токенов, управление профилями, биллингом, инвайтами и API-ключами.

**Статус:** WIP. Структура готова, основные роутеры реализованы. В V1 используется как инфраструктурный компонент (не для конечного пользователя напрямую — для управления тенантами xapi).

**Стек:** Python 3.12, FastAPI, Pydantic v2, PyJWT (HS256), Supabase PostgREST (облачный проект `dskhyumhxgbzmuefmrax`).

---

## Структура

```
src/
  main.py         — FastAPI app, порт 8090
  config.py       — pydantic-settings
  providers/      — OTP-провайдеры (email, sms, telegram, vk_max, whatsapp, console)
  routers/        — эндпоинты: auth, profile, api_keys, sessions, invites, billing, notifications, tenant_params
  services/       — бизнес-логика: jwt_service, otp_service, user_service, billing_service, invite_service, api_key_service, notification_service
  models/         — Pydantic-схемы
  middleware/     — JwtAuthMiddleware, ErrorHandlerMiddleware
  storage/        — supabase.py (аналогичная обёртка как в xapi)
tests/
  test_auth.py, test_health.py, test_jwt_service.py
```

---

## Точки входа

```bash
cd tenant-auth
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8090
pytest tests/ -v
```

---

## Связи

- **Вызывают:** avito-xapi (verifies Bearer JWT), avito-frontend (авторизация пользователей)
- **Supabase:** облачный проект `dskhyumhxgbzmuefmrax` (не self-hosted). Connection string — в глобальном CLAUDE.md
- **Порт:** 8090 (Docker)
- **JWT_SECRET:** общий с avito-xapi — из глобального CLAUDE.md

---

## Конвенции / предупреждения

- OTP провайдеры реализуют `OtpProvider` ABC из `providers/base.py`. `console.py` — dev-провайдер (печатает в stdout)
- `services/jwt_service.py` — создаёт access token с payload `{sub, tenant_id, role, type, exp, iat}`
- `tenant-auth.zip` в корне папки — архив для деплоя, не редактировать вручную
- Суpabase проект отличается от используемого в xapi (разные URL/ключи). Смотри глобальный CLAUDE.md
- `middleware/jwt_auth.py` — проверяет только JWT, не API-ключи (в отличие от xapi)

---

## Связано с ТЗ V1

Не является частью V1 дашборда напрямую (V1 — один пользователь, без публичной регистрации). Используется для управления тенантами xapi. Актуален для V3 (мультипользовательский режим).
