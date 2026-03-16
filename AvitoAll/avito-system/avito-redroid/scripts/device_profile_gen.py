#!/usr/bin/env python3
"""
Device Profile Generator for Avito Redroid Masking
Selects a random device from GSMArena database and generates a complete profile
"""

import argparse
import json
import os
import random
import sys
from typing import Optional

import psycopg2


# Allowed brands for masking (popular Android brands)
ALLOWED_BRANDS = [
    'Samsung', 'Xiaomi', 'Google', 'OnePlus', 'Oppo',
    'Realme', 'Huawei', 'Vivo', 'Honor', 'Motorola'
]

# Budget model keywords to exclude (less realistic for high-end detection bypass)
BUDGET_KEYWORDS = ['Lite', 'Go', 'Neo', 'FE', 'Mini', 'A0', 'A1']

# Minimum release year (Android 11+ support)
MIN_RELEASE_YEAR = 2021

# Known device codenames and build patterns for popular devices
DEVICE_CODENAMES = {
    'Samsung': {
        'Galaxy S23': {'device': 'dm1q', 'product': 'dm1qxx', 'hardware': 'qcom'},
        'Galaxy S23+': {'device': 'dm2q', 'product': 'dm2qxx', 'hardware': 'qcom'},
        'Galaxy S23 Ultra': {'device': 'dm3q', 'product': 'dm3qxx', 'hardware': 'qcom'},
        'Galaxy S22': {'device': 'r0q', 'product': 'r0qxx', 'hardware': 'qcom'},
        'Galaxy S22+': {'device': 's9060', 'product': 's906bxx', 'hardware': 'qcom'},
        'Galaxy S22 Ultra': {'device': 'b0q', 'product': 'b0qxx', 'hardware': 'qcom'},
        'Galaxy S21': {'device': 'o1s', 'product': 'o1sxx', 'hardware': 'exynos'},
        'Galaxy S21+': {'device': 't2s', 'product': 't2sxx', 'hardware': 'exynos'},
        'Galaxy S21 Ultra': {'device': 'p3s', 'product': 'p3sxx', 'hardware': 'exynos'},
        'Galaxy A54': {'device': 'a54x', 'product': 'a54xnsxx', 'hardware': 'exynos'},
        'Galaxy A53': {'device': 'a53x', 'product': 'a53xnsxx', 'hardware': 'exynos'},
        'Galaxy Z Fold5': {'device': 'q5q', 'product': 'q5qxx', 'hardware': 'qcom'},
        'Galaxy Z Flip5': {'device': 'b5q', 'product': 'b5qxx', 'hardware': 'qcom'},
    },
    'Xiaomi': {
        'Xiaomi 13': {'device': 'fuxi', 'product': 'fuxi', 'hardware': 'qcom'},
        'Xiaomi 13 Pro': {'device': 'nuwa', 'product': 'nuwa', 'hardware': 'qcom'},
        'Xiaomi 12': {'device': 'cupid', 'product': 'cupid', 'hardware': 'qcom'},
        'Xiaomi 12 Pro': {'device': 'zeus', 'product': 'zeus', 'hardware': 'qcom'},
        'Redmi Note 12 Pro': {'device': 'ruby', 'product': 'ruby', 'hardware': 'mtk'},
        'Redmi Note 12': {'device': 'tapas', 'product': 'tapas', 'hardware': 'qcom'},
        'POCO F5': {'device': 'marble', 'product': 'marble', 'hardware': 'qcom'},
        'POCO X5 Pro': {'device': 'redwood', 'product': 'redwood', 'hardware': 'qcom'},
    },
    'Google': {
        'Pixel 8': {'device': 'shiba', 'product': 'shiba', 'hardware': 'gs201'},
        'Pixel 8 Pro': {'device': 'husky', 'product': 'husky', 'hardware': 'gs201'},
        'Pixel 7': {'device': 'panther', 'product': 'panther', 'hardware': 'gs101'},
        'Pixel 7 Pro': {'device': 'cheetah', 'product': 'cheetah', 'hardware': 'gs101'},
        'Pixel 7a': {'device': 'lynx', 'product': 'lynx', 'hardware': 'gs101'},
        'Pixel 6': {'device': 'oriole', 'product': 'oriole', 'hardware': 'gs101'},
        'Pixel 6 Pro': {'device': 'raven', 'product': 'raven', 'hardware': 'gs101'},
        'Pixel 6a': {'device': 'bluejay', 'product': 'bluejay', 'hardware': 'gs101'},
    },
    'OnePlus': {
        'OnePlus 11': {'device': 'salami', 'product': 'salami', 'hardware': 'qcom'},
        'OnePlus 10 Pro': {'device': 'NE2215', 'product': 'NE2215', 'hardware': 'qcom'},
        'OnePlus 10T': {'device': 'ovaltine', 'product': 'ovaltine', 'hardware': 'qcom'},
        'OnePlus 9': {'device': 'lemonade', 'product': 'lemonade', 'hardware': 'qcom'},
        'OnePlus 9 Pro': {'device': 'lemonadep', 'product': 'lemonadep', 'hardware': 'qcom'},
        'OnePlus Nord 3': {'device': 'larry', 'product': 'larry', 'hardware': 'mtk'},
    },
    'Oppo': {
        'Oppo Find X6 Pro': {'device': 'PGEM10', 'product': 'PGEM10', 'hardware': 'qcom'},
        'Oppo Find X5 Pro': {'device': 'PFFM10', 'product': 'PFFM10', 'hardware': 'qcom'},
        'Oppo Reno10 Pro': {'device': 'PGFM10', 'product': 'PGFM10', 'hardware': 'qcom'},
        'Oppo Reno9 Pro': {'device': 'PFGM00', 'product': 'PFGM00', 'hardware': 'mtk'},
    },
    'Realme': {
        'Realme GT3': {'device': 'RMX3709', 'product': 'RMX3709', 'hardware': 'qcom'},
        'Realme GT2 Pro': {'device': 'RMX3301', 'product': 'RMX3301', 'hardware': 'qcom'},
        'Realme 11 Pro': {'device': 'RMX3771', 'product': 'RMX3771', 'hardware': 'mtk'},
        'Realme 10 Pro': {'device': 'RMX3661', 'product': 'RMX3661', 'hardware': 'qcom'},
    },
    'Huawei': {
        'Huawei P60 Pro': {'device': 'MNA', 'product': 'MNA-AL00', 'hardware': 'kirin'},
        'Huawei Mate 50 Pro': {'device': 'DCO', 'product': 'DCO-AL00', 'hardware': 'qcom'},
        'Huawei P50 Pro': {'device': 'JAD', 'product': 'JAD-AL50', 'hardware': 'kirin'},
    },
    'Vivo': {
        'Vivo X90 Pro': {'device': 'V2227A', 'product': 'V2227A', 'hardware': 'mtk'},
        'Vivo X80 Pro': {'device': 'V2185A', 'product': 'V2185A', 'hardware': 'qcom'},
        'iQOO 11': {'device': 'V2243A', 'product': 'V2243A', 'hardware': 'qcom'},
    },
    'Honor': {
        'Honor Magic5 Pro': {'device': 'PGT', 'product': 'PGT-AN10', 'hardware': 'qcom'},
        'Honor 90': {'device': 'REA', 'product': 'REA-AN00', 'hardware': 'qcom'},
        'Honor Magic4 Pro': {'device': 'LGE', 'product': 'LGE-AN10', 'hardware': 'qcom'},
    },
    'Motorola': {
        'Motorola Edge 40 Pro': {'device': 'rtwo', 'product': 'rtwo', 'hardware': 'qcom'},
        'Motorola Edge 30 Ultra': {'device': 'eqs', 'product': 'eqs', 'hardware': 'qcom'},
        'Motorola Razr 40 Ultra': {'device': 'zeekr', 'product': 'zeekr', 'hardware': 'qcom'},
    },
}

