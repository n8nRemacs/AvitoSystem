"""
Avito Session Manager
Handles authentication and session persistence

Based on reverse engineering of Avito Android app
"""

import json
import os
import time
import uuid
import hashlib
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AvitoSession")


@dataclass
class SessionData:
    """Complete session data structure"""
    sessid: str
    user_id: Optional[str] = None
    user_hash: Optional[str] = None
    device_id: Optional[str] = None
    phone: Optional[str] = None
    created_at: int = 0
    expires_at: int = 0
    refresh_token: Optional[str] = None

    def __post_init__(self):
        if not self.device_id:
            self.device_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = int(time.time())

    def is_expired(self) -> bool:
        """Check if session is expired"""
        if self.expires_at == 0:
            return False  # No expiration set
        return time.time() > self.expires_at

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'SessionData':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AvitoSessionManager:
    """
    Manages Avito authentication sessions

    Supports:
    - Manual sessid input (from browser cookies)
    - Phone number + SMS code authentication
    - Session persistence (save/load)
    - Session refresh
    """

    # API Endpoints
    AUTH_API = "https://api.avito.ru/auth"
    MOBILE_API = "https://app.avito.ru/api"
    WEB_API = "https://www.avito.ru/web/1"

    DEFAULT_HEADERS = {
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        "X-App": "avito",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def __init__(self, session_file: str = "avito_session.json"):
        self.session_file = Path(session_file)
        self.session: Optional[SessionData] = None
        self._http: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        await self._init_http()
        return self

    async def __aexit__(self, *args):
        await self._close_http()

    async def _init_http(self):
        """Initialize HTTP session"""
        if not self._http or self._http.closed:
            self._http = aiohttp.ClientSession(headers=self.DEFAULT_HEADERS)

    async def _close_http(self):
        """Close HTTP session"""
        if self._http and not self._http.closed:
            await self._http.close()

    def _get_device_id(self) -> str:
        """Generate consistent device ID"""
        if self.session and self.session.device_id:
            return self.session.device_id
        return str(uuid.uuid4())

    # ============ Session Persistence ============

    def save_session(self) -> bool:
        """Save session to file"""
        if not self.session:
            logger.warning("No session to save")
            return False

        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.session.to_dict(), f, indent=2)
            logger.info(f"Session saved to {self.session_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self) -> bool:
        """Load session from file"""
        if not self.session_file.exists():
            logger.info("No saved session found")
            return False

        try:
            with open(self.session_file, 'r') as f:
                data = json.load(f)
            self.session = SessionData.from_dict(data)

            if self.session.is_expired():
                logger.warning("Loaded session is expired")
                return False

            logger.info(f"Session loaded for user: {self.session.user_id or 'unknown'}")
            return True
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False

    def clear_session(self):
        """Clear current session"""
        self.session = None
        if self.session_file.exists():
            self.session_file.unlink()
        logger.info("Session cleared")

    # ============ Manual Session ============

    def set_sessid(self, sessid: str, user_id: str = None, user_hash: str = None) -> SessionData:
        """
        Set session manually from sessid token

        You can get sessid from:
        - Browser DevTools > Application > Cookies > avito.ru > sessid
        - Captured traffic
        """
        self.session = SessionData(
            sessid=sessid,
            user_id=user_id,
            user_hash=user_hash,
            device_id=self._get_device_id()
        )
        self.save_session()
        logger.info("Session set from sessid")
        return self.session

    # ============ Phone Authentication ============

    async def request_sms_code(self, phone: str) -> Dict[str, Any]:
        """
        Request SMS code for phone authentication

        Args:
            phone: Phone number in format +79XXXXXXXXX or 79XXXXXXXXX

        Returns:
            Response data with status
        """
        await self._init_http()

        # Normalize phone
        phone = phone.replace("+", "").replace("-", "").replace(" ", "")
        if not phone.startswith("7"):
            phone = "7" + phone

        device_id = self._get_device_id()

        try:
            # Request SMS code
            async with self._http.post(
                f"{self.AUTH_API}/send-code",
                headers={
                    **self.DEFAULT_HEADERS,
                    "X-DeviceId": device_id,
                },
                json={
                    "phone": phone,
                    "type": "sms"
                }
            ) as resp:
                data = await resp.json()

                if resp.status == 200:
                    logger.info(f"SMS code requested for {phone}")
                    # Store phone for verification
                    self.session = SessionData(
                        sessid="",
                        phone=phone,
                        device_id=device_id
                    )
                    return {"success": True, "data": data}
                else:
                    logger.error(f"SMS request failed: {data}")
                    return {"success": False, "error": data}

        except Exception as e:
            logger.error(f"SMS request error: {e}")
            return {"success": False, "error": str(e)}

    async def verify_sms_code(self, code: str) -> Dict[str, Any]:
        """
        Verify SMS code and complete authentication

        Args:
            code: 6-digit SMS code

        Returns:
            Response with session data
        """
        if not self.session or not self.session.phone:
            return {"success": False, "error": "No phone number set. Call request_sms_code first"}

        await self._init_http()

        try:
            async with self._http.post(
                f"{self.AUTH_API}/verify-code",
                headers={
                    **self.DEFAULT_HEADERS,
                    "X-DeviceId": self.session.device_id,
                },
                json={
                    "phone": self.session.phone,
                    "code": code
                }
            ) as resp:
                data = await resp.json()

                if resp.status == 200 and "session" in data:
                    # Extract session token
                    sessid = data.get("session", {}).get("sessid") or data.get("sessid")
                    user_id = data.get("user", {}).get("id")
                    user_hash = data.get("user", {}).get("hash")

                    if sessid:
                        self.session.sessid = sessid
                        self.session.user_id = str(user_id) if user_id else None
                        self.session.user_hash = user_hash
                        self.session.created_at = int(time.time())

                        # Set expiration (typically 30 days)
                        expires_in = data.get("expires_in", 30 * 24 * 3600)
                        self.session.expires_at = int(time.time()) + expires_in

                        self.save_session()
                        logger.info(f"Authentication successful for user {user_id}")
                        return {"success": True, "session": self.session}

                logger.error(f"Verification failed: {data}")
                return {"success": False, "error": data}

        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {"success": False, "error": str(e)}

    # ============ Session Validation ============

    async def validate_session(self) -> bool:
        """
        Validate current session by making a test API call

        Returns:
            True if session is valid
        """
        if not self.session or not self.session.sessid:
            return False

        await self._init_http()

        try:
            async with self._http.get(
                f"{self.MOBILE_API}/1/profile/info",
                headers={
                    **self.DEFAULT_HEADERS,
                    "Cookie": f"sessid={self.session.sessid}",
                    "X-Session": self.session.sessid,
                    "X-DeviceId": self.session.device_id,
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Update user info
                    if "result" in data:
                        result = data["result"]
                        self.session.user_id = str(result.get("id", self.session.user_id))
                        self.session.user_hash = result.get("hash", self.session.user_hash)
                        self.save_session()
                    logger.info("Session is valid")
                    return True
                elif resp.status == 401:
                    logger.warning("Session is invalid or expired")
                    return False
                else:
                    logger.warning(f"Session validation returned {resp.status}")
                    return False

        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False

    async def get_user_info(self) -> Optional[Dict]:
        """Get current user information"""
        if not self.session or not self.session.sessid:
            return None

        await self._init_http()

        try:
            async with self._http.get(
                f"{self.MOBILE_API}/1/profile/info",
                headers={
                    **self.DEFAULT_HEADERS,
                    "Cookie": f"sessid={self.session.sessid}",
                    "X-Session": self.session.sessid,
                    "X-DeviceId": self.session.device_id,
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()

        except Exception as e:
            logger.error(f"Get user info error: {e}")

        return None

    # ============ Session Refresh ============

    async def refresh_session(self) -> bool:
        """
        Attempt to refresh the session

        Note: This may not be available if refresh token is not stored
        """
        if not self.session:
            return False

        # If we have a refresh token, use it
        if self.session.refresh_token:
            await self._init_http()

            try:
                async with self._http.post(
                    f"{self.AUTH_API}/refresh",
                    headers={
                        **self.DEFAULT_HEADERS,
                        "X-DeviceId": self.session.device_id,
                    },
                    json={
                        "refresh_token": self.session.refresh_token
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "sessid" in data:
                            self.session.sessid = data["sessid"]
                            self.session.created_at = int(time.time())
                            self.save_session()
                            logger.info("Session refreshed")
                            return True

            except Exception as e:
                logger.error(f"Session refresh error: {e}")

        return False


# ============ Utility Functions ============

def extract_sessid_from_cookies(cookies_str: str) -> Optional[str]:
    """
    Extract sessid from browser cookies string

    Args:
        cookies_str: Cookie string from browser (document.cookie or exported)

    Returns:
        sessid value or None
    """
    for cookie in cookies_str.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("sessid="):
            return cookie[7:]
    return None


def extract_sessid_from_file(cookie_file: str) -> Optional[str]:
    """
    Extract sessid from exported cookies file (JSON format)

    Args:
        cookie_file: Path to cookies JSON file

    Returns:
        sessid value or None
    """
    try:
        with open(cookie_file, 'r') as f:
            cookies = json.load(f)

        for cookie in cookies:
            if isinstance(cookie, dict):
                if cookie.get("name") == "sessid":
                    return cookie.get("value")
            elif isinstance(cookie, str) and cookie.startswith("sessid="):
                return cookie[7:]

    except Exception as e:
        logger.error(f"Failed to extract sessid from file: {e}")

    return None


# ============ CLI Interface ============

async def interactive_login():
    """Interactive login via command line"""
    print("\n=== Avito Session Manager ===\n")

    manager = AvitoSessionManager()

    # Check for existing session
    if manager.load_session():
        print(f"Found existing session for user: {manager.session.user_id}")

        async with manager:
            if await manager.validate_session():
                print("Session is still valid!")
                return manager.session
            else:
                print("Session expired, need to re-authenticate")

    print("\nAuthentication options:")
    print("1. Enter sessid manually (from browser)")
    print("2. Login with phone number (SMS)")

    choice = input("\nSelect option (1/2): ").strip()

    if choice == "1":
        sessid = input("Enter sessid: ").strip()
        if sessid:
            manager.set_sessid(sessid)
            async with manager:
                if await manager.validate_session():
                    print(f"\nSuccess! Logged in as user: {manager.session.user_id}")
                    return manager.session
                else:
                    print("\nInvalid sessid")
                    return None

    elif choice == "2":
        phone = input("Enter phone number (e.g., +79123456789): ").strip()

        async with manager:
            result = await manager.request_sms_code(phone)
            if result["success"]:
                code = input("Enter SMS code: ").strip()
                result = await manager.verify_sms_code(code)

                if result["success"]:
                    print(f"\nSuccess! Logged in as user: {manager.session.user_id}")
                    return manager.session
                else:
                    print(f"\nFailed: {result.get('error')}")
            else:
                print(f"\nFailed to send SMS: {result.get('error')}")

    return None


if __name__ == "__main__":
    asyncio.run(interactive_login())
