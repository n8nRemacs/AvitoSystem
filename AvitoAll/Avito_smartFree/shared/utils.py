"""
Utility functions for Avito SmartFree
"""

import base64
import json
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class JWTPayload:
    """Parsed JWT payload from Avito token"""
    exp: int                    # Expiration timestamp
    iat: int                    # Issued at timestamp
    user_id: int                # User ID (u)
    profile_id: Optional[int]   # Profile ID (p)
    session_hash: Optional[str] # Session hash (s)
    device_id: Optional[str]    # Device ID (d)
    platform: Optional[str]     # Platform (pl)

    @property
    def expires_at(self) -> datetime:
        """Get expiration as datetime"""
        return datetime.utcfromtimestamp(self.exp)

    @property
    def issued_at(self) -> datetime:
        """Get issued at as datetime"""
        return datetime.utcfromtimestamp(self.iat)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def hours_until_expiry(self) -> float:
        """Get hours until expiration"""
        delta = self.expires_at - datetime.utcnow()
        return delta.total_seconds() / 3600


def parse_jwt(token: str) -> Optional[JWTPayload]:
    """
    Parse JWT token and extract payload

    Args:
        token: JWT token string

    Returns:
        JWTPayload object or None if parsing fails
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload_b64 = parts[1]

        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        # Decode base64
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload_dict = json.loads(payload_bytes.decode("utf-8"))

        return JWTPayload(
            exp=payload_dict.get("exp", 0),
            iat=payload_dict.get("iat", 0),
            user_id=payload_dict.get("u", 0),
            profile_id=payload_dict.get("p"),
            session_hash=payload_dict.get("s"),
            device_id=payload_dict.get("d"),
            platform=payload_dict.get("pl")
        )
    except Exception:
        return None


def format_time_left(hours: float) -> str:
    """
    Format hours as human-readable string

    Args:
        hours: Hours as float (can be negative)

    Returns:
        Formatted string like "2h 30m" or "45m" or "expired"
    """
    if hours <= 0:
        return "expired"

    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60

    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    else:
        return f"{m}m"


def generate_device_id() -> str:
    """
    Generate random device ID (16 hex characters)

    Returns:
        Device ID string
    """
    return secrets.token_hex(8)


def generate_android_id() -> str:
    """
    Generate random Android ID (16 hex characters)

    Returns:
        Android ID string
    """
    return secrets.token_hex(8)


def generate_imei() -> str:
    """
    Generate random valid IMEI number

    Returns:
        15-digit IMEI string
    """
    # TAC (Type Allocation Code) - first 8 digits
    # Use common TACs from Samsung
    tacs = ["35332510", "35391110", "35456711", "35478909"]
    tac = secrets.choice(tacs)

    # Serial number - next 6 digits
    serial = "".join([str(secrets.randbelow(10)) for _ in range(6)])

    # Calculate Luhn checksum
    imei_without_check = tac + serial
    checksum = _luhn_checksum(imei_without_check)

    return imei_without_check + str(checksum)


def _luhn_checksum(number: str) -> int:
    """Calculate Luhn checksum digit"""
    def digits_of(n):
        return [int(d) for d in str(n)]

    digits = digits_of(number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]

    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))

    return (10 - (checksum % 10)) % 10


def generate_remote_device_id() -> str:
    """
    Generate remote device ID for Avito

    Returns:
        Base64-encoded remote device ID
    """
    random_bytes = secrets.token_bytes(32)
    encoded = base64.b64encode(random_bytes).decode("utf-8")
    return f"{encoded}android"


def generate_user_agent(model: str = "SM-G998B", android_version: str = "12") -> str:
    """
    Generate Avito User-Agent string

    Args:
        model: Device model
        android_version: Android version

    Returns:
        User-Agent string
    """
    return f"AVITO 215.1 (Samsung {model}; Android {android_version}; ru)"


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to +7XXXXXXXXXX format

    Args:
        phone: Phone number in any format

    Returns:
        Normalized phone number
    """
    # Remove all non-digits
    digits = re.sub(r"\D", "", phone)

    # Handle different formats
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    elif not digits.startswith("7"):
        digits = "7" + digits

    return f"+{digits}"


