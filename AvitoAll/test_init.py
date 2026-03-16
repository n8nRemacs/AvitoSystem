"""
Try to find initialization methods
"""
import websocket
import json
from pathlib import Path

def load_session():
    data = json.loads(Path("avito_session_new.json").read_text())
    return data

def main():
    session = load_session()
    sessid = session["session_token"]
    device_id = session["session_data"]["device_id"]
    fp = session["session_data"]["fingerprint"]
    remote_id = session["session_data"]["remote_device_id"]

    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        f"X-RemoteDeviceId: {remote_id}",
        f"f: {fp}",
        "X-App: avito",
        "X-Platform: android",
    ]

    ws = websocket.WebSocket()
    ws.connect("wss://socket.avito.ru/socket?use_seq=true&app_name=android", header=headers)

    msg = ws.recv()
    print(f"[+] Connected: {json.loads(msg).get('value', {}).get('userId')}")

    req_id = 0
    def rpc(method, params={}):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
        return json.loads(ws.recv())

    # Try various initialization/settings methods
    methods = [
        ("messenger.init", {}),
        ("messenger.getSettings.v2", {"fields": []}),
        ("messenger.getSettings.v1", {}),
        ("avito.init", {}),
        ("messenger.subscribe", {}),
        ("avito.getChats.v4", {"limit": 5}),
        ("avito.getChats.v3", {"limit": 5}),
        ("avito.getChats.v2", {"limit": 5}),
        ("messenger.getChats", {"limit": 5}),
    ]

    for method, params in methods:
        print(f"\n[*] {method}")
        r = rpc(method, params)
        if "result" in r:
            print(f"    SUCCESS: {str(r['result'])[:100]}")
        else:
            err = r.get("error", {})
            print(f"    {err.get('code')}: {err.get('message')}")

    ws.close()


if __name__ == "__main__":
    main()
