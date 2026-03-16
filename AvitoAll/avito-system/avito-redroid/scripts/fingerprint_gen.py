#!/usr/bin/env python3
"""
Fingerprint Generator for Avito Redroid Masking
Generates realistic Android fingerprints based on device profile
"""

import argparse
import json
import random
import string
import sys
from datetime import datetime, timedelta


# Known fingerprint patterns for major brands
FINGERPRINT_PATTERNS = {
    'Samsung': {
        'format': 'samsung/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'TP{random.choice(["1A", "2A", "3A"])}.{random.randint(220101, 241231)}.{random.randint(1, 99):03d}',
        'build_number_format': lambda m: f'S{random.randint(100, 999)}B{random.choice(string.ascii_uppercase)}{random.choice(string.ascii_uppercase)}U{random.randint(1, 9)}{random.choice(string.ascii_uppercase)}{random.choice(string.ascii_uppercase)}{random.choice(string.ascii_uppercase)}{random.randint(1, 9)}'
    },
    'Google': {
        'format': 'google/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'{random.choice(["AP", "TP", "SP"])}{v[0]}{random.choice(["A", "B"])}.{random.randint(230101, 241231)}.{random.randint(1, 99):03d}',
        'build_number_format': lambda m: f'{random.randint(10000000, 99999999)}'
    },
    'Xiaomi': {
        'format': 'Xiaomi/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'TKQ1.{random.randint(220101, 241231)}.001',
        'build_number_format': lambda m: f'V{random.randint(14, 15)}.0.{random.randint(1, 30)}.0.{random.choice(["TMCEUXM", "TKAEUXM", "TKAMIXI", "TMFCNXM"])}'
    },
    'OnePlus': {
        'format': 'OnePlus/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'SKQ1.{random.randint(220101, 241231)}.001',
        'build_number_format': lambda m: f'{random.choice(["LE", "NE", "BE"])}{random.randint(2000, 2999)}.{random.randint(1, 12):02d}.{random.randint(1, 50)}'
    },
    'Oppo': {
        'format': 'OPPO/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'TP1A.{random.randint(220101, 241231)}.001',
        'build_number_format': lambda m: f'{random.choice(["RMX", "CPH", "PHM"])}{random.randint(3000, 4000)}_11.{random.choice(["A", "C", "F"])}.{random.randint(10, 50)}'
    },
    'Realme': {
        'format': 'realme/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'TP1A.{random.randint(220101, 241231)}.001',
        'build_number_format': lambda m: f'RMX{random.randint(3000, 4000)}_11_A.{random.randint(10, 99)}'
    },
    'Vivo': {
        'format': 'vivo/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'TP1A.{random.randint(220101, 241231)}.001',
        'build_number_format': lambda m: f'V{random.randint(2000, 2999)}A_PD{random.randint(2100, 2500)}F_EX_A_{random.randint(1, 99)}'
    },
    'Honor': {
        'format': 'HONOR/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'HONORB{random.choice(["LN", "MG", "RN"])}{random.randint(1, 9)}',
        'build_number_format': lambda m: f'{random.randint(7, 8)}.0.0.{random.randint(100, 200)}(C{random.randint(100, 999)}E{random.randint(1, 9)}R{random.randint(1, 9)}P{random.randint(1, 9)})'
    },
    'Motorola': {
        'format': 'motorola/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'T{random.choice(["P1A", "P2A", "KQ1"])}.{random.randint(220101, 241231)}.{random.randint(1, 30):03d}',
        'build_number_format': lambda m: f'{random.randint(33, 35)}.1-{random.randint(1, 50)}-{random.randint(1, 20)}'
    },
    'Huawei': {
        'format': 'HUAWEI/{product}/{device}:{version}/{build_id}/{build_number}:user/release-keys',
        'build_id_format': lambda v: f'HUAWEI{random.choice(["MNA", "DCO", "JAD"])}-{random.choice(["AL", "AN", "TL"])}{random.randint(0, 99):02d}',
        'build_number_format': lambda m: f'13.0.0.{random.randint(100, 300)}(C{random.randint(100, 999)}E{random.randint(1, 9)}R{random.randint(1, 9)}P{random.randint(1, 9)})'
    },
}


def generate_security_patch_date() -> str:
    """Generate realistic security patch date (first of month, recent)"""
    today = datetime.now()
    # Random date in last 6 months, always 1st of month
    months_back = random.randint(0, 5)
    patch_date = today.replace(day=1) - timedelta(days=30 * months_back)
    return patch_date.strftime('%Y-%m-01')


