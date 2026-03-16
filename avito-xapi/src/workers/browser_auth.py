"""
Browser Auth — Playwright manager for remote Avito authorization.

Flow:
  1. Backend launches headless Chromium via Playwright → opens avito.ru/login
  2. Browser screenshots are streamed to the frontend via WebSocket (base64 JPEG)
  3. User keyboard/mouse events are relayed from frontend → Playwright
  4. After login, Playwright extracts cookies + tokens from browser storage
  5. Tokens saved to Supabase (avito_sessions)
  6. Browser is closed

Security: We never see/store the user's password. The user types directly
into the real Avito page rendered in the headless browser. Only cookies/tokens
are extracted after successful login.
"""

import asyncio
import base64
import json
import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger("xapi.browser_auth")

# Playwright is optional — only imported when browser auth is used
_playwright = None
_browser = None


async def _ensure_playwright():
    """Lazy-init Playwright and browser."""
    global _playwright, _browser
    if _browser is not None:
        return _browser

    try:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=420,900",  # Mobile-like viewport
            ],
        )
        logger.info("Playwright browser launched")
        return _browser
    except ImportError:
        raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")
    except Exception as e:
        logger.error("Failed to launch Playwright: %s", e)
        raise


class BrowserAuthSession:
    """Manages a single browser auth session for a tenant."""

    AVITO_LOGIN_URL = "https://www.avito.ru/login"
    SCREENSHOT_INTERVAL = 0.5  # seconds between screenshots
    TOKEN_CHECK_INTERVAL = 2.0  # seconds between token checks after page load

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.page = None
        self.context = None
        self._running = False
        self._token_data: dict[str, Any] | None = None

    async def start(self) -> None:
        """Launch browser context and navigate to Avito login."""
        browser = await _ensure_playwright()
        self.context = await browser.new_context(
            viewport={"width": 420, "height": 900},
            user_agent="Mozilla/5.0 (Linux; Android 14; OnePlus LE2115) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            locale="ru-RU",
        )
        self.page = await self.context.new_page()
        await self.page.goto(self.AVITO_LOGIN_URL, wait_until="domcontentloaded")
        self._running = True
        logger.info("Browser auth session started for tenant %s", self.tenant_id)

    async def screenshot(self) -> str:
        """Take a screenshot and return as base64 JPEG."""
        if not self.page:
            return ""
        png_bytes = await self.page.screenshot(type="jpeg", quality=60)
        return base64.b64encode(png_bytes).decode("ascii")

    async def send_key(self, key: str) -> None:
        """Send a keyboard key press to the page."""
        if not self.page:
            return
        await self.page.keyboard.press(key)

    async def send_text(self, text: str) -> None:
        """Type text into the currently focused element."""
        if not self.page:
            return
        await self.page.keyboard.type(text, delay=50)

    async def click(self, x: int, y: int) -> None:
        """Click at coordinates on the page."""
        if not self.page:
            return
        await self.page.mouse.click(x, y)

    async def check_auth_complete(self) -> dict[str, Any] | None:
        """Check if user has successfully logged in by looking for session cookies/tokens.

        Returns token data dict if auth is complete, None otherwise.
        """
        if not self.page:
            return None

        try:
            cookies = await self.context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}

            # Check for Avito session cookie (sessid or session-related)
            session_token = cookie_dict.get("sessid")
            if not session_token:
                # Try to get from localStorage
                session_token = await self.page.evaluate(
                    "() => localStorage.getItem('session_token') || localStorage.getItem('accessToken')"
                )

            if not session_token:
                # Check if we're on a post-login page (not /login anymore)
                current_url = self.page.url
                if "/login" not in current_url and "avito.ru" in current_url:
                    # User is logged in, try to extract from page
                    session_token = await self.page.evaluate("""() => {
                        try {
                            const data = JSON.parse(localStorage.getItem('auth') || '{}');
                            return data.token || data.session_token || null;
                        } catch(e) { return null; }
                    }""")

            if session_token:
                self._token_data = {
                    "session_token": session_token,
                    "refresh_token": cookie_dict.get("refresh_token"),
                    "cookies": cookie_dict,
                    "source": "browser",
                }
                logger.info("Auth complete for tenant %s, token extracted", self.tenant_id)
                return self._token_data

        except Exception as e:
            logger.debug("Auth check failed: %s", e)

        return None

    async def close(self) -> None:
        """Close browser context and clean up."""
        self._running = False
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
            self.page = None
        logger.info("Browser auth session closed for tenant %s", self.tenant_id)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def token_data(self) -> dict[str, Any] | None:
        return self._token_data


# ── Session registry (one per tenant) ─────────────────

_sessions: dict[str, BrowserAuthSession] = {}


async def start_session(tenant_id: str) -> BrowserAuthSession:
    """Start a new browser auth session for a tenant."""
    if tenant_id in _sessions:
        await _sessions[tenant_id].close()
    session = BrowserAuthSession(tenant_id)
    await session.start()
    _sessions[tenant_id] = session
    return session


def get_session(tenant_id: str) -> BrowserAuthSession | None:
    """Get existing browser auth session."""
    return _sessions.get(tenant_id)


async def close_session(tenant_id: str) -> None:
    """Close and remove a browser auth session."""
    session = _sessions.pop(tenant_id, None)
    if session:
        await session.close()
