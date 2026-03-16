"""
Avito Token Manager
Simple app for manual login and auto token refresh

Features:
- Manual login (phone + password)
- Auto token refresh before expiration
- Session status monitoring
- Multiple session file support
"""

import json
import time
import secrets
import threading
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

try:
    from curl_cffi import requests
except ImportError:
    print("Installing curl_cffi...")
    import subprocess
    subprocess.run(["pip", "install", "curl_cffi"], check=True)
    from curl_cffi import requests


# ============ Configuration ============

SESSION_FILE = "avito_session_active.json"
CHECK_INTERVAL = 300  # Check every 5 minutes
REFRESH_THRESHOLD = 3600  # Refresh if less than 1 hour left


@dataclass
class DeviceConfig:
    """Device configuration for auth requests"""
    device_id: str = "a8d7b75625458809"
    app_version: str = "215.1"
    manufacturer: str = "OnePlus"
    model: str = "LE2115"
    android_version: str = "14"
    locale: str = "ru"

    fingerprint: str = "A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc174f4eab22785947feb2ad956666f28c26fd798f306ccdf536c876453ee72d819c926bde786618ec0c53692e27e758f1d0dbb3666d69b2ede89c9dab24ad985363cf7c60d0e460fd1858cecd14770527a95609c38587ed746f99ea3e08ef90510eb1acae44bc0fa2d61"

    remote_device_id: str = "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android"

    cookies: Dict[str, str] = None

    def __post_init__(self):
        if self.cookies is None:
            self.cookies = {
                "1f_uid": "27835d95-6380-44e1-8289-4a13a511a29b",
                "u": "3bhsmqlh.1i5wwa4.i996zfqfof",
            }

    @property
    def user_agent(self) -> str:
        return f"AVITO {self.app_version} ({self.manufacturer} {self.model}; Android {self.android_version}; {self.locale})"


