# tenant-auth / src / services

**Назначение:** Бизнес-логика сервиса аутентификации. Роутеры тонкие — вся логика здесь.

**Статус:** WIP.

---

## Файлы

- `jwt_service.py` — `create_access_token(user_id, tenant_id, role)` → JWT HS256, `create_refresh_token()` → SHA-256 хэш в Supabase `refresh_tokens`
- `otp_service.py` — генерация и верификация OTP-кодов, делегирование доставки в `OtpProvider`
- `user_service.py` — создание пользователя, поиск по email/phone, обновление профиля
- `api_key_service.py` — генерация, хэширование (SHA-256), хранение и ротация API-ключей
- `billing_service.py` — логика подписки и лимитов
- `invite_service.py` — создание и погашение инвайт-кодов
- `notification_service.py` — сохранение настроек уведомлений

---

## Конвенции

- JWT payload: `{sub: user_id, tenant_id, role, type: "access", exp, iat}` — одинаков с тем, что xapi ожидает в Bearer-токенах
- Refresh-токены хранятся как SHA-256 хэш в Supabase (не сам токен)
