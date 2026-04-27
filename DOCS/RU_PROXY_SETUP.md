# RU-прокси для запросов к Avito

## Зачем

Avito firewall (QRATOR) режет любые запросы с зарубежных IP к `www.avito.ru`, `m.avito.ru` и публичным каталогам — даже Chrome120-impersonate возвращает HTTP 429. Официальный API `api.avito.ru` пропускает любые IP, но он не покрывает поиск чужих объявлений и публичные XML-каталоги.

Решение для разработки и V1-polling — **SOCKS5-туннель через homelab** (`213.108.170.194`, Россия, Нариманов).

## Запуск туннеля

В терминале разработчика (Windows / Linux / macOS, где есть SSH-доступ к homelab):

```bash
ssh -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
    -D 127.0.0.1:1081 -N -f homelab
```

- `-D 1081` — SOCKS5-сервер на порту 1081 (порт 1080 занят xray для anthropic)
- `-N` — без выполнения команд, чистый туннель
- `-f` — в фон после auth
- `ServerAliveInterval=30` — keepalive раз в 30 секунд

Порт 1081 произвольный — можно любой свободный.

## Использование

### curl
```bash
curl --socks5-hostname 127.0.0.1:1081 https://avito.ru/...
```

### Python httpx
```python
import httpx
client = httpx.AsyncClient(proxy="socks5://127.0.0.1:1081")
```

(нужен `httpx[socks]` или установленный `httpx-socks`)

### Python curl_cffi
```python
from curl_cffi import requests
r = requests.get(url, impersonate="chrome120", proxy="socks5://127.0.0.1:1081")
```

## Проверка работоспособности

```bash
curl -s --socks5-hostname 127.0.0.1:1081 https://ifconfig.me
# должно вернуть 213.108.170.194
```

## Остановка туннеля

```bash
# Linux/Mac
pkill -f "ssh.*-D.*1081"

# Windows (если запущен через bash):
# найти PID
ps -ef | grep "ssh.*1081"
# kill <PID>
```

## Когда туннель не нужен

- Запросы к `https://api.anthropic.com` — идут через xray (Финляндия) на :10808
- Запросы к `https://api.avito.ru` — пропускают любой IP, можно идти напрямую
- Запросы к `https://api.openrouter.ai`, `https://api.telegram.org` — не блокируются
- **Прод-деплой на homelab** — там Avito-запросы уже идут с РФ IP, прокси не нужен. Туннель — только для локальной разработки с зарубежной машины.

## Подтверждённо работающие через прокси Avito-эндпоинты

- `https://avito.ru/web/1/catalogs/content/feed/phone_catalog.xml` — 524 бренда / 16149 моделей телефонов
- `https://avito.ru/web/1/catalogs/content/feed/tablets.xml` — 486 брендов / 7391 моделей планшетов
- `https://avito.ru/web/1/catalogs/content/feed/brendy_fashion.xml` — 7522 fashion-бренда (для смарт-часов)
- `https://www.avito.ru/all/...` — страницы поиска (для парсинга выдачи в V1)
- `https://m.avito.ru/api/...` — внутренние JSON-эндпоинты SPA сайта

## Автозапуск (опционально)

Чтобы туннель восстанавливался автоматически — `autossh`:

```bash
autossh -M 0 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -D 127.0.0.1:1081 -N -f homelab
```

Или через `~/.ssh/config`:

```
Host homelab-tunnel
    HostName 213.108.170.194
    User root
    DynamicForward 127.0.0.1:1081
    ServerAliveInterval 30
    ExitOnForwardFailure yes
```

Затем: `ssh -N -f homelab-tunnel`.
