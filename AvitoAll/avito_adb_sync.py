"""
Avito ADB Token Sync
Extracts session tokens from Avito app via ADB root shell and saves/syncs them.

Usage:
    python avito_adb_sync.py                # Read and show tokens
    python avito_adb_sync.py --save         # Save to file
    python avito_adb_sync.py --sync URL     # Sync to server
    python avito_adb_sync.py --watch        # Watch for changes
"""

import subprocess
import json
import base64
import time
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from xml.etree import ElementTree

# ADB path
ADB = r"C:\Users\User\AppData\Local\Android\Sdk\platform-tools\adb.exe"

# Avito SharedPreferences path
AVITO_PREFS = "/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml"

# Output file
SESSION_FILE = "avito_session_live.json"


def run_adb(cmd: str) -> str:
    """Run ADB command and return output"""
    full_cmd = f'"{ADB}" {cmd}'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


def check_device() -> bool:
    """Check if device is connected"""
    output = run_adb("devices")
    lines = output.strip().split('\n')
    for line in lines[1:]:
        if '\tdevice' in line:
            device_id = line.split('\t')[0]
            print(f"[+] Device connected: {device_id}")
            return True
    print("[-] No device connected")
    return False


def read_avito_prefs() -> Optional[str]:
    """Read Avito SharedPreferences XML via root shell"""
    cmd = f'shell "su -c \'cat {AVITO_PREFS}\'"'
    output = run_adb(cmd)

    if "<?xml" in output:
        return output
    else:
        print(f"[-] Failed to read prefs: {output[:200]}")
        return None


def parse_prefs_xml(xml_content: str) -> Dict[str, str]:
    """Parse SharedPreferences XML"""
    values = {}

    # Extract string values
    for match in re.finditer(r'<string name="([^"]+)">([^<]*)</string>', xml_content):
        name, value = match.groups()
        values[name] = value

    # Extract long values
    for match in re.finditer(r'<long name="([^"]+)" value="(\d+)"', xml_content):
        name, value = match.groups()
        values[name] = int(value)

    return values


def parse_jwt(token: str) -> Optional[Dict]:
    """Parse JWT token payload"""
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None

        payload = parts[1]
        # Add padding
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        print(f"[-] JWT parse error: {e}")
        return None


def extract_session(prefs: Dict) -> Optional[Dict]:
    """Extract session data from parsed preferences"""
    session_token = prefs.get('session')
    if not session_token:
        print("[-] No session token found")
        return None

    # Parse JWT
    jwt_data = parse_jwt(session_token)
    if not jwt_data:
        return None

    # Build session object
    session = {
        "session_token": session_token,
        "refresh_token": prefs.get('refresh_token'),
        "fingerprint": prefs.get('fpx'),
        "device_id": prefs.get('device_id'),
        "remote_device_id": prefs.get('remote_device_id'),
        "user_id": jwt_data.get('u'),
        "profile_id": jwt_data.get('p'),
        "user_hash": prefs.get('profile_hashId'),
        "user_name": prefs.get('profile_name'),
        "user_email": prefs.get('profile_email'),
        "expires_at": jwt_data.get('exp'),
        "issued_at": jwt_data.get('iat'),
        "fpx_calc_time": prefs.get('fpx_calc_time'),
        "extracted_at": int(time.time()),
    }

    return session


def print_session_status(session: Dict):
    """Print session status"""
    now = time.time()
    exp = session['expires_at']
    hours_left = (exp - now) / 3600

    print("\n" + "=" * 60)
    print("AVITO SESSION STATUS")
    print("=" * 60)
    print(f"User: {session['user_name']} ({session['user_email']})")
    print(f"User ID: {session['user_id']}")
    print(f"User Hash: {session['user_hash']}")
    print(f"Device ID: {session['device_id']}")
    print("-" * 60)
    print(f"Expires: {datetime.fromtimestamp(exp)}")
    print(f"Time left: {hours_left:.1f} hours")

    if hours_left <= 0:
        print("Status: EXPIRED!")
    elif hours_left < 2:
        print("Status: EXPIRING SOON!")
    else:
        print("Status: OK")

    print("-" * 60)
    print(f"Token: {session['session_token'][:60]}...")
    print(f"Fingerprint: {session['fingerprint'][:60]}...")
    print(f"Refresh: {session['refresh_token']}")
    print("=" * 60)


