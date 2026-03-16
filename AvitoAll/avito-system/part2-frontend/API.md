# Part 2: Frontend (Web Panel) — Описание и API

## Назначение

Веб-интерфейс для управления системой мониторинга. Позволяет добавлять/удалять поиски, настраивать AI-правила, просматривать найденные товары и диалоги с продавцами.

## Функционал

- **Управление поисками** — CRUD поисковых запросов (модель устройства, вилка цены, доставка)
- **Управление AI-правилами** — включение/выключение предустановленных, добавление своих
- **Просмотр результатов** — лента товаров с AI-вердиктами, фильтрация
- **Просмотр диалогов** — история переписок, смена статусов сделок
- **Мониторинг статуса** — валидность токенов, статистика системы

## Что получает (от Backend API)

| Endpoint | Что получает | Где используется |
|----------|-------------|------------------|
| `GET /api/v1/searches` | Список поисков | Страница Поиски |
| `GET /api/v1/rules` | Список AI-правил | Страница Правила |
| `GET /api/v1/items` | Найденные товары | Страница Результаты |
| `GET /api/v1/dialogs` | Диалоги с продавцами | Страница Диалоги |
| `GET /api/v1/stats` | Статистика системы | Страница Статус |

## Что отправляет (на Backend API)

| Действие | Endpoint | Данные |
|----------|----------|--------|
| Создать поиск | `POST /api/v1/searches` | `{query, price_min, price_max, delivery, location_id}` |
| Обновить поиск | `PUT /api/v1/searches/{id}` | `{enabled, price_min, ...}` |
| Удалить поиск | `DELETE /api/v1/searches/{id}` | — |
| Создать правило | `POST /api/v1/rules` | `{text}` |
| Обновить правило | `PUT /api/v1/rules/{id}` | `{enabled}` |
| Удалить правило | `DELETE /api/v1/rules/{id}` | — |
| Обновить статус диалога | `PUT /api/v1/dialogs/{id}` | `{status}` |

---

## Страницы и компоненты

### /searches — Управление поисками

**Функционал:**
- Таблица с колонками: Запрос, Цена от-до, Доставка, Статус, Действия
- Кнопка "Добавить поиск" → модальная форма
- Toggle enabled для каждой строки
- Кнопка удаления (с подтверждением)

**Форма создания поиска (SearchForm):**

| Поле | Тип | Обязательное | Default | Описание |
|------|-----|--------------|---------|----------|
| query | text | Да | — | Название устройства (iPhone 12 Pro) |
| price_min | number | Нет | null | Минимальная цена |
| price_max | number | Нет | null | Максимальная цена |
| delivery | checkbox | Нет | true | Только с Авито Доставкой |
| location_id | select | Нет | 621540 | Регион (Вся Россия / Москва / ...) |

**Валидация:**
- `query` не пустой
- `price_min` ≤ `price_max` (если оба заданы)

---

### /rules — AI-правила (красные флаги)

**Функционал:**
- Список правил: текст, тип (предустановленное/пользовательское), вкл/выкл
- Предустановленные отмечены иконкой 🔒, нельзя удалить
- Toggle enabled для любого правила
- Кнопка удаления только для пользовательских
- Форма добавления: текстовое поле + кнопка

**Предустановленные правила (создаются Backend при инициализации):**
1. iCloud Lock / Activation Lock — пропустить
2. Разбит экран / трещины дисплея — пропустить
3. Разбита задняя крышка — пропустить
4. Не включается / чёрный экран — пропустить
5. Подозрительно низкая цена (< 30% от рыночной) — предупредить
6. Продавец без отзывов / рейтинг < 3.0 — предупредить

---

### /items — Результаты (найденные товары)

**Функционал:**
- Лента карточек товаров
- Фильтры: по поиску (dropdown), по вердикту (OK/RISK/SKIP/Все)
- Пагинация или infinite scroll
- Сортировка: новые первыми

**Карточка товара (ItemCard):**

