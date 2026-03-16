"""
Avito Messenger Listener v2 - Listen for real-time messages
"""
import websocket
import json
import time
import threading
from pathlib import Path
from datetime import datetime


def load_session(filename="avito_session_new.json"):
    data = json.loads(Path(filename).read_text())
    return data["session_token"], data["session_data"]["device_id"]


class AvitoListener:
    def __init__(self, session_file="avito_session_new.json"):
        self.sessid, self.device_id = load_session(session_file)
        self.ws = None
        self.req_id = 0
        self.running = False
        self.user_id = None

    def connect(self):
        ws_url = "wss://socket.avito.ru/socket?use_seq=true&app_name=android"
        headers = [
            f"Cookie: sessid={self.sessid}",
            f"X-Session: {self.sessid}",
            f"X-DeviceId: {self.device_id}",
            "X-App: avito",
            "X-Platform: android",
        ]

        print(f"[*] Connecting...")
        self.ws = websocket.WebSocket()
        self.ws.connect(ws_url, header=headers)

        # Session init
        msg = self.ws.recv()
        data = json.loads(msg)
        if data.get("type") == "session":
            self.user_id = data["value"]["userId"]
            print(f"[+] Connected! User ID: {self.user_id}")

    def rpc(self, method, params=None):
        self.req_id += 1
        self.ws.send(json.dumps({
            "id": self.req_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }))

    def ping_loop(self):
        while self.running:
            try:
                self.rpc("ping", {})
                time.sleep(25)
            except:
                break

    def handle(self, data):
        ts = datetime.now().strftime("%H:%M:%S")
        msg_type = data.get("type") or data.get("type_v2", "")

        if msg_type == "session":
            return

        elif msg_type in ["Message", "messenger.Message"]:
            v = data.get("value", {})
            body = v.get("body", {})
            text = body.get("text", "")

            print(f"\n{'='*50}")
            print(f"[{ts}] NEW MESSAGE!")
            print(f"  Type: {v.get('type', '?')}")
            print(f"  Channel: {v.get('channelId', '')}")
            print(f"  From: {v.get('fromUid', '')[:20]}...")
            print(f"  Text: {text[:100]}")
            if body.get("imageId"):
                print(f"  Image: {body['imageId']}")
            print(f"{'='*50}\n")

        elif msg_type == "ChatTyping":
            v = data.get("value", {})
            print(f"[{ts}] Typing in {v.get('channelId', '')[:20]}...")

        elif "result" in data:
            if data.get("result") == "pong":
                pass  # Ignore pings
            else:
                print(f"[{ts}] RPC: {str(data)[:100]}")

        elif "error" in data:
            print(f"[{ts}] Error: {data['error']}")

        else:
            print(f"[{ts}] Event: {str(data)[:150]}")

    def listen(self):
        self.running = True

        # Ping thread
        t = threading.Thread(target=self.ping_loop, daemon=True)
        t.start()

        print("\n" + "="*50)
        print("LISTENING FOR MESSAGES")
        print("Send a message to this account to test")
        print("Press Ctrl+C to stop")
        print("="*50 + "\n")

        try:
            while self.running:
                msg = self.ws.recv()
                if msg:
                    self.handle(json.loads(msg))
        except KeyboardInterrupt:
            print("\n[*] Stopping...")
        except Exception as e:
            print(f"[-] Error: {e}")
        finally:
            self.running = False
            self.ws.close()


def main():
    print("="*50)
    print("Avito Listener v2")
    print("="*50)

    listener = AvitoListener()
    listener.connect()
    listener.listen()


if __name__ == "__main__":
    main()
