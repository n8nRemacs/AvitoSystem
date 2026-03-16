#!/usr/bin/env python3
"""
Check Android Device/Emulator Build Properties

This script displays the Build properties that Avito uses to identify the device.
Use after running 03_mask_device.bat to verify masking was successful.

Usage:
    python check_device_info.py

Expected output after masking:
    Model:        Pixel 6
    Manufacturer: Google
    Brand:        google
"""

import subprocess
import sys


def run_adb_command(command):
    """Execute ADB command and return output"""
    try:
        result = subprocess.run(
            f"adb shell {command}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: Command timeout"
    except Exception as e:
        return f"ERROR: {str(e)}"


def check_adb_connection():
    """Check if ADB device is connected"""
    try:
        result = subprocess.run(
            "adb devices",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        lines = result.stdout.strip().split('\n')
        devices = [line for line in lines if '\tdevice' in line]

        return len(devices) > 0
    except Exception:
        return False


def main():
    """Main function"""
    print("=" * 70)
    print(" " * 20 + "DEVICE INFORMATION CHECK")
    print("=" * 70)
    print()

    # Check ADB connection
    if not check_adb_connection():
        print("❌ ERROR: No Android device/emulator connected!")
        print()
        print("Please:")
        print("  1. Start the emulator (scripts/02_start_emulator.bat)")
        print("  2. Wait for it to fully boot (~2-3 minutes)")
        print("  3. Run this script again")
        print()
        print("=" * 70)
        sys.exit(1)

    print("✅ Device connected")
    print()

    # Get device properties
    properties = {
        "Model": run_adb_command("getprop ro.product.model"),
        "Manufacturer": run_adb_command("getprop ro.product.manufacturer"),
        "Brand": run_adb_command("getprop ro.product.brand"),
        "Device": run_adb_command("getprop ro.product.device"),
        "Product Name": run_adb_command("getprop ro.product.name"),
        "Android Version": run_adb_command("getprop ro.build.version.release"),
        "API Level": run_adb_command("getprop ro.build.version.sdk"),
        "Build ID": run_adb_command("getprop ro.build.id"),
        "Build Type": run_adb_command("getprop ro.build.type"),
    }

    # Display properties
    print("-" * 70)
    print(" " * 25 + "BUILD PROPERTIES")
    print("-" * 70)

    max_key_length = max(len(key) for key in properties.keys())

    for key, value in properties.items():
        print(f"{key:<{max_key_length + 2}}: {value}")

    print("-" * 70)
    print()

    # Get Build Fingerprint (can be long)
    fingerprint = run_adb_command("getprop ro.build.fingerprint")
    print("Build Fingerprint:")
    if len(fingerprint) > 66:
        print(f"  {fingerprint[:66]}...")
        print(f"  {fingerprint[66:]}")
    else:
        print(f"  {fingerprint}")

    print()
    print("=" * 70)
    print()

    # Check if device is masked
    model = properties["Model"]
    manufacturer = properties["Manufacturer"]

    if "sdk" in model.lower() or "emulator" in model.lower():
        print("⚠️  WARNING: Device still appears as an emulator!")
        print()
        print("   Current Model:", model)
        print("   Expected:      Pixel 6")
        print()
        print("   Run scripts/03_mask_device.bat to fix this.")
    elif model == "Pixel 6" and manufacturer == "Google":
        print("✅ SUCCESS: Device is properly masked as Google Pixel 6!")
        print()
        print("   Avito should see:")
        print("   - Device: Google Pixel 6")
        print("   - No emulator detection")
    else:
        print("ℹ️  INFO: Device has custom properties")
        print()
        print(f"   Model:        {model}")
        print(f"   Manufacturer: {manufacturer}")

    print()
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        sys.exit(1)
