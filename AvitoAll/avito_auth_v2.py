"""
Avito Auth Client v2 - Based on full interceptor analysis
Uses curl_cffi for TLS fingerprint impersonation (bypass QRATOR)

Headers discovered from jadx analysis:
- User-Agent: AVITO {version} ({manufacturer} {model}; Android {androidVersion}; {locale})
- X-DeviceId: device ID (16 hex chars)
- X-Platform: "android"
- X-App: "avito"
- X-AppVer: app version (e.g., "118.8")
- X-Date: Unix timestamp in seconds
- Accept-Language: locale
"""

from curl_cffi import requests
import uuid
import hashlib
import json
import time
import secrets
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from pathlib import Path


class AuthStatus(Enum):
    SUCCESS = "ok"
    INCORRECT_DATA = "incorrect-data"
    TFA_REQUIRED = "tfa_required"
    CAPTCHA_REQUIRED = "captcha_required"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"


@dataclass
class AuthResult:
    status: AuthStatus
    session: Optional[str] = None
    refresh_token: Optional[str] = None
    phash: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    error_message: Optional[str] = None
    tfa_flow: Optional[str] = None
    tfa_phone: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class DeviceProfile:
    """Android device profile matching Avito app fingerprint"""
    device_id: str = field(default_factory=lambda: secrets.token_hex(8))
    manufacturer: str = "OnePlus"
    model: str = "LE2115"
    android_version: str = "14"
    locale: str = "ru_RU"
    app_version: str = "118.8"  # Latest version

    @property
    def user_agent(self) -> str:
        """User-Agent in exact Avito format: AVITO {ver} ({mfr} {model}; Android {ver}; {locale})"""
        return f"AVITO {self.app_version} ({self.manufacturer} {self.model}; Android {self.android_version}; {self.locale})"

    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "android_version": self.android_version,
            "locale": self.locale,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DeviceProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def oneplus9_pro(cls, device_id: Optional[str] = None) -> "DeviceProfile":
        """OnePlus 9 Pro profile (real device from capture)"""
        return cls(
            device_id=device_id or secrets.token_hex(8),
            manufacturer="OnePlus",
            model="LE2115",
            android_version="14",
            locale="ru_RU",
            app_version="118.8",
        )

    @classmethod
    def captured_device(cls) -> "DeviceProfile":
        """Use exact device from captured session"""
        return cls(
            device_id="a8d7b75625458809",  # From captured JWT
            manufacturer="OnePlus",
            model="LE2115",
            android_version="14",
            locale="ru_RU",
            app_version="118.8",
        )


