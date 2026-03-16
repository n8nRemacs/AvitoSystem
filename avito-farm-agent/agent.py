#!/usr/bin/env python3
"""
Farm Agent — daemon running on a rooted Android device.

Responsibilities:
  1. Heartbeat → POST /farm/heartbeat every N seconds
  2. Poll schedule → GET /farm/schedule
  3. Refresh tokens → launch Avito per-profile, Frida grab, POST /farm/tokens
  4. Spoof fingerprint → Frida injects per-profile device identity

Runs as root on the Android device (via adb shell or Termux + root).
"""

import json
import logging
import os
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────

CONFIG_PATH = os.environ.get("FARM_CONFIG", os.path.join(os.path.dirname(__file__), "config.json"))

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

DEVICE_NAME = CONFIG["device_name"]
XAPI_URL = CONFIG["xapi_url"].rstrip("/")
API_KEY = CONFIG["api_key"]
HEARTBEAT_INTERVAL = CONFIG.get("heartbeat_interval_sec", 300)
SCHEDULE_POLL_INTERVAL = CONFIG.get("schedule_poll_interval_sec", 300)
REFRESH_LEAD_TIME = CONFIG.get("refresh_lead_time_sec", 60)
AVITO_WAIT = CONFIG.get("avito_launch_wait_sec", 90)
AVITO_PACKAGE = CONFIG.get("avito_package", "com.avito.android")
FRIDA_SCRIPT = CONFIG.get("frida_script", "grab_token.js")
SPOOF_SCRIPT = CONFIG.get("spoof_script", "spoof_fingerprint.js")

