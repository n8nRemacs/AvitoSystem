"""Re-login with new fingerprint"""
from avito_auth_final import AvitoAuthFinal, CapturedSession
import json
from pathlib import Path

NEW_FP = "A2.a541fb18def1032c46e8ce9356bf78870fa9c764bfb1e9e5b987ddf59dd9d01cc9450700054f77c90fafbcf2130fdc0e28f55511b08ad67d2a56fddf442f3dff07669ef9caeb686faf92383f06c695a6c296491e31ea13d4ed9f4c834316a4fd2cf60b8bde696617a6928526221fc174f4eab22785947feba00bbc60cbd59dcdd798f306ccdf536c876453ee72d819c926bde786618ec0c59d92fb046d297a8405f055c0388a4854eed7182c38fc3c2a70bffea9fd1ea8353b31af94a143f0b96cf2860b58c350fb01c5e8368a24ae001ffa197dea33c426"

session = CapturedSession(fingerprint=NEW_FP)
auth = AvitoAuthFinal(session)

print(f"[*] New fingerprint: {NEW_FP[:50]}...")

result = auth.login("+79171708077", "Mi31415926pSss!", geo="46.360889;48.047291;100;1768295137")

if result.get("status") == "ok":
    print(f"\n[+] SUCCESS! User ID: {result.get('user', {}).get('id')}")
    auth.save_session("avito_session_new.json")
else:
    print(f"[-] Failed: {result.get('status')}")
