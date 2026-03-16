# Avito API - Final Documentation

## Overview

Avito has several APIs:
1. **Messenger HTTP REST API** - `https://app.avito.ru/api/1/messenger/*`
2. **Messenger WebSocket JSON-RPC** - `wss://socket.avito.ru/socket`
3. **Web API (Browser)** - `https://www.avito.ru/web/1/*` / `https://m.avito.ru/web/1/*`
4. **IP Telephony (Call Tracking)** - `https://www.avito.ru/web/1/calltracking-pro/*`

Mobile APIs require fingerprint header. Web APIs work with browser session cookie only.

---

## Authentication

### Required Headers

```
Cookie: sessid={JWT_TOKEN}; 1f_uid={uuid}; u={u_cookie}; v={timestamp}; _avisc={avisc}
X-Session: {JWT_TOKEN}
X-DeviceId: {device_uuid}
X-RemoteDeviceId: {remote_device_id}
f: {fingerprint}
X-App: avito
X-Platform: android
X-AppVersion: 215.1
User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)
Content-Type: application/json
```

### Session Data Structure

```json
{
  "session_token": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "hex_string",
  "session_data": {
    "device_id": "a8d7b75625458809",
    "fingerprint": "A2.hex_string...",
    "remote_device_id": "base64_string...",
    "user_hash": "4c48533419806d790635e8565693e5c2",
    "user_id": 157920214,
    "cookies": {
      "1f_uid": "uuid",
      "u": "string",
      "v": "timestamp",
      "_avisc": "base64"
    }
  }
}
```

### User Hash ID

- Source: Auth API response field `userHashId` or `user_hash`
- Format: 32-char hex string
- Required for: WebSocket URL parameter `my_hash_id`

### Fingerprint (f header)

- Format: `A2.{hex_data}` (~400 chars)
- Stored in SharedPreferences: `com.avito.android_preferences.xml` key `fpx`
- Also stored: `fpx_calc_time` - timestamp when fingerprint was calculated
- **Required for all API requests**
- **Cannot be generated without root access**

#### Fingerprint Generation (Reverse Engineering Analysis)

The fingerprint is generated through heavy VM-obfuscation in native code:

1. **Classes involved:**
   - `com.avito.security.libfp.FingerprintService` - main service
   - `com.avito.security.libfp.LibApplication` - VM interpreter
   - `com.avito.security.libfp.Application` - helper class

2. **Key methods:**
   - `FingerprintService.calculateFingerprint()` - main generation
   - `FingerprintService.calculateFingerprintV2(String)` - v2 generation
   - `FingerprintService.negativeRootCheck()`, `negativeEmulatorCheck()` - anti-fraud

3. **Native obfuscation:**
   - All `LibApplication.i(int, ...)` methods are NATIVE
   - Acts as VM interpreter executing obfuscated bytecode
   - JNI symbols registered dynamically via RegisterNatives
   - No `libfp.so` file in APK - code embedded in existing libraries

4. **Anti-fraud checks:**
   - `negativeDebugCheck()` - detects debugging
   - `negativeEmulatorCheck()` - detects emulators
   - `negativeRootCheck()` - detects root (can be bypassed with Magisk Hide)

5. **Data collected for fingerprint:**
   - Device hardware info (CPU, model, manufacturer)
   - System properties
   - Installed apps signatures
   - Various Android APIs responses

**Conclusion: Fingerprint generation requires root access to extract from SharedPreferences or Frida to hook the generation process. The algorithm cannot be replicated without native code analysis.**

---

## HTTP REST API

Base URL: `https://app.avito.ru`

### Get Channels (Chats)

```
POST /api/1/messenger/getChannels
```

**Request:**
```json
{
  "category": 1,
  "filters": {},
  "limit": 30,
  "offsetTimestamp": null
}
```

**Category values:**
- `0` - All (returns 500 error!)
- `1` - **Works!** Returns all channels
- `6` - Favorites only

**Response:**
```json
{
  "success": {
    "channels": [
      {
        "id": "u2i-gFdm0fc~KmiXS21tNQV_~g",
        "type": 2,
        "isRead": true,
        "unreadCount": 0,
        "users": [
          {"name": "Артём", "id": "68066a9daa4df0b3741fd41dff16e09a"},
          {"name": "РемАкс", "id": "4c48533419806d790635e8565693e5c2"}
        ],
        "lastMessage": {
          "body": {"text": {"text": "Договорились"}},
          "direction": 1,
          "type": 1
        },
        "context": {
          "item": {"title": "iPhone 12"}
        },
        "sortingTimestamp": 1768300000000
      }
    ],
    "hasMore": true
  }
}
```