| Элемент | Источник | Описание |
|---------|----------|----------|
| Фото | `image_urls[0]` | Превью товара |
| Название | `title` | Заголовок объявления |
| Цена | `price` | Форматированная цена (15 000 ₽) |
| Город | `location` | Местоположение |
| Вердикт | `ai_verdict` | Бейдж: OK (зелёный), RISK (жёлтый), SKIP (красный) |
| Оценка | `ai_score` | Число 1-10 |
| Описание AI | `ai_summary` | Краткое описание от AI |
| Дефекты | `ai_defects` | Список найденных проблем |
| Доставка | `delivery` | Иконка 📦 если true |
| Приветствие | `greeted` | ✉️ если отправлено |
| Зарезервирован | `reserved` | 🔒 если true |
| Ссылка | `url` | Кнопка "Открыть на Avito" |

---

### /dialogs — Диалоги с продавцами

**Функционал:**
- Список диалогов: товар, продавец, статус, дата
- Клик → раскрытие истории сообщений
- Dropdown для смены статуса

**Статусы диалога:**
| Статус | Описание | Цвет |
|--------|----------|------|
| new | Создан, приветствие не отправлено | серый |
| greeted | Приветствие отправлено | синий |
| replied | Продавец ответил | голубой |
| deal | Договорились о сделке | зелёный |
| shipped | Товар отправлен | оранжевый |
| done | Сделка завершена | зелёный (темнее) |

---

### /status — Статус системы

**Функционал:**
- Статус токена: ✅ валиден / ⚠️ скоро истечёт / ❌ истёк
- Часов до истечения
- Время последней синхронизации
- Счётчики: активных поисков, найдено сегодня, всего товаров
- Диаграмма распределения по вердиктам

**Данные из `GET /api/v1/stats`:**
```
token_valid: true → зелёный индикатор
token_hours_left: 12.5 → "Осталось 12ч 30мин"
searches_active: 5 → "5 активных поисков"
items_today: 12 → "12 товаров сегодня"
items_by_verdict: {OK: 30, RISK: 50, SKIP: 65} → pie chart
```

---

## HTTP-клиент (api.js)

```javascript
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const API_KEY = import.meta.env.VITE_API_KEY

async function request(method, path, body = null) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': API_KEY
    }
  }
  if (body) options.body = JSON.stringify(body)

  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `${response.status} ${response.statusText}`)
  }

  return response.json()
}

export const api = {
  // Searches
  getSearches: (enabled) =>
    request('GET', `/api/v1/searches${enabled !== undefined ? `?enabled=${enabled}` : ''}`),
  createSearch: (data) =>
    request('POST', '/api/v1/searches', data),
  updateSearch: (id, data) =>
    request('PUT', `/api/v1/searches/${id}`, data),
  deleteSearch: (id) =>
    request('DELETE', `/api/v1/searches/${id}`),

  // Rules
  getRules: () =>
    request('GET', '/api/v1/rules'),
  createRule: (text) =>
    request('POST', '/api/v1/rules', { text }),
  updateRule: (id, data) =>
    request('PUT', `/api/v1/rules/${id}`, data),
  deleteRule: (id) =>
    request('DELETE', `/api/v1/rules/${id}`),

  // Items
  getItems: ({ verdict, searchId, limit, offset } = {}) => {
    const params = new URLSearchParams()
    if (verdict) params.append('verdict', verdict)
    if (searchId) params.append('search_id', searchId)
    if (limit) params.append('limit', limit)
    if (offset) params.append('offset', offset)
    return request('GET', `/api/v1/items?${params}`)
  },
  getItem: (id) =>
    request('GET', `/api/v1/items/${id}`),

  // Dialogs
  getDialogs: (status) =>
    request('GET', `/api/v1/dialogs${status ? `?status=${status}` : ''}`),
  updateDialogStatus: (channelId, status) =>
    request('PUT', `/api/v1/dialogs/${channelId}`, { status }),

  // Stats
  getStats: () =>
    request('GET', '/api/v1/stats')
}
```

---

## Переменные окружения (.env)

```env
VITE_API_URL=http://localhost:8080
VITE_API_KEY=avito_sync_key_2026
```

---

## Что возвращает (пользователю)

Отображает данные в виде:
- Таблиц (поиски, правила, диалоги)
- Карточек (товары)
- Дашборда (статистика)
- Модальных форм (создание/редактирование)
- Toast-уведомлений (успех/ошибка операций)
