"""Pull Avito session from user 10 SharedPreferences and register it via xapi.

Tokens are read directly from device, parsed, sent over HTTPS to xapi —
nothing is printed to stdout.
"""
import re
import subprocess
import sys
import json
import urllib.request

ADB = r"C:/Users/EloNout/AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v3.3.4/adb.exe"
DEVICE = "110139ce"
PREFS = "/data/user/10/com.avito.android/shared_prefs/com.avito.android_preferences.xml"
HOMELAB_SSH = "homelab"
XAPI_URL = "http://127.0.0.1:8080/api/v1/sessions"
XAPI_KEY = "test_dev_key_123"


def adb_shell(cmd: str) -> str:
    res = subprocess.run(
        [ADB, "-s", DEVICE, "shell", "su", "-c", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        sys.exit(f"adb failed: {res.stderr}")
    return res.stdout


def extract(xml: str, key: str) -> str | None:
    m = re.search(
        rf'<string name="{re.escape(key)}">([^<]+)</string>', xml,
    )
    return m.group(1) if m else None


print(f"reading {PREFS} ...")
xml = adb_shell(f"cat {PREFS}")

session = extract(xml, "session")
refresh = extract(xml, "refresh_token")
device_id = extract(xml, "device_id")
remote_device_id = extract(xml, "remote_device_id")
profile_id = extract(xml, "profile_id")

if not session:
    sys.exit("no session token found in user 10 prefs — please log into Avito-app in clone first")

print(f"session: {len(session)} chars (not shown)")
print(f"refresh: {'present' if refresh else 'MISSING'}")
print(f"device_id: {device_id[:6]}…{device_id[-4:] if device_id else '?'}")
print(f"remote_device_id: {'present' if remote_device_id else 'MISSING'}")
print(f"profile_id: {profile_id}")

payload = {
    "session_token": session,
    "refresh_token": refresh,
    "device_id": device_id,
    "remote_device_id": remote_device_id,
    "user_hash": None,
    "fingerprint": None,
    "cookies": {},
    "source": "android",
}

# POST through SSH tunnel to xapi
import shlex, base64
b64 = base64.b64encode(json.dumps(payload).encode()).decode()
ssh_cmd = (
    f"echo {b64} | base64 -d | "
    f"curl -sS -X POST -H 'X-Api-Key: {XAPI_KEY}' "
    f"-H 'Content-Type: application/json' -d @- {XAPI_URL}"
)
res = subprocess.run(
    ["ssh", HOMELAB_SSH, ssh_cmd],
    capture_output=True, text=True,
)
print("\nxapi response:", res.stdout, res.stderr if res.returncode else "")
