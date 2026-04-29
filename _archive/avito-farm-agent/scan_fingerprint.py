"""Static analysis: scan Avito APK DEX files for fingerprint-related code.

Searches for device identification APIs, tracking IDs, and fingerprinting patterns.
"""

import json
import os
import sys
import zipfile

APK_PATH = os.path.join(os.path.dirname(__file__), "apk_work", "avito.apk")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "fingerprint_analysis.json")

# Patterns to search in DEX string tables
PATTERNS = {
    # Device identification
    "ANDROID_ID": "Settings.Secure.ANDROID_ID",
    "android_id": "android_id string literal",
    "getDeviceId": "TelephonyManager.getDeviceId (IMEI pre-Q)",
    "getImei": "TelephonyManager.getImei",
    "getSubscriberId": "TelephonyManager.getSubscriberId (IMSI)",
    "getLine1Number": "TelephonyManager.getLine1Number (phone number)",
    "getSimSerialNumber": "TelephonyManager.getSimSerialNumber",
    "getMacAddress": "WifiInfo.getMacAddress or BluetoothAdapter.getAddress",
    "getSSID": "WifiInfo.getSSID",
    "getBSSID": "WifiInfo.getBSSID",

    # Build info
    "Build.MODEL": "device model",
    "Build.MANUFACTURER": "manufacturer",
    "Build.BRAND": "brand",
    "Build.DEVICE": "device codename",
    "Build.PRODUCT": "product name",
    "Build.FINGERPRINT": "build fingerprint",
    "Build.HARDWARE": "hardware name",
    "Build.BOARD": "board name",
    "Build.DISPLAY": "build display string",
    "Build.HOST": "build host",
    "Build.SERIAL": "device serial (deprecated)",
    "VERSION.SDK_INT": "Android SDK version",
    "VERSION.RELEASE": "Android version string",

    # Advertising / tracking IDs
    "AdvertisingIdClient": "Google Advertising ID client",
    "advertisingId": "advertising ID",
    "getAdvertisingIdInfo": "get Google GAID",
    "appsflyerId": "AppsFlyer tracking ID",
    "AppsFlyerLib": "AppsFlyer SDK",
    "adjustId": "Adjust tracking ID",
    "Adjust.getAdid": "Adjust ADID",

    # Screen / display
    "DisplayMetrics": "screen metrics",
    "getMetrics": "get display metrics",
    "densityDpi": "screen density",
    "widthPixels": "screen width",
    "heightPixels": "screen height",

    # Sensors
    "SensorManager": "sensor access",
    "getSensorList": "enumerate sensors",
    "TYPE_ACCELEROMETER": "accelerometer sensor",
    "TYPE_GYROSCOPE": "gyroscope sensor",

    # Network
    "getUserAgent": "WebView user agent",
    "NetworkInterface": "network interfaces",
    "getNetworkInterfaces": "enumerate network interfaces",

    # Installed apps
    "getInstalledPackages": "list installed packages",
    "getInstalledApplications": "list installed apps",

    # Custom fingerprint headers
    "X-Device-Id": "custom device ID header",
    "X-Device-Fingerprint": "custom fingerprint header",
    "X-Fingerprint": "fingerprint header",
    "device_id": "device_id field",
    "device_fingerprint": "device fingerprint field",
    "deviceId": "deviceId field",
    "deviceFingerprint": "deviceFingerprint field",
    "fingerprint_data": "fingerprint data field",

    # System properties
    "getprop": "system property access",
    "SystemProperties": "SystemProperties access",
    "ro.build": "build system property",
    "ro.product": "product system property",
    "ro.hardware": "hardware system property",
    "ro.serialno": "serial number property",

    # Root / tamper detection
    "su": None,  # too generic, skip counting
    "Superuser": "root detection (Superuser)",
    "Magisk": "Magisk detection",
    "isRooted": "root detection",
    "RootBeer": "RootBeer detection library",
    "SafetyNet": "Google SafetyNet",
    "PlayIntegrity": "Play Integrity API",

    # Frida detection
    "frida": "Frida detection",
    "27042": "Frida default port",
    "xposed": "Xposed detection",

    # Crypto / hashing (for fingerprint generation)
    "MessageDigest": "hashing (MD5/SHA)",
    "getInstance": None,  # too generic

    # GL / GPU
    "GL_RENDERER": "GPU renderer",
    "GL_VENDOR": "GPU vendor",
    "GL_VERSION": "GL version",
    "GLES20": "OpenGL ES 2.0",

    # Timezone / locale
    "TimeZone": "timezone",
    "getDefault": None,  # too generic
    "Locale": "locale info",

    # Battery
    "BatteryManager": "battery info",
    "BATTERY_PROPERTY": "battery property",

    # Clipboard
    "ClipboardManager": "clipboard access",
}


