# AvitoSystem — Reference Documentation Index

**Создано:** 2026-04-28 (компиляция из всех source-файлов перед удалением старых ТЗ)
**Назначение:** Structured knowledge base по реверс-инжинирингу Avito API, Android-setup и auth.

---

## Файлы в этой папке

### `01-avito-api.md` — API Reference
Полный справочник Avito API (мобильный реверс + официальный).

Когда обращаться:
- Хочешь узнать endpoint для поиска, подписок, деталей лота, мессенджера
- Нужна точная структура заголовков и параметров запросов
- Ищешь какой метод делает что в нашем коде (`avito-xapi/src/workers/http_client.py`)

### `02-auth-and-tokens.md` — Auth & Session Lifecycle
JWT-структура, refresh flow, ban detection, multi-account pool.

Когда обращаться:
- Вопросы про истечение/обновление токенов
- Как работает AvitoSessionManager APK и device_commands
- Настройка нового аккаунта в pool
- Что делать при бане (403 flow)

### `03-android-setup.md` — Android Device Setup
Физическая инфраструктура: OnePlus 8T, System Clone, Magisk, ADB passthrough.

Когда обращаться:
- Добавить новый Android-user (System Clone)
- Выдать Magisk root grant новому APK
- Настроить ADB из LXC-контейнера
- Проблемы с NotificationListener

### `04-reverse-engineering-howto.md` — Методология реверс-инжиниринга
Пошаговый гайд по инструментам, процессу и подводным камням при реверсе Avito Android APK.

Когда обращаться:
- Нужно открыть новый endpoint который ещё не задокументирован
- Настроить jadx / frida-server / curl_cffi с нуля
- Понять почему QRATOR блокирует и что делать
- Нужна инструкция по extraction токенов с устройства
- Хочешь повторить autosearch-реверс на новой версии APK

---

## Дополнительные source-файлы (не в этой папке)

| Файл/Папка | Что там | Обновляется ли |
|---|---|---|
| `DOCS/avito_api_snapshots/` | JSON/XML-снимки Official API (categories_tree.json, fields_*.json, phone_catalog.xml) | Нет (2026-04-25 snapshot) |
| `DOCS/avito_api_snapshots/autosearches/README.md` | Полный реверс /5/subscriptions + /2/subscriptions/{id} с live-validated примерами | Нет |
| `DOCS/superpowers/specs/2026-04-28-account-pool-design.md` | Детальный design spec AccountPool (state machine, DB schema, error matrix, testing) | Нет |
| `DOCS/DECISIONS.md` | ADR-001..011 — архитектурные решения с контекстом | Да |
| `CONTINUE.md` | Актуальный статус сессии, operational заметки, команды | Да |

---

## Удалённые файлы (содержимое перенесено сюда)

После создания этих файлов удалены:
- `DOCS/AVITO-API.md` → в `01-avito-api.md`
- `DOCS/REVERSE-GUIDE.md` → в `01-avito-api.md` (QRATOR, Frida-подходы)
- `DOCS/AVITO-FINGERPRINT.md` → в `01-avito-api.md` (fingerprint) + `03-android-setup.md`
- `DOCS/X-API.md` → в `01-avito-api.md` (xapi endpoints)
- `DOCS/token_farm_system.md` → в `02-auth-and-tokens.md` + `03-android-setup.md`
- `DOCS/TENANT_AUTH_SYSTEM.md` → выжимка в `02-auth-and-tokens.md`
