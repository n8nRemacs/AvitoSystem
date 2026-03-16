"""Test typing and other channel-specific methods"""
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

    # Decode JWT to get user hash
    import base64
    payload = sessid.split('.')[1]
    payload += '=' * (4 - len(payload) % 4)
    jwt_data = json.loads(base64.b64decode(payload))
    user_id = jwt_data.get('u')
    print(f"[*] User ID from JWT: {user_id}")

    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {session['session_data']['device_id']}",
        f"f: {session['session_data']['fingerprint']}",
        "X-App: avito",
        "X-Platform: android",
    ]

    ws = websocket.WebSocket()
    ws.connect("wss://socket.avito.ru/socket?use_seq=true&app_name=android", header=headers)

    msg = ws.recv()
    init_data = json.loads(msg)
    print(f"[+] Connected! User ID: {init_data.get('value', {}).get('userId')}")

    req_id = 0
    def rpc(method, params={}):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
        return json.loads(ws.recv())

    print(f"\n[*] Channel: {CHANNEL_ID}")
    print("="*60)

    # Try typing
    print("\n[1] messenger.sendTyping.v2")
    r = rpc("messenger.sendTyping.v2", {
        "channelId": CHANNEL_ID,
        "userId": str(user_id)
    })
    print(f"    Result: {r}")

    # Try read
    print("\n[2] messenger.readChats.v1")
    r = rpc("messenger.readChats.v1", {"channelIds": [CHANNEL_ID]})
    print(f"    Result: {r}")

    # Try body images
    print("\n[3] avito.getBodyImages")
    r = rpc("avito.getBodyImages", {"channelId": CHANNEL_ID})
    print(f"    Result: {r}")

    # Try get chat after these
    print("\n[4] avito.getChatById.v3 (after typing)")
    r = rpc("avito.getChatById.v3", {"channelId": CHANNEL_ID})
    if "result" in r:
        print(f"    SUCCESS!")
    else:
        print(f"    Error: {r.get('error', {}).get('message')}")

    # Try send message
    print("\n[5] avito.sendTextMessage.v2")
    r = rpc("avito.sendTextMessage.v2", {
        "channelId": CHANNEL_ID,
        "randomId": str(uuid.uuid4()),
        "text": "Тест",
        "initActionTimestamp": int(time.time() * 1000)
    })
    if "result" in r:
        print(f"    SUCCESS! Message sent!")
    else:
        print(f"    Error: {r.get('error', {}).get('message')}")

    ws.close()


if __name__ == "__main__":
    main()
