"""Re-login with all current device data"""
from avito_auth_final import AvitoAuthFinal, CapturedSession
import json
from pathlib import Path

# Current data from device
FP = "A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc174f4eab22785947feba00bbc60cbd59dcdd798f306ccdf536c876453ee72d819c926bde786618ec0c59d92fb046d297a8405f055c0388a4854eed7182c38fc3c2a70bffea9fd1ea8353b31af94a143f0b96cf2860b58c350fb01c5e8368a24ae001ffa197dea33c426"

REMOTE_ID = "kSCwY4Kj4HUfwZHG.dETo5G6mASWYj1o8WQV7G9AoYQm3OBcfoD29SM-WGzZa_y5uXhxeKOfQAPNcyR0Kc-hc-w2TeA==.0Ir5Kv9vC5RQ_-0978SocYK64ZNiUpwSmGJGf2c-_74=.android"

COOKIES = {
    "1f_uid": "27835d95-6380-44e1-8289-4a13a511a29b",
    "u": "3bhsmqlh.1i5wwa4.i996zfqfof",
    "v": "1768298018",
    "_avisc": "XDF28nHpInIAwmCg69ejxL2SWJxYRigPu2mNk67+kUI=",
}

session = CapturedSession(
    fingerprint=FP,
    remote_device_id=REMOTE_ID,
    cookies=COOKIES
)

auth = AvitoAuthFinal(session)

print(f"[*] Fingerprint: {FP[:50]}...")
print(f"[*] Remote ID: {REMOTE_ID[:50]}...")
print(f"[*] Cookies: {list(COOKIES.keys())}")

result = auth.login("+79171708077", "Mi31415926pSss!", geo="46.360889;48.047291;100;1768298000")

if result.get("status") == "ok":
    print(f"\n[+] SUCCESS! User ID: {result.get('user', {}).get('id')}")

    # Save full session data
    data = {
        "session_token": auth.session_token,
        "refresh_token": auth.refresh_token,
        "session_data": {
            "device_id": session.device_id,
            "fingerprint": session.fingerprint,
            "remote_device_id": session.remote_device_id,
            "cookies": session.cookies,
        }
    }
    Path("avito_session_new.json").write_text(json.dumps(data, indent=2))
    print("[+] Session saved!")
else:
    print(f"[-] Failed: {result}")
