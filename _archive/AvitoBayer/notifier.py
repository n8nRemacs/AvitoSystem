"""
Telegram уведомления — отправка сводок и лидов в Avito-бот.

Прокси SOCKS5 через Homelab (api.telegram.org заблокирован).
"""
import logging
from typing import TYPE_CHECKING

import httpx

from config import settings

if TYPE_CHECKING:
    from scheduler import ScanResult

logger = logging.getLogger("avito-notifier")


def _esc(s: str) -> str:
    """Escape Markdown v1 special chars."""
    if not s:
        return ""
    for c in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]:
        s = s.replace(c, f"\\{c}")
    return s


class TelegramNotifier:
    def __init__(self):
        self._token = settings.tg_notify_bot_token
        self._chat_id = settings.tg_notify_chat_id
        self._proxy = settings.tg_notify_proxy
        self._enabled = settings.tg_notify_enabled
        self._api = f"https://api.telegram.org/bot{self._token}"
        self._http: httpx.AsyncClient | None = None

    async def init(self):
        kwargs: dict = {"timeout": 15.0}
        if self._proxy:
            kwargs["proxy"] = self._proxy
        self._http = httpx.AsyncClient(**kwargs)

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _send(self, method: str, payload: dict) -> bool:
        if not self._enabled or not self._token or not self._chat_id:
            return False
        if not self._http:
            await self.init()
        try:
            resp = await self._http.post(f"{self._api}/{method}", json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"TG {method} failed: {data.get('description')}")
                return False
            return True
        except Exception as e:
            logger.error(f"TG send error ({method}): {e}")
            return False

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        return await self._send("sendMessage", {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        })

    async def send_photo(self, photo_url: str, caption: str, parse_mode: str = "Markdown") -> bool:
        return await self._send("sendPhoto", {
            "chat_id": self._chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": parse_mode,
        })

    async def send_scan_summary(self, result: "ScanResult") -> bool:
        """Сводка после скана — отправляем только если есть новые items."""
        if result.new_items == 0 and result.leads_created == 0:
            return False

        prices = result.prices
        price_line = ""
        if prices:
            p_min = min(prices)
            p_max = max(prices)
            p_med = sorted(prices)[len(prices) // 2]
            price_line = f"\nЦены: {p_min:,} – {p_max:,} ₽ (медиана {p_med:,} ₽)"

        text = (
            f"📊 *Скан: {_esc(result.search_name)}*\n"
            f"Найдено: {result.total_found} | Новых: {result.new_items} | Лидов: {result.leads_created}"
            f"{price_line}"
        )
        return await self.send_message(text)

    async def send_new_leads(self, leads: list[dict], search: dict) -> None:
        """Карточки новых лидов."""
        for item in leads:
            await self._send_lead_card(item)

    async def _send_lead_card(self, item: dict) -> bool:
        verdict_emoji = {
            "ok": "✅", "partial": "⚠️", "risk": "❌", "skip": "⏭"
        }.get(item.get("llm_verdict", ""), "❓")

        lines = [
            f"{verdict_emoji} *{_esc(item.get('title', ''))}*",
            f"💰 {item['price']:,} ₽" if item.get("price") else "",
            f"📍 {_esc(item.get('location', ''))}" if item.get("location") else "",
            "",
        ]

        score = item.get("llm_score")
        if score is not None:
            lines.append(f"Score: *{score}*/10")
        if item.get("llm_summary"):
            lines.append(_esc(item["llm_summary"]))

        gf = item.get("llm_green_flags") or []
        rf = item.get("llm_red_flags") or []
        mi = item.get("llm_missing_info") or []
        if gf:
            lines.append("✅ " + ", ".join(gf))
        if rf:
            lines.append("❌ " + ", ".join(rf))
        if mi:
            lines.append("❓ Уточнить: " + ", ".join(mi))

        if item.get("url"):
            lines.append("")
            lines.append(f"[🔗 Открыть на Avito]({item['url']})")

        text = "\n".join(line for line in lines if line is not None)
        images = item.get("images") or []
        photo = images[0] if images else None
        if photo:
            return await self.send_photo(photo, text)
        return await self.send_message(text)

    async def send_price_drop(self, item: dict, old_price: int, new_price: int, change_pct: float) -> bool:
        text = (
            f"🔻 *Цена упала: {_esc(item.get('title', ''))}*\n"
            f"{old_price:,} ₽ → {new_price:,} ₽ (−{change_pct:.0f}%)"
        )
        if item.get("url"):
            text += f"\n{item['url']}"
        return await self.send_message(text)

    async def send_price_change(self, item: dict, old_price: int, new_price: int) -> bool:
        direction = "🔻" if new_price < old_price else "🔺"
        diff = abs(new_price - old_price)
        text = (
            f"{direction} *Цена изменилась: {_esc(item.get('title', ''))}*\n"
            f"{old_price:,} ₽ → {new_price:,} ₽ (±{diff:,} ₽)"
        )
        if item.get("url"):
            text += f"\n{item['url']}"
        return await self.send_message(text)

    async def send_new_competitor(self, item: dict) -> bool:
        price_str = f"{item['price']:,} ₽" if item.get("price") else "цена не указана"
        city = item.get("city") or item.get("address", "")
        text = (
            f"🆕 *Новый конкурент: {_esc(item.get('title', ''))}*\n"
            f"{price_str} | {_esc(city)}"
        )
        if item.get("url"):
            text += f"\n{item['url']}"
        return await self.send_message(text)