def scan_dex_strings(apk_path):
    """Extract strings from all DEX files and search for patterns."""
    results = {}

    with zipfile.ZipFile(apk_path, "r") as z:
        dex_files = sorted(n for n in z.namelist() if n.endswith(".dex"))
        print(f"[*] Scanning {len(dex_files)} DEX files...")

        for dex_name in dex_files:
            data = z.read(dex_name)
            # DEX strings are stored as UTF-8 in the string table
            # Quick approach: search raw bytes
            text = data.decode("utf-8", errors="ignore")

            for pattern, desc in PATTERNS.items():
                if desc is None:
                    continue
                if pattern in text:
                    if pattern not in results:
                        results[pattern] = {
                            "description": desc,
                            "found_in": [],
                            "context": [],
                        }
                    results[pattern]["found_in"].append(dex_name)

                    # Try to find surrounding context
                    idx = 0
                    contexts_found = 0
                    while contexts_found < 3:
                        idx = text.find(pattern, idx)
                        if idx == -1:
                            break
                        # Get surrounding readable text
                        start = max(0, idx - 60)
                        end = min(len(text), idx + len(pattern) + 60)
                        snippet = text[start:end]
                        # Clean non-printable
                        clean = "".join(c if c.isprintable() else "." for c in snippet)
                        if clean.strip("."):
                            results[pattern]["context"].append(clean.strip())
                        idx += len(pattern)
                        contexts_found += 1

    return results


def scan_manifest_permissions(apk_path):
    """Extract permissions from APK manifest."""
    from androguard.core.apk import APK
    import logging
    logging.disable(logging.DEBUG)

    a = APK(apk_path)
    perms = a.get_permissions()
    fp_keywords = [
        "phone", "location", "bluetooth", "wifi", "camera",
        "fingerprint", "biometric", "network", "telephony",
        "read_phone", "access_fine", "access_coarse", "internet",
        "nfc", "sensor",
    ]
    fp_perms = [p for p in perms if any(k in p.lower() for k in fp_keywords)]
    return {
        "total_permissions": len(perms),
        "fingerprint_relevant": fp_perms,
        "all_permissions": list(perms),
        "package": a.get_package(),
        "version": a.get_androidversion_name(),
        "target_sdk": a.get_target_sdk_version(),
        "min_sdk": a.get_min_sdk_version(),
    }


