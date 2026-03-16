"""Test different WebSocket URL parameters"""
import websocket
import json
import time
from pathlib import Path

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def test_url(ws_url, headers, name):
    print(f"\n[*] Testing: {name}")
    print(f"    URL: {ws_url[:80]}...")
    try:
        ws = websocket.WebSocket()
        ws.settimeout(10)
        ws.connect(ws_url, header=headers)

        msg = ws.recv()
        data = json.loads(msg)
        user_id = data.get('value', {}).get('userId')
        print(f"    Connected! User: {user_id}")

        # Test getChats
        ws.send(json.dumps({
            "id": 1,
            "jsonrpc": "2.0",
            "method": "avito.getChats.v5",
            "params": {"limit": 5, "filters": {"excludeTags": []}}
        }))

        resp = json.loads(ws.recv())
        if "result" in resp:
            print(f"    getChats: SUCCESS!")
            return True
        else:
            print(f"    getChats: {resp.get('error', {}).get('message', 'error')}")

        ws.close()
    except Exception as e:
        print(f"    Error: {e}")
    return False


def main():
    session = load_session()
    sessid = session["session_token"]
    device_id = session["session_data"]["device_id"]
    fp = session["session_data"]["fingerprint"]
    remote_id = session["session_data"]["remote_device_id"]

    # Base headers
    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        f"X-RemoteDeviceId: {remote_id}",
        f"f: {fp}",
        "X-App: avito",
        "X-Platform: android",
        "User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
    ]

    # Different URL variants
    urls = [
        ("Basic", "wss://socket.avito.ru/socket?use_seq=true&app_name=android"),
        ("With version", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&app_version=215.1"),
        ("With device", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&device_id={device_id}"),
        ("Full params", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&app_version=215.1&device_id={device_id}&platform=android"),
    ]

    for name, url in urls:
        if test_url(url, headers, name):
            print("\n[+] Found working configuration!")
            break


if __name__ == "__main__":
    main()
