#!/usr/bin/env python3
"""
Download Avito APK from APKPure
"""
import os
import sys
import subprocess

print("=" * 60)
print("Avito APK Downloader")
print("=" * 60)

# APKPure direct link (latest version)
APK_URL = "https://d.apkpure.com/b/APK/com.avito.android?version=latest"
APK_OUTPUT = "avito.apk"

print("\n[1/3] Downloading Avito APK from APKPure...")
print(f"URL: {APK_URL}")
print(f"Output: {APK_OUTPUT}")

# Use curl to download
cmd = [
    "curl",
    "-L",  # Follow redirects
    "-o", APK_OUTPUT,
    "--progress-bar",
    APK_URL
]

try:
    result = subprocess.run(cmd, check=True, cwd="../")
    print(f"\n✓ Downloaded successfully to ../avito.apk")

    # Check file size
    if os.path.exists("../avito.apk"):
        size = os.path.getsize("../avito.apk") / (1024 * 1024)
        print(f"✓ File size: {size:.1f} MB")

        if size < 10:
            print("\n⚠ WARNING: File seems too small (< 10 MB)")
            print("  The download might have failed or redirected to a webpage")
            print("\n  Alternative: Download manually from:")
            print("  https://apkpure.com/avito/com.avito.android")
            print("  Save as: C:\\Users\\Dimon\\Pojects\\Reverce\\APK\\Avito\\avito.apk")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ APK ready to install!")
    print("=" * 60)

except subprocess.CalledProcessError as e:
    print(f"\n✗ Error downloading: {e}")
    print("\n  Manual download instructions:")
    print("  1. Open: https://apkpure.com/avito/com.avito.android")
    print("  2. Click 'Download APK' button")
    print("  3. Save to: C:\\Users\\Dimon\\Pojects\\Reverce\\APK\\Avito\\avito.apk")
    sys.exit(1)
