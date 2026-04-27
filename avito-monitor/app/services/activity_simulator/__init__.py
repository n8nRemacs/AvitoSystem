"""V2 Messenger Reliability — activity simulator service.

Fakes human-ish reading of the Avito mobile app: GET chats, peek at unread,
occasionally open a chat and mark it read. Keeps the WS-using xapi session
warm and the account looking actively used. Never sends outgoing text.

See ``DOCS/V2_MESSENGER_RELIABILITY_TZ.md`` §2 (L3) and §6.
"""
