# avito-xapi / src / middleware

**Назначение:** Starlette middleware — авторизация и глобальная обработка ошибок.

**Статус:** working.

---

## Файлы

- `auth.py` — `ApiKeyAuthMiddleware`: проверяет `X-Api-Key` (SHA-256 хэш → Supabase `api_keys`), поддерживает Bearer JWT от tenant-auth. Строит `TenantContext`. Декоратор `require_feature(feature_name)` для per-endpoint проверки фича-флагов тенанта
- `error_handler.py` — `ErrorHandlerMiddleware`: перехватывает непойманные исключения, возвращает JSON `{"detail": "..."}` с нужным HTTP статусом

---

## Порядок middleware в main.py

`ErrorHandlerMiddleware` → `ApiKeyAuthMiddleware` → `CORSMiddleware` (outermost = first).

---

## Конвенции

- После успешной авторизации middleware обновляет `api_keys.last_used_at` (4-й Supabase-запрос в последовательности). Это важно для тестов: `make_authed_sb()` в conftest.py ожидает ровно 4 запроса авторизации перед данными эндпоинта
- Публичные пути (`/health`, `/ready`, `/docs`, `/openapi.json`) — без авторизации, проверяются в начале middleware