# Build ID patterns for different Android versions
BUILD_IDS = {
    '11': ['RQ3A.211001.001', 'RKQ1.211001.001', 'RP1A.201005.004'],
    '12': ['SP1A.210812.015', 'SKQ1.220303.001', 'SP2A.220505.002'],
    '13': ['TQ3A.230605.011', 'TKQ1.221114.001', 'TP1A.220624.014'],
    '14': ['UP1A.231005.007', 'UKQ1.230917.001', 'AP2A.240805.005'],
}

# Security patch dates (realistic recent dates)
SECURITY_PATCHES = [
    '2024-11-01', '2024-10-01', '2024-09-01', '2024-08-01',
    '2024-07-01', '2024-06-01', '2024-05-01', '2024-04-01',
]


def get_db_connection(host: str, port: int, user: str, password: str, database: str):
    """Create database connection"""
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database
    )


def fetch_random_device(conn, brands: list, min_year: int) -> Optional[dict]:
    """Fetch a random device from GSMArena database matching criteria"""

    # Build brand filter
    brand_placeholders = ', '.join(['%s'] * len(brands))

    # Build budget keyword exclusion
    budget_conditions = ' AND '.join([f"model_name NOT LIKE '%{kw}%'" for kw in BUDGET_KEYWORDS])

    query = f"""
        SELECT
            brand,
            model_name,
            chipset,
            cpu,
            os,
            release_year
        FROM zip_gsmarena_raw
        WHERE brand IN ({brand_placeholders})
          AND release_year >= %s
          AND os LIKE '%Android%'
          AND {budget_conditions}
        ORDER BY RANDOM()
        LIMIT 1
    """

    cursor = conn.cursor()
    cursor.execute(query, (*brands, min_year))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        return None

    return {
        'brand': row[0],
        'model_name': row[1],
        'chipset': row[2],
        'cpu': row[3],
        'os': row[4],
        'release_year': row[5],
    }