def mask_phone(phone: str) -> str:
    """
    Mask phone number for display

    Args:
        phone: Phone number

    Returns:
        Masked phone like +7***XXX-XX-XX
    """
    normalized = normalize_phone(phone)
    if len(normalized) >= 12:
        return f"{normalized[:2]}***{normalized[5:8]}-{normalized[8:10]}-{normalized[10:12]}"
    return normalized


def mask_token(token: str, visible_chars: int = 20) -> str:
    """
    Mask token for display

    Args:
        token: Token string
        visible_chars: Number of visible characters at start

    Returns:
        Masked token
    """
    if len(token) <= visible_chars:
        return token
    return f"{token[:visible_chars]}..."


def build_avito_headers(
    session_token: str,
    fingerprint: str,
    device_id: str,
    remote_device_id: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, str]:
    """
    Build headers for Avito API requests

    Args:
        session_token: JWT session token
        fingerprint: Fingerprint header value
        device_id: Device ID
        remote_device_id: Remote device ID (optional)
        user_agent: User-Agent string (optional)

    Returns:
        Dictionary of headers
    """
    import time

    headers = {
        "User-Agent": user_agent or generate_user_agent(),
        "X-App": "avito",
        "X-Platform": "android",
        "X-AppVersion": "215.1",
        "X-DeviceId": device_id,
        "X-Session": session_token,
        "X-Date": str(int(time.time())),
        "f": fingerprint,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cookie": f"sessid={session_token}"
    }

    if remote_device_id:
        headers["X-RemoteDeviceId"] = remote_device_id

    return headers


def build_ws_url(user_hash: str) -> str:
    """
    Build WebSocket URL for Avito

    Args:
        user_hash: User hash ID

    Returns:
        WebSocket URL
    """
    return (
        f"wss://socket.avito.ru/socket"
        f"?use_seq=true"
        f"&app_name=android"
        f"&id_version=v2"
        f"&my_hash_id={user_hash}"
    )


def extract_channel_info(channel: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract useful info from Avito channel object

    Args:
        channel: Channel dict from API

    Returns:
        Simplified channel info
    """
    users = channel.get("users", [])
    other_user = users[0] if users else {}

    context = channel.get("context", {})
    item = context.get("value", {}) if context.get("type") == "item" else {}

    last_message = channel.get("lastMessage", {})
    body = last_message.get("body", {})
    text_obj = body.get("text", {})

    return {
        "id": channel.get("id"),
        "unread_count": channel.get("unreadCount", 0),
        "user_name": other_user.get("name", "Unknown"),
        "user_id": other_user.get("id"),
        "user_avatar": other_user.get("avatar", {}).get("96x96"),
        "item_title": item.get("title"),
        "item_price": item.get("price", {}).get("value"),
        "last_message_text": text_obj.get("text", ""),
        "last_message_time": last_message.get("created", 0)
    }


def extract_message_info(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract useful info from Avito message object

    Args:
        message: Message dict from API/WebSocket

    Returns:
        Simplified message info
    """
    body = message.get("body", {})
    text_obj = body.get("text", {})

    return {
        "id": message.get("id"),
        "channel_id": message.get("channelId"),
        "author_id": message.get("authorId") or message.get("fromUid"),
        "text": text_obj.get("text", ""),
        "type": message.get("type", "text"),
        "created": message.get("created", 0),
        "has_image": body.get("imageId") is not None,
        "has_voice": body.get("voiceId") is not None
    }


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = timedelta(seconds=period_seconds)
        self.calls: list[datetime] = []

    def can_call(self) -> bool:
        """Check if a call is allowed"""
        now = datetime.utcnow()
        # Remove old calls
        self.calls = [t for t in self.calls if now - t < self.period]
        return len(self.calls) < self.max_calls

    def record_call(self) -> None:
        """Record a call"""
        self.calls.append(datetime.utcnow())

    async def wait_if_needed(self) -> None:
        """Wait if rate limit is exceeded"""
        import asyncio
        while not self.can_call():
            await asyncio.sleep(0.1)
        self.record_call()
