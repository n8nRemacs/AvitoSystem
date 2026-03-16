"""
WebSocket endpoint for remote browser authentication.

Protocol (JSON messages over WebSocket):

Client → Server:
  {"type": "start"}                         — Start browser session
  {"type": "click", "x": 100, "y": 200}    — Click at coordinates
  {"type": "key", "key": "Enter"}           — Press key
  {"type": "text", "text": "hello"}         — Type text
  {"type": "close"}                         — Close session

Server → Client:
  {"type": "screenshot", "data": "base64..."} — Browser screenshot (JPEG)
  {"type": "status", "status": "started"}     — Session status update
  {"type": "auth_complete", "tokens": {...}}  — Auth successful, tokens extracted
  {"type": "error", "message": "..."}         — Error message
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.workers.browser_auth import start_session, get_session, close_session

router = APIRouter(tags=["Browser Auth"])
logger = logging.getLogger("xapi.auth_browser")


@router.websocket("/api/v1/auth/browser")
async def browser_auth_ws(ws: WebSocket):
    """WebSocket endpoint for remote Avito login via Playwright.

    The tenant must provide their API key as a query parameter:
      ws://host/api/v1/auth/browser?api_key=xxx

    Note: WebSocket auth bypasses the HTTP middleware.
    We validate the API key manually here.
    """
    await ws.accept()

    # Extract API key from query params
    api_key = ws.query_params.get("api_key")
    if not api_key:
        await ws.send_json({"type": "error", "message": "Missing api_key query parameter"})
        await ws.close()
        return

    # Validate API key → resolve tenant_id
    tenant_id = await _resolve_tenant(api_key)
    if not tenant_id:
        await ws.send_json({"type": "error", "message": "Invalid API key"})
        await ws.close()
        return

    session = None
    screenshot_task = None

    try:
        async for raw in ws.iter_json():
            msg_type = raw.get("type")

            if msg_type == "start":
                try:
                    session = await start_session(tenant_id)
                    await ws.send_json({"type": "status", "status": "started"})

                    # Start screenshot streaming
                    screenshot_task = asyncio.create_task(
                        _stream_screenshots(ws, session, tenant_id)
                    )
                except Exception as e:
                    logger.error("Failed to start browser session: %s", e)
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg_type == "click" and session:
                x = raw.get("x", 0)
                y = raw.get("y", 0)
                await session.click(x, y)

            elif msg_type == "key" and session:
                key = raw.get("key", "")
                await session.send_key(key)

            elif msg_type == "text" and session:
                text = raw.get("text", "")
                await session.send_text(text)

            elif msg_type == "close":
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for tenant %s", tenant_id)
    except Exception as e:
        logger.error("WebSocket error for tenant %s: %s", tenant_id, e)
    finally:
        if screenshot_task:
            screenshot_task.cancel()
        if session:
            await close_session(tenant_id)


async def _stream_screenshots(ws: WebSocket, session, tenant_id: str):
    """Background task: stream screenshots + check auth completion."""
    auth_check_counter = 0

    while session.is_running:
        try:
            # Send screenshot
            img_b64 = await session.screenshot()
            if img_b64:
                await ws.send_json({"type": "screenshot", "data": img_b64})

            # Periodically check if auth is complete
            auth_check_counter += 1
            if auth_check_counter % 4 == 0:  # Every ~2 seconds
                token_data = await session.check_auth_complete()
                if token_data:
                    # Save session to Supabase
                    saved = await _save_browser_session(tenant_id, token_data)
                    await ws.send_json({
                        "type": "auth_complete",
                        "tokens": {
                            "session_token": token_data.get("session_token", "")[:20] + "...",
                            "source": "browser",
                        },
                        "saved": saved,
                    })
                    # Close after successful auth
                    await close_session(tenant_id)
                    return

            await asyncio.sleep(session.SCREENSHOT_INTERVAL)
        except Exception:
            break


async def _resolve_tenant(api_key: str) -> str | None:
    """Validate API key and return tenant_id."""
    import hashlib
    from src.storage.supabase import get_supabase

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    sb = get_supabase()
    resp = sb.table("api_keys").select("tenant_id").eq("key_hash", key_hash).eq("is_active", True).execute()
    if resp.data:
        return resp.data[0]["tenant_id"]
    return None


async def _save_browser_session(tenant_id: str, token_data: dict) -> bool:
    """Save extracted browser tokens to Supabase."""
    from src.storage.supabase import get_supabase
    from src.workers import jwt_parser
    from datetime import datetime, timezone

    try:
        sb = get_supabase()
        session_token = token_data.get("session_token", "")

        # Parse JWT for user_id and expiry
        user_id = None
        expires_at = None
        try:
            payload = jwt_parser.decode_jwt_payload(session_token)
            user_id = payload.get("user_id") or payload.get("sub")
            exp = payload.get("exp")
            if exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        except Exception:
            pass

        # Deactivate old sessions
        sb.table("avito_sessions").update({"is_active": False}).eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()

        # Insert new session
        tokens = {
            "session_token": session_token,
            "refresh_token": token_data.get("refresh_token"),
            "cookies": token_data.get("cookies", {}),
        }

        sb.table("avito_sessions").insert({
            "tenant_id": tenant_id,
            "tokens": tokens,
            "user_id": user_id,
            "source": "browser",
            "is_active": True,
            "expires_at": expires_at,
        }).execute()

        # Audit
        sb.table("audit_log").insert({
            "tenant_id": tenant_id,
            "action": "session.browser_auth",
            "details": {"user_id": user_id},
        }).execute()

        return True
    except Exception as e:
        logger.error("Failed to save browser session: %s", e)
        return False