**Pagination:**
```python
# First page
resp = get_channels(limit=30, offsetTimestamp=None)

# Next pages - use sortingTimestamp from last channel
last_ts = resp["success"]["channels"][-1]["sortingTimestamp"]
resp = get_channels(limit=30, offsetTimestamp=last_ts)

# Continue until hasMore=false
```

**Tested:** ~3000 channels with pagination works correctly.

---

### Get Messages

```
POST /api/1/messenger/getUserVisibleMessages
```

**Request:**
```json
{
  "channelId": "u2i-xxx",
  "limit": 50,
  "before": null,
  "after": null
}
```

**Response:**
```json
{
  "success": {
    "messages": [
      {
        "id": "12f70ec959e9ff2975f6135e9ef251a5",
        "authorId": "4c48533419806d790635e8565693e5c2",
        "body": {
          "idempotencyKey": "uuid",
          "text": {"text": "Привет!"}
        },
        "channelId": "u2i-xxx",
        "createdAt": 1768299248468329563,
        "type": "text",
        "isFirstMessage": false
      }
    ]
  }
}
```

**Important:** Message text is nested: `body.text.text`

---

### Send Text Message

```
POST /api/1/messenger/sendTextMessage
```

**Request:**
```json
{
  "channelId": "u2i-xxx",
  "text": "Hello!",
  "idempotencyKey": "uuid-v4"
}
```

**Response:**
```json
{
  "success": {
    "message": {
      "id": "message_hash",
      "authorId": "user_hash",
      "body": {"text": {"text": "Hello!"}},
      "channelId": "u2i-xxx",
      "createdAt": 1768299248468329563
    }
  }
}
```

---

### Read Chats

```
POST /api/1/messenger/readChats
```

**Request:**
```json
{
  "channelIds": ["u2i-xxx"]
}
```

---

### Get Channel by ID

```
POST /api/1/messenger/getChannelById
```

**Request:**
```json
{
  "category": 0,
  "channelId": "u2i-xxx"
}
```

---

## WebSocket JSON-RPC API

### Connection URL

**CRITICAL:** Must include `id_version=v2` and `my_hash_id` parameters!

```
wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={user_hash}
```

Without these parameters, most methods return `Forbidden (-32043)`.

### TLS Fingerprint

Use `curl_cffi` with `impersonate="chrome120"` to match browser TLS fingerprint.

```python
from curl_cffi import requests

session = requests.Session(impersonate="chrome120")
ws = session.ws_connect(ws_url, headers=headers)
```

### Session Init Response

After connect, server sends:
```json
{
  "id": 1,
  "type": "session",
  "value": {
    "userId": 157920214,
    "serverTime": 1768300000000,
    "seq": "9423"
  }
}
```

---

### JSON-RPC Methods

