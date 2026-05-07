import os
import time
from curl_cffi import requests as curl_requests
from src.workers.rate_limiter import TokenBucket
from src.workers.session_reader import SessionData
from src.config import settings


class BaseAvitoClient:
    """Base HTTP client for Avito API with TLS impersonation and rate limiting."""

    BASE_URL = "https://app.avito.ru/api"
    APP_VERSION = "215.1"

    def __init__(self, session_data: SessionData, rate_limiter: TokenBucket | None = None):
        self.session_data = session_data
        # QRATOR на стороне Avito привязывает trust-score к паре (token, IP).
        # JWT, выпущенный для Avito-app на телефоне (через VPN-выход
        # 155.212.217.226), captcha-блокируется при первом же использовании
        # с любого другого IP — в т.ч. с нашего VPS. Чтобы исходящие запросы
        # к Avito выходили с того же IP, что и Avito-app, маршрутизируем их
        # через SOCKS5 (ssh -D туннель до ru-vpn). Все остальные запросы
        # (Supabase REST, и т.п.) идут напрямую — этот прокси относится
        # только к curl_cffi-сессии, которая стучится в app.avito.ru.
        proxy_url = (os.environ.get("AVITO_SOCKS_PROXY") or "").strip()
        if proxy_url:
            self.http = curl_requests.Session(
                impersonate="chrome120",
                proxies={"http": proxy_url, "https": proxy_url},
            )
        else:
            self.http = curl_requests.Session(impersonate="chrome120")
        self.rate_limiter = rate_limiter or TokenBucket(
            rate=settings.rate_limit_rps,
            burst=settings.rate_limit_burst,
        )

    def _headers(self) -> dict[str, str]:
        """Build the 12+ mandatory headers for Avito API."""
        sd = self.session_data
        cookie_parts = [f"sessid={sd.session_token}"]
        if sd.cookies:
            for k, v in sd.cookies.items():
                cookie_parts.append(f"{k}={v}")

        return {
            "User-Agent": f"AVITO {self.APP_VERSION} (OnePlus LE2115; Android 14; ru)",
            "X-Session": sd.session_token,
            "X-DeviceId": sd.device_id or "",
            "X-RemoteDeviceId": sd.remote_device_id or "",
            "f": sd.fingerprint or "",
            "X-App": "avito",
            "X-Platform": "android",
            "X-AppVersion": self.APP_VERSION,
            "Content-Type": "application/json",
            "Cookie": "; ".join(cookie_parts),
            "X-Date": str(int(time.time())),
            "Accept-Encoding": "zstd;q=1.0, gzip;q=0.8",
        }
