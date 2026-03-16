"""Test pagination for channels"""
from curl_cffi import requests
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')

def load_session():
    return json.loads(Path("avito_session_new.json").read_text(encoding='utf-8'))

def main():
    session_data = load_session()
    sessid = session_data["session_token"]
    device_id = session_data["session_data"]["device_id"]
    fp = session_data["session_data"]["fingerprint"]
    remote_id = session_data["session_data"]["remote_device_id"]
    cookies = session_data["session_data"]["cookies"]

    session = requests.Session(impersonate="chrome120")

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

    total = 0
    offset = None
    page = 0

    print("[*] Testing pagination...")

    while True:
        page += 1
        resp = session.post(
            "https://app.avito.ru/api/1/messenger/getChannels",
            headers=headers,
            json={"category": 1, "filters": {}, "limit": 30, "offsetTimestamp": offset}
        )

        data = resp.json()
        channels = data.get("success", {}).get("channels", [])
        has_more = data.get("success", {}).get("hasMore", False)

        total += len(channels)
        print(f"  Page {page}: {len(channels)} channels (total: {total}, hasMore: {has_more})")

        if not channels or not has_more:
            break

        # Get offset from last channel
        last = channels[-1]
        offset = last.get("sortingTimestamp")
        print(f"    Next offset: {offset}")

        # Stop after 5 pages for demo
        if page >= 5:
            print(f"\n  [Stopped at page 5 for demo]")
            break

    print(f"\n[+] Total channels loaded: {total}")


if __name__ == "__main__":
    main()