def parse_android_version(os_string: str) -> str:
    """Extract Android version from OS string"""
    if not os_string:
        return '13'

    # Try to find version number like "Android 13" or "Android 14"
    import re
    match = re.search(r'Android\s+(\d+)', os_string)
    if match:
        return match.group(1)

    return '13'  # Default to Android 13


def get_sdk_version(android_version: str) -> str:
    """Get SDK version from Android version"""
    sdk_map = {
        '11': '30',
        '12': '31',
        '12L': '32',
        '13': '33',
        '14': '34',
    }
    return sdk_map.get(android_version, '33')


def determine_hardware(chipset: str) -> str:
    """Determine hardware type from chipset name"""
    if not chipset:
        return 'qcom'

    chipset_lower = chipset.lower()

    if 'snapdragon' in chipset_lower or 'qualcomm' in chipset_lower:
        return 'qcom'
    elif 'dimensity' in chipset_lower or 'helio' in chipset_lower or 'mediatek' in chipset_lower:
        return 'mtk'
    elif 'exynos' in chipset_lower or 'samsung' in chipset_lower:
        return 'exynos'
    elif 'tensor' in chipset_lower or 'google' in chipset_lower:
        return 'gs201'
    elif 'kirin' in chipset_lower or 'hisilicon' in chipset_lower:
        return 'kirin'
    elif 'apple' in chipset_lower:
        return 'apple'

    return 'qcom'  # Default


def generate_device_codename(brand: str, model: str) -> dict:
    """Generate device codename and product name"""

    # Check if we have known codenames
    if brand in DEVICE_CODENAMES:
        for known_model, codes in DEVICE_CODENAMES[brand].items():
            if known_model.lower() in model.lower() or model.lower() in known_model.lower():
                return codes

    # Generate codenames based on brand conventions
    manufacturer = brand.lower()

    if brand == 'Samsung':
        # Samsung uses letter combinations
        device = f"sm{random.randint(100, 999)}q"
        product = f"{device}xx"
    elif brand == 'Xiaomi':
        # Xiaomi uses nature names
        names = ['jasmine', 'violet', 'lavender', 'tulip', 'begonia', 'cezanne', 'picasso']
        device = random.choice(names)
        product = device
    elif brand == 'Google':
        # Google uses animal names
        names = ['panther', 'cheetah', 'lynx', 'oriole', 'raven', 'bluejay', 'felix']
        device = random.choice(names)
        product = device
    elif brand == 'OnePlus':
        # OnePlus uses food names or model codes
        names = ['lemonade', 'salami', 'avocado', 'kebab', 'hotdog', 'instantnoodle']
        device = random.choice(names)
        product = device
    elif brand in ['Oppo', 'Realme', 'Vivo']:
        # These use model numbers
        device = f"RMX{random.randint(3000, 4000)}"
        product = device
    else:
        # Generic
        device = f"{manufacturer[:3]}{random.randint(100, 999)}"
        product = device

    return {
        'device': device,
        'product': product,
        'hardware': 'qcom'
    }


def generate_build_number(brand: str, android_version: str) -> str:
    """Generate realistic build number for device"""

    # Samsung format: S911BXXU2AWA1
    if brand == 'Samsung':
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        return f"S{random.randint(100, 999)}B{random.choice(letters)}{random.choice(letters)}U{random.randint(1, 5)}A{random.choice(letters)}{random.choice(letters)}{random.randint(1, 9)}"

    # Google format: AP2A.240805.005
    elif brand == 'Google':
        return f"AP{android_version[0]}A.{random.randint(230101, 241231)}.{random.randint(1, 99):03d}"

    # Xiaomi format: V14.0.8.0.TMCEUXM
    elif brand == 'Xiaomi':
        region = random.choice(['EEA', 'GLO', 'CHN', 'IND'])
        return f"V{android_version}.0.{random.randint(1, 20)}.0.T{random.choice(['M', 'K', 'L'])}{random.choice(['C', 'F', 'B'])}E{region[0]}{region[1]}M"

    # OnePlus format: LE2115_11.C.21_0210_202301011200
    elif brand == 'OnePlus':
        return f"LE{random.randint(2000, 2500)}_{android_version}.C.{random.randint(10, 30)}_{random.randint(100, 999)}_{random.randint(2023, 2024)}{random.randint(1, 12):02d}{random.randint(1, 28):02d}{random.randint(1000, 2359):04d}"

    # Generic format
    else:
        return f"{brand[:3].upper()}{random.randint(1000, 9999)}.{random.randint(1, 12):02d}.{random.randint(1, 28):02d}"


