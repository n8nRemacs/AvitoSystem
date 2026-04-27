"""
AvitoBayer MCP Server — поиск iPhone под восстановление на Avito.

Блоки:
  1. Saved Searches  — сохранённые URL поиска Avito с типом назначения
  2. Processing Rules — правила обработки по типу поиска
  3. Search           — поиск объявлений, карточка товара
  4. Messenger        — чаты, сообщения
  5. Leads            — pipeline лидов
"""
import json
import logging
import base64
from urllib.parse import urlparse, parse_qs
from typing import Any

from mcp.server.fastmcp import FastMCP

from xapi_client import XApiClient
from supabase_client import SupabaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("avito-mcp")

mcp = FastMCP(
    "AvitoBayer",
    instructions=(
        "MCP-сервер для работы с Avito. "
        "Рабочий процесс: пользователь формирует поиск на avito.ru с нужными фильтрами, "
        "копирует URL и сохраняет через save_search с указанием типа (buy/competitors/price_monitor). "
        "К каждому типу привязаны правила обработки (processing rules). "
        "Далее можно искать по сохранённым поискам, смотреть карточки, вести переписку и управлять лидами."
    ),
)

xapi = XApiClient()
supabase = SupabaseClient()


def _fmt(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def parse_avito_url(url: str) -> dict[str, Any]:
    """Разобрать URL поиска Avito на составные части."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    segments = parsed.path.strip("/").split("/")

    result: dict[str, Any] = {
        "region": segments[0] if segments else "all",
        "category_path": "/".join(segments[1:]),
        "raw_params": {k: v[0] for k, v in params.items()},
    }

    if len(segments) > 1:
        last = segments[-1]
        if "-" in last:
            name, code = last.rsplit("-", 1)
            result["model_slug"] = name
            result["category_filter_code"] = code

    if "d" in params:
        result["with_delivery"] = params["d"][0] == "1"
    if "s" in params:
        sort_map = {"1": "date", "2": "price", "3": "price_desc", "104": "relevance"}
        result["sort"] = sort_map.get(params["s"][0], params["s"][0])
    if "p" in params:
        try:
            result["page"] = int(params["p"][0])
        except ValueError:
            pass
    if "f" in params:
        f_val = params["f"][0]
        padded = f_val + "=" * (4 - len(f_val) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded)
            for i in range(len(decoded)):
                if decoded[i : i + 1] == b"{":
                    try:
                        end = decoded.index(b"}", i) + 1
                        j = json.loads(decoded[i:end])
                        if "from" in j:
                            result["price_min"] = j["from"]
                        if "to" in j:
                            result["price_max"] = j["to"]
                    except (ValueError, json.JSONDecodeError):
                        pass
        except Exception:
            pass

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. SAVED SEARCHES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def save_search(
    name: str,
    avito_url: str,
    search_type: str = "buy",
    description: str | None = None,
    processing_rules_id: str | None = None,
) -> str:
    """Сохранить поисковый запрос Avito по URL.

    Пользователь формирует поиск на avito.ru с нужными фильтрами, копирует URL.

    Args:
        name: Короткое название, например "iPhone 12 Pro 9-13к"
        avito_url: Полный URL поиска с avito.ru
        search_type: Тип назначения:
            - "buy" — поиск товаров для покупки (дефолт)
            - "competitors" — мониторинг конкурентов
            - "price_monitor" — отслеживание цен
        description: Описание / заметки
        processing_rules_id: UUID правила обработки (если не указан — используется дефолтное для типа)

    Returns:
        Сохранённый поиск с разобранными параметрами URL
    """
    try:
        parsed = parse_avito_url(avito_url)

        # Если правила не указаны, найти дефолтное для типа
        if not processing_rules_id:
            rules = await supabase.get_rules(search_type=search_type)
            if rules:
                processing_rules_id = rules[0]["id"]

        data: dict[str, Any] = {
            "name": name,
            "avito_url": avito_url,
            "search_type": search_type,
        }
        if description:
            data["description"] = description
        if processing_rules_id:
            data["processing_rules_id"] = processing_rules_id

        result = await supabase.create_search(data)
        result["parsed_filters"] = parsed
        return _fmt(result)
    except Exception as e:
        return f"Ошибка сохранения: {e}"


@mcp.tool()
async def list_searches(
    active_only: bool = True, search_type: str | None = None
) -> str:
    """Получить список сохранённых поисковых запросов.

    Args:
        active_only: true = только активные
        search_type: Фильтр по типу: "buy", "competitors", "price_monitor"

    Returns:
        Список поисков с id, name, avito_url, search_type, правила обработки, last_run_at
    """
    try:
        data = await supabase.get_searches(active_only=active_only, search_type=search_type)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def get_search_details(search_id: str) -> str:
    """Получить детали сохранённого поиска с правилами обработки и разобранным URL.

    Args:
        search_id: UUID сохранённого поиска

    Returns:
        Полная информация: URL, тип, правила обработки, разобранные фильтры
    """
    try:
        search = await supabase.get_search(search_id)
        if not search:
            return "Поиск не найден"
        search["parsed_filters"] = parse_avito_url(search["avito_url"])
        return _fmt(search)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def update_search(
    search_id: str,
    name: str | None = None,
    avito_url: str | None = None,
    search_type: str | None = None,
    is_active: bool | None = None,
    processing_rules_id: str | None = None,
    description: str | None = None,
) -> str:
    """Обновить сохранённый поиск.

    Args:
        search_id: UUID поиска
        name: Новое название
        avito_url: Новый URL
        search_type: Новый тип: "buy", "competitors", "price_monitor"
        is_active: Активен или нет
        processing_rules_id: UUID нового правила обработки
        description: Описание

    Returns:
        Обновлённый поиск
    """
    try:
        data: dict[str, Any] = {}
        if name:
            data["name"] = name
        if avito_url:
            data["avito_url"] = avito_url
        if search_type:
            data["search_type"] = search_type
        if is_active is not None:
            data["is_active"] = is_active
        if processing_rules_id:
            data["processing_rules_id"] = processing_rules_id
        if description is not None:
            data["description"] = description
        if not data:
            return "Нечего обновлять"
        result = await supabase.update_search(search_id, data)
        return _fmt(result)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def delete_search(search_id: str) -> str:
    """Удалить сохранённый поиск.

    Args:
        search_id: UUID поиска
    """
    try:
        await supabase.delete_search(search_id)
        return _fmt({"status": "ok", "deleted": search_id})
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def parse_search_url(avito_url: str) -> str:
    """Разобрать URL поиска Avito — показать какие фильтры в нём заданы.

    Args:
        avito_url: URL с avito.ru

    Returns:
        Регион, категория, модель, цена, доставка, сортировка
    """
    try:
        return _fmt(parse_avito_url(avito_url))
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. PROCESSING RULES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def list_rules(search_type: str | None = None) -> str:
    """Получить список правил обработки поисковых запросов.

    Args:
        search_type: Фильтр по типу: "buy", "competitors", "price_monitor"

    Returns:
        Список правил с параметрами: score_threshold, auto_questions, check_interval и т.д.
    """
    try:
        data = await supabase.get_rules(search_type=search_type)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def create_rule(
    name: str,
    search_type: str,
    score_threshold: float = 5.0,
    auto_questions: list[str] | None = None,
    check_interval_minutes: int = 60,
    max_leads_per_run: int = 10,
    alert_on_new: bool = True,
    alert_on_price_change: bool = False,
    alert_on_price_drop_pct: float | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    custom_rules: dict | None = None,
) -> str:
    """Создать правило обработки для поискового запроса.

    Args:
        name: Название правила
        search_type: Тип: "buy", "competitors", "price_monitor"
        score_threshold: Мин. оценка для создания лида (0-10)
        auto_questions: Список первичных вопросов продавцу
        check_interval_minutes: Частота проверки (минуты)
        max_leads_per_run: Макс. лидов за один прогон
        alert_on_new: Уведомлять о новых объявлениях
        alert_on_price_change: Уведомлять об изменении цены
        alert_on_price_drop_pct: Порог падения цены для алерта (%)
        price_min: Фильтр мин. цены при обработке
        price_max: Фильтр макс. цены при обработке
        custom_rules: Произвольные правила (JSON)

    Returns:
        Созданное правило
    """
    try:
        data: dict[str, Any] = {
            "name": name,
            "search_type": search_type,
            "score_threshold": score_threshold,
            "check_interval_minutes": check_interval_minutes,
            "max_leads_per_run": max_leads_per_run,
            "alert_on_new": alert_on_new,
            "alert_on_price_change": alert_on_price_change,
        }
        if auto_questions:
            data["auto_questions"] = auto_questions
        if alert_on_price_drop_pct is not None:
            data["alert_on_price_drop_pct"] = alert_on_price_drop_pct
        if price_min is not None:
            data["price_min"] = price_min
        if price_max is not None:
            data["price_max"] = price_max
        if custom_rules:
            data["custom_rules"] = custom_rules

        result = await supabase.create_rule(data)
        return _fmt(result)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def update_rule(
    rule_id: str,
    name: str | None = None,
    score_threshold: float | None = None,
    auto_questions: list[str] | None = None,
    check_interval_minutes: int | None = None,
    max_leads_per_run: int | None = None,
    alert_on_new: bool | None = None,
    alert_on_price_change: bool | None = None,
    alert_on_price_drop_pct: float | None = None,
    custom_rules: dict | None = None,
) -> str:
    """Обновить правило обработки.

    Args:
        rule_id: UUID правила
        name: Название
        score_threshold: Мин. оценка для лида
        auto_questions: Вопросы продавцу
        check_interval_minutes: Частота проверки
        max_leads_per_run: Макс. лидов за прогон
        alert_on_new: Алерт на новые
        alert_on_price_change: Алерт на изменение цены
        alert_on_price_drop_pct: Порог падения цены
        custom_rules: Произвольные правила

    Returns:
        Обновлённое правило
    """
    try:
        data: dict[str, Any] = {}
        if name:
            data["name"] = name
        if score_threshold is not None:
            data["score_threshold"] = score_threshold
        if auto_questions is not None:
            data["auto_questions"] = auto_questions
        if check_interval_minutes is not None:
            data["check_interval_minutes"] = check_interval_minutes
        if max_leads_per_run is not None:
            data["max_leads_per_run"] = max_leads_per_run
        if alert_on_new is not None:
            data["alert_on_new"] = alert_on_new
        if alert_on_price_change is not None:
            data["alert_on_price_change"] = alert_on_price_change
        if alert_on_price_drop_pct is not None:
            data["alert_on_price_drop_pct"] = alert_on_price_drop_pct
        if custom_rules is not None:
            data["custom_rules"] = custom_rules
        if not data:
            return "Нечего обновлять"
        result = await supabase.update_rule(rule_id, data)
        return _fmt(result)
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. SEARCH HISTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def get_search_history(search_id: str, limit: int = 20) -> str:
    """Получить историю запусков поиска (цены, кол-во, динамика).

    Args:
        search_id: UUID сохранённого поиска
        limit: Кол-во последних запусков

    Returns:
        Список запусков: avg_price, min_price, max_price, results_count, leads_created
    """
    try:
        data = await supabase.get_runs(search_id, limit=limit)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. SEARCH (Avito API)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def search_items(
    query: str,
    price_min: int | None = None,
    price_max: int | None = None,
    location_id: int | None = None,
    category_id: int | None = None,
    sort: str | None = None,
    page: int = 1,
    per_page: int = 30,
    with_delivery: bool | None = None,
    owner: str | None = None,
) -> str:
    """Поиск объявлений на Avito через мобильный API.

    Для точных фильтров лучше сохранить URL через save_search.

    Args:
        query: Поисковый запрос
        price_min: Мин. цена (руб)
        price_max: Макс. цена (руб)
        location_id: Регион: 621540=Россия, 637640=Москва, 653240=СПб
        category_id: Категория
        sort: "date", "price", "price_desc"
        page: Страница
        per_page: Кол-во (макс 100)
        with_delivery: Только с доставкой
        owner: "private" / "company"
    """
    try:
        data = await xapi.search_items(
            query=query, price_min=price_min, price_max=price_max,
            location_id=location_id, category_id=category_id,
            sort=sort, page=page, per_page=per_page,
            with_delivery=with_delivery, owner=owner,
        )
        return _fmt(data)
    except Exception as e:
        return f"Ошибка поиска: {e}"


@mcp.tool()
async def get_item_details(item_id: int) -> str:
    """Получить полную карточку объявления.

    Args:
        item_id: ID объявления на Avito
    """
    try:
        data = await xapi.get_item(item_id)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. MESSENGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def get_channels(limit: int = 30, offset_timestamp: int | None = None) -> str:
    """Список чатов Avito.

    Args:
        limit: Кол-во (макс 100)
        offset_timestamp: Пагинация
    """
    try:
        data = await xapi.get_channels(limit=limit, offset_timestamp=offset_timestamp)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def get_messages(channel_id: str, limit: int = 50, offset_id: str | None = None) -> str:
    """История сообщений чата.

    Args:
        channel_id: ID канала ("u2i-xxx")
        limit: Кол-во (макс 100)
        offset_id: Пагинация
    """
    try:
        data = await xapi.get_messages(channel_id, limit=limit, offset_id=offset_id)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def send_message(channel_id: str, text: str) -> str:
    """Отправить сообщение в чат.

    Args:
        channel_id: ID канала ("u2i-xxx")
        text: Текст сообщения
    """
    try:
        data = await xapi.send_message(channel_id, text)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def create_chat_by_item(item_id: str) -> str:
    """Создать чат по объявлению.

    Args:
        item_id: ID объявления
    """
    try:
        data = await xapi.create_channel_by_item(item_id)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def mark_chat_read(channel_id: str) -> str:
    """Пометить чат прочитанным.

    Args:
        channel_id: ID канала
    """
    try:
        data = await xapi.mark_read(channel_id)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def get_unread_count() -> str:
    """Кол-во непрочитанных сообщений."""
    try:
        data = await xapi.get_unread_count()
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. LEADS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def create_lead(
    item_id: str, title: str,
    price: int | None = None, score: float | None = None,
    notes: str | None = None, seller_id: str | None = None,
    channel_id: str | None = None, url: str | None = None,
) -> str:
    """Добавить объявление в shortlist.

    Args:
        item_id: ID объявления
        title: Название
        price: Цена
        score: Оценка (0-10)
        notes: Заметки
        seller_id: ID продавца
        channel_id: ID чата
        url: Ссылка
    """
    try:
        data: dict[str, Any] = {"item_id": item_id, "title": title}
        for k, v in [("price", price), ("score", score), ("notes", notes),
                      ("seller_id", seller_id), ("channel_id", channel_id), ("url", url)]:
            if v is not None:
                data[k] = v
        result = await supabase.create_lead(data)
        return _fmt(result)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def get_leads(status: str | None = None, limit: int = 50, offset: int = 0) -> str:
    """Список лидов.

    Args:
        status: Фильтр (new, selected, auto_questions_sent, waiting_reply, operator_needed, negotiation, rejected, deal_candidate, closed)
        limit: Кол-во
        offset: Смещение
    """
    try:
        data = await supabase.get_leads(status=status, limit=limit, offset=offset)
        return _fmt(data)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
async def update_lead(
    lead_id: str,
    status: str | None = None, score: float | None = None,
    notes: str | None = None, channel_id: str | None = None,
) -> str:
    """Обновить лид.

    Args:
        lead_id: UUID лида
        status: Новый статус
        score: Новая оценка
        notes: Заметки
        channel_id: ID чата
    """
    try:
        data: dict[str, Any] = {}
        for k, v in [("status", status), ("score", score), ("notes", notes), ("channel_id", channel_id)]:
            if v is not None:
                data[k] = v
        if not data:
            return "Нечего обновлять"
        result = await supabase.update_lead(lead_id, data)
        return _fmt(result)
    except Exception as e:
        return f"Ошибка: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    mcp.run(transport="stdio")
