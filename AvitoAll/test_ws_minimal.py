"""Test WebSocket with minimal headers"""
from curl_cffi import requests
import json
from pathlib import Path

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def main():
    session_data = load_session()
    sessid = session_data["session_token"]
    device_id = session_data["session_data"]["device_id"]

    session = requests.Session(impersonate="chrome120")
    ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"

    # Try different header combinations
    header_sets = [
        ("Minimal", {
            "Cookie": f"sessid={sessid}",
            "X-Session": sessid,
        }),
        ("With DeviceId", {
            "Cookie": f"sessid={sessid}",
            "X-Session": sessid,
            "X-DeviceId": device_id,
        }),
        ("With Platform", {
            "Cookie": f"sessid={sessid}",
            "X-Session": sessid,
            "X-DeviceId": device_id,
            "X-Platform": "android",
            "X-App": "avito",
        }),
    ]

    for name, headers in header_sets:
        print(f"\n[*] Testing: {name}")
        print(f"    Headers: {list(headers.keys())}")

        try:
            ws = session.ws_connect(ws_url, headers=headers)
            msg = ws.recv()[0]
            data = json.loads(msg)
            print(f"    Connected: User {data.get('value', {}).get('userId')}")

            ws.send(json.dumps({
                "id": 1, "jsonrpc": "2.0",
                "method": "avito.getChats.v5",
                "params": {"limit": 5, "filters": {}}
            }).encode())

            resp = json.loads(ws.recv()[0])
            if "result" in resp:
                print(f"    getChats: SUCCESS!")
                break
            else:
                print(f"    getChats: {resp.get('error', {}).get('message')}")

            ws.close()
        except Exception as e:
            print(f"    Error: {e}")


if __name__ == "__main__":
    main()
