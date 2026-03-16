"""
Test WebSocket with fingerprint header
"""
import websocket
import json
from pathlib import Path

CHANNEL_ID = "u2i-PJIRB81Ps9iX81CSTNUgPw"

def load_session():
    data = json.loads(Path("avito_session_new.json").read_text())
    return (
        data["session_token"],
        data["session_data"]["device_id"],
        data["session_data"]["fingerprint"]
    )

def main():
    sessid, device_id, fingerprint = load_session()
    print(f"[*] FP: {fingerprint[:50]}...")

    # Add fingerprint to WebSocket headers
    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        f"f: {fingerprint}",  # ADD FINGERPRINT!
        "X-App: avito",
        "X-Platform: android",
    ]

    ws = websocket.WebSocket()
    ws.connect("wss://socket.avito.ru/socket?use_seq=true&app_name=android", header=headers)

    msg = ws.recv()
    data = json.loads(msg)
    print(f"[+] Connected! User ID: {data.get('value', {}).get('userId')}")

    req_id = 0
    def rpc(method, params):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
        return json.loads(ws.recv())

    print("\n" + "="*50)

    # Test getChats
    print("[1] avito.getChats.v5")
    r = rpc("avito.getChats.v5", {"limit": 20, "filters": {"excludeTags": ["p", "s"]}})
    if "result" in r:
        chats = r["result"].get("chats", [])
        print(f"    SUCCESS! {len(chats)} chats")
        for c in chats[:3]:
            print(f"      - {c.get('user',{}).get('name','?')}: {c.get('channelId','')[:25]}...")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    # Test history
    print("\n[2] messenger.history.v2")
    r = rpc("messenger.history.v2", {"channelId": CHANNEL_ID, "limit": 5})
    if "result" in r:
        msgs = r["result"].get("messages", [])
        print(f"    SUCCESS! {len(msgs)} messages")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    # Test send
    print("\n[3] avito.sendTextMessage.v2")
    import uuid, time
    r = rpc("avito.sendTextMessage.v2", {
        "channelId": CHANNEL_ID,
        "randomId": str(uuid.uuid4()),
        "text": "Test",
        "initActionTimestamp": int(time.time() * 1000)
    })
    if "result" in r:
        print(f"    SUCCESS! Message sent")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    ws.close()
    print("\n[+] Done!")


if __name__ == "__main__":
    main()