#### Get Chats

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "method": "avito.getChats.v5",
  "params": {
    "limit": 30,
    "filters": {}
  }
}
```

#### Get Chat by ID

```json
{
  "id": 2,
  "jsonrpc": "2.0",
  "method": "avito.getChatById.v3",
  "params": {
    "channelId": "u2i-xxx"
  }
}
```

#### Get Message History

```json
{
  "id": 3,
  "jsonrpc": "2.0",
  "method": "messenger.history.v2",
  "params": {
    "channelId": "u2i-xxx",
    "limit": 100
  }
}
```

#### Send Text Message

```json
{
  "id": 4,
  "jsonrpc": "2.0",
  "method": "avito.sendTextMessage.v2",
  "params": {
    "channelId": "u2i-xxx",
    "randomId": "uuid-v4",
    "text": "Message text",
    "initActionTimestamp": 1768300000000
  }
}
```

#### Send Typing Indicator

```json
{
  "id": 5,
  "jsonrpc": "2.0",
  "method": "messenger.sendTyping.v2",
  "params": {
    "channelId": "u2i-xxx",
    "userId": "user_hash"
  }
}
```

#### Mark Chats as Read

```json
{
  "id": 6,
  "jsonrpc": "2.0",
  "method": "messenger.readChats.v1",
  "params": {
    "channelIds": ["u2i-xxx"]
  }
}
```

#### Get Unread Count

```json
{
  "id": 7,
  "jsonrpc": "2.0",
  "method": "messenger.getUnreadCount.v1",
  "params": {}
}
```

#### Ping (Keep-alive)

```json
{
  "id": 100,
  "jsonrpc": "2.0",
  "method": "ping",
  "params": {}
}
```

---

### WebSocket Push Events (Server -> Client)

#### New Message

```json
{
  "seq": "9269",
  "id": 3,
  "type": "Message",
  "type_v2": "messenger.Message",
  "value": {
    "id": "8550e1ed03edab7afdd44d657b7f1c13",
    "body": {
      "randomId": "uuid",
      "text": "Текст сообщения"
    },
    "channelId": "u2i-xxx",
    "type": "text",
    "created": 1768300000000,
    "fromUid": "sender_hash",
    "uid": "receiver_hash"
  }
}
```

**Note:** In push events, text is directly in `body.text` (not nested like HTTP API)

#### Typing Indicator

```json
{
  "id": 2,
  "type": "ChatTyping",
  "value": {
    "channelId": "u2i-xxx",
    "fromUid": "user_hash"
  }
}
```

#### Chat Read

```json
{
  "type": "ChatRead",
  "value": {
    "channelId": "u2i-xxx"
  }
}
```

---

## IP Telephony (Call Tracking) API

Base URL: `https://www.avito.ru`

**Authentication:** Only requires `sessid` cookie from browser session. No fingerprint needed.

### Get Call History

```
POST /web/1/calltracking-pro/history
```

**Request:**
```json
{
  "dateFrom": "2025-01-01",
  "dateTo": "2026-01-13",
  "limit": 20,
  "offset": 0,
  "sortingField": "createTime",
  "sortingDirection": "desc",
  "newOrRepeated": "all",
  "receivedOrMissed": "all",
  "showSpam": true,
  "itemFilters": {}
}
```

**Response:**
```json
{
  "result": {
    "items": [
      {
        "id": 1108478743,
        "caller": "+7 927 576-67-88",
        "receiver": "+7 917 170-80-77",
        "duration": "0:42",
        "waitingTime": "0:05",
        "hasRecord": true,
        "isNew": false,
        "isSpamTagged": false,
        "isCallback": false,
        "createTime": "2026-01-13T13:06:26+03:00",
        "item": {
          "id": 123456,
          "title": "iPhone 12"
        }
      }
    ],
    "total": 150
  },
  "status": "success"
}
```

**Pagination:**
```python
# First page
resp = get_call_history(limit=50, offset=0)

# Next pages
offset += 50
resp = get_call_history(limit=50, offset=offset)

# Continue until offset >= total
```

---

### Download Call Recording

```
GET /web/1/calltracking-pro/audio?historyId={call_id}
```

**Parameters:**
- `historyId` - ID звонка из истории (поле `id`)

**Response:** Audio file (MP3)

**Example:**
```python
import requests

session = requests.Session()
session.cookies.set('sessid', 'YOUR_SESSID')

# Download recording
resp = session.get(
    'https://www.avito.ru/web/1/calltracking-pro/audio',
    params={'historyId': '1108478743'}
)

with open('call.mp3', 'wb') as f:
    f.write(resp.content)
```

---

### Call History Fields

| Field | Description |
|-------|-------------|
| `id` | Уникальный ID звонка (для скачивания записи) |
| `caller` | Номер звонившего |
| `receiver` | Номер принявшего (ваш виртуальный номер) |
| `duration` | Длительность разговора "M:SS" |
| `waitingTime` | Время ожидания ответа |
| `hasRecord` | Есть ли запись звонка |
| `isNew` | Новый/первичный звонок |
| `isSpamTagged` | Помечен как спам |
| `isCallback` | Обратный звонок |
| `createTime` | Время звонка (ISO 8601) |
| `item` | Связанное объявление |

---

## Error Codes

| Code | Message | Cause |
|------|---------|-------|
| -32043 | Forbidden | Missing `id_version=v2` or `my_hash_id` in WebSocket URL |
| -32601 | Method not found | Invalid method name/version |
| 500 | Internal error | Invalid category (0) in HTTP API |
| 401 | Unauthorized | Session expired, need new sessid |

