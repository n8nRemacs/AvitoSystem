# tenant-auth / src / models

**Назначение:** Pydantic v2 схемы запросов и ответов сервиса аутентификации.

**Статус:** WIP.

---

## Файлы

- `auth.py` — RegisterRequest, LoginRequest, OtpVerifyRequest, TokenResponse
- `user.py` — UserProfile, UpdateProfileRequest
- `api_key.py` — ApiKeyCreate, ApiKeyResponse
- `billing.py` — SubscriptionInfo, PaymentRecord
- `invite.py` — InviteCreate, InviteResponse
- `notification.py` — NotificationSettings
- `common.py` — базовые типы и миксины