HEADERS = {
    "X-Api-Key": API_KEY,
    "Content-Type": "application/json",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

log_file = CONFIG.get("log_file")
if log_file:
    logging.getLogger().addHandler(logging.FileHandler(log_file))

logger = logging.getLogger("farm-agent")


# ── API helpers ───────────────────────────────────────

def api_post(path: str, data: dict) -> dict | None:
    """POST to X-API, return JSON or None on error."""
    try:
        resp = requests.post(f"{XAPI_URL}{path}", json=data, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("API POST %s failed: %s", path, e)
        return None


def api_get(path: str) -> dict | None:
    """GET from X-API, return JSON or None on error."""
    try:
        resp = requests.get(f"{XAPI_URL}{path}", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("API GET %s failed: %s", path, e)
        return None


# ── Heartbeat ─────────────────────────────────────────

def send_heartbeat():
    """Send heartbeat to X-API."""
    result = api_post("/farm/heartbeat", {"device_id": DEVICE_NAME})
    if result:
        logger.info("Heartbeat sent OK")
    else:
        logger.warning("Heartbeat failed")


def heartbeat_loop():
    """Background loop: heartbeat every N seconds."""
    while True:
        send_heartbeat()
        time.sleep(HEARTBEAT_INTERVAL)


# ── Schedule polling ──────────────────────────────────

def get_schedule() -> list[dict]:
    """Fetch refresh schedule from X-API."""
    data = api_get("/farm/schedule")
    if data and "schedule" in data:
        return data["schedule"]
    return []


def needs_refresh(item: dict) -> bool:
    """Check if a binding needs token refresh based on TTL."""
    ttl = item.get("ttl_seconds")
    if ttl is None:
        return False
    # Refresh if TTL is less than lead time (default 60 seconds)
    return ttl <= REFRESH_LEAD_TIME


# ── Token refresh (core logic) ────────────────────────

def refresh_profile(profile_id: int, binding_id: str) -> bool:
    """Refresh token for a single Android profile.

    Steps:
      1. Launch Avito in the user profile (am start --user)
      2. Wait for Avito to auto-refresh token (~90 seconds)
      3. Run Frida to grab the new token from SharedPreferences
      4. Force-stop Avito in the profile
      5. POST the new token to X-API

    Returns True on success, False on failure.
    """
    logger.info("Refreshing profile %d (binding %s)", profile_id, binding_id)

    try:
        # Step 1: Launch Avito
        logger.info("  [1/4] Launching %s --user %d", AVITO_PACKAGE, profile_id)
        subprocess.run(
            ["am", "start", "--user", str(profile_id),
             "-n", f"{AVITO_PACKAGE}/{AVITO_PACKAGE}.DeeplinkActivity"],
            check=True, capture_output=True, timeout=30,
        )

        # Step 2: Wait for token refresh
        logger.info("  [2/4] Waiting %d seconds for Avito to refresh token...", AVITO_WAIT)
        time.sleep(AVITO_WAIT)

        # Step 3: Grab token via Frida
        logger.info("  [3/4] Running Frida to grab token...")
        token_data = grab_token_frida(profile_id)

        if not token_data or not token_data.get("session_token"):
            logger.error("  Failed: Frida could not extract token for profile %d", profile_id)
            return False

        # Step 4: Force-stop Avito
        logger.info("  [4/4] Stopping Avito in profile %d", profile_id)
        subprocess.run(
            ["am", "force-stop", "--user", str(profile_id), AVITO_PACKAGE],
            capture_output=True, timeout=15,
        )

        # Step 5: Upload to X-API
        result = api_post("/farm/tokens", {
            "device_id": DEVICE_NAME,
            "android_profile_id": profile_id,
            "session_token": token_data["session_token"],
            "refresh_token": token_data.get("refresh_token"),
            "fingerprint": token_data.get("fingerprint"),
            "cookies": token_data.get("cookies"),
        })

        if result and result.get("status") == "ok":
            logger.info("  Token uploaded for profile %d → tenant %s, user %s",
                        profile_id, result.get("tenant_id"), result.get("user_id"))
            return True
        else:
            logger.error("  Token upload failed for profile %d", profile_id)
            return False

    except subprocess.TimeoutExpired:
        logger.error("  Timeout during refresh for profile %d", profile_id)
        return False
    except Exception as e:
        logger.error("  Refresh failed for profile %d: %s", profile_id, e)
        return False


def grab_token_frida(profile_id: int) -> dict | None:
    """Run Frida grab_token.js against Avito in a user profile.

    Returns dict with session_token, refresh_token, fingerprint, cookies
    or None on failure.
    """
    script_path = os.path.join(os.path.dirname(__file__), FRIDA_SCRIPT)
    if not os.path.exists(script_path):
        logger.error("Frida script not found: %s", script_path)
        return None

    try:
        # Use frida CLI to attach to Avito in the specific user profile
        # The grab_token.js script outputs JSON to stdout
        result = subprocess.run(
            ["frida", "-U",
             "--attach-name", AVITO_PACKAGE,
             "-l", script_path,
             "--no-pause",
             "-q"],  # quiet mode
            capture_output=True, text=True, timeout=30,
        )

        # Parse output for TOKEN_DATA| prefix
        for line in result.stdout.splitlines():
            if line.startswith("TOKEN_DATA|"):
                json_str = line[len("TOKEN_DATA|"):]
                return json.loads(json_str)

        logger.warning("No TOKEN_DATA found in Frida output for profile %d", profile_id)
        return None

    except subprocess.TimeoutExpired:
        logger.error("Frida timed out for profile %d", profile_id)
        return None
    except Exception as e:
        logger.error("Frida failed for profile %d: %s", profile_id, e)
        return None


# ── Schedule loop ─────────────────────────────────────

def schedule_loop():
    """Main loop: poll schedule, refresh tokens as needed."""
    while True:
        try:
            schedule = get_schedule()
            logger.info("Schedule: %d bindings", len(schedule))

            for item in schedule:
                if needs_refresh(item):
                    profile_id = item.get("android_profile_id")
                    binding_id = item.get("binding_id", "unknown")
                    ttl = item.get("ttl_seconds", 0)
                    logger.info("Profile %d needs refresh (TTL=%d sec)", profile_id, ttl)
                    refresh_profile(profile_id, binding_id)
                    # Small delay between refreshes
                    time.sleep(5)

        except Exception as e:
            logger.error("Schedule loop error: %s", e)

        time.sleep(SCHEDULE_POLL_INTERVAL)


# ── Main ──────────────────────────────────────────────

def main():
    logger.info("=== Farm Agent starting ===")
    logger.info("Device: %s", DEVICE_NAME)
    logger.info("X-API: %s", XAPI_URL)
    logger.info("Heartbeat: %ds, Schedule poll: %ds", HEARTBEAT_INTERVAL, SCHEDULE_POLL_INTERVAL)

    # Initial heartbeat
    send_heartbeat()

    # Start heartbeat in background thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # Main loop: schedule polling + refresh
    schedule_loop()


if __name__ == "__main__":
    main()
