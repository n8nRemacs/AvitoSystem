#!/bin/bash
# Simple watchdog script - restarts bot if it crashes
# Usage: ./run_forever.sh

cd "$(dirname "$0")"

while true; do
    echo "[$(date)] Starting Avito Bridge..."
    python3 avito_telegram_bot_v2.py

    EXIT_CODE=$?
    echo "[$(date)] Bot exited with code $EXIT_CODE"

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Clean exit, stopping"
        break
    fi

    echo "[$(date)] Restarting in 10 seconds..."
    sleep 10
done
