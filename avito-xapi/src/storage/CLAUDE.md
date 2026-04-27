# avito-xapi / src / storage

**Назначение:** Лёгкий PostgREST клиент для Supabase. Заменяет тяжёлый `supabase-py`.

**Статус:** working.

---

## Файлы

- `supabase.py` — `QueryBuilder` (chainable: `.select().eq().order().limit().execute()`), `SupabaseClient`, `get_supabase()` singleton, `QueryResult(data, count)`

---

## Конвенции

- API намеренно имитирует `supabase-py` для лёгкой миграции: `sb.table("x").select("*").eq("id", v).execute()`
- Использует **синхронный** `httpx.Client` — вся кодовая база xapi синхронная на уровне storage
- `get_supabase()` возвращает синглтон — один httpx.Client на весь процесс
- Причина замены supabase-py: конфликт зависимостей `gotrue` на Python 3.14+
- В тестах патчится через `patch("src.storage.supabase.get_supabase", return_value=mock_sb)`
