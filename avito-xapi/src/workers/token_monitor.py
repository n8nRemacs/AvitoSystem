import asyncio
import logging
from src.workers import jwt_parser
from src.workers.session_reader import SessionData

logger = logging.getLogger("xapi.token_monitor")

# Alert thresholds in seconds
ALERT_WARNING = 30 * 60   # 30 minutes
ALERT_CRITICAL = 10 * 60  # 10 minutes


def get_alerts_for_session(session: SessionData) -> list[dict]:
    """Generate alerts for a single session based on TTL."""
    alerts = []
    ttl = jwt_parser.time_left(session.session_token)

    if ttl <= 0:
        alerts.append({
            "level": "expired",
            "message": "Token has expired. Upload a new session or authorize through browser.",
            "ttl_seconds": ttl,
        })
    elif ttl <= ALERT_CRITICAL:
        minutes = ttl // 60
        alerts.append({
            "level": "critical",
            "message": f"Token expires in {minutes} min! Launch Avito on Android/Redroid immediately.",
            "ttl_seconds": ttl,
        })
    elif ttl <= ALERT_WARNING:
        minutes = ttl // 60
        alerts.append({
            "level": "warning",
            "message": f"Token expires in {minutes} min. Prepare to refresh.",
            "ttl_seconds": ttl,
        })

    return alerts
