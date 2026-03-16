#!/usr/bin/env python3
"""
Avito Session Server

Simple HTTP server to receive session updates from Android app.
Saves session and restarts the Telegram bot.

Run on server: python3 avito_session_server.py
"""

import json
import subprocess
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
HOST = "0.0.0.0"
PORT = 8080
SESSION_FILE = "/root/Avito/avito_session_new.json"
BOT_SERVICE = "avito-bridge"
API_KEY = "avito_sync_key_2026"  # Simple API key for auth

class SessionHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {args[0]}")

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "avito-session-server"})
        elif self.path == "/status":
            self.handle_status()
        elif self.path == "/api/v1/mcp/status":
            self.handle_mcp_status()
        elif self.path == "/api/v1/full-status":
            self.handle_full_status()
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/v1/sessions":
            self.handle_session_update()
        elif self.path == "/api/v1/mcp/restart":
            self.handle_mcp_restart()
        else:
            self.send_json(404, {"error": "Not found"})

    def handle_status(self):
        """Return current session status"""
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, 'r') as f:
                    session = json.load(f)

                import time
                expires_at = session.get('expires_at', 0)
                hours_left = (expires_at - time.time()) / 3600

                self.send_json(200, {
                    "status": "ok",
                    "expires_at": expires_at,
                    "hours_left": round(hours_left, 2),
                    "is_valid": hours_left > 0
                })
            else:
                self.send_json(200, {"status": "no_session"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def handle_mcp_status(self):
        """Return MCP (Telegram bot) service status"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", BOT_SERVICE],
                capture_output=True,
                text=True
            )
            is_running = result.stdout.strip() == "active"

            # Get uptime if running
            uptime = None
            if is_running:
                result2 = subprocess.run(
                    ["systemctl", "show", BOT_SERVICE, "--property=ActiveEnterTimestamp"],
                    capture_output=True,
                    text=True
                )
                if result2.returncode == 0:
                    uptime = result2.stdout.strip().replace("ActiveEnterTimestamp=", "")

            self.send_json(200, {
                "service": BOT_SERVICE,
                "is_running": is_running,
                "status": "running" if is_running else "stopped",
                "uptime_since": uptime
            })
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def handle_mcp_restart(self):
        """Restart MCP (Telegram bot) service"""
        try:
            # Check API key
            api_key = self.headers.get("X-Device-Key", "")
            if api_key != API_KEY:
                self.send_json(401, {"error": "Invalid API key"})
                return

            result = subprocess.run(
                ["systemctl", "restart", BOT_SERVICE],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"[+] MCP restarted by API request")
                self.send_json(200, {
                    "success": True,
                    "message": f"Service {BOT_SERVICE} restarted"
                })
            else:
                self.send_json(500, {
                    "success": False,
                    "error": result.stderr
                })
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def handle_full_status(self):
        """Return full status: session + MCP"""
        import time
        try:
            response = {
                "server": {
                    "status": "ok",
                    "timestamp": int(time.time())
                },
                "session": None,
                "mcp": None
            }

            # Session status
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, 'r') as f:
                    session = json.load(f)
                expires_at = session.get('expires_at', 0)
                hours_left = (expires_at - time.time()) / 3600
                updated_at = session.get('updated_at', 0)

                response["session"] = {
                    "exists": True,
                    "expires_at": expires_at,
                    "hours_left": round(hours_left, 2),
                    "is_valid": hours_left > 0,
                    "updated_at": updated_at,
                    "token_preview": session.get('session_token', '')[:30] + "..."
                }
            else:
                response["session"] = {"exists": False}

            # MCP status
            result = subprocess.run(
                ["systemctl", "is-active", BOT_SERVICE],
                capture_output=True,
                text=True
            )
            is_running = result.stdout.strip() == "active"
            response["mcp"] = {
                "service": BOT_SERVICE,
                "is_running": is_running,
                "status": "running" if is_running else "stopped"
            }

            self.send_json(200, response)
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def handle_session_update(self):
        """Handle session update from Android app"""
        try:
            # Check API key
            api_key = self.headers.get("X-Device-Key", "")
            if api_key != API_KEY:
                self.send_json(401, {"error": "Invalid API key"})
                return

            # Read body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            # Validate required fields
            required = ["session_token", "fingerprint"]
            for field in required:
                if field not in data and field not in data.get("session_data", {}):
                    self.send_json(400, {"error": f"Missing field: {field}"})
                    return

            # Format session data
            session = self.format_session(data)

            # Save to file
            with open(SESSION_FILE, 'w') as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

            print(f"[+] Session saved: expires in {session.get('hours_left', '?')}h")

            # Restart bot
            result = subprocess.run(
                ["systemctl", "restart", BOT_SERVICE],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"[+] Bot restarted")
                self.send_json(200, {
                    "success": True,
                    "message": "Session updated, bot restarted",
                    "session_id": session.get('session_token', '')[:20] + "..."
                })
            else:
                print(f"[-] Bot restart failed: {result.stderr}")
                self.send_json(200, {
                    "success": True,
                    "message": "Session updated, bot restart failed",
                    "warning": result.stderr
                })

        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON"})
        except Exception as e:
            print(f"[-] Error: {e}")
            self.send_json(500, {"error": str(e)})

    def format_session(self, data):
        """Format session data to expected structure"""
        import time

        # Handle both flat and nested formats
        session_token = data.get("session_token", "")
        refresh_token = data.get("refresh_token", "")

        session_data = data.get("session_data", {})
        fingerprint = data.get("fingerprint") or session_data.get("fingerprint", "")
        device_id = data.get("device_id") or session_data.get("device_id", "")
        remote_device_id = data.get("remote_device_id") or session_data.get("remote_device_id", "")
        user_hash = data.get("user_hash") or session_data.get("user_hash", "")
        cookies = data.get("cookies") or session_data.get("cookies", {})

        # Parse expires_at from JWT if not provided
        expires_at = data.get("expires_at", 0)
        if not expires_at and session_token:
            try:
                import base64
                parts = session_token.split('.')
                if len(parts) >= 2:
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    decoded = base64.urlsafe_b64decode(payload)
                    jwt_data = json.loads(decoded)
                    expires_at = jwt_data.get('exp', 0)
            except:
                pass

        hours_left = (expires_at - time.time()) / 3600 if expires_at else 0

        return {
            "session_token": session_token,
            "refresh_token": refresh_token,
            "session_data": {
                "device_id": device_id,
                "fingerprint": fingerprint,
                "remote_device_id": remote_device_id,
                "user_hash": user_hash,
                "cookies": cookies
            },
            "expires_at": expires_at,
            "hours_left": round(hours_left, 2),
            "updated_at": int(time.time())
        }


def main():
    print("=" * 50)
    print("Avito Session Server")
    print("=" * 50)
    print(f"Listening on {HOST}:{PORT}")
    print(f"Session file: {SESSION_FILE}")
    print(f"Bot service: {BOT_SERVICE}")
    print("=" * 50)

    server = HTTPServer((HOST, PORT), SessionHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped")
        server.shutdown()


if __name__ == "__main__":
    main()
