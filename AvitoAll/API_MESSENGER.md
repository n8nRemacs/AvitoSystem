# Avito Messenger API Documentation

## Overview

Avito Messenger uses **JSON-RPC over WebSocket** for real-time messaging.

## Authentication

### Headers
- `Cookie: sessid={session_token}` **OR** `X-Session: {session_token}`
- `Origin: https://www.avito.ru`
- `X-Request-Id: {uuid}`
- `X-DeviceId: {device_id}`
- `X-App: avito`
- `User-Agent: AVITO 215.1 (OnePlus LE2115; Android 14; ru)`

### WebSocket Query Params
- `seq={sequence_id}` - sequence number
- `id_version=v2`
- `my_hash_id={user_hash_id}` - user identifier

## HTTP API Endpoints (app.avito.ru)

### Messenger API (POST /api/1/messenger/*)

#### Get Channels
```
POST /api/1/messenger/getChannels
Content-Type: application/json

{
    "category": 0,  // 0=all, 1=unread, 6=favorites
    "filters": {},
    "limit": 20,
    "offsetTimestamp": null
}
```

#### Get Channel by ID
```
POST /api/1/messenger/getChannelById
Content-Type: application/json

{
    "category": 0,
    "channelId": "u2i-xxx"
}
```

#### Send Text Message
```
POST /api/1/messenger/sendTextMessage
Content-Type: application/json

{
    "channelId": "u2i-xxx",
    "text": "Hello!",
    "idempotencyKey": "uuid-v4",
    "chunkIndex": null,
    "quoteMessageId": null,
    "source": null,
    "xHash": null
}
```

#### Get Messages
```
POST /api/1/messenger/getUserVisibleMessages
Content-Type: application/json

{
    "channelId": "u2i-xxx",
    "limit": 50,
    "before": null,
    "after": null
}
```

#### Read Chats
```
POST /api/1/messenger/readChats
Content-Type: application/json

{
    "channelIds": ["u2i-xxx"]
}
```

## WebSocket JSON-RPC API

### Connection
```
wss://socket.avito.ru/...?seq={seq}&id_version=v2&my_hash_id={hash}
```

### Message Format
```json
{
    "jsonrpc": "2.0",
    "method": "method.name",
    "params": {...},
    "id": "request-id"
}
```

### Methods

#### avito.sendTextMessage.v2
Send a text message to a channel.
```json
{
    "method": "avito.sendTextMessage.v2",
    "params": {
        "channelId": "u2i-xxx",
        "randomId": "uuid",
        "text": "Message text",
        "templates": [],
        "quoteMessageId": null,
        "chunkIndex": null,
        "xHash": null,
        "initActionTimestamp": null
    }
}
```

#### avito.getChats.v5
Get list of chat channels.
```json
{
    "method": "avito.getChats.v5",
    "params": {
        "offsetTimestamp": null,
        "limit": 20,
        "filters": {}
    }
}
```

#### avito.getChatById.v3
Get specific chat by ID.
```json
{
    "method": "avito.getChatById.v3",
    "params": {
        "channelId": "u2i-xxx"
    }
}
```

#### messenger.history.v2
Get message history.
```json
{
    "method": "messenger.history.v2",
    "params": {
        "channelId": "u2i-xxx",
        "limit": 50,
        "before": null,
        "after": null
    }
}
```

#### avito.chatCreateByItemId.v2
Create a chat for an item/listing.
```json
{
    "method": "avito.chatCreateByItemId.v2",
    "params": {
        "itemId": "123456789",
        "source": null,
        "extra": null,
        "xHash": null
    }
}
```

#### messenger.chatCreateByUserId.v2
Create chat with specific user.
```json
{
    "method": "messenger.chatCreateByUserId.v2",
    "params": {
        "opponentId": "user_hash"
    }
}
```

#### messenger.sendTyping.v2
Send typing indicator.
```json
{
    "method": "messenger.sendTyping.v2",
    "params": {
        "channelId": "u2i-xxx",
        "userIds": ["user_hash"],
        "initActionTimestamp": null
    }
}
```

#### messenger.readChat
Mark channel as read.
```json
{
    "method": "messenger.readChat",
    "params": {
        "channelId": "u2i-xxx",
        "lastMessageTime": 1704067200000
    }
}
```

#### messenger.getUsers.v2
Get user information.
```json
{
    "method": "messenger.getUsers.v2",
    "params": {
        "channelId": "u2i-xxx",
        "userIds": ["user_hash1", "user_hash2"]
    }
}
```

#### ping
Keep-alive.
```json
{
    "method": "ping",
    "params": {}
}
```

### Media Messages

#### avito.sendImageMessage.v2
```json
{
    "method": "avito.sendImageMessage.v2",
    "params": {
        "channelId": "u2i-xxx",
        "randomId": "uuid",
        "imageId": "image_id",
        "quoteMessageId": null,
        "chunkIndex": null
    }
}
```

#### messenger.sendVoice
```json
{
    "method": "messenger.sendVoice",
    "params": {
        "channelId": "u2i-xxx",
        "fileId": "file_id",
        "voiceId": "voice_id",
        "randomId": "uuid",
        "quoteMessageId": null,
        "chunkIndex": null
    }
}
```

#### messenger.sendVideo.v2
```json
{
    "method": "messenger.sendVideo.v2",
    "params": {
        "channelId": "u2i-xxx",
        "fileId": "file_id",
        "videoId": "video_id",
        "randomId": "uuid",
        "quoteMessageId": null,
        "chunkIndex": null
    }
}
```

## Response Format

### Success
```json
{
    "jsonrpc": "2.0",
    "result": {...},
    "id": "request-id"
}
```

### Error
```json
{
    "jsonrpc": "2.0",
    "error": {
        "code": -32600,
        "message": "Error description"
    },
    "id": "request-id"
}
```

## Data Types

### Channel ID Format
- `u2i-{hash}` - user-to-item chat
- Format varies based on chat type

### Message Structure
```json
{
    "id": "message_id",
    "channelId": "u2i-xxx",
    "author": {
        "id": "user_hash",
        "name": "Username"
    },
    "created": 1704067200,
    "body": {
        "type": "text",
        "text": "Message content"
    },
    "status": "sent|delivered|read"
}
```

## Notes

1. All timestamps are in milliseconds (Unix epoch)
2. `randomId` should be UUID v4 for deduplication
3. `chunkIndex` is used for message ordering in chunks
4. `xHash` is optional hash for some operations
5. WebSocket connection requires valid session cookie
