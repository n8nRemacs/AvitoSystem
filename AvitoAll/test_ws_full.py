"""
Test WebSocket with ALL headers from real app
"""
import websocket
import json
import time
import uuid
from pathlib import Path

CHANNEL_ID = "u2i-PJIRB81Ps9iX81CSTNUgPw"

def load_session():
    data = json.loads(Path("avito_session_new.json").read_text())
    return data

def main():
    session = load_session()
    sessid = session["session_token"]
    device_id = session["session_data"]["device_id"]
    fingerprint = session["session_data"]["fingerprint"]
    remote_device_id = session["session_data"]["remote_device_id"]
    cookies = session["session_data"]["cookies"]

    print(f"[*] Session token: {sessid[:50]}...")
    print(f"[*] Device ID: {device_id}")
    print(f"[*] Fingerprint: {fingerprint[:50]}...")
    print(f"[*] Remote Device ID: {remote_device_id[:50]}...")

    # Build ALL headers like real app
    cookie_str = f"sessid={sessid}; " + "; ".join(f"{k}={v}" for k, v in cookies.items())

    headers = [
        "User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        f"Cookie: {cookie_str}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        f"X-RemoteDeviceId: {remote_device_id}",
        f"f: {fingerprint}",
        "X-App: avito",
        "X-Platform: android",
        "X-Supported-Features: helpcenter-form-46049",
        "AT-v: 1",
        "Schema-Check: 0",
        f"X-Date: {int(time.time())}",
    ]

    print(f"\n[*] Connecting with {len(headers)} headers...")

    ws = websocket.WebSocket()
    ws.connect("wss://socket.avito.ru/socket?use_seq=true&app_name=android", header=headers)

    msg = ws.recv()
    data = json.loads(msg)
    print(f"[+] Connected! User ID: {data.get('value', {}).get('userId')}")
    print(f"    Server time: {data.get('value', {}).get('serverTime')}")
    print(f"    Seq: {data.get('value', {}).get('seq')}")

    req_id = 0
    def rpc(method, params):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
        return json.loads(ws.recv())

    print("\n" + "="*60)

    # Test all methods
    tests = [
        ("avito.getChats.v5", {"limit": 20, "filters": {"excludeTags": ["p", "s"]}}),
        ("avito.getChatById.v3", {"channelId": CHANNEL_ID}),
        ("messenger.history.v2", {"channelId": CHANNEL_ID, "limit": 5}),
        ("messenger.getUnreadCount.v1", {}),
        ("messenger.quickReplies.v1", {}),
    ]

    for method, params in tests:
        print(f"\n[*] {method}")
        r = rpc(method, params)
        if "result" in r:
            result = r["result"]
            if isinstance(result, dict):
                keys = list(result.keys())[:5]
                print(f"    SUCCESS! Keys: {keys}")
            else:
                print(f"    SUCCESS! Result: {result}")
        else:
            print(f"    Error: {r.get('error', {}).get('message', r)}")

    ws.close()
    print("\n[+] Done!")


if __name__ == "__main__":
    main()
