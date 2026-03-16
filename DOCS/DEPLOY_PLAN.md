# AvitoSystem — План деплоя

**Цель:** Довести систему от "код готов" до работающего продакшена.

---

## Фаза 1: База данных (5 минут)

### 1.1. Применить миграцию

1. Открыть Supabase Dashboard:
   `https://supabase.com/dashboard/project/bkxpajeqrkutktmtmwui`
2. Перейти в **SQL Editor**
3. Вставить содержимое `supabase/migrations/001_init.sql` → **Run**
4. Вставить содержимое `supabase/migrations/002_seed.sql` → **Run**
5. Проверить: **Table Editor** → должны появиться 8 таблиц

### 1.2. Проверить RLS

В `001_init.sql` включён RLS на всех таблицах, но политик нет (backend использует anon key).
Нужно **либо**:
- Использовать **service_role key** (обходит RLS) — безопаснее
- **Либо** отключить RLS на время разработки:
  ```sql
  ALTER TABLE supervisors DISABLE ROW LEVEL SECURITY;
  ALTER TABLE toolkits DISABLE ROW LEVEL SECURITY;
  ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;
  ALTER TABLE api_keys DISABLE ROW LEVEL SECURITY;
  ALTER TABLE avito_sessions DISABLE ROW LEVEL SECURITY;
  ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY;
  ALTER TABLE farm_devices DISABLE ROW LEVEL SECURITY;
  ALTER TABLE account_bindings DISABLE ROW LEVEL SECURITY;
  ```

> **Рекомендация:** На этапе MVP — отключить RLS. В проде — переключиться на service_role key.

---

## Фаза 2: Подготовка к деплою (5 минут)

### 2.1. Git init

```bash
cd ~/Проекты/AvitoSystem
git init
git add .
git commit -m "Initial commit: full SaaS platform"
```

### 2.2. Перенос кода на homelab

**Вариант A** — через git remote (если есть GitHub/GitLab):
```bash
git remote add origin <url>
git push -u origin main
# На homelab:
git clone <url> /opt/avito-system
```

**Вариант B** — через rsync/scp:
```bash
rsync -avz --exclude='node_modules' --exclude='.env' --exclude='__pycache__' \
  ~/Проекты/AvitoSystem/ avito-homelab:/opt/avito-system/
```

### 2.3. Создать .env на homelab

```bash
ssh avito-homelab
cd /opt/avito-system/avito-xapi
cp .env.example .env
# Проверить/изменить SUPABASE_KEY если используем service_role key
nano .env
```

---

## Фаза 3: Деплой (10 минут)

### 3.1. Docker Compose

```bash
ssh avito-homelab
cd /opt/avito-system
docker compose up -d --build
```

Ожидаемый вывод:
```
✔ xapi     Built
✔ frontend Built
✔ xapi     Started
✔ frontend Started
```

### 3.2. Проверка

```bash
# Healthcheck
curl http://localhost:8080/health
# Ожидаем: {"status":"ok","version":"0.1.0"}

# Frontend
curl -I http://localhost:3000
# Ожидаем: HTTP/1.1 200 OK

# Через домен (с VPS)
curl https://avito.newlcd.ru/health
curl -I https://avito.newlcd.ru/
```

### 3.3. Проверка API с тестовым ключом

```bash
# Из seed данных: test_dev_key_123
curl -H "X-Api-Key: test_dev_key_123" \
  https://avito.newlcd.ru/api/v1/sessions/current
# Ожидаем: {"detail":"No active Avito session"} (404 — нормально, сессии нет)
```

---

## Фаза 4: Загрузка сессии Avito (15 минут)

Без активной сессии Avito мессенджер, поиск и звонки не работают.

### Вариант A: Ручная загрузка токена

1. На Android с Avito: перехватить токен через Frida/mitmproxy
2. Загрузить через API:
   ```bash
   curl -X POST https://avito.newlcd.ru/api/v1/sessions \
     -H "X-Api-Key: test_dev_key_123" \
     -H "Content-Type: application/json" \
     -d '{
       "session_token": "<JWT от Avito>",
       "device_id": "<device_id>",
       "source": "android"
     }'
   ```

### Вариант B: Через Browser Auth (Playwright)

1. Открыть `https://avito.newlcd.ru` → Dashboard
2. Перейти в раздел сессий → "Авторизация через браузер"
3. Ввести логин/пароль Avito
4. Playwright выполнит авторизацию и сохранит токен

### Вариант C: Farm Agent (позже)

Farm agent автоматически снимает и обновляет токены с рутованных устройств.

---

## Фаза 5: E2E проверка (10 минут)

### 5.1. Мессенджер

1. Открыть `https://avito.newlcd.ru` в браузере
2. Ввести API key → перейти в Messenger
3. Проверить: каналы загружаются, сообщения отображаются
4. Индикатор "Live" (зелёный) — SSE работает
5. Отправить сообщение с другого аккаунта → должно появиться без обновления

### 5.2. Поиск

1. Перейти в Search → ввести запрос
2. Результаты должны загрузиться с картинками и ценами

### 5.3. API напрямую

```bash
# Каналы
curl -H "X-Api-Key: test_dev_key_123" \
  https://avito.newlcd.ru/api/v1/messenger/channels

# SSE поток
curl -N "https://avito.newlcd.ru/api/v1/messenger/realtime/events?api_key=test_dev_key_123"

# Статус WS
curl -H "X-Api-Key: test_dev_key_123" \
  https://avito.newlcd.ru/api/v1/messenger/realtime/status
```

---

## Фаза 6: Ферма устройств (отдельная сессия)

> Это можно делать позже, когда основная система уже работает.

### 6.1. Подготовка устройства

- Android с root (Magisk/KernelSU)
- Установить Frida server
- Установить Python (Termux)

### 6.2. Снятие отпечатка

```bash
frida -U -f ru.avito -l frida_scripts/sniff_fingerprint.js --no-pause
```

Заполнить `DOCS/AVITO-FINGERPRINT.md` данными.

### 6.3. Запуск Farm Agent

```bash
# На устройстве
pip install aiohttp frida-tools
python farm_daemon.py --api-url https://avito.newlcd.ru/api/v1 --device-key <key>
```

---

## Чеклист

- [ ] Миграция SQL применена в Supabase
- [ ] RLS отключён или используется service_role key
- [ ] Код перенесён на homelab
- [ ] `.env` создан и настроен
- [ ] `docker compose up -d --build` — успешно
- [ ] `curl /health` — 200
- [ ] Frontend открывается в браузере
- [ ] API отвечает с тестовым ключом
- [ ] Сессия Avito загружена
- [ ] Мессенджер отображает каналы
- [ ] SSE индикатор "Live" работает
- [ ] Отправка/получение сообщений работает
- [ ] Поиск возвращает результаты

---

## Возможные проблемы и решения

| Проблема | Решение |
|----------|---------|
| `docker compose build` падает на curl_cffi | Убедиться что в Dockerfile установлен `gcc` и `libcurl4-openssl-dev` |
| Supabase RLS блокирует запросы | Отключить RLS или использовать service_role key |
| SSE не работает через nginx | Проверить `X-Accel-Buffering: no` в ответе и `proxy_buffering off` в nginx |
| WebSocket к Avito не подключается | Проверить что сессия активна и не истекла; проверить TLS fingerprint |
| Frontend не видит API | Проверить CORS_ORIGINS в .env и nginx proxy_pass |
| Порт 8080/3000 не проброшен | Проверить ssh-tunnel.service на homelab (уже настроен) |