def generate_fingerprint(brand: str, product: str, device: str, android_version: str,
                          build_id: str, build_number: str) -> str:
    """Generate Android fingerprint in standard format"""
    # Format: brand/product/device:version/build_id/build_number:type/tags
    manufacturer = brand.lower()
    return f"{manufacturer}/{product}/{device}:{android_version}/{build_id}/{build_number}:user/release-keys"


def generate_profile(db_device: dict) -> dict:
    """Generate complete device profile from database device info"""

    brand = db_device['brand']
    model = db_device['model_name']

    # Parse Android version
    android_version = parse_android_version(db_device.get('os', ''))
    sdk_version = get_sdk_version(android_version)

    # Get device codenames
    codenames = generate_device_codename(brand, model)
    device = codenames['device']
    product = codenames['product']
    hardware = codenames.get('hardware') or determine_hardware(db_device.get('chipset'))

    # Generate build info
    build_id = random.choice(BUILD_IDS.get(android_version, BUILD_IDS['13']))
    build_number = generate_build_number(brand, android_version)
    security_patch = random.choice(SECURITY_PATCHES)

    # Generate fingerprint
    fingerprint = generate_fingerprint(brand, product, device, android_version, build_id, build_number)

    profile = {
        'brand': brand,
        'model': model,
        'device': device,
        'product': product,
        'manufacturer': brand.lower(),
        'hardware': hardware,
        'chipset': db_device.get('chipset', 'Unknown'),
        'cpu': db_device.get('cpu', 'Unknown'),
        'android_version': android_version,
        'sdk_version': sdk_version,
        'build_id': build_id,
        'build_number': build_number,
        'security_patch': security_patch,
        'fingerprint': fingerprint,
        'release_year': db_device.get('release_year', 2023),
        'source': 'gsmarena_db',
    }

    return profile


def main():
    parser = argparse.ArgumentParser(description='Generate random device profile from GSMArena DB')
    parser.add_argument('--db-host', default=os.environ.get('GSMARENA_DB_HOST', '85.198.98.104'),
                        help='Database host')
    parser.add_argument('--db-port', type=int, default=int(os.environ.get('GSMARENA_DB_PORT', 5433)),
                        help='Database port')
    parser.add_argument('--db-user', default=os.environ.get('GSMARENA_DB_USER', 'postgres'),
                        help='Database user')
    parser.add_argument('--db-password', default=os.environ.get('GSMARENA_DB_PASSWORD', ''),
                        help='Database password')
    parser.add_argument('--db-name', default=os.environ.get('GSMARENA_DB_NAME', 'postgres'),
                        help='Database name')
    parser.add_argument('--output', '-o', required=True,
                        help='Output JSON file path')
    parser.add_argument('--brand', action='append', dest='brands',
                        help='Specific brand to use (can be repeated)')
    parser.add_argument('--min-year', type=int, default=MIN_RELEASE_YEAR,
                        help=f'Minimum release year (default: {MIN_RELEASE_YEAR})')

    args = parser.parse_args()

    # Use specified brands or defaults
    brands = args.brands if args.brands else ALLOWED_BRANDS

    print(f"=== Device Profile Generator ===")
    print(f"Database: {args.db_host}:{args.db_port}")
    print(f"Brands: {', '.join(brands)}")
    print(f"Min year: {args.min_year}")

    try:
        # Connect to database
        print("\nConnecting to database...")
        conn = get_db_connection(
            args.db_host, args.db_port,
            args.db_user, args.db_password,
            args.db_name
        )

        # Fetch random device
        print("Selecting random device...")
        db_device = fetch_random_device(conn, brands, args.min_year)
        conn.close()

        if not db_device:
            print("ERROR: No device found matching criteria!")
            sys.exit(1)

        print(f"Selected: {db_device['brand']} {db_device['model_name']} ({db_device['release_year']})")

        # Generate profile
        print("Generating device profile...")
        profile = generate_profile(db_device)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(args.output), exist_ok=True)

        # Save profile
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

        print(f"\n=== Profile Generated ===")
        print(f"Brand: {profile['brand']}")
        print(f"Model: {profile['model']}")
        print(f"Device: {profile['device']}")
        print(f"Product: {profile['product']}")
        print(f"Android: {profile['android_version']} (SDK {profile['sdk_version']})")
        print(f"Build: {profile['build_id']}")
        print(f"Fingerprint: {profile['fingerprint']}")
        print(f"\nSaved to: {args.output}")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
