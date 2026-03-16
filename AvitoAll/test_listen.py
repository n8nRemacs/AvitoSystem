"""Listen for incoming messages via WebSocket"""
from curl_cffi import requests
import json
from pathlib import Path
import sys
import time

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
    user_hash = "4c48533419806d790635e8565693e5c2"

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
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
    }

    ws_url = f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}"

    print("[*] Connecting to WebSocket...")
    ws = session.ws_connect(ws_url, headers=headers)

    # Get session init
    init = json.loads(ws.recv()[0])
    print(f"[+] Connected! User: {init['value']['userId']}, Seq: {init['value']['seq']}")
    print("[*] Listening for messages (30 sec)... Send something in Avito app!\n")

    start = time.time()
    while time.time() - start < 30:
        try:
            msg = ws.recv()
            if msg:
                data = json.loads(msg[0])
                msg_type = data.get("type", data.get("type_v2", ""))

                if msg_type == "Message":
                    value = data.get("value", {})
                    body = value.get("body", {})
                    text = body.get("text", "[media]")
                    from_uid = value.get("fromUid", "")
                    channel = value.get("channelId", "")[:25]

                    if from_uid != user_hash:
                        print(f"[INCOMING] {text}")
                        print(f"  Channel: {channel}...")
                        print(f"  From: {from_uid[:20]}...")
                        print()
                    else:
                        print(f"[OUTGOING] {text}")
                        print()

                elif msg_type == "ChatTyping":
                    print(f"[TYPING] Someone is typing...")

                elif msg_type:
                    print(f"[{msg_type}] {str(data)[:100]}")

        except Exception as e:
            pass
        time.sleep(0.3)

    print("\n[*] Done listening")
    ws.close()


if __name__ == "__main__":
    main()