class AvitoTokenManager:
    """Manages Avito authentication tokens"""

    BASE_URL = "https://app.avito.ru/api"

    def __init__(self, session_file: str = SESSION_FILE):
        self.session_file = Path(session_file)
        self.device = DeviceConfig()
        self.http = requests.Session(impersonate="chrome120")

        # Session data
        self.session_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.user_name: Optional[str] = None
        self.expires_at: Optional[int] = None

        # Auto-refresh
        self._auto_refresh_thread: Optional[threading.Thread] = None
        self._stop_refresh = threading.Event()

    # ============ Headers ============

    def _build_headers(self, geo: Optional[str] = None) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "User-Agent": self.device.user_agent,
            "X-Supported-Features": "helpcenter-form-46049",
            "X-App": "avito",
            "X-DeviceId": self.device.device_id,
            "Schema-Check": "0",
            "f": self.device.fingerprint,
            "X-Platform": "android",
            "X-RemoteDeviceId": self.device.remote_device_id,
            "AT-v": "1",
            "Accept-Encoding": "zstd;q=1.0, gzip;q=0.8",
            "X-Date": str(int(time.time())),
        }
        if geo:
            headers["X-Geo"] = geo
        return headers

    def _build_cookies(self) -> str:
        """Build cookie string"""
        return "; ".join(f"{k}={v}" for k, v in self.device.cookies.items())

    # ============ Session Management ============

    def save_session(self) -> bool:
        """Save current session to file"""
        if not self.session_token:
            print("[-] No session to save")
            return False

        data = {
            "session_token": self.session_token,
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "expires_at": self.expires_at,
            "device": {
                "device_id": self.device.device_id,
                "fingerprint": self.device.fingerprint,
                "remote_device_id": self.device.remote_device_id,
                "cookies": self.device.cookies,
            },
            "saved_at": int(time.time()),
        }

        self.session_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[+] Session saved to {self.session_file}")
        return True

    def load_session(self) -> bool:
        """Load session from file"""
        if not self.session_file.exists():
            print(f"[-] Session file not found: {self.session_file}")
            return False

        try:
            data = json.loads(self.session_file.read_text())

            self.session_token = data.get("session_token")
            self.refresh_token = data.get("refresh_token")
            self.user_id = data.get("user_id")
            self.user_name = data.get("user_name")
            self.expires_at = data.get("expires_at")

            # Load device config if saved
            if "device" in data:
                dev = data["device"]
                self.device.device_id = dev.get("device_id", self.device.device_id)
                self.device.fingerprint = dev.get("fingerprint", self.device.fingerprint)
                self.device.remote_device_id = dev.get("remote_device_id", self.device.remote_device_id)
                if dev.get("cookies"):
                    self.device.cookies = dev["cookies"]

            print(f"[+] Session loaded: {self.user_name or self.user_id}")
            return True

        except Exception as e:
            print(f"[-] Failed to load session: {e}")
            return False

    def _parse_jwt_exp(self, token: str) -> Optional[int]:
        """Extract expiration from JWT token"""
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                # Add padding if needed
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += "=" * padding

                decoded = base64.urlsafe_b64decode(payload)
                data = json.loads(decoded)
                return data.get("exp")
        except:
            pass
        return None

    # ============ Authentication ============

    def login(self, phone: str, password: str) -> bool:
        """
        Login with phone and password

        Args:
            phone: Phone number (+7XXXXXXXXXX)
            password: Password

        Returns:
            True if login successful
        """
        print(f"\n[*] Logging in as {phone[:7]}***...")

        url = f"{self.BASE_URL}/11/auth"

        headers = self._build_headers(geo="46.360889;48.047291;100;" + str(int(time.time())))
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
        headers["Cookie"] = self._build_cookies()

        data = {
            "login": phone,
            "password": password,
            "token": "",
            "isSandbox": "false",
            "fid": secrets.token_hex(16),
        }

        try:
            response = self.http.post(url, headers=headers, data=data)
            result = response.json()

            if result.get("status") == "ok":
                res = result.get("result", {})
                self.session_token = res.get("session")
                self.refresh_token = res.get("refreshToken")

                user = res.get("user", {})
                self.user_id = str(user.get("id", ""))
                self.user_name = user.get("name", "")

                # Parse expiration from JWT
                if self.session_token:
                    self.expires_at = self._parse_jwt_exp(self.session_token)

                print(f"[+] SUCCESS! User: {self.user_name} (ID: {self.user_id})")
                self.save_session()
                return True
            else:
                error = result.get("result", {}).get("message", str(result))
                print(f"[-] Login failed: {error}")
                return False

        except Exception as e:
            print(f"[-] Error: {e}")
            return False

    # ============ Token Refresh ============

    def refresh(self) -> bool:
        """
        Refresh session token using refresh_token

        Returns:
            True if refresh successful
        """
        if not self.refresh_token:
            print("[-] No refresh token available")
            return False

        print("[*] Refreshing token...")

        url = f"{self.BASE_URL}/11/auth/refresh"

        headers = self._build_headers()
        headers["Content-Type"] = "application/json"
        headers["Cookie"] = self._build_cookies()

        # Add current session if available
        if self.session_token:
            headers["X-Session"] = self.session_token

        data = {
            "refresh_token": self.refresh_token
        }

        try:
            response = self.http.post(url, headers=headers, json=data)
            result = response.json()

            if result.get("status") == "ok":
                res = result.get("result", {})

                new_session = res.get("session")
                new_refresh = res.get("refreshToken")

                if new_session:
                    self.session_token = new_session
                    self.expires_at = self._parse_jwt_exp(new_session)
                    print(f"[+] New session token obtained")

                if new_refresh:
                    self.refresh_token = new_refresh
                    print(f"[+] New refresh token obtained")

                self.save_session()
                return True
            else:
                print(f"[-] Refresh failed: {result}")
                return False

        except Exception as e:
            print(f"[-] Refresh error: {e}")
            return False

    # ============ Status ============

    def get_status(self) -> Dict:
        """Get current session status"""
        now = int(time.time())

        status = {
            "has_session": bool(self.session_token),
            "has_refresh": bool(self.refresh_token),
            "user_id": self.user_id,
            "user_name": self.user_name,
            "expires_at": self.expires_at,
            "expires_in": None,
            "is_expired": None,
        }

        if self.expires_at:
            status["expires_in"] = self.expires_at - now
            status["is_expired"] = now > self.expires_at

        return status

    def print_status(self):
        """Print current session status"""
        status = self.get_status()

        print("\n" + "=" * 50)
        print("SESSION STATUS")
        print("=" * 50)

        if not status["has_session"]:
            print("Status: NO SESSION")
            return

        print(f"User: {status['user_name']} (ID: {status['user_id']})")
        print(f"Session: {'Yes' if status['has_session'] else 'No'}")
        print(f"Refresh Token: {'Yes' if status['has_refresh'] else 'No'}")

        if status["expires_at"]:
            exp_time = datetime.fromtimestamp(status["expires_at"])
            print(f"Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")

            if status["is_expired"]:
                print("Status: EXPIRED!")
            else:
                hours = status["expires_in"] / 3600
                if hours < 1:
                    mins = status["expires_in"] / 60
                    print(f"Status: Valid ({mins:.0f} minutes left)")
                else:
                    print(f"Status: Valid ({hours:.1f} hours left)")

        print("=" * 50)

    # ============ Auto Refresh ============

    def start_auto_refresh(self, check_interval: int = CHECK_INTERVAL,
                           refresh_threshold: int = REFRESH_THRESHOLD):
        """
        Start auto-refresh daemon

        Args:
            check_interval: How often to check (seconds)
            refresh_threshold: Refresh if less than this many seconds left
        """
        if self._auto_refresh_thread and self._auto_refresh_thread.is_alive():
            print("[*] Auto-refresh already running")
            return

        self._stop_refresh.clear()

        def refresh_loop():
            print(f"[*] Auto-refresh started (check every {check_interval}s, refresh at {refresh_threshold}s)")

            while not self._stop_refresh.is_set():
                status = self.get_status()

                if status["expires_in"] is not None:
                    if status["expires_in"] < refresh_threshold:
                        print(f"\n[!] Token expires in {status['expires_in']}s, refreshing...")
                        if self.refresh():
                            print("[+] Auto-refresh successful")
                        else:
                            print("[-] Auto-refresh failed!")

                self._stop_refresh.wait(check_interval)

            print("[*] Auto-refresh stopped")

        self._auto_refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self._auto_refresh_thread.start()

    def stop_auto_refresh(self):
        """Stop auto-refresh daemon"""
        self._stop_refresh.set()
        if self._auto_refresh_thread:
            self._auto_refresh_thread.join(timeout=2)


