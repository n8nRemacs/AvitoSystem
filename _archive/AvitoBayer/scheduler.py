"""
Scan loop — автоматический прогон saved_searches по расписанию.

Использует asyncio tasks. Каждый saved_search получает свою задачу,
которая ждёт check_interval_minutes, потом запускает run_scan().
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, parse_qs

import httpx

from config import settings
from xapi_client import XApiClient

logger = logging.getLogger("avito-scheduler")


@dataclass
class ScanResult:
    search_id: str
    search_name: str
    total_found: int
    new_items: int
    leads_created: int
    prices: list[int] = field(default_factory=list)
    new_leads: list[dict] = field(default_factory=list)
    error: str | None = None


def _parse_avito_url(url: str) -> dict[str, Any]:
    """Извлечь параметры поиска из Avito URL.

    Примеры:
      https://www.avito.ru/moskva/telefony/iphone_15_pro_max-ASgBAgICAUSSA8YQ?pmin=50000&pmax=100000
      https://www.avito.ru/rossiya?q=iphone+15+pro&pmin=60000
    """
    params: dict[str, Any] = {}
    if not url:
        return params
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        # Price range
        if "pmin" in qs:
            try:
                params["price_min"] = int(qs["pmin"][0])
            except (ValueError, IndexError):
                pass
        if "pmax" in qs:
            try:
                params["price_max"] = int(qs["pmax"][0])
            except (ValueError, IndexError):
                pass

        # Explicit q= param takes priority
        if "q" in qs:
            params["query"] = qs["q"][0]

        # Parse path: /{city}/{category}/{slug} or /{city}/{slug}
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if parts:
            params["search_area"] = parts[0]

        if "query" not in params and len(parts) >= 2:
            # Use last path segment as search slug
            slug = parts[-1]
            # Remove Avito category code at end (e.g. -ASgBAgICAUSSA8YQ)
            slug = re.sub(r"-[A-Za-z0-9+/=]{8,}$", "", slug)
            query = slug.replace("-", " ").replace("_", " ").strip()
            if query and query != parts[0]:  # not just the city
                params["query"] = query

    except Exception as e:
        logger.warning(f"Failed to parse Avito URL '{url}': {e}")

    return params


async def _llm_evaluate(item: dict, rule: dict) -> dict:
    """Оценить объявление через LLM. Возвращает поля для scanned_items."""
    if not settings.llm_api_key:
        return {}

    green_flags = rule.get("green_flags") or []
    red_flags = rule.get("red_flags") or []
    custom_prompt = rule.get("llm_prompt", "")

    system = (
        "Ты — оценщик объявлений на Avito. Отвечай строго в JSON без markdown.\n"
        + (f"Green flags (хорошие признаки): {', '.join(green_flags)}\n" if green_flags else "")
        + (f"Red flags (плохие признаки): {', '.join(red_flags)}\n" if red_flags else "")
        + (custom_prompt + "\n" if custom_prompt else "")
        + 'Верни JSON: {"verdict":"ok|partial|risk|skip","score":0-10,'
          '"summary":"...","green_flags":[],"red_flags":[],"missing_info":[]}'
    )

    user_text = (
        f"Название: {item.get('title', '')}\n"
        f"Цена: {item.get('price', '?')} ₽\n"
        f"Адрес: {item.get('city') or item.get('address', '')}\n"
    )

    client_kwargs: dict = {"timeout": 30.0}
    if settings.tg_notify_proxy:
        client_kwargs["proxy"] = settings.tg_notify_proxy

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": 512,
                    "system": system,
                    "messages": [{"role": "user", "content": user_text}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"LLM API call failed: {e}")
        return {}

    text = (data.get("content") or [{}])[0].get("text", "{}")
    try:
        result = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            result = json.loads(m.group()) if m else {}
        except Exception:
            result = {}

    return {
        "llm_verdict": result.get("verdict"),
        "llm_score": result.get("score"),
        "llm_summary": result.get("summary"),
        "llm_green_flags": result.get("green_flags"),
        "llm_red_flags": result.get("red_flags"),
        "llm_missing_info": result.get("missing_info"),
    }


class ScanScheduler:
    """
    Asyncio-based планировщик сканирования.

    Каждый активный saved_search получает свою asyncio-задачу (_run_loop),
    которая после первого прогона ждёт check_interval_minutes и повторяет.
    """

    def __init__(self, sb, notifier=None):
        self._sb = sb          # SB instance (из api.py)
        self._notifier = notifier
        self._xapi = XApiClient()
        self._tasks: dict[str, asyncio.Task] = {}
        self._last_run: dict[str, datetime] = {}
        self._next_run: dict[str, datetime] = {}
        self._running = False
        self._reload_task: asyncio.Task | None = None

    def _fire_notify(self, coro):
        """Schedule a notification coroutine with error logging."""
        task = asyncio.create_task(coro)
        task.add_done_callback(self._on_notify_done)

    @staticmethod
    def _on_notify_done(task: asyncio.Task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Notification failed: {exc}")

    async def start(self):
        if self._running:
            return
        self._running = True
        self._reload_task = asyncio.create_task(self._load_and_schedule())
        logger.info("Scheduler started")

    async def stop(self):
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        if self._reload_task:
            self._reload_task.cancel()
            self._reload_task = None
        await self._xapi.close()
        logger.info("Scheduler stopped")

    async def _load_and_schedule(self):
        try:
            searches = await self._sb.select("saved_searches", {
                "is_active": "eq.true",
                "select": "*,search_processing_rules(*)",
            })
            logger.info(f"Loaded {len(searches)} active searches for scheduling")
            for search in searches:
                self._schedule(search)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Failed to load searches: {e}")

    def _get_interval(self, search: dict) -> int:
        rules = search.get("search_processing_rules")
        if isinstance(rules, dict):
            val = rules.get("check_interval_minutes")
        elif isinstance(rules, list) and rules:
            val = rules[0].get("check_interval_minutes")
        else:
            val = None
        if val:
            return int(val)
        defaults = {"buy": 30, "competitors": 360, "price_monitor": 120}
        return defaults.get(search.get("search_type", "buy"), 30)

    def _schedule(self, search: dict):
        sid = search["id"]
        if sid in self._tasks and not self._tasks[sid].done():
            return
        interval = self._get_interval(search)
        task = asyncio.create_task(self._run_loop(sid, interval))
        self._tasks[sid] = task
        logger.info(f"Scheduled search {sid} ({search.get('name')}) every {interval}m")

    async def _run_loop(self, search_id: str, interval_minutes: int):
        """Периодический цикл для одного search."""
        try:
            while self._running:
                try:
                    result = await self.run_scan(search_id)
                    self._last_run[search_id] = datetime.now(timezone.utc)
                    self._next_run[search_id] = datetime(
                        *datetime.now(timezone.utc).timetuple()[:6],
                        tzinfo=timezone.utc
                    )
                    if self._notifier and not result.error:
                        await self._notifier.send_scan_summary(result)
                        if result.new_leads:
                            await self._notifier.send_new_leads(result.new_leads, {})
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Scan loop error for {search_id}: {e}")

                # Wait for next interval
                next_dt = datetime.now(timezone.utc).timestamp() + interval_minutes * 60
                self._next_run[search_id] = datetime.fromtimestamp(next_dt, tz=timezone.utc)
                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            pass

    def reload_search(self, search_id: str):
        """Перепланировать search (после обновления через API)."""
        if search_id in self._tasks:
            self._tasks[search_id].cancel()
            del self._tasks[search_id]
        asyncio.create_task(self._reload_one(search_id))

    async def _reload_one(self, search_id: str):
        try:
            search = await self._sb.select_one("saved_searches", {
                "id": f"eq.{search_id}",
                "select": "*,search_processing_rules(*)",
            })
            if search and search.get("is_active"):
                self._schedule(search)
            elif search_id in self._tasks:
                self._tasks[search_id].cancel()
                del self._tasks[search_id]
        except Exception as e:
            logger.error(f"Failed to reload search {search_id}: {e}")

    def status(self) -> dict:
        now = datetime.now(timezone.utc)
        jobs = []
        for sid, task in self._tasks.items():
            next_run = self._next_run.get(sid)
            last_run = self._last_run.get(sid)
            jobs.append({
                "search_id": sid,
                "active": not task.done() and not task.cancelled(),
                "last_run": last_run.isoformat() if last_run else None,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return {
            "running": self._running,
            "jobs_count": len(jobs),
            "jobs": jobs,
        }

    async def run_scan(self, search_id: str) -> ScanResult:
        """Запустить один скан для saved_search."""
        search = await self._sb.select_one("saved_searches", {
            "id": f"eq.{search_id}",
            "select": "*,search_processing_rules(*)",
        })
        if not search:
            return ScanResult(search_id=search_id, search_name="unknown",
                              total_found=0, new_items=0, leads_created=0,
                              error="Search not found")

        rules = search.get("search_processing_rules") or {}
        if isinstance(rules, list):
            rules = rules[0] if rules else {}

        score_threshold: float = float(rules.get("score_threshold") or 6.0)
        max_leads_per_run: int = int(rules.get("max_leads_per_run") or 3)
        search_type: str = search.get("search_type", "buy")

        # Parse URL to get search params
        url_params = _parse_avito_url(search.get("avito_url", ""))
        query = url_params.get("query") or search.get("name", "")
        if not query:
            return ScanResult(search_id=search_id, search_name=search.get("name", ""),
                              total_found=0, new_items=0, leads_created=0,
                              error="Cannot extract query from URL")

        logger.info(f"Scanning '{search.get('name')}' — query='{query}'")

        # Call xapi search
        try:
            resp = await self._xapi.search_items(
                query=query,
                price_min=url_params.get("price_min"),
                price_max=url_params.get("price_max"),
                search_area=url_params.get("search_area"),
                per_page=50,
            )
        except Exception as e:
            logger.error(f"xapi search failed for {search_id}: {e}")
            return ScanResult(search_id=search_id, search_name=search.get("name", ""),
                              total_found=0, new_items=0, leads_created=0,
                              error=str(e))

        items = resp.get("items", [])
        total = resp.get("total") or len(items)
        prices = [int(it["price"]) for it in items if it.get("price")]

        new_items_count = 0
        leads_created = 0
        new_leads: list[dict] = []

        for item in items:
            item_id = str(item.get("id", ""))
            if not item_id:
                continue

            # Дедупликация по item_id + search_id
            existing = await self._sb.select_one("scanned_items", {
                "item_id": f"eq.{item_id}",
                "search_id": f"eq.{search_id}",
                "select": "id,price",
            })

            if existing:
                # Мониторинг цены
                if search_type == "price_monitor" and self._notifier:
                    old_price = existing.get("price") or 0
                    new_price = item.get("price") or 0
                    if old_price and new_price and old_price != new_price:
                        drop_pct = float(rules.get("alert_on_price_drop_pct") or 0)
                        if drop_pct and new_price < old_price:
                            change = (old_price - new_price) / old_price * 100
                            if change >= drop_pct:
                                self._fire_notify(
                                    self._notifier.send_price_drop(item, old_price, new_price, change)
                                )
                        elif rules.get("alert_on_price_change"):
                            self._fire_notify(
                                self._notifier.send_price_change(item, old_price, new_price)
                            )
                        # Обновить цену
                        try:
                            await self._sb.update("scanned_items", existing["id"], {"price": new_price})
                        except Exception:
                            pass
                continue

            # Новый item
            new_items_count += 1
            images = []
            for img in (item.get("images") or []):
                if isinstance(img, dict):
                    images.append(img.get("url", ""))
                elif isinstance(img, str):
                    images.append(img)
            images = [u for u in images if u]

            scanned_data: dict[str, Any] = {
                "item_id": item_id,
                "search_id": search_id,
                "title": item.get("title", ""),
                "price": item.get("price"),
                "location": item.get("city") or item.get("address"),
                "url": item.get("url"),
                "images": images or None,
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "status": "new",
            }

            # LLM оценка (опционально)
            if rules.get("llm_prompt") or (rules.get("green_flags") and settings.llm_api_key):
                try:
                    eval_result = await _llm_evaluate(item, rules)
                    scanned_data.update({k: v for k, v in eval_result.items() if v is not None})
                except Exception as e:
                    logger.warning(f"LLM eval failed for item {item_id}: {e}")

            # Сохранить в scanned_items
            try:
                saved = await self._sb.insert("scanned_items",
                                              {k: v for k, v in scanned_data.items() if v is not None})
            except Exception as e:
                logger.warning(f"Failed to save scanned item {item_id}: {e}")
                continue

            # Создать лид если квалифицирован
            score = scanned_data.get("llm_score")
            verdict = scanned_data.get("llm_verdict", "ok")
            qualified = (
                max_leads_per_run > 0
                and leads_created < max_leads_per_run
                and verdict not in ("skip", "risk")
                and (score is None or float(score) >= score_threshold)
            )

            if qualified:
                try:
                    lead = await self._sb.insert("leads", {
                        "item_id": item_id,
                        "title": item.get("title", ""),
                        "price": item.get("price"),
                        "score": score,
                        "url": item.get("url"),
                        "notes": scanned_data.get("llm_summary"),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "new",
                    })
                    leads_created += 1
                    lead_item = {**scanned_data, "lead_id": lead.get("id"), "id": saved.get("id")}
                    new_leads.append(lead_item)
                    try:
                        await self._sb.update("scanned_items", saved["id"], {"status": "lead_created"})
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Failed to create lead for {item_id}: {e}")

            # Алерт о новом конкуренте
            if search_type == "competitors" and rules.get("alert_on_new") and self._notifier:
                self._fire_notify(self._notifier.send_new_competitor(item))

        # Сохранить search_run
        try:
            await self._sb.insert("search_runs", {
                "search_id": search_id,
                "run_at": datetime.now(timezone.utc).isoformat(),
                "results_count": total,
                "new_items_count": new_items_count,
                "leads_created": leads_created,
                "avg_price": int(sum(prices) / len(prices)) if prices else None,
            })
        except Exception as e:
            logger.warning(f"Failed to save search_run: {e}")

        # Обновить last_run_at
        try:
            await self._sb.update("saved_searches", search_id, {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_results_count": total,
            })
        except Exception as e:
            logger.warning(f"Failed to update search last_run: {e}")

        logger.info(
            f"Scan done: '{search.get('name')}' — "
            f"total={total}, new={new_items_count}, leads={leads_created}"
        )

        return ScanResult(
            search_id=search_id,
            search_name=search.get("name", ""),
            total_found=total,
            new_items=new_items_count,
            leads_created=leads_created,
            prices=prices,
            new_leads=new_leads,
        )
