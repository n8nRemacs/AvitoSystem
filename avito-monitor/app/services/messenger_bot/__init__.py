"""V2 reliability — messenger-bot service.

Long-lived service that holds an SSE connection to xapi, listens for
``new_message`` push events, and sends a single template reply to the very
first inbound message in a brand-new chat. Idempotent across restarts via the
``chat_dialog_state`` table, rate-limited via DB queries on
``messenger_messages``, and kill-switchable via env + ``/pause`` + ``/resume``.

Stage 6 of the V2 Messenger Reliability TZ; see
``DOCS/V2_MESSENGER_RELIABILITY_TZ.md`` §1, §2 L4 scenario G, §6 env vars.
"""
