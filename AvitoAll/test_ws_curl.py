"""Test WebSocket with curl_cffi (same TLS fingerprint as HTTP)"""
from curl_cffi import requests
import json
from pathlib import Path

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

def main():
    session = load_session()
    sessid = session["session_token"]
    device_id = session["session_data"]["device_id"]
    fp = session["session_data"]["fingerprint"]
    remote_id = session["session_data"]["remote_device_id"]

    print("[*] Using curl_cffi WebSocket with chrome120 impersonation")

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

    print(f"[*] Connecting to {ws_url[:60]}...")

    try:
        # Use curl_cffi WebSocket with impersonation
        with requests.WebSocket(ws_url, headers=headers, impersonate="chrome120") as ws:
            # Receive session init
            msg = ws.recv()[0]
            data = json.loads(msg)
            print(f"[+] Connected! User: {data.get('value', {}).get('userId')}")

            # Test getChats
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
                print(f"\n[+] SUCCESS! Found {len(chats)} chats:")
                for c in chats[:5]:
                    user = c.get("user", {})
                    print(f"    - {user.get('name', '?')}: {c.get('channelId', '')[:25]}...")
            else:
                print(f"\n[-] Error: {resp.get('error', {}).get('message', resp)}")

    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
