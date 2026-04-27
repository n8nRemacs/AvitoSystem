# supabase

**Назначение:** SQL-миграции базовой схемы AvitoSystem (не Alembic, прямой SQL для Supabase).

**Статус:** working. Схема применена в Supabase проекте `bkxpajeqrkutktmtmwui` (используется avito-xapi).

---

## migrations/

| Файл | Содержимое |
|---|---|
| `001_init.sql` | Основные таблицы: `supervisors`, `toolkits`, `tenants`, `api_keys`, `avito_sessions` |
| `002_seed.sql` | Тестовые данные: TEST_SUPERVISOR, TEST_TOOLKIT, TEST_TENANT, TEST_API_KEY (соответствует `conftest.py` в xapi) |
| `003_tenant_auth.sql` | Таблицы для tenant-auth: `users`, `refresh_tokens`, `invites`, `billing_records` |
| `004_tenant_auth_seed.sql` | Seed-данные для tenant-auth |

---

## Применение миграций

```bash
# Через psql (Supabase cloud)
psql "postgresql://postgres.bkxpajeqrkutktmtmwui:...@aws-1-eu-central-1.pooler.supabase.com:5432/postgres" \
  -f supabase/migrations/001_init.sql

# Или через Supabase Studio SQL Editor
```

Connection strings — в глобальном `c:\Projects\Sync\CLAUDE.md`.

---

## Конвенции / предупреждения

- Это **не** Alembic. Для V1 планируется переход на Alembic (ТЗ раздел 2.1)
- `002_seed.sql` создаёт те же UUID-константы, что используются в `avito-xapi/tests/conftest.py`. При изменении seed — обновлять и тесты
- Для AvitoBayer используется **другая** БД (Supabase self-hosted 213.108.170.194:8000), схема в `AvitoBayer/migration_leads.sql`