def main():
    if not os.path.exists(APK_PATH):
        print(f"[-] APK not found: {APK_PATH}")
        sys.exit(1)

    print(f"[*] Analyzing: {APK_PATH}")
    print(f"[*] Size: {os.path.getsize(APK_PATH) / 1024 / 1024:.1f} MB")

    # Scan DEX files
    dex_results = scan_dex_strings(APK_PATH)

    # Scan manifest
    print("[*] Scanning manifest permissions...")
    try:
        manifest_info = scan_manifest_permissions(APK_PATH)
    except Exception as e:
        print(f"[-] Manifest scan failed: {e}")
        manifest_info = {"error": str(e)}

    # Compile results
    report = {
        "apk_info": manifest_info,
        "fingerprint_apis": {},
        "tracking_sdks": {},
        "detection_mechanisms": {},
        "display_info": {},
        "other": {},
    }

    # Categorize findings
    categories = {
        "fingerprint_apis": [
            "ANDROID_ID", "android_id", "getDeviceId", "getImei",
            "getSubscriberId", "getLine1Number", "getSimSerialNumber",
            "getMacAddress", "getSSID", "getBSSID", "Build.MODEL",
            "Build.MANUFACTURER", "Build.BRAND", "Build.DEVICE",
            "Build.PRODUCT", "Build.FINGERPRINT", "Build.HARDWARE",
            "Build.BOARD", "Build.DISPLAY", "Build.HOST", "Build.SERIAL",
            "VERSION.SDK_INT", "VERSION.RELEASE", "getprop",
            "SystemProperties", "ro.build", "ro.product", "ro.hardware",
            "ro.serialno", "MessageDigest", "GL_RENDERER", "GL_VENDOR",
            "GL_VERSION", "GLES20", "SensorManager", "getSensorList",
            "TYPE_ACCELEROMETER", "TYPE_GYROSCOPE", "NetworkInterface",
            "getNetworkInterfaces", "getUserAgent", "getInstalledPackages",
            "getInstalledApplications", "TimeZone", "Locale",
            "BatteryManager", "BATTERY_PROPERTY", "ClipboardManager",
        ],
        "tracking_sdks": [
            "AdvertisingIdClient", "advertisingId", "getAdvertisingIdInfo",
            "appsflyerId", "AppsFlyerLib", "adjustId", "Adjust.getAdid",
        ],
        "detection_mechanisms": [
            "Superuser", "Magisk", "isRooted", "RootBeer",
            "SafetyNet", "PlayIntegrity", "frida", "27042", "xposed",
        ],
        "display_info": [
            "DisplayMetrics", "getMetrics", "densityDpi",
            "widthPixels", "heightPixels",
        ],
        "other": [
            "X-Device-Id", "X-Device-Fingerprint", "X-Fingerprint",
            "device_id", "device_fingerprint", "deviceId",
            "deviceFingerprint", "fingerprint_data",
        ],
    }

    for cat, patterns in categories.items():
        for pat in patterns:
            if pat in dex_results:
                report[cat][pat] = dex_results[pat]

    # Save JSON report
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'=' * 60}")
    print("AVITO FINGERPRINT ANALYSIS REPORT")
    print(f"{'=' * 60}")

    if isinstance(manifest_info, dict) and "package" in manifest_info:
        print(f"\nPackage: {manifest_info['package']}")
        print(f"Version: {manifest_info['version']}")
        print(f"Target SDK: {manifest_info['target_sdk']}")
        print(f"Min SDK: {manifest_info['min_sdk']}")
        print(f"\nFingerprint-relevant permissions ({len(manifest_info.get('fingerprint_relevant', []))}):")
        for p in manifest_info.get("fingerprint_relevant", []):
            print(f"  - {p}")

    for cat, label in [
        ("fingerprint_apis", "DEVICE FINGERPRINT APIs"),
        ("tracking_sdks", "TRACKING SDKs"),
        ("detection_mechanisms", "ROOT/TAMPER DETECTION"),
        ("display_info", "DISPLAY INFO"),
        ("other", "CUSTOM HEADERS/FIELDS"),
    ]:
        items = report[cat]
        if items:
            print(f"\n{label} ({len(items)} found):")
            for pat, info in sorted(items.items()):
                files = ", ".join(info["found_in"][:3])
                print(f"  [{pat}] {info['description']}")
                print(f"    Found in: {files}")
                if info["context"]:
                    print(f"    Context: {info['context'][0][:100]}")

    print(f"\n[*] Full report: {OUTPUT_FILE}")
    print(f"[*] Total patterns found: {len(dex_results)}")


if __name__ == "__main__":
    main()
