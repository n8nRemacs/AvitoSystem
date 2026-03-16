#!/usr/bin/env python3
"""
Extract Avito tokens from SharedPreferences XML
"""
import sys
import xml.etree.ElementTree as ET
import json
from datetime import datetime
import os
import base64

def parse_shared_prefs(xml_file):
    """Parse SharedPreferences XML and extract tokens"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        tokens = {}

        # Extract all string values
        for string_elem in root.findall('string'):
            name = string_elem.get('name')
            value = string_elem.text

            if name and value:
                # Session token (JWT)
                if 'session' in name.lower() or 'token' in name.lower():
                    if value.startswith('eyJ'):  # JWT format
                        tokens['session_token'] = value

                # Refresh token
                if 'refresh' in name.lower():
                    tokens['refresh_token'] = value

                # Fingerprint
                if 'fingerprint' in name.lower() or name == 'f':
                    tokens['fingerprint'] = value

                # Device ID
                if 'device' in name.lower() and 'id' in name.lower():
                    tokens['device_id'] = value

                # User ID
                if 'user' in name.lower() and 'id' in name.lower():
                    try:
                        tokens['user_id'] = int(value)
                    except:
                        tokens['user_id'] = value

        # Try to decode JWT to get more info
        if 'session_token' in tokens:
            try:
                # Decode JWT payload (without signature verification)
                parts = tokens['session_token'].split('.')
                if len(parts) >= 2:
                    # Add padding if needed
                    payload = parts[1]
                    payload += '=' * (4 - len(payload) % 4)

                    decoded = base64.urlsafe_b64decode(payload)
                    jwt_data = json.loads(decoded)

                    # Extract expiration
                    if 'exp' in jwt_data:
                        tokens['expires_at'] = jwt_data['exp']

                    # Extract user info if present
                    if 'userId' in jwt_data and 'user_id' not in tokens:
                        tokens['user_id'] = jwt_data['userId']

                    # Extract device info if present
                    if 'deviceInfo' in jwt_data:
                        tokens['device_info'] = jwt_data['deviceInfo']
            except Exception as e:
                print(f"[!] Warning: Could not decode JWT: {e}")

        return tokens

    except Exception as e:
        print(f"[X] Error parsing XML: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: extract_tokens.py <shared_prefs.xml>")
        sys.exit(1)

    xml_file = sys.argv[1]

    if not os.path.exists(xml_file):
        print(f"[X] File not found: {xml_file}")
        sys.exit(1)

    print(f"Parsing {xml_file}...")

    tokens = parse_shared_prefs(xml_file)

    if not tokens:
        print("[X] No tokens found")
        sys.exit(1)

    # Check required fields
    required_fields = ['session_token', 'fingerprint']
    missing = [f for f in required_fields if f not in tokens]

    if missing:
        print(f"[!] Warning: Missing fields: {', '.join(missing)}")
        print("\nFound fields:")
        for key in tokens.keys():
            value_preview = str(tokens[key])[:50] + "..." if len(str(tokens[key])) > 50 else str(tokens[key])
            print(f"  - {key}: {value_preview}")
        print("\nYou may need to:")
        print("  1. Login to Avito")
        print("  2. Open 'Messages' tab")
        print("  3. Wait 30 seconds")
        print("  4. Try again")
        sys.exit(1)

    # Add metadata
    tokens['extracted_at'] = int(datetime.now().timestamp())
    tokens['extracted_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Save to file
    os.makedirs('output', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/session_{timestamp}.json'

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Tokens saved to: {output_file}")
    print(f"\nExtracted:")
    print(f"  - session_token: {tokens['session_token'][:50]}...")
    print(f"  - fingerprint: {tokens.get('fingerprint', 'N/A')}")
    print(f"  - device_id: {tokens.get('device_id', 'N/A')}")
    print(f"  - user_id: {tokens.get('user_id', 'N/A')}")

    if 'expires_at' in tokens:
        exp_date = datetime.fromtimestamp(tokens['expires_at'])
        print(f"  - expires_at: {exp_date.strftime('%Y-%m-%d %H:%M:%S')}")

    if 'device_info' in tokens:
        print(f"\nDevice Info:")
        for key, value in tokens['device_info'].items():
            print(f"  - {key}: {value}")

if __name__ == '__main__':
    main()
