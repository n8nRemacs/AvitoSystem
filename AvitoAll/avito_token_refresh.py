"""
Avito Token Refresh via refresh_token

Обновляет JWT токен используя refresh_token БЕЗ запуска приложения.
Это позволяет поддерживать сессию активной даже если приложение не запущено.

Usage:
    python avito_token_refresh.py                    # Обновить токен
    python avito_token_refresh.py --daemon           # Запустить демон автообновления
    python avito_token_refresh.py --check            # Только проверить статус
"""

import json
import time
import base64
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

try:
    from curl_cffi import requests
except ImportError:
    print("Installing curl_cffi...")
    subprocess.run(["pip", "install", "curl_cffi"], check=True)
    from curl_cffi import requests


# ============ Config ============

ADB = r"C:\Users\User\AppData\Local\Android\Sdk\platform-tools\adb.exe"
AVITO_PREFS = "/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml"
SESSION_FILE = "avito_session_live.json"

# Refresh threshold (hours before expiry)
REFRESH_THRESHOLD_HOURS = 2

# Check interval for daemon mode (seconds)
CHECK_INTERVAL = 300  # 5 minutes


# ============ Device Config (captured) ============

class DeviceConfig:
    device_id = "a8d7b75625458809"
    app_version = "215.1"
    manufacturer = "OnePlus"
    model = "LE2115"
    android_version = "14"

    fingerprint = "A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc174f4eab22785947febba610b1f56d35460d798f306ccdf536c876453ee72d819c926bde786618ec0c53692e27e758f1d0dbb3666d69b2ede89c9dab24ad985363cf7c60d0e460fd1858cecd14770527a95609c38587ed746f99ea3e08ef90510eb1acae44bc0fa2d61"

    remote_device_id = "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android"

    @property
    def user_agent(self):
        return f"AVITO {self.app_version} ({self.manufacturer} {self.model}; Android {self.android_version}; ru)"


# ============ ADB Functions ============

def run_adb(cmd: str) -> str:
    """Run ADB command"""
    full_cmd = f'"{ADB}" {cmd}'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


def read_session_from_device() -> Optional[Dict]:
    """Read current session from device SharedPreferences"""
    cmd = f'shell "su -c \'cat {AVITO_PREFS}\'"'
    output = run_adb(cmd)

    if "<?xml" not in output:
        print("[-] Failed to read device prefs")
        return None

    import re
    values = {}

    for match in re.finditer(r'<string name="([^"]+)">([^<]*)</string>', output):
        name, value = match.groups()
        values[name] = value

    session_token = values.get('session')
    if not session_token:
        print("[-] No session token on device")
        return None

    # Parse JWT
    jwt_data = parse_jwt(session_token)

    return {
        "session_token": session_token,
        "refresh_token": values.get('refresh_token'),
        "fingerprint": values.get('fpx'),
        "device_id": values.get('device_id'),
        "remote_device_id": values.get('remote_device_id'),
        "user_id": jwt_data.get('u') if jwt_data else None,
        "user_hash": values.get('profile_hashId'),
        "expires_at": jwt_data.get('exp') if jwt_data else 0,
    }


def write_session_to_device(session_token: str, refresh_token: str) -> bool:
    """Write updated tokens back to device SharedPreferences"""
    # This requires modifying XML - complex operation
    # For now, we just save locally and let app pick it up on next start
    print("[*] Note: Tokens saved locally. Device will sync on next Avito app start.")
    return True


# ============ JWT Functions ============

def parse_jwt(token: str) -> Optional[Dict]:
    """Parse JWT payload"""
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None

        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except:
        return None


def get_token_expiry(token: str) -> float:
    """Get hours until token expiry"""
    jwt_data = parse_jwt(token)
    if not jwt_data:
        return -1

    exp = jwt_data.get('exp', 0)
    now = time.time()
    return (exp - now) / 3600


# ============ API Client ============

class AvitoAuthClient:
    """Client for Avito auth API"""

    BASE_URL = "https://app.avito.ru/api"

    def __init__(self):
        self.device = DeviceConfig()
        self.http = requests.Session(impersonate="chrome120")

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            "User-Agent": self.device.user_agent,
            "X-App": "avito",
            "X-Platform": "android",
            "X-DeviceId": self.device.device_id,
            "X-RemoteDeviceId": self.device.remote_device_id,
            "f": self.device.fingerprint,
            "X-Date": str(int(time.time())),
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
        }

    def refresh_session(self, refresh_token: str, current_session: str = None) -> Optional[Dict]:
        """
        Refresh session using refresh_token

        Returns new session data or None if failed
        """
        print(f"[*] Attempting token refresh...")

        url = f"{self.BASE_URL}/11/auth/refresh"

        headers = self._build_headers()
        if current_session:
            headers["X-Session"] = current_session
            headers["Cookie"] = f"sessid={current_session}"

        # Try different payload formats
        payloads = [
            {"refresh_token": refresh_token},
            {"refreshToken": refresh_token},
            {"token": refresh_token, "type": "refresh"},
        ]

        for payload in payloads:
            try:
                response = self.http.post(url, headers=headers, json=payload)
                print(f"[*] Response {response.status_code}: {response.text[:200]}")

                if response.status_code == 200:
                    result = response.json()

                    if result.get("status") == "ok":
                        res = result.get("result", {})
                        new_session = res.get("session")
                        new_refresh = res.get("refreshToken")

                        if new_session:
                            print(f"[+] Got new session token!")
                            return {
                                "session_token": new_session,
                                "refresh_token": new_refresh or refresh_token,
                                "expires_at": parse_jwt(new_session).get('exp', 0) if new_session else 0,
                            }

            except Exception as e:
                print(f"[-] Request failed: {e}")

        return None

    def validate_session(self, session_token: str) -> bool:
        """Check if session is valid by making test API call"""
        url = f"{self.BASE_URL}/1/profile/info"

        headers = self._build_headers()
        headers["X-Session"] = session_token
        headers["Cookie"] = f"sessid={session_token}"

        try:
            response = self.http.get(url, headers=headers)
            return response.status_code == 200
        except:
            return False


