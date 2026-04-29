#!/system/bin/sh
# refresh.sh — Refresh Avito token for a specific Android profile.
#
# Usage: ./refresh.sh <profile_id>
#
# Steps:
#   1. Start Avito in the given user profile
#   2. Optionally inject spoof_fingerprint.js via Frida
#   3. Wait for Avito to auto-refresh the token
#   4. Run grab_token.js to extract the new token
#   5. Force-stop Avito
#
# The extracted token is printed to stdout as TOKEN_DATA|{json}
# The agent.py daemon calls this script and parses the output.

set -e

PROFILE_ID="${1}"
if [ -z "$PROFILE_ID" ]; then
    echo "Usage: $0 <profile_id>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AVITO_PACKAGE="com.avito.android"
AVITO_ACTIVITY="${AVITO_PACKAGE}/${AVITO_PACKAGE}.DeeplinkActivity"
WAIT_SECONDS="${AVITO_WAIT:-90}"
GRAB_SCRIPT="${SCRIPT_DIR}/grab_token.js"
SPOOF_SCRIPT="${SCRIPT_DIR}/spoof_fingerprint.js"
SPOOF_CONFIG="/data/local/tmp/farm_profiles/${PROFILE_ID}.json"

echo "[$(date)] Starting refresh for profile ${PROFILE_ID}"

# Step 1: Start Avito with optional fingerprint spoofing
if [ -f "$SPOOF_CONFIG" ] && [ -f "$SPOOF_SCRIPT" ]; then
    echo "[1/5] Launching Avito with fingerprint spoofing..."
    # Spawn with Frida to inject spoof at startup
    frida -U -f "$AVITO_PACKAGE" \
        --aux="uid=${PROFILE_ID}" \
        -l "$SPOOF_SCRIPT" \
        --no-pause -q &
    FRIDA_PID=$!
    sleep 5
else
    echo "[1/5] Launching Avito (no spoof config)..."
    am start --user "$PROFILE_ID" -n "$AVITO_ACTIVITY" 2>/dev/null || true
fi

# Step 2: Wait for token refresh
echo "[2/5] Waiting ${WAIT_SECONDS}s for Avito to refresh token..."
sleep "$WAIT_SECONDS"

# Step 3: Grab token
echo "[3/5] Extracting token via Frida..."
TOKEN_OUTPUT=$(frida -U \
    --attach-name "$AVITO_PACKAGE" \
    -l "$GRAB_SCRIPT" \
    --no-pause -q \
    2>/dev/null || echo "")

# Step 4: Force-stop Avito
echo "[4/5] Stopping Avito..."
am force-stop --user "$PROFILE_ID" "$AVITO_PACKAGE" 2>/dev/null || true

# Kill spoof Frida if running
if [ -n "$FRIDA_PID" ]; then
    kill "$FRIDA_PID" 2>/dev/null || true
fi

# Step 5: Output token
echo "[5/5] Done."
echo "$TOKEN_OUTPUT" | grep "^TOKEN_DATA|" || echo "TOKEN_DATA|{\"error\":\"no_token_found\"}"

echo "[$(date)] Refresh complete for profile ${PROFILE_ID}"
