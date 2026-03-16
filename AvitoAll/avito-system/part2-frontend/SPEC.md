# Part 2: Web Panel (Frontend)

## Обзор

Веб-панель для управления системой мониторинга. SPA на Vue 3.

**Порт:** 3000
**Стек:** Vue 3 + Vite + TailwindCSS
**Папка:** `part2-frontend/`

## Структура файлов

```
part2-frontend/
├── SPEC.md
├── package.json
├── vite.config.js
├── index.html
├── .env.example
└── src/
    ├── main.js
    ├── App.vue
    ├── api.js               # HTTP-клиент к Backend API
    ├── router.js             # Vue Router
    ├── components/
    │   ├── Layout.vue        # Навигация + layout
    │   ├── SearchForm.vue    # Форма добавления поиска
    │   ├── RuleForm.vue      # Форма добавления правила
    │   ├── ItemCard.vue      # Карточка товара с вердиктом
    │   └── StatusBadge.vue   # Цветной бейдж (OK/RISK/SKIP)
    └── views/
        ├── SearchesView.vue  # Управление поисками
        ├── RulesView.vue     # AI-правила (красные флаги)
        ├── ItemsView.vue     # Лента найденных товаров
        ├── DialogsView.vue   # Диалоги с продавцами
        └── StatusView.vue    # Статус системы
```

## .env.example

```env
VITE_API_URL=http://localhost:8080
VITE_API_KEY=avito_sync_key_2026
```

## Страницы

### 1. Поиски (SearchesView.vue) — `/searches`

**Функционал:**
- Таблица всех поисков: query, цена мин-макс, доставка, вкл/выкл
- Кнопка "Добавить поиск" → модальная форма
- Переключатель enabled для каждого поиска
- Кнопка удаления

**Форма добавления (SearchForm.vue):**
- `query` — текстовое поле, обязательное (название устройства)
- `price_min` — число, опционально
- `price_max` — число, опционально
- `delivery` — чекбокс, по умолчанию включен
- `location_id` — выпадающий список (Вся Россия = 621540, Москва = 637640)

**API:**
- GET `/api/v1/searches` → список
- POST `/api/v1/searches` → создать
- PUT `/api/v1/searches/{id}` → обновить
- DELETE `/api/v1/searches/{id}` → удалить

### 2. AI-правила (RulesView.vue) — `/rules`

**Функционал:**
- Список правил: текст, предустановленное/пользовательское, вкл/выкл
- Предустановленные правила нельзя удалить, можно выключить
- Кнопка "Добавить правило" → текстовое поле
- Переключатель enabled

**API:**
- GET `/api/v1/rules` → список
- POST `/api/v1/rules` → создать
- PUT `/api/v1/rules/{id}` → обновить
- DELETE `/api/v1/rules/{id}` → удалить

### 3. Результаты (ItemsView.vue) — `/items`

**Функционал:**
- Лента карточек товаров, сортировка по дате (новые сверху)
- Фильтры: по поиску, по вердикту (OK/RISK/SKIP/все)
- Карточка товара (ItemCard.vue):
  - Фото (первое фото из image_urls)
  - Название, цена, город
  - Цветной бейдж вердикта: OK (зелёный), RISK (жёлтый), SKIP (красный)
  - AI-оценка (1-10)
  - AI-summary (краткое описание)
  - Дефекты (список)
  - Статус: отправлено приветствие? зарезервирован?
  - Ссылка на Avito

**API:**
- GET `/api/v1/items?search_id=&verdict=&limit=50&offset=0`

### 4. Диалоги (DialogsView.vue) — `/dialogs`

**Функционал:**
- Список диалогов: товар, продавец, статус, дата
- Клик → раскрытие истории сообщений
- Смена статуса: new → greeted → replied → deal → shipped → done

**API:**
- GET `/api/v1/dialogs`
- PUT `/api/v1/dialogs/{channel_id}`

### 5. Статус (StatusView.vue) — `/status`

**Функционал:**
- Статус токенов: валиден / истекает / истёк, часов осталось
- Статистика: поисков активных, товаров найдено, диалогов
- Распределение по вердиктам (пай-чарт или бары)

**API:**
- GET `/api/v1/stats`

## HTTP-клиент (api.js)

```javascript
const API_URL = import.meta.env.VITE_API_URL
const API_KEY = import.meta.env.VITE_API_KEY

async function request(method, path, body) {
  const resp = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': API_KEY
    },
    body: body ? JSON.stringify(body) : undefined
  })
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`)
  return resp.json()
}

export const api = {
  getSearches: () => request('GET', '/api/v1/searches'),
  createSearch: (data) => request('POST', '/api/v1/searches', data),
  updateSearch: (id, data) => request('PUT', `/api/v1/searches/${id}`, data),
  deleteSearch: (id) => request('DELETE', `/api/v1/searches/${id}`),
  // ... аналогично для rules, items, dialogs, stats
}
```

## Vite Config

```javascript
export default {
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8080'  // Проксирование к бэкенду в dev
    }
  }
}
```

## UI/UX

- **Тёмная тема** (опционально, как дефолт)
- **TailwindCSS** для стилей
- **Адаптивный** — работает на мобильных
- **Минимализм** — без лишних элементов

## Зависимости (package.json)

```json
{
  "dependencies": {
    "vue": "^3.4",
    "vue-router": "^4.2"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.5",
    "vite": "^5.0",
    "tailwindcss": "^3.4",
    "autoprefixer": "^10.4",
    "postcss": "^8.4"
  }
}
```

## Запуск

```bash
cd part2-frontend
npm install
cp .env.example .env
npm run dev
# → http://localhost:3000
```
