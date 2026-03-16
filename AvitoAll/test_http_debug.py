"""Debug HTTP API response"""
from curl_cffi import requests
import json
from pathlib import Path
import sys

# Fix encoding
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

    print("[*] Getting channels (category=1)")
    resp = session.post(
        "https://app.avito.ru/api/1/messenger/getChannels",
        headers=headers,
        json={"category": 1, "filters": {}, "limit": 10}
    )

    if resp.status_code == 200:
        data = resp.json()
        channels = data.get("success", {}).get("channels", [])
        has_more = data.get("success", {}).get("hasMore", False)
        print(f"[+] Found {len(channels)} channels (hasMore: {has_more})\n")

        for i, ch in enumerate(channels[:5]):
            print(f"--- Channel {i+1} ---")
            print(f"  id: {ch.get('id', '?')}")

            # Users - это список
            users = ch.get("users", [])
            if users:
                for user in users[:2]:
                    if isinstance(user, dict):
                        name = user.get('name', '?')
                        print(f"  user: {name}")

            # Last message
            last = ch.get("lastMessage", {})
            if last:
                body = last.get("body", {})
                text = ""
                if isinstance(body, dict):
                    text = str(body.get("text", ""))
                print(f"  lastMessage: {text[:50] if text else '[no text]'}")

            # Context/item
            ctx = ch.get("context", {})
            if ctx:
                item = ctx.get("item", {})
                if item:
                    title = str(item.get('title', '?'))
                    print(f"  item: {title[:40]}")

            print()

        # Test getting messages for first channel
        if channels:
            channel_id = channels[0].get("id")
            print(f"\n[*] Getting messages for {channel_id}")

            msg_resp = session.post(
                "https://app.avito.ru/api/1/messenger/getUserVisibleMessages",
                headers=headers,
                json={"channelId": channel_id, "limit": 5}
            )
            print(f"    Status: {msg_resp.status_code}")
            if msg_resp.status_code == 200:
                msg_data = msg_resp.json()
                if "success" in msg_data:
                    messages = msg_data["success"].get("messages", [])
                    print(f"    Messages: {len(messages)}")
                    for m in messages[:3]:
                        body = m.get("body", {})
                        text = str(body.get('text', ''))
                        print(f"      - {text[:50] if text else '[media]'}")
                else:
                    print(f"    Response keys: {list(msg_data.keys())}")
            else:
                print(f"    Error: {msg_resp.text[:100]}")

    else:
        print(f"[-] Status: {resp.status_code}")


if __name__ == "__main__":
    main()
