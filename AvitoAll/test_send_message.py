"""Test sending message via HTTP API"""
from curl_cffi import requests
import json
from pathlib import Path
import uuid
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

    # Get first channel
    print("[*] Getting channels...")
    resp = session.post(
        "https://app.avito.ru/api/1/messenger/getChannels",
        headers=headers,
        json={"category": 1, "filters": {}, "limit": 5}
    )

    if resp.status_code != 200:
        print(f"[-] Error getting channels: {resp.status_code}")
        return

    data = resp.json()
    channels = data.get("success", {}).get("channels", [])

    if not channels:
        print("[-] No channels found")
        return

    # Show available channels
    print(f"[+] Found {len(channels)} channels:")
    for i, ch in enumerate(channels):
        users = ch.get("users", [])
        names = [u.get('name', '?') for u in users if isinstance(u, dict)]
        print(f"  [{i}] {ch.get('id', '?')[:25]}... - {', '.join(names)}")

    # Find Dmitriy's channel (index 1)
    channel_id = channels[1].get("id")  # Дмитрий
    print(f"\n[*] Sending to Dmitriy: {channel_id}")

    # Send test message
    test_message = "Привет! Это тестовое сообщение."

    print(f"[*] Sending: {test_message}")
    send_resp = session.post(
        "https://app.avito.ru/api/1/messenger/sendTextMessage",
        headers=headers,
        json={
            "channelId": channel_id,
            "text": test_message,
            "idempotencyKey": str(uuid.uuid4()),
            "chunkIndex": None,
            "quoteMessageId": None,
            "source": None,
            "xHash": None
        }
    )

    print(f"[*] Status: {send_resp.status_code}")
    print(f"[*] Response: {send_resp.text[:300]}")


if __name__ == "__main__":
    main()
