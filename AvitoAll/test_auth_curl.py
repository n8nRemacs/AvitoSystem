"""
Test Avito auth with curl_cffi for TLS fingerprint impersonation
"""
from curl_cffi import requests
import json
import time
import secrets
import hashlib
import base64

# Device parameters from captured session
DEVICE_ID = "a8d7b75625458809"
USER_AGENT = "AVITO 116.3 (OnePlus LE2115; Android 14; ru_RU)"

# Generate tracker UID
def generate_tracker_uid():
    data = f"{DEVICE_ID}:{secrets.token_hex(8)}:{int(time.time())}"
    return hashlib.md5(data.encode()).hexdigest()

# Generate push token
def generate_push_token():
    project_id = base64.b64encode(secrets.token_bytes(12)).decode().replace("=", "")
    token_part = base64.b64encode(secrets.token_bytes(100)).decode().replace("=", "")[:140]
    return f"{project_id}:{token_part}"

# Create session with Android impersonation
session = requests.Session(impersonate="chrome120")

# Common headers
headers = {
    "User-Agent": USER_AGENT,
    "X-App": "avito",
    "X-Platform": "android",
    "X-DeviceId": DEVICE_ID,
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

tracker_uid = generate_tracker_uid()
print(f"Device ID: {DEVICE_ID}")
print(f"Tracker UID: {tracker_uid}")
print(f"User-Agent: {USER_AGENT}")

# 1. Warmup - visitor generate
print("\n--- Warmup: visitorGenerate ---")
try:
    resp = session.post(
        "https://app.avito.ru/api/1/visitorGenerate",
        data={"deviceId": DEVICE_ID},
        headers=headers,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        visitor = data.get("result", {}).get("visitor", "")
        print(f"Visitor: {visitor[:40]}..." if visitor else "No visitor")
except Exception as e:
    print(f"Error: {e}")

time.sleep(1)

# 2. Warmup - auth suggest
print("\n--- Warmup: auth/suggest ---")
try:
    resp = session.get(
        "https://app.avito.ru/api/1/auth/suggest",
        params={"hashUserIds[0]": DEVICE_ID},
        headers=headers,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        socials = data.get("result", {}).get("socials", [])
        print(f"Available methods: {len(socials)}")
except Exception as e:
    print(f"Error: {e}")

time.sleep(1.5)

# 3. Login
print("\n--- Login ---")
auth_headers = headers.copy()
auth_headers["X-Geo-required"] = "true"
auth_headers["Content-Type"] = "application/x-www-form-urlencoded"

auth_data = {
    "login": "+79997253777",
    "password": "31415926Mips",
    "token": generate_push_token(),
    "isSandbox": "false",
    "fid": tracker_uid,
}

print(f"Sending to: https://app.avito.ru/api/11/auth")
print(f"Data keys: {list(auth_data.keys())}")

try:
    resp = session.post(
        "https://app.avito.ru/api/11/auth",
        data=auth_data,
        headers=auth_headers,
    )
    print(f"Status: {resp.status_code}")
    print(f"Response headers: {dict(resp.headers)}")

    result = resp.json()
    print(f"\nResponse:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    status = result.get("status")
    if status == "ok":
        print("\n=== SUCCESS ===")
        user = result.get("result", {}).get("user", {})
        print(f"User ID: {user.get('id')}")
        print(f"User Name: {user.get('name')}")

        # Save session
        session_data = {
            "session": result["result"]["session"],
            "refreshToken": result["result"]["refreshToken"],
            "phash": result["result"]["phash"],
            "user": user,
        }
        with open("avito_auth_session.json", "w") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        print("Session saved!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
