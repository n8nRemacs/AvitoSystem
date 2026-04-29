# tenant-auth / src / storage

**Назначение:** PostgREST-клиент для Supabase. Идентичен по устройству `avito-xapi/src/storage/supabase.py`.

**Статус:** WIP.

---

## Файлы

- `supabase.py` — `QueryBuilder`, `SupabaseClient`, `get_supabase()` singleton

Подключается к Supabase **облачного** проекта `dskhyumhxgbzmuefmrax` (не self-hosted). URL и SERVICE_ROLE_KEY берутся из `.env` / глобального `CLAUDE.md`.

Используется: `services/jwt_service.py` (refresh_tokens), `services/user_service.py`, `services/api_key_service.py`.