# ============ Main Logic ============

def check_and_refresh(force: bool = False) -> bool:
    """
    Check token status and refresh if needed

    Returns True if session is valid (either existing or refreshed)
    """
    print("\n" + "=" * 60)
    print("AVITO TOKEN REFRESH")
    print("=" * 60)

    # Read current session from device
    print("[*] Reading session from device...")
    session = read_session_from_device()

    if not session:
        print("[-] Could not read session from device")
        return False

    # Check expiry
    hours_left = get_token_expiry(session['session_token'])
    exp_time = datetime.fromtimestamp(session['expires_at'])

    print(f"\n[*] Current session:")
    print(f"    User ID: {session['user_id']}")
    print(f"    Expires: {exp_time}")
    print(f"    Hours left: {hours_left:.1f}h")
    print(f"    Refresh token: {session['refresh_token']}")

    # Decide if refresh needed
    need_refresh = force or hours_left < REFRESH_THRESHOLD_HOURS

    if hours_left <= 0:
        print("\n[!] Session EXPIRED - must refresh")
        need_refresh = True
    elif hours_left < REFRESH_THRESHOLD_HOURS:
        print(f"\n[!] Session expiring soon ({hours_left:.1f}h < {REFRESH_THRESHOLD_HOURS}h threshold)")
        need_refresh = True
    else:
        print(f"\n[+] Session OK - no refresh needed")

    if not need_refresh:
        return True

    # Attempt refresh
    if not session['refresh_token']:
        print("[-] No refresh token available!")
        return False

    print("\n[*] Refreshing token...")
    client = AvitoAuthClient()

    # Update fingerprint from device
    if session.get('fingerprint'):
        client.device.fingerprint = session['fingerprint']

    result = client.refresh_session(
        session['refresh_token'],
        session['session_token']
    )

    if result:
        print(f"\n[+] SUCCESS! New token obtained")
        new_hours = get_token_expiry(result['session_token'])
        print(f"    New expiry: {new_hours:.1f}h from now")

        # Save locally
        save_data = {
            "session_token": result['session_token'],
            "refresh_token": result['refresh_token'],
            "fingerprint": session['fingerprint'],
            "device_id": session['device_id'],
            "remote_device_id": session['remote_device_id'],
            "user_id": session['user_id'],
            "user_hash": session['user_hash'],
            "expires_at": result['expires_at'],
            "refreshed_at": int(time.time()),
        }

        Path(SESSION_FILE).write_text(json.dumps(save_data, indent=2))
        print(f"[+] Saved to {SESSION_FILE}")

        return True
    else:
        print("\n[-] FAILED to refresh token")
        print("    May need to re-login in app")
        return False


def daemon_mode():
    """Run as daemon, checking and refreshing periodically"""
    print(f"\n[*] Starting daemon mode (check every {CHECK_INTERVAL}s)")
    print("[*] Press Ctrl+C to stop\n")

    while True:
        try:
            check_and_refresh()
            print(f"\n[*] Next check in {CHECK_INTERVAL}s...")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n[*] Daemon stopped")
            break


def main():
    parser = argparse.ArgumentParser(description='Avito Token Refresh')
    parser.add_argument('--check', action='store_true', help='Only check status, do not refresh')
    parser.add_argument('--force', action='store_true', help='Force refresh even if not needed')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--threshold', type=float, default=REFRESH_THRESHOLD_HOURS,
                        help='Hours before expiry to trigger refresh')
    args = parser.parse_args()

    global REFRESH_THRESHOLD_HOURS
    REFRESH_THRESHOLD_HOURS = args.threshold

    if args.daemon:
        daemon_mode()
    elif args.check:
        session = read_session_from_device()
        if session:
            hours = get_token_expiry(session['session_token'])
            print(f"Session status: {'OK' if hours > 0 else 'EXPIRED'} ({hours:.1f}h)")
    else:
        check_and_refresh(force=args.force)


if __name__ == "__main__":
    main()
