#!/usr/bin/env python3
"""
Check device masking on Redroid
"""
import subprocess
import sys

def docker_exec(command):
    """Execute command in Redroid container"""
    cmd = ['docker', 'exec', 'avito-redroid', 'sh', '-c', command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def main():
    print("=" * 60)
    print("Device Masking Check")
    print("=" * 60)

    # Check if container is running
    result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
    if 'avito-redroid' not in result.stdout:
        print("\n[X] Redroid container is not running")
        print("\nStart it with: scripts\\02_start_redroid.bat")
        sys.exit(1)

    print("\n[OK] Redroid is running")

    # Get device properties
    props = {
        'Model': docker_exec('getprop ro.product.model'),
        'Manufacturer': docker_exec('getprop ro.product.manufacturer'),
        'Brand': docker_exec('getprop ro.product.brand'),
        'Device': docker_exec('getprop ro.product.device'),
        'Name': docker_exec('getprop ro.product.name'),
        'Fingerprint': docker_exec('getprop ro.build.fingerprint'),
        'Android Version': docker_exec('getprop ro.build.version.release'),
        'API Level': docker_exec('getprop ro.build.version.sdk'),
    }

    print("\nDevice Properties:")
    print("-" * 60)

    for key, value in props.items():
        if value:
            print(f"{key:20s}: {value}")
        else:
            print(f"{key:20s}: [NOT SET]")

    # Check if masked as Pixel 6
    is_masked = (
        props.get('Model') == 'Pixel 6' and
        props.get('Manufacturer') == 'Google' and
        props.get('Brand') == 'google'
    )

    print("\n" + "=" * 60)
    if is_masked:
        print("STATUS: Device is masked as Google Pixel 6")
        print("=" * 60)
        print("\n[OK] Avito will see this as real Pixel 6 device")
    else:
        print("STATUS: Device is NOT masked properly")
        print("=" * 60)
        print("\n[!] Warning: Avito may detect this as emulator/container")
        print("\nTo fix:")
        print("  1. Run: scripts\\03_setup_device.bat")
        print("  2. Or restart container to apply build.prop")
        sys.exit(1)

    # Additional checks for emulator indicators
    print("\nEmulator Detection Check:")
    print("-" * 60)

    emulator_indicators = {
        'QEMU': docker_exec('getprop ro.kernel.qemu'),
        'Goldfish': docker_exec('getprop ro.hardware | grep goldfish'),
        'Ranchu': docker_exec('getprop ro.hardware | grep ranchu'),
        'Emulator': docker_exec('getprop ro.build.characteristics | grep emulator'),
    }

    has_indicators = False
    for indicator, value in emulator_indicators.items():
        status = "FOUND" if value and value != '0' else "OK"
        symbol = "[!]" if status == "FOUND" else "[OK]"
        print(f"{symbol} {indicator:20s}: {status}")
        if status == "FOUND":
            has_indicators = True

    if has_indicators:
        print("\n[!] Warning: Some emulator indicators present")
        print("    This may not be a problem with Redroid")
    else:
        print("\n[OK] No emulator indicators found")

    print("\n" + "=" * 60)
    print("Device check complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()
