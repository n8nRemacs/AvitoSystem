"""
Avito Messenger -> Telegram Bot Bridge
Auto-forwards all incoming Avito messages to Telegram
"""
import json
import sys
from pathlib import Path
import uuid
import time
import threading
import urllib.request
import urllib.parse

from curl_cffi import requests as curl_requests

# === CONFIGURATION ===
TELEGRAM_BOT_TOKEN = "8244492730:AAErO55dU1We-UvJOK84aKYCMWXlONgh4z4"
ADMIN_CHAT_ID = None

# === Load Avito Session ===
def load_session():
    return json.loads(Path("avito_session_new.json").read_text(encoding="utf-8"))


class AvitoClient:
    def __init__(self):
        session_data = load_session()
        self.sessid = session_data["session_token"]
        self.device_id = session_data["session_data"]["device_id"]
        self.fp = session_data["session_data"]["fingerprint"]
        self.remote_id = session_data["session_data"]["remote_device_id"]
        self.cookies = session_data["session_data"]["cookies"]
        self.user_hash = "4c48533419806d790635e8565693e5c2"
        self.user_id = 157920214

        self.session = curl_requests.Session(impersonate="chrome120")
        self.ws = None
        self.user_names = {}

    def _headers(self):
        cookie_str = f"sessid={self.sessid}"
        for k, v in self.cookies.items():
            cookie_str += f"; {k}={v}"
        return {
            "Cookie": cookie_str,
            "X-Session": self.sessid,
            "X-DeviceId": self.device_id,
            "X-RemoteDeviceId": self.remote_id,
            "f": self.fp,
            "X-App": "avito",
            "X-Platform": "android",
            "X-AppVersion": "215.1",
            "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
            "Content-Type": "application/json",
        }

    def get_channels(self, limit=30):
        resp = self.session.post(
            "https://app.avito.ru/api/1/messenger/getChannels",
            headers=self._headers(),
            json={"category": 1, "filters": {}, "limit": limit}
        )
        channels = resp.json().get("success", {}).get("channels", [])
        for ch in channels:
            for user in ch.get("users", []):
                if isinstance(user, dict):
                    uid = user.get("id", "")
                    name = user.get("name", "")
                    if uid and name:
                        self.user_names[uid] = name
        return channels

    def get_messages(self, channel_id, limit=20):
        resp = self.session.post(
            "https://app.avito.ru/api/1/messenger/getUserVisibleMessages",
            headers=self._headers(),
            json={"channelId": channel_id, "limit": limit}
        )
        return resp.json().get("success", {}).get("messages", [])

    def send_message(self, channel_id, text):
        resp = self.session.post(
            "https://app.avito.ru/api/1/messenger/sendTextMessage",
            headers=self._headers(),
            json={
                "channelId": channel_id,
                "text": text,
                "idempotencyKey": str(uuid.uuid4()),
            }
        )
        return resp.json()

    def connect_ws(self):
        ws_url = f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={self.user_hash}"
        self.ws = self.session.ws_connect(ws_url, headers=self._headers())
        init = json.loads(self.ws.recv()[0])
        print(f"[Avito] Connected! User: {init['value']['userId']}", flush=True)
        return init

    def send_ping(self):
        if self.ws:
            try:
                ping_msg = json.dumps({"id": 999, "jsonrpc": "2.0", "method": "ping", "params": {}})
                self.ws.send(ping_msg.encode())
                return True
            except:
                return False
        return False

    def get_user_name(self, user_hash):
        return self.user_names.get(user_hash, user_hash[:8] + "...")


# === Telegram ===
def send_tg(chat_id, text):
    if not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }).encode()
    try:
        urllib.request.urlopen(url, data, timeout=10)
    except Exception as e:
        print(f"[TG] send error: {e}", flush=True)


def get_tg_updates(offset):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=1"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        return json.loads(resp.read()).get("result", [])
    except:
        return []


# === Global state ===
avito = None
current_channel = None
channels_cache = []
ws_lock = threading.Lock()
last_ping = 0


def ping_thread():
    """Thread for sending ping to keep WebSocket alive"""
    global avito, last_ping

    while True:
        time.sleep(25)  # Ping every 25 seconds
        try:
            with ws_lock:
                if avito and avito.ws:
                    if avito.send_ping():
                        last_ping = time.time()
                        print("[PING] sent", flush=True)
        except Exception as e:
            print(f"[PING Error] {e}", flush=True)


