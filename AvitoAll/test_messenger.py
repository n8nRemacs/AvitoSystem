"""
Quick Messenger API Test
"""
import websocket
import json
import time
from pathlib import Path


def load_session():
    """Load saved session"""
    data = json.loads(Path("avito_session_final.json").read_text())
    return data["session_token"], data["session_data"]["device_id"]


def test_messenger():
    sessid, device_id = load_session()
    print(f"[*] Session token: {sessid[:50]}...")
    print(f"[*] Device ID: {device_id}")

    # WebSocket connection
    ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"

    headers = [
        f"Cookie: sessid={sessid}",
        f"X-Session: {sessid}",
        f"X-DeviceId: {device_id}",
        "X-App: avito",
        "X-Platform: android",
    ]

    print(f"\n[*] Connecting to {ws_url}")

    ws = websocket.WebSocket()
    ws.connect(ws_url, header=headers)

    print("[+] Connected!")

    # Read session init
    msg = ws.recv()
    print(f"\n[SESSION] {msg}")

    session_data = json.loads(msg)
    if session_data.get("type") == "session":
        print(f"[+] User ID: {session_data['value']['userId']}")
        print(f"[+] Server time: {session_data['value']['serverTime']}")

    # Get chats
    request_id = 1

    def send_rpc(method, params=None):
        nonlocal request_id
        request_id += 1
        msg = {
            "id": request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        ws.send(json.dumps(msg))
        return json.loads(ws.recv())

    print("\n" + "="*60)
    print("[*] Getting chats...")

    # Try different API versions and params
    chats_response = None
    for method in ["avito.getChats.v5", "avito.getChats.v4", "messenger.getChats"]:
        print(f"[*] Trying {method}...")
        resp = send_rpc(method, {
            "limit": 10,
            "filters": {"excludeTags": ["p", "s"]}
        })
        if "result" in resp:
            chats_response = resp
            print(f"[+] Success with {method}")
            break
        else:
            print(f"    Error: {resp.get('error', {}).get('message', resp)}")

    if chats_response and "result" in chats_response:
        chats = chats_response["result"].get("chats", [])
        print(f"\n[+] Found {len(chats)} chats:\n")

        for i, chat in enumerate(chats[:5]):
            channel_id = chat.get("channelId", "")
            user = chat.get("user", {})
            last_msg = chat.get("lastMessage", {})

            print(f"  {i+1}. {user.get('name', 'Unknown')}")
            print(f"     Channel: {channel_id}")
            print(f"     Last: {last_msg.get('body', {}).get('text', '[no text]')[:50]}")
            print()
    else:
        print(f"[-] All methods failed")

    # Get unread count
    print("="*60)
    print("[*] Getting unread count...")

    unread = send_rpc("messenger.getUnreadCount.v1", {})
    print(f"[+] Unread: {unread}")

    # Try settings
    print("\n[*] Getting messenger settings...")
    settings = send_rpc("messenger.getSettings.v2", {"fields": []})
    print(f"[+] Settings: {json.dumps(settings, indent=2, ensure_ascii=False)[:500]}")

    # Try ping
    print("\n[*] Ping...")
    ping = send_rpc("ping", {})
    print(f"[+] Ping: {ping}")

    # Try quick replies
    print("\n[*] Quick replies...")
    qr = send_rpc("messenger.quickReplies.v1", {})
    print(f"[+] Quick replies: {json.dumps(qr, indent=2, ensure_ascii=False)[:300]}")

    ws.close()
    print("\n[+] Test complete!")


if __name__ == "__main__":
    test_messenger()
