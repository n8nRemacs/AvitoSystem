"""
Avito Auth Client - Realistic Implementation
Based on reverse engineering of Avito Android app v116.3

Uses real device fingerprints and proper headers to avoid detection.
"""

import httpx
import uuid
import hashlib
import base64
import json
import time
import secrets
from dataclasses import dataclass
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
    tfa_phone_list: Optional[List[str]] = None
    raw_response: Optional[Dict] = None


class DeviceProfile:
    """Real Android device profile for realistic fingerprinting"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        manufacturer: str = "OnePlus",
        model: str = "LE2115",
        android_version: str = "14",
        locale: str = "ru_RU",
        app_version: str = "116.3",
    ):
        self.device_id = device_id or self._generate_device_id()
        self.manufacturer = manufacturer
        self.model = model
        self.android_version = android_version
        self.locale = locale
        self.app_version = app_version

        # Derived values
        self.install_id = self._generate_install_id()

    def _generate_device_id(self) -> str:
        """Generate device ID (16 hex chars, lowercase)"""
        return secrets.token_hex(8)

    def _generate_install_id(self) -> str:
        """Generate install ID based on device"""
        return hashlib.md5(f"{self.device_id}:install".encode()).hexdigest()

    @property
    def user_agent(self) -> str:
        """User-Agent in exact Avito format"""
        return f"AVITO {self.app_version} ({self.manufacturer} {self.model}; Android {self.android_version}; {self.locale})"

    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "android_version": self.android_version,
            "locale": self.locale,
            "app_version": self.app_version,
            "install_id": self.install_id,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DeviceProfile":
        return cls(
            device_id=data.get("device_id"),
            manufacturer=data.get("manufacturer", "OnePlus"),
            model=data.get("model", "LE2115"),
            android_version=data.get("android_version", "14"),
            locale=data.get("locale", "ru_RU"),
            app_version=data.get("app_version", "116.3"),
        )

    @classmethod
    def oneplus9_pro(cls, device_id: Optional[str] = None) -> "DeviceProfile":
        """OnePlus 9 Pro profile (LE2115)"""
        return cls(
            device_id=device_id,
            manufacturer="OnePlus",
            model="LE2115",
            android_version="14",
            locale="ru_RU",
            app_version="116.3",
        )


class AvitoAuth:
    BASE_URL = "https://app.avito.ru/api"

    def __init__(self, device: Optional[DeviceProfile] = None):
        self.device = device or DeviceProfile.oneplus9_pro()
        self.tracker_uid = self._generate_tracker_uid()
        self.visitor_token: Optional[str] = None

        # Session data
        self.session_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.phash: Optional[str] = None

        # Create HTTP client with proper headers
        self.client = httpx.Client(
            headers=self._build_headers(),
            timeout=30.0,
            follow_redirects=True,
            http2=True,  # Avito uses HTTP/2
        )

    def _build_headers(self) -> Dict[str, str]:
        """Build headers exactly like Avito Android app"""
        return {
            "User-Agent": self.device.user_agent,
            "X-App": "avito",
            "X-Platform": "android",
            "X-DeviceId": self.device.device_id,
            "X-Geo-required": "true",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _generate_tracker_uid(self) -> str:
        """Generate tracker/fingerprint UID (fid parameter)"""
        # Based on device_id + random component
        data = f"{self.device.device_id}:{secrets.token_hex(8)}:{int(time.time())}"
        return hashlib.md5(data.encode()).hexdigest()

    def _generate_push_token(self) -> str:
        """Generate realistic Firebase push token"""
        # Firebase tokens have specific format: project:token
        # We generate something that looks valid
        project_id = base64.b64encode(secrets.token_bytes(12)).decode().replace("=", "")
        token_part = base64.b64encode(secrets.token_bytes(100)).decode().replace("=", "")[:140]
        return f"{project_id}:{token_part}"

    def _add_session_headers(self):
        """Add session header if logged in"""
        if self.session_token:
            self.client.headers["X-Session"] = self.session_token

    def warmup(self) -> bool:
        """
        Make initial requests to establish session before auth.
        This mimics normal app behavior on startup.
        """
        print("[*] Warming up connection...")

        try:
            # 1. Generate visitor token (app does this on first launch)
            print("    [1/3] Generating visitor token...")
            resp = self.client.post(
                f"{self.BASE_URL}/1/visitorGenerate",
                data={"deviceId": self.device.device_id}
            )
            if resp.status_code == 200:
                data = resp.json()
                self.visitor_token = data.get("result", {}).get("visitor")
                print(f"    [+] Visitor: {self.visitor_token[:30] if self.visitor_token else 'None'}...")

            # 2. Get auth suggestions
            print("    [2/3] Getting auth suggestions...")
            resp = self.client.get(
                f"{self.BASE_URL}/1/auth/suggest",
                params={"hashUserIds[0]": self.device.device_id}
            )
            if resp.status_code == 200:
                data = resp.json()
                socials = data.get("result", {}).get("socials", [])
                print(f"    [+] Available auth methods: {len(socials)}")

            # 3. Small delay to look natural
            print("    [3/3] Waiting...")
            time.sleep(1.5)

            print("[+] Warmup complete")
            return True

        except Exception as e:
            print(f"[-] Warmup failed: {e}")
            return False

    def login(self, phone: str, password: str, suggest_key: Optional[str] = None) -> AuthResult:
        """
        Login with phone and password.

        Args:
            phone: Phone number in format +7XXXXXXXXXX
            password: Account password
            suggest_key: Optional suggest key from previous login

        Returns:
            AuthResult with session tokens or error info
        """
        print(f"\n[*] Logging in as {phone[:7]}***...")

        url = f"{self.BASE_URL}/11/auth"

        # Build form data exactly like the app
        data = {
            "login": phone,
            "password": password,
            "token": self._generate_push_token(),
            "isSandbox": "false",
            "fid": self.tracker_uid,
        }

        if suggest_key:
            data["suggestKey"] = suggest_key

        # Add geo header for auth
        headers = {"X-Geo-required": "true"}

        try:
            response = self.client.post(url, data=data, headers=headers)

            print(f"[*] Response status: {response.status_code}")

            if response.status_code == 429:
                return AuthResult(
                    status=AuthStatus.RATE_LIMITED,
                    error_message="Too many requests - rate limited"
                )

            result = response.json()

            # Debug output
            status = result.get("status", "unknown")
            print(f"[*] API status: {status}")

            return self._parse_auth_response(result)

        except httpx.HTTPStatusError as e:
            return AuthResult(
                status=AuthStatus.BLOCKED,
                error_message=f"HTTP Error: {e.response.status_code}"
            )
        except Exception as e:
            return AuthResult(
                status=AuthStatus.INCORRECT_DATA,
                error_message=str(e)
            )

    def verify_tfa(self, code: str, flow: str = "sms") -> AuthResult:
        """
        Verify TFA code (SMS).

        Args:
            code: SMS verification code
            flow: TFA flow type (default: sms)

        Returns:
            AuthResult with session tokens or error
        """
        print(f"\n[*] Verifying TFA code: {code}...")

        url = f"{self.BASE_URL}/2/tfa/auth"

        data = {
            "code": code,
            "flow": flow,
            "fid": self.tracker_uid,
        }

        try:
            response = self.client.post(url, data=data)
            result = response.json()

            print(f"[*] TFA Response status: {result.get('status', 'unknown')}")

            return self._parse_auth_response(result)

        except Exception as e:
            return AuthResult(
                status=AuthStatus.INCORRECT_DATA,
                error_message=str(e)
            )

    def _parse_auth_response(self, response: Dict) -> AuthResult:
        """Parse auth API response into AuthResult"""
        status = response.get("status", "")
        result_data = response.get("result", {})

        # Success
        if status == "ok":
            user = result_data.get("user", {})
            self.session_token = result_data.get("session")
            self.refresh_token = result_data.get("refreshToken")
            self.phash = result_data.get("phash")
            self._add_session_headers()

            return AuthResult(
                status=AuthStatus.SUCCESS,
                session=self.session_token,
                refresh_token=self.refresh_token,
                phash=self.phash,
                user_id=user.get("id"),
                user_name=user.get("name"),
                raw_response=response
            )

        # TFA required - check multiple indicators
        tfa_indicators = ["phoneList", "phone", "tfa", "TfaCheck"]
        if any(ind in str(result_data) for ind in tfa_indicators):
            return AuthResult(
                status=AuthStatus.TFA_REQUIRED,
                tfa_flow=result_data.get("flow", "sms"),
                tfa_phone=result_data.get("phone"),
                tfa_phone_list=result_data.get("phoneList"),
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

        # Captcha required
        if "captcha" in str(result_data).lower():
            return AuthResult(
                status=AuthStatus.CAPTCHA_REQUIRED,
                error_message="Captcha required",
                raw_response=response
            )

        # Unknown response
        return AuthResult(
            status=AuthStatus.INCORRECT_DATA,
            error_message=f"Unknown response status: {status}",
            raw_response=response
        )

    def save_session(self, filepath: str):
        """Save complete session to file"""
        data = {
            "device": self.device.to_dict(),
            "tracker_uid": self.tracker_uid,
            "visitor_token": self.visitor_token,
            "session_token": self.session_token,
            "refresh_token": self.refresh_token,
            "phash": self.phash,
            "saved_at": int(time.time()),
        }
        Path(filepath).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[+] Session saved to {filepath}")

    def load_session(self, filepath: str) -> bool:
        """Load session from file"""
        try:
            data = json.loads(Path(filepath).read_text())

            if "device" in data:
                self.device = DeviceProfile.from_dict(data["device"])
                # Rebuild client with new device headers
                self.client = httpx.Client(
                    headers=self._build_headers(),
                    timeout=30.0,
                    follow_redirects=True,
                    http2=True,
                )

            self.tracker_uid = data.get("tracker_uid", self.tracker_uid)
            self.visitor_token = data.get("visitor_token")
            self.session_token = data.get("session_token")
            self.refresh_token = data.get("refresh_token")
            self.phash = data.get("phash")

            self._add_session_headers()

            print(f"[+] Session loaded from {filepath}")
            print(f"    Device ID: {self.device.device_id}")
            return True

        except Exception as e:
            print(f"[-] Failed to load session: {e}")
            return False


def interactive_login():
    """Interactive login flow with realistic behavior"""
    print("=" * 60)
    print("Avito Auth Client - Realistic Mode")
    print("=" * 60)

    # Check for existing session/device
    session_file = Path("avito_auth_session.json")
    device = None

    if session_file.exists():
        print(f"\n[?] Found existing session file. Use same device? (y/n)")
        choice = input("> ").strip().lower()
        if choice == "y":
            try:
                data = json.loads(session_file.read_text())
                device = DeviceProfile.from_dict(data.get("device", {}))
                print(f"[+] Using existing device: {device.device_id}")
            except:
                pass

    if device is None:
        # Use known device_id from captured session
        print("\n[?] Use captured device_id (a8d7b75625458809)? (y/n)")
        choice = input("> ").strip().lower()
        if choice == "y":
            device = DeviceProfile.oneplus9_pro(device_id="a8d7b75625458809")
        else:
            device = DeviceProfile.oneplus9_pro()

    print(f"\n[*] Device Profile:")
    print(f"    Device ID: {device.device_id}")
    print(f"    User-Agent: {device.user_agent}")

    auth = AvitoAuth(device=device)

    # Warmup
    print("\n" + "-" * 60)
    auth.warmup()

    # Get credentials
    print("\n" + "-" * 60)
    phone = input("Phone (+7...): ").strip()
    password = input("Password: ").strip()

    # Login
    print("\n" + "-" * 60)
    result = auth.login(phone, password)

    if result.status == AuthStatus.SUCCESS:
        print(f"\n{'=' * 60}")
        print("[+] LOGIN SUCCESSFUL!")
        print(f"    User ID: {result.user_id}")
        print(f"    User Name: {result.user_name}")
        print(f"    Session: {result.session[:50]}..." if result.session else "    Session: None")
        print(f"    Refresh Token: {result.refresh_token}")
        print(f"    PHash: {result.phash}")
        print(f"{'=' * 60}")

        auth.save_session("avito_auth_session.json")

    elif result.status == AuthStatus.TFA_REQUIRED:
        print(f"\n{'=' * 60}")
        print("[!] TFA/SMS VERIFICATION REQUIRED")
        print(f"    Flow: {result.tfa_flow}")
        print(f"    Phone: {result.tfa_phone}")
        if result.tfa_phone_list:
            print(f"    Available phones: {result.tfa_phone_list}")
        print(f"{'=' * 60}")

        code = input("\nEnter SMS code: ").strip()
        tfa_result = auth.verify_tfa(code, result.tfa_flow or "sms")

        if tfa_result.status == AuthStatus.SUCCESS:
            print(f"\n[+] TFA SUCCESSFUL!")
            print(f"    User ID: {tfa_result.user_id}")
            print(f"    User Name: {tfa_result.user_name}")
            auth.save_session("avito_auth_session.json")
        else:
            print(f"\n[-] TFA Failed: {tfa_result.error_message}")
            if tfa_result.raw_response:
                print(f"    Response: {json.dumps(tfa_result.raw_response, indent=2, ensure_ascii=False)}")

    elif result.status == AuthStatus.CAPTCHA_REQUIRED:
        print(f"\n[-] CAPTCHA REQUIRED")
        print("    Cannot proceed automatically - captcha solving not implemented")
        if result.raw_response:
            print(f"    Response: {json.dumps(result.raw_response, indent=2, ensure_ascii=False)}")

    elif result.status == AuthStatus.RATE_LIMITED:
        print(f"\n[-] RATE LIMITED")
        print("    Too many requests. Wait and try again later.")

    else:
        print(f"\n[-] LOGIN FAILED: {result.error_message}")
        if result.raw_response:
            print(f"    Response: {json.dumps(result.raw_response, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    interactive_login()