---

## Working Python Client

```python
from curl_cffi import requests as curl_requests
import json
import uuid
import time
from pathlib import Path

class AvitoMessenger:
    def __init__(self, session_file="avito_session.json"):
        data = json.loads(Path(session_file).read_text(encoding="utf-8"))
        self.sessid = data["session_token"]
        self.device_id = data["session_data"]["device_id"]
        self.fp = data["session_data"]["fingerprint"]
        self.remote_id = data["session_data"]["remote_device_id"]
        self.cookies = data["session_data"]["cookies"]
        self.user_hash = data["session_data"]["user_hash"]

        self.session = curl_requests.Session(impersonate="chrome120")
        self.ws = None

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

    # HTTP API
    def get_channels(self, limit=30, offset=None):
        resp = self.session.post(
            "https://app.avito.ru/api/1/messenger/getChannels",
            headers=self._headers(),
            json={"category": 1, "filters": {}, "limit": limit, "offsetTimestamp": offset}
        )
        return resp.json().get("success", {}).get("channels", [])

    def get_messages(self, channel_id, limit=50):
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
            json={"channelId": channel_id, "text": text, "idempotencyKey": str(uuid.uuid4())}
        )
        return resp.json()

    # WebSocket
    def connect_ws(self):
        url = f"wss://socket.avito.ru/socket?use_seq=true&app_name=android&id_version=v2&my_hash_id={self.user_hash}"
        self.ws = self.session.ws_connect(url, headers=self._headers())
        return json.loads(self.ws.recv()[0])

    def recv_ws(self):
        try:
            msg = self.ws.recv()
            return json.loads(msg[0]) if msg else None
        except:
            return None
```

---

## Data Extraction (Root Required)

### Fingerprint
```bash
# From SharedPreferences (requires root)
adb shell "su -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml'" | grep fpx

# Example output:
# <string name="fpx">A2.a541fb18def1032c46e8ce9356bf78870fa9c764...</string>
# <long name="fpx_calc_time" value="1768297821046" />
```

### Session Token
```bash
# Get JWT session token
adb shell "su -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml'" | grep session
```

### All Required Data
```bash
# Complete data extraction script
adb shell "su -c 'cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml'" > avito_prefs.xml

# Parse and extract:
# - fpx (fingerprint)
# - session (JWT token)
# - device_id, user_id, etc.
```

### Device Info (for antifraud.xml)
```bash
adb shell "su -c 'cat /data/data/com.avito.android/shared_prefs/antifraud.xml'"

# Contains: cpuInfo, deviceManufacturer, deviceModel, isEmulator, isRoot
```

---

## Important Notes

1. **WebSocket URL params are critical** - Without `id_version=v2` and `my_hash_id`, methods return Forbidden.

2. **HTTP category=1 works** - Category 0 returns 500, category 1 returns all channels.

3. **TLS fingerprint matters** - Use curl_cffi with chrome120 impersonation.

4. **Fingerprint header `f`** - Generated by native `libfp.so`, required for all requests. **Cannot be generated without root.**

5. **Session expires in 24h** - Use refresh_token to get new session.

6. **Channel ID format** - Always `u2i-{base64_encoded_id}`.

7. **Message text location differs:**
   - HTTP API: `body.text.text`
   - WebSocket push: `body.text`

8. **Pagination** - Use `sortingTimestamp` from last channel as `offsetTimestamp`.

---

## Files

- `avito_session_new.json` - Current session data (for mobile API)
- `avito_telegram_bot.py` - Working Telegram bridge bot (real-time messages)
- `avito_user_client.py` - Full client for Messenger + IP Telephony (browser session)
- `API_AUTH.md` - Auth flow documentation
- `API_MESSENGER.md` - Original messenger API notes

---

## Quick Start

### Mobile API (requires root for fingerprint)
```python
from avito_telegram_bot import AvitoClient
client = AvitoClient()  # loads avito_session_new.json
channels = client.get_channels()
```

### Web API (browser session only)
```bash
# Export chats
python avito_user_client.py --sessid "YOUR_SESSID" chats

# Export calls with recordings
python avito_user_client.py --sessid "YOUR_SESSID" calls

# Download single recording
python avito_user_client.py --sessid "YOUR_SESSID" download-call 1108478743
```

Get `sessid` from browser: F12 → Application → Cookies → `sessid`
