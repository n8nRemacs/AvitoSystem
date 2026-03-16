"""Clean test with proper message handling"""
import websocket
import json
import time
import uuid
from pathlib import Path

CHANNEL_ID = "u2i-PJIRB81Ps9iX81CSTNUgPw"

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def main():
    session = load_session()
    sessid = session["session_token"]

    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {session['session_data']['device_id']}",
        f"f: {session['session_data']['fingerprint']}",
        "X-App: avito",
        "X-Platform: android",
    ]

    ws = websocket.WebSocket()
    ws.settimeout(5)
    ws.connect("wss://socket.avito.ru/socket?use_seq=true&app_name=android", header=headers)

    # Session init
    msg = ws.recv()
    print(f"[+] Connected: {json.loads(msg).get('value', {}).get('userId')}")

    req_id = 0
    pending = {}

    def send_rpc(method, params={}):
        nonlocal req_id
        req_id += 1
        msg = {"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}
        ws.send(json.dumps(msg))
        pending[req_id] = method
        return req_id

    def recv_all():
        """Receive all pending messages"""
        results = {}
        while True:
            try:
                msg = ws.recv()
                data = json.loads(msg)

                # Check if RPC response
                if "id" in data and data["id"] in pending:
                    method = pending.pop(data["id"])
                    results[method] = data
                else:
                    # Push event
                    evt_type = data.get("type") or data.get("type_v2", "unknown")
                    print(f"    [PUSH] {evt_type}")
            except:
                break
        return results

    print("\n" + "="*60)

    # Send all requests
    send_rpc("messenger.readChats.v1", {"channelIds": [CHANNEL_ID]})
    send_rpc("avito.getChatById.v3", {"channelId": CHANNEL_ID})
    send_rpc("messenger.history.v2", {"channelId": CHANNEL_ID, "limit": 5})
    send_rpc("avito.getChats.v5", {"limit": 5, "filters": {}})
    send_rpc("avito.sendTextMessage.v2", {
        "channelId": CHANNEL_ID,
        "randomId": str(uuid.uuid4()),
        "text": "Test from Python",
        "initActionTimestamp": int(time.time() * 1000)
    })

    time.sleep(2)
    results = recv_all()

    for method, data in results.items():
        print(f"\n[{method}]")
        if "result" in data:
            r = data["result"]
            if isinstance(r, dict):
                print(f"  SUCCESS! Keys: {list(r.keys())[:5]}")
                if "messages" in r:
                    for m in r["messages"][:2]:
                        print(f"    - {m.get('body', {}).get('text', '[media]')[:40]}")
                if "chats" in r:
                    for c in r["chats"][:2]:
                        print(f"    - {c.get('user', {}).get('name', '?')}")
            else:
                print(f"  SUCCESS! {r}")
        else:
            print(f"  Error: {data.get('error', {}).get('message', data)}")

    ws.close()


if __name__ == "__main__":
    main()
