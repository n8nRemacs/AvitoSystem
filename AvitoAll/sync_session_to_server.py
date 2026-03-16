"""
Avito Session Sync to Server

Reads session from phone via ADB and uploads to server.
Can run as daemon for automatic sync before token expiry.

Usage:
    python sync_session_to_server.py              # Sync once
    python sync_session_to_server.py --daemon     # Run as daemon
    python sync_session_to_server.py --check      # Just check status
"""

import subprocess
import json
import base64
import time
import re
import argparse
from datetime import datetime
from pathlib import Path

# ============ Configuration ============

# ADB path
ADB = r"C:\Users\User\AppData\Local\Android\Sdk\platform-tools\adb.exe"

# Avito SharedPreferences path on device
AVITO_PREFS = "/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml"

# Server configuration
SERVER_HOST = "155.212.221.189"
SERVER_USER = "root"
SERVER_SESSION_PATH = "/root/Avito/avito_session_new.json"

# Local cache
LOCAL_SESSION_FILE = "avito_session_live.json"

# Daemon settings
CHECK_INTERVAL_SECONDS = 300  # 5 minutes
SYNC_THRESHOLD_HOURS = 2      # Sync if less than 2 hours left


# ============ ADB Functions ============

def run_adb(cmd):
    """Run ADB command"""
    full_cmd = f'"{ADB}" {cmd}'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


def check_device():
    """Check if device is connected"""
    output = run_adb("devices")
    for line in output.strip().split('\n')[1:]:
        if '\tdevice' in line:
            return line.split('\t')[0]
    return None


def read_avito_prefs():
    """Read Avito SharedPreferences XML via root shell"""
    cmd = f'shell "su -c \'cat {AVITO_PREFS}\'"'
    output = run_adb(cmd)
    if "<?xml" in output:
        return output
    return None


def parse_prefs_xml(xml_content):
    """Parse SharedPreferences XML"""
    values = {}

    for match in re.finditer(r'<string name="([^"]+)">([^<]*)</string>', xml_content):
        name, value = match.groups()
        values[name] = value

    for match in re.finditer(r'<long name="([^"]+)" value="(\d+)"', xml_content):
        name, value = match.groups()
        values[name] = int(value)

    return values


def parse_jwt(token):
    """Parse JWT payload"""
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None

        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except:
        return None


# ============ Session Functions ============

def read_session_from_device():
    """Read session from device and return formatted data"""
    xml = read_avito_prefs()
    if not xml:
        return None

    prefs = parse_prefs_xml(xml)

    session_token = prefs.get('session')
    if not session_token:
        return None

    jwt_data = parse_jwt(session_token)

    return {
        "session_token": session_token,
        "refresh_token": prefs.get('refresh_token'),
        "session_data": {
            "device_id": prefs.get('device_id'),
            "fingerprint": prefs.get('fpx'),
            "remote_device_id": prefs.get('remote_device_id'),
            "user_hash": prefs.get('profile_hashId'),
            "user_id": jwt_data.get('u') if jwt_data else None,
            "cookies": {
                "1f_uid": "27835d95-6380-44e1-8289-4a13a511a29b",
                "u": "3bhsmqlh.1i5wwa4.i996zfqfof"
            }
        },
        "expires_at": jwt_data.get('exp', 0) if jwt_data else 0,
        "updated_at": int(time.time())
    }


def get_token_hours_left(session):
    """Get hours until token expiry"""
    if not session or not session.get('expires_at'):
        return -1
    return (session['expires_at'] - time.time()) / 3600


def save_session_local(session):
    """Save session to local file"""
    Path(LOCAL_SESSION_FILE).write_text(json.dumps(session, indent=2, ensure_ascii=False))
    print(f"[+] Saved locally: {LOCAL_SESSION_FILE}")


def upload_to_server(session):
    """Upload session to server via SCP"""
    # Save to temp file first
    temp_file = Path("_temp_session.json")
    temp_file.write_text(json.dumps(session, indent=2, ensure_ascii=False))

    # SCP to server
    cmd = f'scp -o StrictHostKeyChecking=no "{temp_file}" {SERVER_USER}@{SERVER_HOST}:{SERVER_SESSION_PATH}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    temp_file.unlink()  # Delete temp file

    if result.returncode == 0:
        print(f"[+] Uploaded to {SERVER_HOST}:{SERVER_SESSION_PATH}")
        return True
    else:
        print(f"[-] Upload failed: {result.stderr}")
        return False


