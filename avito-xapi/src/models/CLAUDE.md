# avito-xapi / src / models

**Назначение:** Pydantic v2 схемы — тела запросов, ответы API, внутренние сущности.

**Статус:** working.

---

## Файлы

- `common.py` — базовые типы, общие миксины
- `tenant.py` — `Tenant`, `Toolkit`, `ApiKeyInfo`, `TenantContext` — основные сущности авторизации
- `session.py` — схемы Avito-сессии (загрузка, статус, история)
- `search.py` — `ItemCard`, `ItemImage`, `ItemDetail`, `SearchResponse`
- `messenger.py` — Channel, Message, SendMessage request/response
- `calls.py` — схемы IP-телефонии

---

## Конвенции

- Все модели — Pydantic v2 (`model_config`, `model_validator` вместо `@validator`)
- `ItemCard` — нормализованная карточка объявления: поля `id`, `title`, `price`, `images`, `url`, `seller_id`. Сырые данные нормализуются в `routers/search.py::_normalize_item_card()`
- `TenantContext` — передаётся через все роутеры как результат middleware авторизации
