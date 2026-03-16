"""
Avito Auth Client - Final Version
Based on full Frida capture of real auth request (2026-01-13)

CAPTURED HEADERS (17 total):
- User-Agent, X-App, X-Platform, X-DeviceId, X-Date, X-Geo
- X-Supported-Features, X-RemoteDeviceId, Schema-Check, AT-v
- f (fingerprint), Accept-Encoding, Content-Type, Host, Connection, Cookie
"""

from curl_cffi import requests
import json
import time
import secrets
from dataclasses import dataclass
from typing import Optional, Dict
from pathlib import Path


@dataclass
class CapturedSession:
    """Session data captured from real device"""
    device_id: str = "a8d7b75625458809"
    app_version: str = "215.1"
    manufacturer: str = "OnePlus"
    model: str = "LE2115"
    android_version: str = "14"
    locale: str = "ru"

    # Captured fingerprint - CRITICAL for auth
    fingerprint: str = "A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc174f4eab22785947feb2ad956666f28c26fd798f306ccdf536c876453ee72d819c926bde786618ec0c53692e27e758f1d0dbb3666d69b2ede89c9dab24ad985363cf7c60d0e460fd1858cecd14770527a95609c38587ed746f99ea3e08ef90510eb1acae44bc0fa2d61"

    # Captured visitor/remote device ID
    remote_device_id: str = "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android"

    # Captured cookies
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


class AvitoAuthFinal:
    """Avito Auth using captured session data"""

    BASE_URL = "https://app.avito.ru/api"

    def __init__(self, session_data: Optional[CapturedSession] = None):
        self.session_data = session_data or CapturedSession()
        self.session = requests.Session(impersonate="chrome120")

        # Auth result
        self.session_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def _build_headers(self, geo: Optional[str] = None) -> Dict[str, str]:
        """Build exact headers as captured from device"""
        headers = {
            "User-Agent": self.session_data.user_agent,
            "X-Supported-Features": "helpcenter-form-46049",
            "X-App": "avito",
            "X-DeviceId": self.session_data.device_id,
            "Schema-Check": "0",
            "f": self.session_data.fingerprint,  # CRITICAL!
            "X-Platform": "android",
            "X-RemoteDeviceId": self.session_data.remote_device_id,
            "AT-v": "1",
            "Accept-Encoding": "zstd;q=1.0, gzip;q=0.8",
            "X-Date": str(int(time.time())),
        }

        if geo:
            headers["X-Geo"] = geo

        return headers

    def _build_cookies(self) -> str:
        """Build cookie string"""
        return "; ".join(f"{k}={v}" for k, v in self.session_data.cookies.items())

    def login(self, phone: str, password: str, geo: Optional[str] = None) -> Dict:
        """
        Login with exact captured request format

        Args:
            phone: Phone number (+7XXXXXXXXXX)
            password: Password
            geo: Optional geo string (lat;lng;accuracy;timestamp)
        """
        print(f"[*] Logging in as {phone[:7]}***...")

        url = f"{self.BASE_URL}/11/auth"

        # Headers exactly as captured
        headers = self._build_headers(geo)
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
        headers["Cookie"] = self._build_cookies()

        # Body
        data = {
            "login": phone,
            "password": password,
            "token": "",
            "isSandbox": "false",
            "fid": secrets.token_hex(16),
        }

        print(f"[*] Request URL: {url}")
        print(f"[*] Headers count: {len(headers)}")

        try:
            response = self.session.post(url, headers=headers, data=data)

            print(f"[*] Response: {response.status_code}")

            result = response.json()

            if result.get("status") == "ok":
                res = result.get("result", {})
                self.session_token = res.get("session")
                self.refresh_token = res.get("refreshToken")

                user = res.get("user", {})
                print(f"[+] SUCCESS! User: {user.get('name')} (ID: {user.get('id')})")

                return {
                    "status": "ok",
                    "session": self.session_token,
                    "refresh_token": self.refresh_token,
                    "user": user
                }
            else:
                print(f"[-] Failed: {result}")
                return result

        except Exception as e:
            print(f"[-] Error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def save_session(self, path: str):
        """Save session to file"""
        data = {
            "session_token": self.session_token,
            "refresh_token": self.refresh_token,
            "session_data": {
                "device_id": self.session_data.device_id,
                "fingerprint": self.session_data.fingerprint,
                "remote_device_id": self.session_data.remote_device_id,
                "cookies": self.session_data.cookies,
            }
        }
        Path(path).write_text(json.dumps(data, indent=2))
        print(f"[+] Session saved to {path}")


def main():
    print("=" * 70)
    print("Avito Auth - Final Version (with captured fingerprint)")
    print("=" * 70)

    auth = AvitoAuthFinal()

    print(f"\n[*] Using captured session:")
    print(f"    Device ID: {auth.session_data.device_id}")
    print(f"    User-Agent: {auth.session_data.user_agent}")
    print(f"    Fingerprint: {auth.session_data.fingerprint[:50]}...")

    print("\n" + "-" * 70)
    phone = input("Phone (+7...): ").strip()
    password = input("Password: ").strip()

    # Use captured geo
    geo = "46.360889;48.047291;100;1768295137"

    print("\n" + "-" * 70)
    result = auth.login(phone, password, geo=geo)

    if result.get("status") == "ok":
        auth.save_session("avito_session_final.json")
    else:
        print(f"\n[-] Result: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")


if __name__ == "__main__":
    main()
