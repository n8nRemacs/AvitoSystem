import json
import base64
import time
from typing import Any


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload without signature verification (Avito uses HS512, we don't have the secret)."""
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT: expected at least 2 parts")

    payload_b64 = parts[1]
    # Add padding
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding

    decoded = base64.urlsafe_b64decode(payload_b64)
    return json.loads(decoded)


def decode_jwt_header(token: str) -> dict[str, Any]:
    """Decode JWT header."""
    parts = token.split(".")
    if not parts:
        raise ValueError("Invalid JWT: empty string")

    header_b64 = parts[0]
    padding = 4 - len(header_b64) % 4
    if padding != 4:
        header_b64 += "=" * padding

    decoded = base64.urlsafe_b64decode(header_b64)
    return json.loads(decoded)


def get_expiry(token: str) -> int | None:
    """Get expiration timestamp (Unix seconds) from JWT."""
    try:
        payload = decode_jwt_payload(token)
        return payload.get("exp")
    except Exception:
        return None


def is_expired(token: str) -> bool:
    """Check if token is expired."""
    exp = get_expiry(token)
    if exp is None:
        return True
    return time.time() > exp


def time_left(token: str) -> int:
    """Seconds remaining until token expires. Negative if expired."""
    exp = get_expiry(token)
    if exp is None:
        return -1
    return int(exp - time.time())


def get_user_id(token: str) -> int | None:
    """Extract Avito user_id from JWT payload."""
    try:
        payload = decode_jwt_payload(token)
        return payload.get("user_id") or payload.get("sub")
    except Exception:
        return None