class AvitoAuth:
    """Avito Auth Client with TLS fingerprint impersonation"""
    BASE_URL = "https://app.avito.ru/api"

    # TLS fingerprint to impersonate (okhttp4_android_* for Android app)
    IMPERSONATE = "okhttp4_android_13"

    def __init__(self, device: Optional[DeviceProfile] = None):
        self.device = device or DeviceProfile.oneplus9_pro()
        self.tracker_uid = self._generate_tracker_uid()

        # Session state
        self.session_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.phash: Optional[str] = None

        # Create session with TLS impersonation
        self.session = requests.Session(impersonate=self.IMPERSONATE)

    def _generate_tracker_uid(self) -> str:
        """Generate tracker/fingerprint UID (fid parameter)"""
        data = f"{self.device.device_id}:{secrets.token_hex(8)}:{int(time.time())}"
        return hashlib.md5(data.encode()).hexdigest()

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build request headers exactly like Avito Android app"""
        headers = {
            "User-Agent": self.device.user_agent,
            "X-App": "avito",
            "X-Platform": "android",
            "X-AppVer": self.device.app_version,
            "X-DeviceId": self.device.device_id,
            "X-Date": str(int(time.time())),  # Unix timestamp in seconds
            "Accept": "application/json",
            "Accept-Language": self.device.locale.replace("_", "-"),
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if self.session_token:
            headers["X-Session"] = self.session_token

        if extra:
            headers.update(extra)

        return headers

    def warmup(self) -> bool:
        """
        Make warmup requests to look like normal app behavior.
        """
        print("[*] Warming up connection...")

        try:
            # 1. Get auth suggestions (app does this on login screen)
            print("    [1/2] Getting auth suggestions...")
            headers = self._build_headers()
            resp = self.session.get(
                f"{self.BASE_URL}/1/auth/suggest",
                headers=headers,
                params={"hashUserIds[0]": hashlib.md5(self.device.device_id.encode()).hexdigest()}
            )
            print(f"    [+] Status: {resp.status_code}")

            # 2. Small delay
            print("    [2/2] Waiting...")
            time.sleep(1.0)

            print("[+] Warmup complete")
            return True

        except Exception as e:
            print(f"[-] Warmup failed: {e}")
            return False

    def login(self, phone: str, password: str) -> AuthResult:
        """
        Login with phone and password.

        Args:
            phone: Phone number in format +7XXXXXXXXXX
            password: Account password

        Returns:
            AuthResult with session or error
        """
        print(f"\n[*] Logging in as {phone[:7]}***...")

        url = f"{self.BASE_URL}/11/auth"

        # Headers including X-Geo-required for auth
        headers = self._build_headers({"X-Geo-required": "true"})

        # Form data matching app exactly
        data = {
            "login": phone,
            "password": password,
            "token": "",  # Push token can be empty
            "isSandbox": "false",
            "fid": self.tracker_uid,
        }

        try:
            print(f"[*] POST {url}")
            print(f"[*] Headers: {json.dumps(headers, indent=2)}")

            response = self.session.post(url, headers=headers, data=data)

            print(f"[*] Response status: {response.status_code}")
            print(f"[*] Response headers: {dict(response.headers)}")

            if response.status_code == 400:
                try:
                    result = response.json()
                except:
                    result = {"error": response.text}
                return AuthResult(
                    status=AuthStatus.BLOCKED,
                    error_message=f"400 Bad Request: {result}",
                    raw_response=result if isinstance(result, dict) else {"text": result}
                )

            if response.status_code == 429:
                return AuthResult(
                    status=AuthStatus.RATE_LIMITED,
                    error_message="Too many requests"
                )

            result = response.json()
            print(f"[*] Response: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")

            return self._parse_auth_response(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return AuthResult(
                status=AuthStatus.INCORRECT_DATA,
                error_message=str(e)
            )

    def verify_tfa(self, code: str, flow: str = "sms") -> AuthResult:
        """Verify TFA/SMS code"""
        print(f"\n[*] Verifying TFA code...")

        url = f"{self.BASE_URL}/2/tfa/auth"
        headers = self._build_headers()

        data = {
            "code": code,
            "flow": flow,
            "fid": self.tracker_uid,
        }

        try:
            response = self.session.post(url, headers=headers, data=data)
            result = response.json()
            return self._parse_auth_response(result)
        except Exception as e:
            return AuthResult(status=AuthStatus.INCORRECT_DATA, error_message=str(e))

    def _parse_auth_response(self, response: Dict) -> AuthResult:
        """Parse auth API response"""
        status = response.get("status", "")
        result_data = response.get("result", {})

        if status == "ok":
            user = result_data.get("user", {})
            self.session_token = result_data.get("session")
            self.refresh_token = result_data.get("refreshToken")
            self.phash = result_data.get("phash")

            return AuthResult(
                status=AuthStatus.SUCCESS,
                session=self.session_token,
                refresh_token=self.refresh_token,
                phash=self.phash,
                user_id=user.get("id"),
                user_name=user.get("name"),
                raw_response=response
            )

        # TFA required
        if any(x in str(result_data) for x in ["phoneList", "phone", "tfa"]):
            return AuthResult(
                status=AuthStatus.TFA_REQUIRED,
                tfa_flow=result_data.get("flow", "sms"),
                tfa_phone=result_data.get("phone"),
                raw_response=response
            )

        # Incorrect credentials
        if status == "incorrect-data":
            messages = result_data.get("messages", {})
            error_msg = messages.get("password") or messages.get("login") or str(messages)
            return AuthResult(
                status=AuthStatus.INCORRECT_DATA,
                error_message=error_msg,
                raw_response=response
            )

        # Captcha
        if "captcha" in str(result_data).lower():
            return AuthResult(
                status=AuthStatus.CAPTCHA_REQUIRED,
                error_message="Captcha required",
                raw_response=response
            )

        return AuthResult(
            status=AuthStatus.INCORRECT_DATA,
            error_message=f"Unknown status: {status}",
            raw_response=response
        )

    def save_session(self, filepath: str):
        """Save session to file"""
        data = {
            "device": self.device.to_dict(),
            "tracker_uid": self.tracker_uid,
            "session_token": self.session_token,
            "refresh_token": self.refresh_token,
            "phash": self.phash,
            "saved_at": int(time.time()),
        }
        Path(filepath).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[+] Session saved to {filepath}")


def main():
    """Interactive login"""
    print("=" * 60)
    print("Avito Auth Client v2 - TLS Fingerprint Impersonation")
    print("=" * 60)

    # Use captured device profile
    print("\n[?] Use captured device (a8d7b75625458809)? (y/n) ", end="")
    if input().strip().lower() == "y":
        device = DeviceProfile.captured_device()
    else:
        device = DeviceProfile.oneplus9_pro()

    print(f"\n[*] Device Profile:")
    print(f"    ID: {device.device_id}")
    print(f"    UA: {device.user_agent}")

    auth = AvitoAuth(device=device)

    # Warmup
    print("\n" + "-" * 60)
    auth.warmup()

    # Credentials
    print("\n" + "-" * 60)
    phone = input("Phone (+7...): ").strip()
    password = input("Password: ").strip()

    # Login
    print("\n" + "-" * 60)
    result = auth.login(phone, password)

    if result.status == AuthStatus.SUCCESS:
        print(f"\n{'=' * 60}")
        print("[+] LOGIN SUCCESSFUL!")
        print(f"    User: {result.user_name} (ID: {result.user_id})")
        print(f"    Session: {result.session[:50]}..." if result.session else "")
        print(f"{'=' * 60}")
        auth.save_session("avito_session_v2.json")

    elif result.status == AuthStatus.TFA_REQUIRED:
        print(f"\n[!] TFA REQUIRED - Flow: {result.tfa_flow}")
        code = input("SMS Code: ").strip()
        tfa_result = auth.verify_tfa(code)
        if tfa_result.status == AuthStatus.SUCCESS:
            print("[+] TFA SUCCESS!")
            auth.save_session("avito_session_v2.json")
        else:
            print(f"[-] TFA Failed: {tfa_result.error_message}")

    else:
        print(f"\n[-] LOGIN FAILED: {result.status.value}")
        print(f"    Error: {result.error_message}")
        if result.raw_response:
            print(f"    Response: {json.dumps(result.raw_response, indent=2, ensure_ascii=False)[:1000]}")


if __name__ == "__main__":
    main()