def save_session(session: Dict, filename: str = SESSION_FILE):
    """Save session to JSON file"""
    # Format for API use
    api_session = {
        "session_token": session['session_token'],
        "refresh_token": session['refresh_token'],
        "session_data": {
            "device_id": session['device_id'],
            "fingerprint": session['fingerprint'],
            "remote_device_id": session['remote_device_id'],
            "user_hash": session['user_hash'],
            "cookies": {}
        },
        "user_id": session['user_id'],
        "user_name": session['user_name'],
        "expires_at": session['expires_at'],
        "extracted_at": session['extracted_at'],
    }

    Path(filename).write_text(json.dumps(api_session, indent=2, ensure_ascii=False))
    print(f"\n[+] Session saved to {filename}")


def sync_to_server(session: Dict, server_url: str, api_key: str = ""):
    """Sync session to server"""
    try:
        import requests
    except ImportError:
        print("[-] requests module not installed")
        return False

    payload = {
        "session_token": session['session_token'],
        "refresh_token": session['refresh_token'],
        "fingerprint": session['fingerprint'],
        "device_id": session['device_id'],
        "remote_device_id": session['remote_device_id'],
        "user_id": session['user_id'],
        "user_hash": session['user_hash'],
        "expires_at": session['expires_at'],
        "cookies": {},
        "synced_at": int(time.time()),
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Device-Key"] = api_key

    try:
        resp = requests.post(f"{server_url}/api/v1/sessions", json=payload, headers=headers, timeout=30)
        if resp.ok:
            print(f"[+] Synced to server: {resp.json()}")
            return True
        else:
            print(f"[-] Server error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[-] Sync error: {e}")
        return False


def watch_session(interval: int = 60):
    """Watch for session changes and auto-save"""
    print(f"\n[*] Watching session (check every {interval}s)... Ctrl+C to stop")

    last_token = None

    while True:
        try:
            xml = read_avito_prefs()
            if xml:
                prefs = parse_prefs_xml(xml)
                session = extract_session(prefs)

                if session:
                    current_token = session['session_token']

                    if current_token != last_token:
                        print(f"\n[!] Token changed at {datetime.now()}")
                        print_session_status(session)
                        save_session(session)
                        last_token = current_token
                    else:
                        hours_left = (session['expires_at'] - time.time()) / 3600
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] OK - {hours_left:.1f}h left", end='\r')

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[*] Stopped watching")
            break


def main():
    parser = argparse.ArgumentParser(description='Avito ADB Token Sync')
    parser.add_argument('--save', action='store_true', help='Save session to file')
    parser.add_argument('--sync', metavar='URL', help='Sync to server URL')
    parser.add_argument('--key', metavar='API_KEY', help='Server API key')
    parser.add_argument('--watch', action='store_true', help='Watch for token changes')
    parser.add_argument('--interval', type=int, default=60, help='Watch interval (seconds)')
    args = parser.parse_args()

    print("[*] Avito ADB Token Sync")
    print("-" * 40)

    # Check device
    if not check_device():
        return

    # Read preferences
    print("[*] Reading Avito SharedPreferences...")
    xml = read_avito_prefs()
    if not xml:
        return

    # Parse
    prefs = parse_prefs_xml(xml)
    print(f"[+] Parsed {len(prefs)} preferences")

    # Extract session
    session = extract_session(prefs)
    if not session:
        return

    # Print status
    print_session_status(session)

    # Save
    if args.save:
        save_session(session)

    # Sync
    if args.sync:
        sync_to_server(session, args.sync, args.key or "")

    # Watch
    if args.watch:
        watch_session(args.interval)


if __name__ == "__main__":
    main()
