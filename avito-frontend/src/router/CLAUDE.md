# avito-frontend / src / router

**Назначение:** Vue Router — маршруты и navigation guard.

**Статус:** not_used_in_v1.

---

## Файлы

- `index.js` — все маршруты + `beforeEach` guard: auth-routes требуют `localStorage.access_token`, guest-routes редиректят залогиненных на `/dashboard`

Три группы маршрутов: `guest` (login/register/verify), `auth` (dashboard/profile), `panel` (legacy xapi: auth/messenger/search/farm — без guard).
