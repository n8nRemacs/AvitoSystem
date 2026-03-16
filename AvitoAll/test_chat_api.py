"""
Test chat API with known channel ID
"""
import websocket
import json
from pathlib import Path

CHANNEL_ID = "u2i-PJIRB81Ps9iX81CSTNUgPw"

def load_session():
    data = json.loads(Path("avito_session_new.json").read_text())
    return data["session_token"], data["session_data"]["device_id"]

def main():
    sessid, device_id = load_session()

    ws = websocket.WebSocket()
    ws.connect(
        "wss://socket.avito.ru/socket?use_seq=true&app_name=android",
        header=[
            f"Cookie: sessid={sessid}",
            f"X-Session: {sessid}",
            f"X-DeviceId: {device_id}",
            "X-App: avito",
            "X-Platform: android",
        ]
    )

    # Session init
    msg = ws.recv()
    data = json.loads(msg)
    print(f"[+] Connected! User ID: {data.get('value', {}).get('userId')}")

    req_id = 0
    def rpc(method, params):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
        return json.loads(ws.recv())

    print(f"\n[*] Channel: {CHANNEL_ID}")
    print("="*60)

    # 1. Get chat by ID
    print("\n[1] avito.getChatById.v3")
    r = rpc("avito.getChatById.v3", {"channelId": CHANNEL_ID})
    if "result" in r:
        chat = r["result"]
        user = chat.get("user", {})
        print(f"    User: {user.get('name', '?')}")
        print(f"    Item: {chat.get('item', {}).get('title', '?')[:40]}")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    # 2. Get history
    print("\n[2] messenger.history.v2")
    r = rpc("messenger.history.v2", {"channelId": CHANNEL_ID, "limit": 10})
    if "result" in r:
        messages = r["result"].get("messages", [])
        print(f"    Found {len(messages)} messages:")
        for m in messages[-5:]:
            body = m.get("body", {})
            text = body.get("text", "[media]")[:50]
            print(f"      - {text}")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    # 3. Get last action times
    print("\n[3] messenger.getLastActionTimes.v2")
    r = rpc("messenger.getLastActionTimes.v2", {"channelIds": [CHANNEL_ID]})
    print(f"    Result: {r}")

    # 4. Try getChats one more time
    print("\n[4] avito.getChats.v5 (retry)")
    r = rpc("avito.getChats.v5", {"limit": 10, "filters": {"excludeTags": []}})
    if "result" in r:
        print(f"    SUCCESS! {len(r['result'].get('chats', []))} chats")
    else:
        print(f"    Error: {r.get('error', {}).get('message', r)}")

    ws.close()
    print("\n[+] Done!")


if __name__ == "__main__":
    main()
