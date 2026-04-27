"""Telegram long-polling daemon (Block 5).

Run with ``python -m app.integrations.telegram``. The daemon owns its
own ``aiogram.Bot`` — separate from the one ``MessengerProvider`` uses
for outbound delivery — so command handling and notification sending
never block each other on the same connection pool.
"""
