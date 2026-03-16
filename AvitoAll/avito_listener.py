"""
Avito Messenger Real-time Listener
Listens for incoming messages via WebSocket
"""
import websocket
import json
import time
import threading
from pathlib import Path
from datetime import datetime


def load_session():
    """Load saved session"""
    data = json.loads(Path("avito_session_final.json").read_text())
    return data["session_token"], data["session_data"]["device_id"]


class AvitoListener:
    def __init__(self):
        self.sessid, self.device_id = load_session()
        self.ws = None
        self.request_id = 0
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

        print(f"[*] Connecting to WebSocket...")
        self.ws = websocket.WebSocket()
        self.ws.connect(ws_url, header=headers)
        print("[+] Connected!")

        # Read session init
        msg = self.ws.recv()
        data = json.loads(msg)
        if data.get("type") == "session":
            self.user_id = data["value"]["userId"]
            print(f"[+] User ID: {self.user_id}")
            print(f"[+] Server time: {data['value']['serverTime']}")

    def send_rpc(self, method, params=None):
        self.request_id += 1
        msg = {
            "id": self.request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        self.ws.send(json.dumps(msg))

    def ping_loop(self):
        """Keep connection alive with pings"""
        while self.running:
            try:
                self.send_rpc("ping", {})
                time.sleep(30)
            except:
                break

    def handle_message(self, data):
        """Handle incoming WebSocket message"""
        msg_type = data.get("type") or data.get("type_v2", "")

        timestamp = datetime.now().strftime("%H:%M:%S")

        if msg_type == "session":
            return  # Already handled

        elif msg_type in ["Message", "messenger.Message"]:
            value = data.get("value", {})
            body = value.get("body", {})
            text = body.get("text", "")
            msg_type_inner = value.get("type", "unknown")
            channel_id = value.get("channelId", "")
            from_uid = value.get("fromUid", "")

            print(f"\n{'='*60}")
            print(f"[{timestamp}] NEW MESSAGE!")
            print(f"  Type: {msg_type_inner}")
            print(f"  From: {from_uid[:16]}...")
            print(f"  Channel: {channel_id}")
            print(f"  Text: {text}")
            if body.get("imageId"):
                print(f"  Image: {body['imageId']}")
            if body.get("voiceId"):
                print(f"  Voice: {body['voiceId']}")
            print(f"{'='*60}\n")

        elif msg_type == "ChatTyping":
            value = data.get("value", {})
            print(f"[{timestamp}] Typing... (channel: {value.get('channelId', '')[:20]})")

        elif msg_type == "ChatRead":
            value = data.get("value", {})
            print(f"[{timestamp}] Chat read: {value.get('channelId', '')[:20]}")

        elif "result" in data:
            # RPC response
            if data.get("result") == "pong":
                pass  # Ignore pings
            else:
                print(f"[{timestamp}] RPC Response: {json.dumps(data, ensure_ascii=False)[:200]}")

        elif "error" in data:
            print(f"[{timestamp}] Error: {data['error']}")

        else:
            print(f"[{timestamp}] Unknown: {json.dumps(data, ensure_ascii=False)[:200]}")

    def listen(self):
        """Main listening loop"""
        self.running = True

        # Start ping thread
        ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        ping_thread.start()

        print("\n" + "="*60)
        print("LISTENING FOR MESSAGES (Ctrl+C to stop)")
        print("="*60 + "\n")

        try:
            while self.running:
                try:
                    msg = self.ws.recv()
                    if msg:
                        data = json.loads(msg)
                        self.handle_message(data)
                except websocket.WebSocketConnectionClosedException:
                    print("[-] Connection closed!")
                    break
                except json.JSONDecodeError:
                    print(f"[-] Invalid JSON: {msg[:100]}")

        except KeyboardInterrupt:
            print("\n[*] Stopping...")
        finally:
            self.running = False
            self.ws.close()
            print("[+] Disconnected")


def main():
    print("="*60)
    print("Avito Messenger Listener")
    print("="*60)

    listener = AvitoListener()
    listener.connect()
    listener.listen()


if __name__ == "__main__":
    main()
