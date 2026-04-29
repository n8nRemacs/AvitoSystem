# avito-frontend / src / views

**Назначение:** Страницы Vue Router. Каждый файл — верхнеуровневый компонент-страница.

**Статус:** not_used_in_v1 (весь avito-frontend вне скоупа V1).

---

## Страницы

- `LoginView.vue` — форма входа → OTP-запрос через tenant-auth
- `RegisterView.vue` — регистрация нового тенанта
- `VerifyOtpView.vue` — ввод OTP-кода, получение токенов
- `DashboardView.vue` — главная после логина
- `ProfileView.vue` — профиль тенанта
- `AuthView.vue` — управление Avito-сессиями (legacy xapi panel)
- `MessengerView.vue` — мессенджер Avito (legacy xapi panel)
- `SearchView.vue` — поиск объявлений (legacy xapi panel)
- `FarmView.vue` — token farm устройства (legacy xapi panel)
