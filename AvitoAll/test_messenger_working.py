"""Working Messenger API - with proper URL params"""
from curl_cffi import requests
import json
from pathlib import Path
import uuid
import time

def load_session():
    return json.loads(Path("avito_session_new.json").read_text())

class AvitoMessenger:
    def __init__(self):
        session_data = load_session()
        self.sessid = session_data["session_token"]
        self.device_id = session_data["session_data"]["device_id"]
        self.fp = session_data["session_data"]["fingerprint"]
        self.remote_id = session_data["session_data"]["remote_device_id"]
        self.user_hash = "4c48533419806d790635e8565693e5c2"
        self.user_id = 157920214

        self.session = requests.Session(impersonate="chrome120")
        self.ws = None
        self.request_id = 0

    def connect(self):
        ws_url = f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={self.user_hash}"

        headers = {
            "Cookie": f"sessid={self.sessid}",
            "X-Session": self.sessid,
            "X-DeviceId": self.device_id,
            "X-RemoteDeviceId": self.remote_id,
            "f": self.fp,
            "X-App": "avito",
            "X-Platform": "android",
            "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        }

        print("[*] Connecting to WebSocket...")
        self.ws = self.session.ws_connect(ws_url, headers=headers)

        # Get session init
        msg = json.loads(self.ws.recv()[0])
        print(f"[+] Connected! User: {msg['value']['userId']}, Seq: {msg['value']['seq']}")
        self.seq = msg['value']['seq']
        return True

    def send_rpc(self, method, params):
        self.request_id += 1
        req = {
            "id": self.request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        self.ws.send(json.dumps(req).encode())
        resp = json.loads(self.ws.recv()[0])
        return resp

    def get_chats(self, limit=30, include_all=True):
        """Get all chats"""
        params = {"limit": limit, "filters": {}}
        if not include_all:
            params["filters"]["excludeTags"] = ["p", "s"]
        return self.send_rpc("avito.getChats.v5", params)

    def get_history(self, channel_id, limit=50):
        """Get message history for a channel"""
        return self.send_rpc("messenger.history.v2", {
            "channelId": channel_id,
            "limit": limit
        })

    def send_message(self, channel_id, text):
        """Send text message"""
        return self.send_rpc("avito.sendTextMessage.v2", {
            "channelId": channel_id,
            "randomId": str(uuid.uuid4()),
            "text": text,
            "initActionTimestamp": int(time.time() * 1000)
        })

    def close(self):
        if self.ws:
            self.ws.close()


def main():
    messenger = AvitoMessenger()
    messenger.connect()

    # Get all chats (no filters)
    print("\n[*] Getting all chats...")
    resp = messenger.get_chats(limit=30, include_all=True)

    if "result" in resp:
        chats = resp["result"].get("chats", [])
        print(f"[+] Found {len(chats)} chats:")

        for i, chat in enumerate(chats[:10]):
            user = chat.get("user", {})
            item = chat.get("item", {})
            last_msg = chat.get("lastMessage", {})
            last_text = last_msg.get("body", {}).get("text", "")[:40]

            print(f"\n  [{i+1}] Channel: {chat.get('channelId', '')[:30]}...")
            print(f"      User: {user.get('name', '?')}")
            print(f"      Item: {item.get('title', '?')[:30]}")
            print(f"      Last: {last_text}")
            print(f"      Unread: {chat.get('unreadCount', 0)}")

        # If we have chats, test history on first one
        if chats:
            first_channel = chats[0].get("channelId")
            print(f"\n[*] Getting history for {first_channel[:30]}...")

            hist_resp = messenger.get_history(first_channel, limit=10)
            if "result" in hist_resp:
                messages = hist_resp["result"].get("messages", [])
                print(f"[+] {len(messages)} messages:")
                for msg in messages[:5]:
                    body = msg.get("body", {})
                    print(f"    - {body.get('text', body)[:50]}")
            else:
                print(f"[-] History error: {hist_resp.get('error', {}).get('message')}")

    else:
        print(f"[-] Error: {resp.get('error', {}).get('message')}")

    messenger.close()


if __name__ == "__main__":
    main()
