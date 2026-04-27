# avito-frontend

**Назначение:** Vue 3 SPA — панель управления тенанта: авторизация через tenant-auth, управление Avito-сессиями, поиск, мессенджер, token farm.

**Статус:** not_used_in_v1. V1 требует HTMX-дашборд (сервер-рендеринг), а не SPA. Этот фронтенд — референс для UX-паттернов и компонентного состава.

**Стек:** Vue 3, Vite, Pinia, Tailwind CSS, Naive UI, Vue Router.

---

## Структура

```
src/
  views/       — страницы: Login, Register, VerifyOtp, Dashboard, Profile, Auth, Messenger, Search, Farm
  components/  — UI-компоненты по доменам: auth/, farm/, layout/, messenger/, search/
  stores/      — Pinia stores: auth, tenant, search, messenger, farm
  router/      — index.js (маршруты + navigation guard)
  api/         — index.js (базовый HTTP клиент), tenant-auth.js (методы auth API)
```

---

## Маршруты

- `/login`, `/register`, `/verify` — guest (без токена)
- `/dashboard`, `/profile` — auth (требует access_token)
- `/auth`, `/messenger`, `/search`, `/farm` — "legacy xapi panel" (без guard, просто panel)

---

## Точки входа

```bash
cd avito-frontend
npm install
npm run dev      # dev server :5173
npm run build    # dist/
docker compose up frontend  # nginx :3000
```

---

## Конвенции / предупреждения

- Токен хранится в `localStorage` (`access_token`) — navigation guard проверяет его наличие
- В V1 **не использовать** этот фронтенд — он выброшен из скоупа (ТЗ раздел 2.3: HTMX + Jinja2)
- Может служить референсом: компоненты мессенджера, search-форма, farm UI — как образец UX для HTMX-шаблонов
- `AvitoView.vue` и `ScannedItemsView.vue` физически лежат в `AvitoBayer/` (не здесь) — Vue-компоненты прототипа

---

## Связано с ТЗ V1

ТЗ раздел 2.3 явно указывает: HTMX, не SPA. Этот фронтенд — архив/референс. Для V1 создаётся новый `avito-monitor/templates/` на Jinja2+HTMX.
