#!/usr/bin/env python3
"""
Extract Avito tokens from Android container
Connects via ADB and pulls SharedPreferences
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
import base64
import tempfile


# Avito SharedPreferences paths
AVITO_PREFS_PATHS = [
    '/data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml',
    '/data/data/com.avito.android/shared_prefs/avito_auth_v2.xml',
    '/data/data/com.avito.android/shared_prefs/auth_prefs.xml',
    '/data/data/com.avito.android/shared_prefs/secure_prefs.xml',
]

# Token field names to look for
TOKEN_FIELDS = {
    'session': ['session', 'token', 'access_token', 'jwt', 'auth_token'],
    'refresh': ['refresh_token', 'refresh'],
    'fingerprint': ['fingerprint', 'f', 'device_fingerprint'],
    'device_id': ['device_id', 'deviceId', 'did', 'android_id'],
    'user_id': ['user_id', 'userId', 'uid'],
}


def run_adb(args: list, host: str = None) -> tuple:
    """Run ADB command and return (stdout, stderr, returncode)"""
    cmd = ['adb']
    if host:
        cmd.extend(['-H', host.split(':')[0], '-P', host.split(':')[1] if ':' in host else '5555'])
    cmd.extend(args)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return '', 'ADB command timed out', 1
    except FileNotFoundError:
        return '', 'ADB not found in PATH', 1


def pull_file(remote_path: str, local_path: str, host: str = None) -> bool:
    """Pull file from device via ADB"""
    stdout, stderr, code = run_adb(['pull', remote_path, local_path], host)
    return code == 0


def parse_shared_prefs(xml_content: str) -> dict:
    """Parse SharedPreferences XML and extract token data"""
    try:
        root = ET.fromstring(xml_content)
        data = {}

        # Extract all string values
        for elem in root.findall('string'):
            name = elem.get('name', '')
            value = elem.text or ''

            if name and value:
                data[name] = value

        # Extract int/long values
        for elem in root.findall('long') + root.findall('int'):
            name = elem.get('name', '')
            value = elem.get('value', '')
            if name and value:
                try:
                    data[name] = int(value)
                except ValueError:
                    data[name] = value

        return data

    except ET.ParseError as e:
        print(f"[!] XML parse error: {e}")
        return {}


def extract_tokens(prefs_data: dict) -> dict:
    """Extract token values from SharedPreferences data"""
    tokens = {}

    for name, value in prefs_data.items():
        name_lower = name.lower()
        value_str = str(value)

        # Session token (JWT format)
        if value_str.startswith('eyJ'):
            if not tokens.get('session_token') or len(value_str) > len(tokens.get('session_token', '')):
                tokens['session_token'] = value_str
            continue

        # Check field categories
        for token_type, keywords in TOKEN_FIELDS.items():
            for keyword in keywords:
                if keyword.lower() in name_lower:
                    if token_type == 'session' and value_str.startswith('eyJ'):
                        tokens['session_token'] = value_str
                    elif token_type == 'refresh':
                        tokens['refresh_token'] = value_str
                    elif token_type == 'fingerprint':
                        tokens['fingerprint'] = value_str
                    elif token_type == 'device_id':
                        tokens['device_id'] = value_str
                    elif token_type == 'user_id':
                        try:
                            tokens['user_id'] = int(value_str)
                        except ValueError:
                            tokens['user_id'] = value_str
                    break

    # Decode JWT to extract additional info
    if 'session_token' in tokens:
        try:
            parts = tokens['session_token'].split('.')
            if len(parts) >= 2:
                payload = parts[1]
                # Add padding
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload)
                jwt_data = json.loads(decoded)

                if 'exp' in jwt_data:
                    tokens['expires_at'] = jwt_data['exp']
                    tokens['expires_date'] = datetime.fromtimestamp(jwt_data['exp']).isoformat()

                if 'userId' in jwt_data and 'user_id' not in tokens:
                    tokens['user_id'] = jwt_data['userId']

                if 'deviceInfo' in jwt_data:
                    tokens['jwt_device_info'] = jwt_data['deviceInfo']

        except Exception as e:
            print(f"[!] JWT decode warning: {e}")

    return tokens


def main():
    parser = argparse.ArgumentParser(description='Extract Avito tokens from Android container')
    parser.add_argument('--host', '-H', default='localhost:5555',
                        help='ADB host:port (default: localhost:5555)')
    parser.add_argument('--output', '-o', default='/opt/output/tokens',
                        help='Output directory for tokens')
    parser.add_argument('--xml', '-x',
                        help='Parse local XML file instead of pulling from device')

    args = parser.parse_args()

    print("=== Avito Token Extractor ===")
    print(f"Time: {datetime.now().isoformat()}")

    all_prefs_data = {}

    if args.xml:
        # Parse local file
        print(f"\nParsing local file: {args.xml}")
        try:
            with open(args.xml, 'r', encoding='utf-8') as f:
                content = f.read()
            all_prefs_data = parse_shared_prefs(content)
        except FileNotFoundError:
            print(f"[X] File not found: {args.xml}")
            sys.exit(1)
    else:
        # Connect and pull from device
        print(f"\nConnecting to: {args.host}")

        # Check ADB connection
        stdout, stderr, code = run_adb(['devices'])
        if code != 0:
            print(f"[X] ADB error: {stderr}")
            sys.exit(1)

        # Root shell for access
        print("Getting root access...")
        run_adb(['root'])

        # Create temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            for prefs_path in AVITO_PREFS_PATHS:
                local_file = os.path.join(tmpdir, os.path.basename(prefs_path))

                print(f"Trying: {prefs_path}")
                if pull_file(prefs_path, local_file):
                    try:
                        with open(local_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        prefs = parse_shared_prefs(content)
                        all_prefs_data.update(prefs)
                        print(f"  Found {len(prefs)} entries")
                    except Exception as e:
                        print(f"  Parse error: {e}")
                else:
                    print(f"  Not found or no access")

    if not all_prefs_data:
        print("\n[X] No SharedPreferences data found!")
        print("\nMake sure:")
        print("  1. Avito app is installed")
        print("  2. User is logged in")
        print("  3. Container has root access")
        sys.exit(1)

    print(f"\nTotal entries found: {len(all_prefs_data)}")

    # Extract tokens
    tokens = extract_tokens(all_prefs_data)

    if not tokens:
        print("\n[X] No tokens extracted!")
        print("Available keys in prefs:")
        for key in list(all_prefs_data.keys())[:20]:
            print(f"  - {key}")
        sys.exit(1)

    # Add metadata
    tokens['extracted_at'] = int(datetime.now().timestamp())
    tokens['extracted_date'] = datetime.now().isoformat()

    # Ensure output directory exists
    os.makedirs(args.output, exist_ok=True)

    # Save with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(args.output, f'tokens_{timestamp}.json')

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)

    # Also save as latest.json
    latest_file = os.path.join(args.output, 'latest.json')
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)

    print(f"\n=== Tokens Extracted ===")
    print(f"Output: {output_file}")
    print(f"Latest: {latest_file}")
    print()

    # Display summary
    if 'session_token' in tokens:
        print(f"Session Token: {tokens['session_token'][:50]}...")
    if 'refresh_token' in tokens:
        print(f"Refresh Token: {tokens['refresh_token'][:30]}...")
    if 'fingerprint' in tokens:
        print(f"Fingerprint: {tokens['fingerprint']}")
    if 'device_id' in tokens:
        print(f"Device ID: {tokens['device_id']}")
    if 'user_id' in tokens:
        print(f"User ID: {tokens['user_id']}")
    if 'expires_date' in tokens:
        print(f"Expires: {tokens['expires_date']}")


if __name__ == '__main__':
    main()