def websocket_listener():
    """Thread for listening to Avito WebSocket"""
    global ADMIN_CHAT_ID, avito

    reconnect_delay = 5

    while True:
        try:
            if avito and avito.ws:
                msg = avito.ws.recv()
                if msg:
                    data = json.loads(msg[0])
                    msg_type = data.get("type", "")

                    # Skip ping responses
                    if data.get("id") == 999:
                        continue

                    if msg_type == "Message":
                        value = data.get("value", {})
                        from_uid = value.get("fromUid", "")

                        if from_uid == avito.user_hash:
                            continue

                        body = value.get("body", {})
                        txt_obj = body.get("text", {})
                        if isinstance(txt_obj, dict):
                            text = txt_obj.get("text", "")
                        else:
                            text = str(txt_obj) if txt_obj else ""

                        if not text:
                            if body.get("imageId"):
                                text = "[Image]"
                            elif body.get("voiceId"):
                                text = "[Voice]"
                            else:
                                text = "[Media]"

                        sender = avito.get_user_name(from_uid)
                        tg_msg = f"<b>{sender}</b> - {text}"

                        print(f"[MSG] {sender}: {text[:50]}", flush=True)

                        if ADMIN_CHAT_ID:
                            send_tg(ADMIN_CHAT_ID, tg_msg)

                    reconnect_delay = 5  # Reset delay on success

        except Exception as e:
            print(f"[WS Error] {e}", flush=True)
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)  # Exponential backoff
            try:
                with ws_lock:
                    avito.connect_ws()
            except Exception as e2:
                print(f"[WS Reconnect failed] {e2}", flush=True)

        time.sleep(0.1)


def telegram_handler():
    """Thread for handling Telegram commands"""
    global ADMIN_CHAT_ID, avito, current_channel, channels_cache

    tg_offset = 0
    print("[TG] Handler started", flush=True)

    while True:
        try:
            updates = get_tg_updates(tg_offset)
            if updates:
                print(f"[TG] Got {len(updates)} updates", flush=True)
            for upd in updates:
                tg_offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")

                if not chat_id or not text:
                    continue

                print(f"[TG] Got: {text}", flush=True)

                if text == "/start":
                    ADMIN_CHAT_ID = chat_id
                    send_tg(chat_id, "Avito Bridge Active!\n\nIncoming messages will appear here.\n\n/chats - list\n/select N - select\n/history - messages")
                    print(f"[TG] Admin: {chat_id}", flush=True)

                elif text == "/chats":
                    channels_cache = avito.get_channels(limit=15)
                    msg_text = "Chats:\n\n"
                    for i, ch in enumerate(channels_cache):
                        users = ch.get("users", [])
                        names = [u.get("name", "?") for u in users if isinstance(u, dict)]
                        name = names[0] if names else "?"
                        unread = ch.get("unreadCount", 0)
                        mark = f"({unread})" if unread else ""
                        msg_text += f"{i}. {name} {mark}\n"
                    send_tg(chat_id, msg_text)

                elif text.startswith("/select"):
                    try:
                        idx = int(text.split()[1])
                        if channels_cache and 0 <= idx < len(channels_cache):
                            current_channel = channels_cache[idx].get("id")
                            users = channels_cache[idx].get("users", [])
                            names = [u.get("name", "?") for u in users if isinstance(u, dict)]
                            send_tg(chat_id, f"Selected: {', '.join(names)}")
                        else:
                            send_tg(chat_id, "Use /chats first")
                    except:
                        send_tg(chat_id, "Usage: /select N")

                elif text == "/history":
                    if not current_channel:
                        send_tg(chat_id, "Use /select N first")
                    else:
                        messages = avito.get_messages(current_channel, limit=10)
                        msg_text = "History:\n\n"
                        for m in reversed(messages):
                            body = m.get("body", {})
                            txt_obj = body.get("text", {})
                            if isinstance(txt_obj, dict):
                                txt = txt_obj.get("text", "[media]")
                            else:
                                txt = str(txt_obj) if txt_obj else "[media]"
                            author = m.get("authorId", "")
                            name = avito.get_user_name(author)
                            msg_text += f"<b>{name}</b>: {txt[:60]}\n\n"
                        send_tg(chat_id, msg_text)

                elif not text.startswith("/"):
                    if not current_channel:
                        send_tg(chat_id, "Use /select N first")
                    else:
                        result = avito.send_message(current_channel, text)
                        if "success" in result:
                            send_tg(chat_id, "Sent!")
                        else:
                            send_tg(chat_id, f"Error")

        except Exception as e:
            print(f"[TG Error] {e}", flush=True)

        time.sleep(1)


def main():
    global avito

    print("[*] Starting Avito -> Telegram Bridge", flush=True)

    avito = AvitoClient()

    print("[*] Loading channels...", flush=True)
    avito.get_channels(limit=100)
    print(f"[+] Cached {len(avito.user_names)} users", flush=True)

    print("[*] Connecting WebSocket...", flush=True)
    avito.connect_ws()

    # Start threads
    ws_thread = threading.Thread(target=websocket_listener, daemon=True)
    tg_thread = threading.Thread(target=telegram_handler, daemon=True)
    ping_th = threading.Thread(target=ping_thread, daemon=True)

    ws_thread.start()
    tg_thread.start()
    ping_th.start()

    print("[*] Ready! Send /start to bot", flush=True)

    # Keep main thread alive
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
