"""Test HTTP Messenger API"""
from curl_cffi import requests
import json
from pathlib import Path

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def main():
    session_data = load_session()
    sessid = session_data["session_token"]
    device_id = session_data["session_data"]["device_id"]
    fp = session_data["session_data"]["fingerprint"]
    remote_id = session_data["session_data"]["remote_device_id"]
    cookies = session_data["session_data"]["cookies"]

    print("[*] Testing HTTP Messenger API")

    session = requests.Session(impersonate="chrome120")

    # Build cookie string
    cookie_str = f"sessid={sessid}"
    for k, v in cookies.items():
        cookie_str += f"; {k}={v}"

    headers = {
        "Cookie": cookie_str,
        "X-Session": sessid,
        "X-DeviceId": device_id,
        "X-RemoteDeviceId": remote_id,
        "f": fp,
        "X-App": "avito",
        "X-Platform": "android",
        "X-AppVersion": "215.1",
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        "Content-Type": "application/json",
    }

    # Test different category values
    for category in [0, 1, 2, 3, 4, 5, 6]:
        print(f"\n[*] Category {category}")
        try:
            resp = session.post(
                "https://app.avito.ru/api/1/messenger/getChannels",
                headers=headers,
                json={"category": category, "filters": {}, "limit": 30}
            )
            print(f"    Status: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                if "success" in data:
                    channels = data["success"].get("channels", [])
                    print(f"    Found {len(channels)} channels")
                    for ch in channels[:5]:
                        ctx = ch.get("context", {})
                        item = ctx.get("item", {})
                        opponent = ch.get("opponentName", "?")
                        print(f"      - {opponent}: {item.get('title', '?')[:30]}")
                elif "channels" in data:
                    channels = data.get("channels", [])
                    print(f"    Found {len(channels)} channels")
                else:
                    print(f"    Keys: {list(data.keys())[:5]}")
            else:
                print(f"    Error: {resp.text[:100]}")
        except Exception as e:
            print(f"    Error: {e}")


if __name__ == "__main__":
    main()