# ============ CLI Interface ============

def main():
    """Interactive CLI"""
    print("\n" + "=" * 50)
    print("AVITO TOKEN MANAGER")
    print("=" * 50)

    manager = AvitoTokenManager()

    # Try to load existing session
    if manager.load_session():
        manager.print_status()

    while True:
        print("\n--- Menu ---")
        print("1. Login (phone + password)")
        print("2. Refresh token")
        print("3. Check status")
        print("4. Start auto-refresh")
        print("5. Stop auto-refresh")
        print("6. Load session from file")
        print("7. Exit")

        try:
            choice = input("\nSelect [1-7]: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            phone = input("Phone (+7...): ").strip()
            password = input("Password: ").strip()
            if phone and password:
                manager.login(phone, password)
                manager.print_status()

        elif choice == "2":
            if manager.refresh():
                manager.print_status()

        elif choice == "3":
            manager.print_status()

        elif choice == "4":
            try:
                interval = input(f"Check interval (seconds) [{CHECK_INTERVAL}]: ").strip()
                interval = int(interval) if interval else CHECK_INTERVAL

                threshold = input(f"Refresh threshold (seconds) [{REFRESH_THRESHOLD}]: ").strip()
                threshold = int(threshold) if threshold else REFRESH_THRESHOLD

                manager.start_auto_refresh(interval, threshold)
            except ValueError:
                print("[-] Invalid input")

        elif choice == "5":
            manager.stop_auto_refresh()

        elif choice == "6":
            filename = input(f"Session file [{SESSION_FILE}]: ").strip()
            if filename:
                manager.session_file = Path(filename)
            manager.load_session()
            manager.print_status()

        elif choice == "7":
            manager.stop_auto_refresh()
            print("\nBye!")
            break

        else:
            print("[-] Invalid choice")

    manager.stop_auto_refresh()


if __name__ == "__main__":
    main()
