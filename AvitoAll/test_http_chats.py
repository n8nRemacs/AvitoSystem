"""
Test HTTP REST API for chats
"""
from curl_cffi import requests
import json
from pathlib import Path


def load_session(filename="avito_session_new.json"):
    data = json.loads(Path(filename).read_text())
    return data


def test():
    session_data = load_session()
    sessid = session_data["session_token"]
    device_id = session_data["session_data"]["device_id"]
    fingerprint = session_data["session_data"]["fingerprint"]

    print(f"[*] Testing HTTP API for chats")

    sess = requests.Session(impersonate="chrome120")

    headers = {
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        "X-Session": sessid,
        "X-DeviceId": device_id,
        "X-Platform": "android",
        "X-App": "avito",
        "f": fingerprint,
        "Cookie": f"sessid={sessid}",
    }

    # Try REST API endpoints
    endpoints = [
        "https://app.avito.ru/api/1/messenger/chats",
        "https://app.avito.ru/api/2/messenger/chats",
        "https://app.avito.ru/api/3/messenger/chats",
        "https://app.avito.ru/api/1/chats",
        "https://app.avito.ru/api/2/chats",
    ]

    for url in endpoints:
        print(f"\n[*] GET {url}")
        try:
            resp = sess.get(url, headers=headers, params={"limit": 10})
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"    Response: {json.dumps(data, ensure_ascii=False)[:300]}")
            else:
                print(f"    Response: {resp.text[:200]}")
        except Exception as e:
            print(f"    Error: {e}")


if __name__ == "__main__":
    test()
