#!/usr/bin/env python3
"""
Check Status of Avito Tokens

This script reads the latest session file and displays:
- Token expiration status
- Time until expiration
- User information
- Device information

Usage:
    python check_token_status.py
    python check_token_status.py --file output/session_20260126_083000.json
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import argparse


def format_time_delta(seconds):
    """Format time delta in human readable format"""
    if seconds < 0:
        return "EXPIRED"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 48:
        days = hours // 24
        return f"{days} days {hours % 24} hours"
    elif hours > 0:
        return f"{hours} hours {minutes} minutes"
    else:
        return f"{minutes} minutes"


def get_latest_session_file(output_dir="output"):
    """Get the latest session file from output directory"""
    session_files = list(Path(output_dir).glob("session_*.json"))

    if not session_files:
        return None

    # Sort by modification time, most recent first
    session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return session_files[0]


def check_token_status(session_file):
    """Check token status from session file"""
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            session = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {session_file}")
        return False
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON in file: {session_file}")
        return False

    print("=" * 70)
    print(" " * 20 + "AVITO TOKEN STATUS")
    print("=" * 70)
    print()

    # File info
    file_time = datetime.fromtimestamp(Path(session_file).stat().st_mtime)
    print(f"Session file:  {session_file}")
    print(f"File created:  {file_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # User info
    print("-" * 70)
    print(" " * 25 + "USER INFORMATION")
    print("-" * 70)
    print(f"User ID:       {session.get('user_id', 'N/A')}")
    print(f"User Hash:     {session.get('user_hash', 'N/A')[:20]}...")
    print(f"Device ID:     {session.get('device_id', 'N/A')}")
    print()

    # Token info
    print("-" * 70)
    print(" " * 25 + "TOKEN INFORMATION")
    print("-" * 70)

    session_token = session.get('session_token', '')
    refresh_token = session.get('refresh_token', '')
    fingerprint = session.get('fingerprint', '')

    print(f"Session Token: {session_token[:40]}... ({len(session_token)} chars)")
    print(f"Refresh Token: {refresh_token[:40]}...")
    print(f"Fingerprint:   {fingerprint[:40]}...")
    print()

    # Expiration info
    print("-" * 70)
    print(" " * 25 + "EXPIRATION STATUS")
    print("-" * 70)

    expires_at = session.get('expires_at', 0)
    extracted_at = session.get('extracted_at', 0)

    if expires_at:
        expires_time = datetime.fromtimestamp(expires_at)
        print(f"Expires at:    {expires_time.strftime('%Y-%m-%d %H:%M:%S')}")

        now = int(time.time())
        time_left = expires_at - now

        print(f"Time left:     {format_time_delta(time_left)}")
        print()

        # Status indicator
        if time_left < 0:
            status = "🔴 EXPIRED"
            recommendation = "Token is expired. Extract new token: 06_extract_tokens.bat"
        elif time_left < 3600:  # < 1 hour
            status = "🟠 EXPIRING SOON"
            recommendation = "Token expires in less than 1 hour. Refresh recommended."
        elif time_left < 7200:  # < 2 hours
            status = "🟡 REFRESH RECOMMENDED"
            recommendation = "Token expires in less than 2 hours. Consider refreshing."
        else:
            status = "🟢 VALID"
            recommendation = "Token is fresh. No action needed."

        print(f"Status:        {status}")
        print(f"Action:        {recommendation}")
    else:
        print("⚠️  Warning: No expiration time found in session file")

    print()

    # Device info
    if 'device_info' in session:
        print("-" * 70)
        print(" " * 25 + "DEVICE INFORMATION")
        print("-" * 70)
        device_info = session['device_info']
        for key, value in device_info.items():
            print(f"{key:<15}: {value}")
        print()

    print("=" * 70)
    return True


def main():
    parser = argparse.ArgumentParser(description='Check Avito token status')
    parser.add_argument('--file', '-f', help='Session file to check', default=None)
    parser.add_argument('--output-dir', '-o', help='Output directory', default='output')

    args = parser.parse_args()

    if args.file:
        session_file = Path(args.file)
    else:
        # Find latest session file
        session_file = get_latest_session_file(args.output_dir)

        if not session_file:
            print("❌ Error: No session files found in output directory")
            print()
            print("Please extract tokens first:")
            print("  cd scripts")
            print("  06_extract_tokens.bat")
            return 1

        print(f"ℹ️  Using latest session file: {session_file}")
        print()

    if not check_token_status(session_file):
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
