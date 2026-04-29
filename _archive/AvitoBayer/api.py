"""
AvitoBayer REST API — внешний HTTP API для управления и получения данных.

Порт: 8132
Используется: TG-ботом, внешними сервисами, фронтендом.
"""
import logging
from datetime import datetime, timezone
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from config import settings
from notifier import TelegramNotifier
from scheduler import ScanScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("avito-api")


# ── Supabase helper ────────────────────────────────────

class SB:
    """Async Supabase PostgREST wrapper."""

    def __init__(self):
        self.url = settings.supabase_url.rstrip("/")
        self.http: httpx.AsyncClient | None = None

    async def init(self):
        self.http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        if self.http:
            await self.http.aclose()

    def _h(self, prefer: str | None = None) -> dict:
        h = {
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _r(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    async def select(self, table: str, params: dict) -> list:
        resp = await self.http.get(self._r(table), params=params, headers=self._h())
        resp.raise_for_status()
        return resp.json()

    async def select_one(self, table: str, params: dict) -> dict | None:
        rows = await self.select(table, {**params, "limit": "1"})
        return rows[0] if rows else None

    async def insert(self, table: str, data: dict) -> dict:
        resp = await self.http.post(self._r(table), json=data, headers=self._h(prefer="return=representation"))
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def update(self, table: str, id: str, data: dict) -> dict:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = await self.http.patch(self._r(table), json=data, params={"id": f"eq.{id}"}, headers=self._h(prefer="return=representation"))
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def delete(self, table: str, id: str):
        resp = await self.http.delete(self._r(table), params={"id": f"eq.{id}"}, headers=self._h())
        resp.raise_for_status()

    async def count(self, table: str, params: dict | None = None) -> int:
        p = dict(params) if params else {}
        p["select"] = "id"
        h = self._h()
        h["Prefer"] = "count=exact"
        h["Range-Unit"] = "items"
        h["Range"] = "0-0"
        resp = await self.http.get(self._r(table), params=p, headers=h)
        cr = resp.headers.get("content-range", "")
        # "0-0/42" -> 42
        if "/" in cr:
            try:
                return int(cr.split("/")[1])
            except (ValueError, IndexError):
                pass
        return len(resp.json())


sb = SB()
notifier = TelegramNotifier()
scheduler = ScanScheduler(sb, notifier)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await sb.init()
    await notifier.init()
    logger.info("AvitoBayer API started on port 8132")
    if settings.scheduler_autostart:
        await scheduler.start()
        logger.info("Scheduler autostarted")
    yield
    await scheduler.stop()
    await notifier.close()
    await sb.close()
    logger.info("AvitoBayer API stopped")


app = FastAPI(
    title="AvitoBayer API",
    version="1.0.0",
    description="REST API для управления Avito-парсером: поиски, правила, результаты сканирования",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/health")
async def health():
    return {"status": "ok", "service": "avito-bayer"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. SEARCHES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SearchCreate(BaseModel):
    name: str
    avito_url: str
    search_type: str = "buy"
    description: str | None = None
    processing_rules_id: str | None = None


class SearchUpdate(BaseModel):
    name: str | None = None
    avito_url: str | None = None
    search_type: str | None = None
    description: str | None = None
    is_active: bool | None = None
    processing_rules_id: str | None = None


@app.get("/api/searches")
async def list_searches(
    active_only: bool = True,
    search_type: str | None = None,
):
    params: dict[str, str] = {
        "select": "*,search_processing_rules(*)",
        "order": "created_at.desc",
    }
    if active_only:
        params["is_active"] = "eq.true"
    if search_type:
        params["search_type"] = f"eq.{search_type}"
    return await sb.select("saved_searches", params)


@app.get("/api/searches/{search_id}")
async def get_search(search_id: str):
    row = await sb.select_one("saved_searches", {
        "id": f"eq.{search_id}",
        "select": "*,search_processing_rules(*)",
    })
    if not row:
        raise HTTPException(404, "Search not found")
    return row


@app.post("/api/searches", status_code=201)
async def create_search(body: SearchCreate):
    data = body.model_dump(exclude_none=True)
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("is_active", True)

    # Auto-link default rule
    if not data.get("processing_rules_id"):
        rules = await sb.select("search_processing_rules", {
            "search_type": f"eq.{data.get('search_type', 'buy')}",
            "select": "id",
            "limit": "1",
        })
        if rules:
            data["processing_rules_id"] = rules[0]["id"]

    return await sb.insert("saved_searches", data)


@app.patch("/api/searches/{search_id}")
async def update_search(search_id: str, body: SearchUpdate):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    result = await sb.update("saved_searches", search_id, data)
    scheduler.reload_search(search_id)
    return result


@app.delete("/api/searches/{search_id}", status_code=204)
async def delete_search(search_id: str):
    # Delete related runs first
    resp = await sb.http.delete(sb._r("search_runs"), params={"search_id": f"eq.{search_id}"}, headers=sb._h())
    resp.raise_for_status()
    await sb.delete("saved_searches", search_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. RULES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RuleUpdate(BaseModel):
    name: str | None = None
    score_threshold: float | None = None
    check_interval_minutes: int | None = None
    max_leads_per_run: int | None = None
    alert_on_new: bool | None = None
    alert_on_price_change: bool | None = None
    alert_on_price_drop_pct: float | None = None
    auto_questions: list[str] | None = None
    llm_prompt: str | None = None
    green_flags: list[str] | None = None
    red_flags: list[str] | None = None
    custom_rules: dict | None = None


@app.get("/api/rules")
async def list_rules(search_type: str | None = None):
    params: dict[str, str] = {"select": "*", "order": "created_at.desc"}
    if search_type:
        params["search_type"] = f"eq.{search_type}"
    return await sb.select("search_processing_rules", params)


@app.get("/api/rules/{rule_id}")
async def get_rule(rule_id: str):
    row = await sb.select_one("search_processing_rules", {"id": f"eq.{rule_id}", "select": "*"})
    if not row:
        raise HTTPException(404, "Rule not found")
    return row


@app.patch("/api/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdate):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    result = await sb.update("search_processing_rules", rule_id, data)
    # Reload all searches that use this rule
    searches = await sb.select("saved_searches", {
        "processing_rules_id": f"eq.{rule_id}",
        "is_active": "eq.true",
        "select": "id",
    })
    for s in searches:
        scheduler.reload_search(s["id"])
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. SCANNED ITEMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ScannedItemUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    llm_verdict: str | None = None
    llm_score: float | None = None


@app.get("/api/scanned")
async def list_scanned(
    verdict: str | None = None,
    status: str | None = None,
    search_id: str | None = None,
    model: str | None = None,
    reserved: bool | None = None,
    min_score: float | None = None,
    published_from: str | None = None,
    published_to: str | None = None,
    sort: str = "scanned_at.desc",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    params: dict[str, str] = {
        "select": "*",
        "order": sort,
        "limit": str(limit),
        "offset": str(offset),
    }
    if verdict:
        params["llm_verdict"] = f"eq.{verdict}"
    if status:
        params["status"] = f"eq.{status}"
    if search_id:
        params["search_id"] = f"eq.{search_id}"
    if model:
        params["model"] = f"ilike.*{model}*"
    if reserved is not None:
        params["is_reserved"] = f"eq.{str(reserved).lower()}"
    if min_score is not None:
        params["llm_score"] = f"gte.{min_score}"
    if published_from:
        params["published_at"] = f"gte.{published_from}"
    if published_to:
        # PostgREST doesn't support two conditions on same column easily
        # Use "and" syntax
        if "published_at" in params:
            params["and"] = f"(published_at.gte.{published_from},published_at.lte.{published_to})"
            del params["published_at"]
        else:
            params["published_at"] = f"lte.{published_to}"

    return await sb.select("scanned_items", params)


@app.get("/api/scanned/stats")
async def scanned_stats():
    total = await sb.count("scanned_items")
    reserved = await sb.count("scanned_items", {"is_reserved": "eq.true"})

    # Count by verdict
    by_verdict = {}
    for v in ("ok", "partial", "risk", "skip"):
        c = await sb.count("scanned_items", {"llm_verdict": f"eq.{v}"})
        if c:
            by_verdict[v] = c
    none_verdict = total - sum(by_verdict.values())
    if none_verdict > 0:
        by_verdict["none"] = none_verdict

    # Count by status
    by_status = {}
    for s in ("new", "viewed", "lead_created", "sent_to_tg", "skipped"):
        c = await sb.count("scanned_items", {"status": f"eq.{s}"})
        if c:
            by_status[s] = c
    other_status = total - sum(by_status.values())
    if other_status > 0:
        by_status["other"] = other_status

    return {
        "total": total,
        "reserved": reserved,
        "by_verdict": by_verdict,
        "by_status": by_status,
    }


@app.get("/api/scanned/{item_id}")
async def get_scanned_item(item_id: str):
    row = await sb.select_one("scanned_items", {"id": f"eq.{item_id}", "select": "*"})
    if not row:
        raise HTTPException(404, "Item not found")
    return row


@app.patch("/api/scanned/{item_id}")
async def update_scanned_item(item_id: str, body: ScannedItemUpdate):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    if data.get("status") == "viewed":
        data["viewed_at"] = datetime.now(timezone.utc).isoformat()
    return await sb.update("scanned_items", item_id, data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. SEARCH RUNS (history)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/api/runs/{search_id}")
async def get_runs(search_id: str, limit: int = 30):
    return await sb.select("search_runs", {
        "search_id": f"eq.{search_id}",
        "select": "*",
        "order": "run_at.desc",
        "limit": str(limit),
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. LEADS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LeadCreate(BaseModel):
    item_id: str
    title: str
    price: int | None = None
    score: float | None = None
    notes: str | None = None
    seller_id: str | None = None
    channel_id: str | None = None
    url: str | None = None


class LeadUpdate(BaseModel):
    status: str | None = None
    score: float | None = None
    notes: str | None = None
    channel_id: str | None = None


@app.get("/api/leads")
async def list_leads(
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    params: dict[str, str] = {
        "select": "*",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if status:
        params["status"] = f"eq.{status}"
    return await sb.select("leads", params)


@app.post("/api/leads", status_code=201)
async def create_lead(body: LeadCreate):
    data = body.model_dump(exclude_none=True)
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("status", "new")
    return await sb.insert("leads", data)


@app.patch("/api/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdate):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    return await sb.update("leads", lead_id, data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. SCHEDULER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/api/scheduler/status")
async def scheduler_status():
    return scheduler.status()


@app.post("/api/scheduler/start")
async def scheduler_start():
    await scheduler.start()
    return {"ok": True, "running": scheduler._running}


@app.post("/api/scheduler/stop")
async def scheduler_stop():
    await scheduler.stop()
    return {"ok": True, "running": scheduler._running}


@app.post("/api/scheduler/run/{search_id}")
async def scheduler_run_one(search_id: str):
    result = await scheduler.run_scan(search_id)
    if result.error:
        raise HTTPException(500, result.error)
    return {
        "search_id": result.search_id,
        "search_name": result.search_name,
        "total_found": result.total_found,
        "new_items": result.new_items,
        "leads_created": result.leads_created,
    }


@app.post("/api/scheduler/run-all")
async def scheduler_run_all():
    searches = await sb.select("saved_searches", {
        "is_active": "eq.true",
        "select": "id,name",
    })
    results = []
    for s in searches:
        result = await scheduler.run_scan(s["id"])
        results.append({
            "search_id": result.search_id,
            "search_name": result.search_name,
            "new_items": result.new_items,
            "leads_created": result.leads_created,
            "error": result.error,
        })
    return {"ran": len(results), "results": results}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. TELEGRAM (отправка в канал)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TG_BOT_TOKEN = settings.tg_notify_bot_token
TG_API = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"


class TgSendRequest(BaseModel):
    chat_id: str | int
    item_id: str  # scanned_items.id


@app.post("/api/tg/send")
async def send_to_telegram(body: TgSendRequest):
    """Отправить отсканированный товар в TG канал."""
    item = await sb.select_one("scanned_items", {"id": f"eq.{body.item_id}", "select": "*"})
    if not item:
        raise HTTPException(404, "Item not found")

    # Format message
    verdict_emoji = {"ok": "\u2705", "partial": "\u26A0\uFE0F", "risk": "\u274C", "skip": "\u23ED"}.get(item.get("llm_verdict", ""), "\u2753")
    reserved = "\u26D4 ЗАРЕЗЕРВИРОВАН" if item.get("is_reserved") else ""

    lines = [
        f"{verdict_emoji} *{_esc(item['title'])}*",
        f"\U0001F4B0 {item['price']:,} \u20BD" if item.get("price") else "",
        f"\U0001F4CD {_esc(item.get('location', ''))}" if item.get("location") else "",
        reserved,
        "",
        f"Score: *{item.get('llm_score', '?')}*/10" if item.get("llm_score") is not None else "",
        _esc(item.get("llm_summary", "")) if item.get("llm_summary") else "",
        "",
    ]

    # Green flags
    gf = item.get("llm_green_flags") or []
    if gf:
        lines.append("\u2705 " + ", ".join(gf))

    # Red flags
    rf = item.get("llm_red_flags") or []
    if rf:
        lines.append("\u274C " + ", ".join(rf))

    # Missing info
    mi = item.get("llm_missing_info") or []
    if mi:
        lines.append("\u2753 Уточнить: " + ", ".join(mi))

    if item.get("url"):
        lines.append("")
        lines.append(f"[\U0001F517 Открыть на Avito]({item['url']})")

    text = "\n".join(l for l in lines if l is not None)

    # Send photo + text or just text
    image = (item.get("images") or [None])[0]

    tg_client_kwargs: dict = {"timeout": 15.0}
    if settings.tg_notify_proxy:
        tg_client_kwargs["proxy"] = settings.tg_notify_proxy

    async with httpx.AsyncClient(**tg_client_kwargs) as client:
        if image:
            resp = await client.post(f"{TG_API}/sendPhoto", json={
                "chat_id": body.chat_id,
                "photo": image,
                "caption": text,
                "parse_mode": "Markdown",
            })
        else:
            resp = await client.post(f"{TG_API}/sendMessage", json={
                "chat_id": body.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            })

    result = resp.json()
    if not result.get("ok"):
        raise HTTPException(502, f"Telegram error: {result.get('description', 'unknown')}")

    # Update item status
    msg_id = result.get("result", {}).get("message_id")
    await sb.update("scanned_items", body.item_id, {
        "status": "sent_to_tg",
        "tg_message_id": msg_id,
    })

    return {"ok": True, "message_id": msg_id}


def _esc(s: str) -> str:
    """Escape Markdown special chars."""
    for c in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]:
        s = s.replace(c, f"\\{c}")
    return s


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8132, reload=False)
