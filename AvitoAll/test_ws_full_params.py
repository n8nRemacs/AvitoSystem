"""Test WebSocket with full URL parameters (my_hash_id, id_version, seq)"""
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

    # user_hash from old session file
    user_hash = "4c48533419806d790635e8565693e5c2"

    print("[*] Testing WebSocket with full URL params")

    session = requests.Session(impersonate="chrome120")

    # Different URL variants to test
    urls = [
        ("Basic", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android"),
        ("With hash", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&my_hash_id={user_hash}"),
        ("With version", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}"),
        ("Full", f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&seq=0&id_version=v2&my_hash_id={user_hash}"),
    ]

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

    for name, ws_url in urls:
        print(f"\n[*] Testing: {name}")
        print(f"    URL params: {ws_url.split('?')[1][:60]}...")

        try:
            ws = session.ws_connect(ws_url, headers=headers)

            # Get session init
            msg = ws.recv()[0]
            data = json.loads(msg)
            print(f"    Connected! User: {data.get('value', {}).get('userId')}")
            seq = data.get('value', {}).get('seq')
            print(f"    Seq: {seq}")

            # Test getChats
            ws.send(json.dumps({
                "id": 1,
                "jsonrpc": "2.0",
                "method": "avito.getChats.v5",
                "params": {"limit": 10, "filters": {"excludeTags": ["p", "s"]}}
            }).encode())

            resp = json.loads(ws.recv()[0])
            if "result" in resp:
                chats = resp["result"].get("chats", [])
                print(f"    getChats: SUCCESS! {len(chats)} chats")
                for c in chats[:3]:
                    user = c.get("user", {})
                    print(f"      - {user.get('name', '?')}")
                ws.close()
                return True
            else:
                err = resp.get('error', {})
                print(f"    getChats: {err.get('message')} ({err.get('code')})")

            ws.close()
        except Exception as e:
            print(f"    Error: {e}")

    return False


if __name__ == "__main__":
    main()
