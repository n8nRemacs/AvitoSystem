# Расширение X-API — Добавление новых эндпоинтов

Инструкция по добавлению новых возможностей в X-API, когда мы реверсим новый функционал Avito.

---

## Содержание

1. [Алгоритм реверс-инжиниринга нового эндпоинта Avito](#часть-1-алгоритм-реверс-инжиниринга)
2. [Добавление нового эндпоинта в X-API (5 шагов)](#часть-2-добавление-в-x-api)
3. [Шаблоны кода](#часть-3-шаблоны-кода)
4. [Чеклист](#чеклист)

---

## Часть 1: Алгоритм реверс-инжиниринга

### Шаг 1: Определить цель

Что именно нужно перехватить? Примеры:
- Как Avito показывает карточку товара (endpoint + формат)
- Как работает поиск по категориям
- Как загружается фото в чат
- Как работает система отзывов

### Шаг 2: Подготовить Frida

Подключить Frida к Avito на рутованном устройстве:

```bash
# На устройстве (запустить frida-server)
adb shell "su -c '/data/local/tmp/frida-server &'"

# На ПК (подключиться к процессу)
frida -U com.avito.android -l script.js
```

### Шаг 3: Перехват HTTP трафика

Использовать скрипт `http_capture.js` для перехвата OkHttp запросов:

```javascript
// http_capture.js — базовый скрипт перехвата
Java.perform(function() {
    var RealCall = Java.use("okhttp3.internal.connection.RealCall");

    RealCall.execute.implementation = function() {
        var request = this.request();
        var url = request.url().toString();
        var method = request.method();
        var headers = request.headers();
        var body = null;

        if (request.body() != null) {
            var buffer = Java.use("okio.Buffer").$new();
            request.body().writeTo(buffer);
            body = buffer.readUtf8();
        }

        console.log("\n=== HTTP REQUEST ===");
        console.log("Method: " + method);
        console.log("URL: " + url);
        console.log("Headers: " + headers.toString());
        if (body) console.log("Body: " + body);

        var response = this.execute();

        console.log("=== HTTP RESPONSE ===");
        console.log("Code: " + response.code());
        // Тело ответа нужно читать осторожно (один раз!)

        return response;
    };
});
```

### Шаг 4: Перехват WebSocket трафика

Для WS методов использовать `ws_full_capture.js`:

```javascript
// ws_full_capture.js — перехват WebSocket
Java.perform(function() {
    var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

    // Исходящие сообщения
    RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
        console.log("\n>>> WS SEND: " + text);
        return this.send(text);
    };

    // Входящие сообщения
    var WebSocketListener = Java.use("okhttp3.WebSocketListener");
    WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String')
        .implementation = function(ws, text) {
        console.log("\n<<< WS RECV: " + text);
        this.onMessage(ws, text);
    };
});
```

### Шаг 5: Выполнить действие в приложении

1. Запустить Frida с нужным скриптом
2. Открыть Avito и выполнить целевое действие (напр. открыть карточку товара)
3. Записать перехваченные запросы/ответы

### Шаг 6: Задокументировать

Записать в `DOCS/AVITO-API.md`:

```markdown
### X.X Новый endpoint

```
POST /api/XX/new_endpoint
```

**Запрос:**
\```json
{ перехваченное тело запроса }
\```

**Ответ:**
\```json
{ перехваченное тело ответа }
\```

**Заголовки:** стандартные (см. Блок 2) / только sessid / особые
**Rate limit:** наблюдения
**Ошибки:** замеченные коды
```

### Шаг 7: Проверить воспроизводимость

Попробовать воспроизвести через curl_cffi:

```python
from curl_cffi import requests

session = requests.Session(impersonate="chrome120")
resp = session.post(
    "https://app.avito.ru/api/XX/new_endpoint",
    headers=build_headers(session_data),
    json=request_body
)
print(resp.status_code, resp.json())
```

Если работает → эндпоинт подтверждён, можно добавлять в X-API.

### Инструменты реверса

| Инструмент | Что делает | Когда использовать |
|------------|------------|-------------------|
| Frida + http_capture.js | Перехват HTTP | Новые REST endpoints |
| Frida + ws_full_capture.js | Перехват WebSocket | Новые JSON-RPC методы |
| Frida + frida_avito_hooks.js | Перехват SharedPrefs | Новые токены/настройки |
| jadx | Декомпиляция APK | Анализ кода, имена классов |
| curl_cffi | Тест запросов | Проверка воспроизводимости |
| mitmproxy | HTTPS прокси | Альтернатива Frida |

---

## Часть 2: Добавление в X-API

### Шаг 1: Добавить метод в worker

Открыть `src/workers/http_client.py` (для HTTP) или `src/workers/ws_client.py` (для WebSocket).

Добавить метод, следуя паттерну:

```python
# src/workers/http_client.py

async def new_capability(self, param1: str, param2: int = 10) -> dict:
    """Описание из AVITO-API.md.

    Avito endpoint: POST /api/XX/new_endpoint
    Docs: AVITO-API.md → Блок X → X.X
    """
    return await self._request(
        "POST",
        f"{self.BASE_URL}/api/XX/new_endpoint",
        json={
            "param1": param1,
            "param2": param2,
        }
    )
```

Для WebSocket:

```python
# src/workers/ws_client.py

async def new_ws_method(self, channel_id: str) -> dict:
    """Описание из AVITO-API.md.

    WS method: avito.newMethod.v1
    Docs: AVITO-API.md → Блок 4 → 4.X
    """
    return await self._send_rpc("avito.newMethod.v1", {
        "channelId": channel_id,
    })
```

### Шаг 2: Создать Pydantic модели

Создать или дополнить файл в `src/models/`:

```python
# src/models/new_feature.py
from pydantic import BaseModel, Field

class NewFeatureRequest(BaseModel):
    """Запрос к новому эндпоинту."""
    param1: str = Field(..., description="Описание параметра 1")
    param2: int = Field(10, description="Описание параметра 2", ge=1, le=100)

class NewFeatureItem(BaseModel):
    """Элемент ответа."""
    id: str
    name: str
    value: int

class NewFeatureResponse(BaseModel):
    """Ответ нового эндпоинта."""
    items: list[NewFeatureItem]
    total: int
    has_more: bool = False
```

### Шаг 3: Создать router

Создать или дополнить файл в `src/routers/`:

```python
# src/routers/new_feature.py
from fastapi import APIRouter, Depends, Query
from src.dependencies import get_avito_client
from src.workers.http_client import AvitoHttpClient
from src.models.new_feature import NewFeatureRequest, NewFeatureResponse

router = APIRouter(
    prefix="/api/v1/new-feature",
    tags=["New Feature"],
)

@router.get(
    "/items",
    response_model=NewFeatureResponse,
    summary="Краткое описание",
    description="Подробное описание. Соответствует Avito POST /api/XX/new_endpoint.",
)
async def get_new_feature_items(
    param1: str = Query(..., description="Описание"),
    param2: int = Query(10, ge=1, le=100),
    client: AvitoHttpClient = Depends(get_avito_client),
):
    raw = await client.new_capability(param1, param2)
    return normalize_new_feature_response(raw)


def normalize_new_feature_response(raw: dict) -> dict:
    """Нормализация ответа Avito в формат X-API."""
    items = raw.get("result", {}).get("items", [])
    return {
        "items": [
            {
                "id": str(item["id"]),
                "name": item.get("title", ""),
                "value": item.get("value", 0),
            }
            for item in items
        ],
        "total": raw.get("result", {}).get("total", len(items)),
        "has_more": raw.get("result", {}).get("hasMore", False),
    }
```

### Шаг 4: Зарегистрировать router

В `src/main.py` добавить:

```python
from src.routers import new_feature

app.include_router(new_feature.router)
```

### Шаг 5: Написать тесты

```python
# tests/test_new_feature.py
import pytest
from unittest.mock import AsyncMock, patch

class TestNewFeatureUnit:
    """Unit тесты (без реальных запросов к Avito)."""

    def test_normalize_response(self):
        raw = {
            "result": {
                "items": [{"id": 123, "title": "Test", "value": 42}],
                "total": 1,
                "hasMore": False,
            }
        }
        from src.routers.new_feature import normalize_new_feature_response
        result = normalize_new_feature_response(raw)
        assert result["items"][0]["id"] == "123"
        assert result["items"][0]["name"] == "Test"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_endpoint_returns_200(self, client, mock_avito):
        mock_avito.new_capability.return_value = {
            "result": {"items": [], "total": 0}
        }
        resp = await client.get(
            "/api/v1/new-feature/items?param1=test",
            headers={"X-Api-Key": "test_key"}
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestNewFeatureIntegration:
    """Integration тесты (реальные запросы, только с AVITO_SESSION_FILE)."""

    @pytest.mark.asyncio
    async def test_real_request(self, real_client):
        resp = await real_client.get(
            "/api/v1/new-feature/items?param1=iPhone",
            headers={"X-Api-Key": "real_key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
```

### Шаг 6: Обновить документацию

1. В `DOCS/AVITO-API.md` — добавить описание Avito endpoint в соответствующий блок
2. В `DOCS/X-API.md` — добавить описание нового эндпоинта X-API
3. В `docs/curl_examples.md` — добавить curl пример:

```bash
# New Feature — получить items
curl -X GET "http://localhost:8080/api/v1/new-feature/items?param1=test" \
  -H "X-Api-Key: your_key"
```

---

## Часть 3: Шаблоны кода

### Шаблон worker метода (HTTP)

```python
async def {method_name}(self, {params}) -> dict:
    """
    {Описание}.

    Avito: {METHOD} {URL}
    Docs: AVITO-API.md → Блок {N}
    """
    return await self._request(
        "{METHOD}",
        f"{self.BASE_URL}/{path}",
        json={payload},  # или params={params} для GET
    )
```

### Шаблон worker метода (WebSocket)

```python
async def {method_name}(self, {params}) -> dict:
    """
    {Описание}.

    WS method: {method.name.vX}
    Docs: AVITO-API.md → Блок 4
    """
    return await self._send_rpc("{method.name.vX}", {
        {params_dict}
    })
```

### Шаблон Pydantic модели

```python
from pydantic import BaseModel, Field
from enum import Enum

class {Name}Request(BaseModel):
    """{Описание запроса}."""
    field1: str = Field(..., description="{Описание}")
    field2: int = Field(default, ge=min, le=max, description="{Описание}")

class {Name}Response(BaseModel):
    """{Описание ответа}."""
    items: list[{ItemModel}] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False
```

### Шаблон router endpoint

```python
@router.{method}(
    "/{path}",
    response_model={ResponseModel},
    summary="{Краткое описание}",
    description="{Подробное описание}. Avito: {endpoint}.",
    responses={
        404: {"model": ErrorResponse, "description": "Not found"},
        502: {"model": ErrorResponse, "description": "Avito error"},
    },
)
async def {handler_name}(
    {path_params},
    {query_params}: type = Query(default, description="{Описание}"),
    client: AvitoHttpClient = Depends(get_avito_client),
):
    raw = await client.{worker_method}({params})
    return normalize_{name}_response(raw)
```

---

## Чеклист

При добавлении нового эндпоинта убедитесь:

- [ ] Avito endpoint задокументирован в `AVITO-API.md`
- [ ] Endpoint проверен через curl_cffi (работает с реальным токеном)
- [ ] Метод добавлен в worker (`http_client.py` или `ws_client.py`)
- [ ] Pydantic модели созданы/обновлены в `src/models/`
- [ ] Router создан/обновлен в `src/routers/`
- [ ] Router зарегистрирован в `src/main.py` (`app.include_router(...)`)
- [ ] Unit тест написан (с mock, без реальных запросов)
- [ ] Integration тест написан (с `@pytest.mark.integration`)
- [ ] Нормализация ответа реализована (скрывает различия Avito форматов)
- [ ] curl пример добавлен в `docs/curl_examples.md`
- [ ] `X-API.md` обновлён с описанием нового эндпоинта
- [ ] Endpoint виден в Swagger UI (`/docs`)
- [ ] Ответ проверен через "Try it out" в Swagger UI

---

## FAQ

**Q: Нужно ли перезапускать сервер?**
A: Да, после добавления нового router нужен перезапуск. В dev-режиме uvicorn с `--reload` делает это автоматически.

**Q: Что если Avito изменит формат ответа?**
A: Функция `normalize_*_response()` изолирует формат Avito. Если ответ изменился — обновить только эту функцию, X-API клиенты не заметят.

**Q: Как добавить endpoint который использует и HTTP и WS?**
A: Worker может вызывать оба клиента. Например, получить данные через HTTP, а потом подписаться на обновления через WS. Router использует один worker метод, который внутри решает какой транспорт использовать.

**Q: Куда добавлять новый блок в AVITO-API.md?**
A: Создать новый блок с номером (Блок 9, 10, и т.д.) в конце файла. Добавить ссылку в содержание.
