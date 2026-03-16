"""
Messenger API Test - New Account
"""
import websocket
import json
from pathlib import Path


def load_session(filename="avito_session_new.json"):
    data = json.loads(Path(filename).read_text())
    return data["session_token"], data["session_data"]["device_id"]


def test():
    sessid, device_id = load_session()
    print(f"[*] Session: {sessid[:50]}...")
    print(f"[*] Device: {device_id}")

    ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"
    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        "X-App: avito",
        "X-Platform: android",
    ]

    print(f"\n[*] Connecting...")
    ws = websocket.WebSocket()
    ws.connect(ws_url, header=headers)
    print("[+] Connected!")

    # Session init
    msg = ws.recv()
    data = json.loads(msg)
    print(f"\n[SESSION] User ID: {data.get('value', {}).get('userId')}")

    # RPC helper
    req_id = 0
    def rpc(method, params=None):
        nonlocal req_id
        req_id += 1
        ws.send(json.dumps({
            "id": req_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }))
        return json.loads(ws.recv())

    # Test methods
    print("\n" + "="*50)

    # Try different getChats versions and params
    for method in ["avito.getChats.v5", "avito.getChats.v4", "avito.getChats.v3"]:
        print(f"\n[*] {method}...")
        chats = rpc(method, {"limit": 20, "filters": {"excludeTags": ["p","s"]}})
        if "result" in chats:
            chat_list = chats["result"].get("chats", [])
            print(f"[+] SUCCESS! {len(chat_list)} chats")
            for i, c in enumerate(chat_list[:3]):
                print(f"    {i+1}. {c.get('user',{}).get('name','?')} - {c.get('channelId','')[:25]}...")
            break
        else:
            print(f"    {chats.get('error',{}).get('message','?')}")

    # Also try quickReplies
    print("\n[*] Quick replies...")
    qr = rpc("messenger.quickReplies.v1", {})
    print(f"    Result: {qr.get('result', qr.get('error',{}))}")

    # Unread count
    print("\n" + "="*50)
    unread = rpc("messenger.getUnreadCount.v1", {})
    print(f"[*] Unread: {unread.get('result', {}).get('unreadChats', 'error')}")

    ws.close()
    print("\n[+] Done!")


if __name__ == "__main__":
    test()
