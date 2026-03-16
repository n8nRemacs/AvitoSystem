"""Test WebSocket with curl_cffi Session.ws_connect"""
from curl_cffi import requests
import json
from pathlib import Path

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def main():
    session_data = load_session()
    sessid = session_data["session_token"]
    device_id = session_data["session_data"]["device_id"]
    fp = session_data["session_data"]["fingerprint"]
    remote_id = session_data["session_data"]["remote_device_id"]

    print("[*] Using curl_cffi Session.ws_connect with chrome120")

    # Create session with impersonation
    session = requests.Session(impersonate="chrome120")

    ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"

    headers = {
        "Cookie": f"sessid={sessid}",
        "X-Session": sessid,
        "X-DeviceId": device_id,
        "X-RemoteDeviceId": remote_id,
        "f": fp,
        "X-App": "avito",
        "X-Platform": "android",
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
    }

    print(f"[*] Connecting...")

    try:
        ws = session.ws_connect(ws_url, headers=headers)

        # Receive session init
        msg = ws.recv()[0]
        data = json.loads(msg)
        print(f"[+] Connected! User: {data.get('value', {}).get('userId')}")
        print(f"    Seq: {data.get('value', {}).get('seq')}")

        # Test getChats
        print("\n[*] Testing getChats...")
        req = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "avito.getChats.v5",
            "params": {"limit": 10, "filters": {"excludeTags": ["p", "s"]}}
        }
        ws.send(json.dumps(req).encode())

        resp_data = ws.recv()[0]
        resp = json.loads(resp_data)

        if "result" in resp:
            chats = resp["result"].get("chats", [])
            print(f"[+] SUCCESS! Found {len(chats)} chats:")
            for c in chats[:5]:
                user = c.get("user", {})
                last = c.get("lastMessage", {}).get("body", {}).get("text", "")[:30]
                print(f"    - {user.get('name', '?')}: {last}")
        else:
            print(f"[-] Error: {resp.get('error', {}).get('message', resp)}")

        ws.close()

    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