def generate_fingerprint(brand: str, product: str, device: str,
                          android_version: str, build_id: str = None,
                          build_number: str = None) -> dict:
    """Generate complete fingerprint information"""

    manufacturer = brand.lower()

    # Get brand pattern or use default
    pattern_info = FINGERPRINT_PATTERNS.get(brand, {
        'format': f'{manufacturer}/{{product}}/{{device}}:{{version}}/{{build_id}}/{{build_number}}:user/release-keys',
        'build_id_format': lambda v: f'TP1A.{random.randint(220101, 241231)}.{random.randint(1, 99):03d}',
        'build_number_format': lambda m: f'{random.randint(10000000, 99999999)}'
    })

    # Generate or use provided build_id
    if not build_id:
        build_id = pattern_info['build_id_format'](android_version)

    # Generate or use provided build_number
    if not build_number:
        build_number = pattern_info['build_number_format'](product)

    # Format fingerprint
    fingerprint = pattern_info['format'].format(
        product=product,
        device=device,
        version=android_version,
        build_id=build_id,
        build_number=build_number
    )

    # Handle special brand naming in fingerprint
    if brand == 'Samsung':
        fingerprint = fingerprint.replace(f'{manufacturer}/', 'samsung/')
    elif brand == 'Xiaomi':
        fingerprint = fingerprint.replace(f'{manufacturer}/', 'Xiaomi/')

    return {
        'fingerprint': fingerprint,
        'build_id': build_id,
        'build_number': build_number,
        'security_patch': generate_security_patch_date()
    }


def validate_fingerprint(fingerprint: str) -> bool:
    """Validate fingerprint format"""
    # Format: brand/product/device:version/build_id/build_number:type/tags
    parts = fingerprint.split(':')
    if len(parts) != 3:
        return False

    first_part = parts[0]  # brand/product/device
    if first_part.count('/') != 2:
        return False

    second_part = parts[1]  # version/build_id/build_number
    if second_part.count('/') != 2:
        return False

    third_part = parts[2]  # type/tags
    if third_part.count('/') != 1:
        return False

    return True


def update_profile_fingerprint(profile: dict) -> dict:
    """Update profile with new fingerprint data"""

    brand = profile.get('brand', 'Samsung')
    product = profile.get('product', 'unknown')
    device = profile.get('device', 'unknown')
    android_version = profile.get('android_version', '13')
    build_id = profile.get('build_id')
    build_number = profile.get('build_number')

    fp_data = generate_fingerprint(brand, product, device, android_version, build_id, build_number)

    profile['fingerprint'] = fp_data['fingerprint']
    profile['build_id'] = fp_data['build_id']
    profile['build_number'] = fp_data['build_number']
    profile['security_patch'] = fp_data['security_patch']

    return profile


def main():
    parser = argparse.ArgumentParser(description='Generate or update Android fingerprint')
    parser.add_argument('--profile', '-p',
                        help='Path to device profile JSON (will update in place)')
    parser.add_argument('--brand', '-b', default='Samsung',
                        help='Device brand')
    parser.add_argument('--product', '-r', default='dm1qxx',
                        help='Product name')
    parser.add_argument('--device', '-d', default='dm1q',
                        help='Device codename')
    parser.add_argument('--version', '-v', default='13',
                        help='Android version')
    parser.add_argument('--output', '-o',
                        help='Output JSON file (optional)')
    parser.add_argument('--validate', action='store_true',
                        help='Validate fingerprint format only')

    args = parser.parse_args()

    print("=== Fingerprint Generator ===")

    if args.profile:
        # Update existing profile
        print(f"Loading profile: {args.profile}")
        try:
            with open(args.profile, 'r', encoding='utf-8') as f:
                profile = json.load(f)
        except FileNotFoundError:
            print(f"ERROR: Profile not found: {args.profile}")
            sys.exit(1)

        # Update fingerprint
        updated_profile = update_profile_fingerprint(profile)

        # Validate
        if args.validate:
            is_valid = validate_fingerprint(updated_profile['fingerprint'])
            print(f"Fingerprint valid: {is_valid}")
            if not is_valid:
                sys.exit(1)
            sys.exit(0)

        # Save back to profile
        with open(args.profile, 'w', encoding='utf-8') as f:
            json.dump(updated_profile, f, indent=2, ensure_ascii=False)

        print(f"Updated: {args.profile}")
        print(f"Fingerprint: {updated_profile['fingerprint']}")

        # Also save to output if specified
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(updated_profile, f, indent=2, ensure_ascii=False)
            print(f"Also saved to: {args.output}")

    else:
        # Generate standalone fingerprint
        fp_data = generate_fingerprint(args.brand, args.product, args.device, args.version)

        print(f"\nBrand: {args.brand}")
        print(f"Product: {args.product}")
        print(f"Device: {args.device}")
        print(f"Android: {args.version}")
        print(f"\nFingerprint: {fp_data['fingerprint']}")
        print(f"Build ID: {fp_data['build_id']}")
        print(f"Build Number: {fp_data['build_number']}")
        print(f"Security Patch: {fp_data['security_patch']}")

        # Validate
        is_valid = validate_fingerprint(fp_data['fingerprint'])
        print(f"\nFormat valid: {is_valid}")

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(fp_data, f, indent=2, ensure_ascii=False)
            print(f"Saved to: {args.output}")


if __name__ == '__main__':
    main()