def restart_bot_on_server():
    """Restart avito-bridge service on server"""
    cmd = f'ssh -o StrictHostKeyChecking=no {SERVER_USER}@{SERVER_HOST} "systemctl restart avito-bridge"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        print("[+] Bot restarted on server")
        return True
    else:
        print(f"[-] Restart failed: {result.stderr}")
        return False


def check_server_session():
    """Check session status on server"""
    cmd = f'ssh -o StrictHostKeyChecking=no {SERVER_USER}@{SERVER_HOST} "cat {SERVER_SESSION_PATH} 2>/dev/null"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0 and result.stdout:
        try:
            session = json.loads(result.stdout)
            return session
        except:
            pass
    return None


# ============ Main Logic ============

def sync_once(force=False):
    """Perform one sync cycle"""
    print("\n" + "=" * 50)
    print(f"AVITO SESSION SYNC - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Check device
    device = check_device()
    if not device:
        print("[-] No device connected!")
        return False
    print(f"[+] Device: {device}")

    # Read session from device
    print("[*] Reading session from device...")
    session = read_session_from_device()

    if not session:
        print("[-] Failed to read session from device")
        return False

    hours_left = get_token_hours_left(session)
    print(f"[+] Token expires in {hours_left:.1f}h")

    if hours_left <= 0:
        print("[!] Token EXPIRED on device!")
        return False

    # Check if sync needed
    server_session = check_server_session()
    server_hours = get_token_hours_left(server_session) if server_session else -1

    print(f"[*] Server token: {server_hours:.1f}h left" if server_hours > 0 else "[*] Server token: EXPIRED/MISSING")

    need_sync = force or server_hours < SYNC_THRESHOLD_HOURS or server_hours < hours_left - 0.5

    if not need_sync:
        print("[+] No sync needed - server token is fresh")
        return True

    # Sync
    print("[*] Syncing to server...")
    save_session_local(session)

    if upload_to_server(session):
        restart_bot_on_server()
        print("\n[+] SYNC COMPLETE!")
        return True

    return False


def daemon_mode():
    """Run as daemon, checking and syncing periodically"""
    print(f"\n[*] Starting daemon mode")
    print(f"    Check interval: {CHECK_INTERVAL_SECONDS}s")
    print(f"    Sync threshold: {SYNC_THRESHOLD_HOURS}h before expiry")
    print("[*] Press Ctrl+C to stop\n")

    while True:
        try:
            sync_once(force=False)
            print(f"\n[*] Next check in {CHECK_INTERVAL_SECONDS}s...")
            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n[*] Daemon stopped")
            break
        except Exception as e:
            print(f"[-] Error: {e}")
            time.sleep(60)  # Wait a minute on error


def check_status():
    """Just check status, don't sync"""
    print("\n=== STATUS CHECK ===\n")

    # Device
    device = check_device()
    print(f"Device: {device or 'NOT CONNECTED'}")

    if device:
        session = read_session_from_device()
        if session:
            hours = get_token_hours_left(session)
            exp = datetime.fromtimestamp(session['expires_at'])
            print(f"Device token: {hours:.1f}h left (expires {exp})")
        else:
            print("Device token: FAILED TO READ")

    # Server
    server_session = check_server_session()
    if server_session:
        hours = get_token_hours_left(server_session)
        exp = datetime.fromtimestamp(server_session.get('expires_at', 0))
        print(f"Server token: {hours:.1f}h left (expires {exp})")
    else:
        print("Server token: NOT FOUND")

    print()


def main():
    global CHECK_INTERVAL_SECONDS, SYNC_THRESHOLD_HOURS

    parser = argparse.ArgumentParser(description='Avito Session Sync to Server')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--check', action='store_true', help='Just check status')
    parser.add_argument('--force', action='store_true', help='Force sync even if not needed')
    parser.add_argument('--interval', type=int, default=CHECK_INTERVAL_SECONDS, help='Check interval (seconds)')
    parser.add_argument('--threshold', type=float, default=SYNC_THRESHOLD_HOURS, help='Sync threshold (hours)')
    args = parser.parse_args()

    CHECK_INTERVAL_SECONDS = args.interval
    SYNC_THRESHOLD_HOURS = args.threshold

    if args.check:
        check_status()
    elif args.daemon:
        daemon_mode()
    else:
        sync_once(force=args.force)


if __name__ == "__main__":
    main()
