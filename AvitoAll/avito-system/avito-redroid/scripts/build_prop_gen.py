#!/usr/bin/env python3
"""
Build.prop Generator for Avito Redroid Masking
Generates Android build.prop file from device profile
"""

import argparse
import json
import os
import sys
from datetime import datetime


def generate_build_prop(profile: dict) -> str:
    """Generate build.prop content from device profile"""

    brand = profile['brand']
    model = profile['model']
    device = profile['device']
    product = profile['product']
    manufacturer = profile['manufacturer']
    hardware = profile['hardware']
    android_version = profile['android_version']
    sdk_version = profile['sdk_version']
    build_id = profile['build_id']
    build_number = profile['build_number']
    security_patch = profile['security_patch']
    fingerprint = profile['fingerprint']

    # Generate timestamps
    now = datetime.now()
    build_date = now.strftime('%a %b %d %H:%M:%S UTC %Y')
    build_date_utc = int(now.timestamp())

    # Build description
    build_description = f"{product}-user {android_version} {build_id} {build_number} release-keys"

    build_prop = f"""# Build.prop generated for Avito Redroid Masking
# Device: {brand} {model}
# Generated: {now.isoformat()}

#
# PRODUCT
#
ro.product.model={model}
ro.product.brand={brand}
ro.product.name={product}
ro.product.device={device}
ro.product.manufacturer={manufacturer}
ro.product.board={hardware}

ro.product.system.brand={brand}
ro.product.system.device={device}
ro.product.system.manufacturer={manufacturer}
ro.product.system.model={model}
ro.product.system.name={product}

ro.product.vendor.brand={brand}
ro.product.vendor.device={device}
ro.product.vendor.manufacturer={manufacturer}
ro.product.vendor.model={model}
ro.product.vendor.name={product}

ro.product.odm.brand={brand}
ro.product.odm.device={device}
ro.product.odm.manufacturer={manufacturer}
ro.product.odm.model={model}
ro.product.odm.name={product}

#
# BUILD
#
ro.build.id={build_id}
ro.build.display.id={build_number}
ro.build.version.incremental={build_number}
ro.build.version.sdk={sdk_version}
ro.build.version.release={android_version}
ro.build.version.release_or_codename={android_version}
ro.build.version.security_patch={security_patch}
ro.build.version.base_os=
ro.build.version.preview_sdk=0
ro.build.version.codename=REL
ro.build.version.all_codenames=REL
ro.build.version.min_supported_target_sdk=23
ro.build.type=user
ro.build.user=android-build
ro.build.host=build.android.com
ro.build.tags=release-keys
ro.build.flavor={product}-user
ro.build.product={device}
ro.build.description={build_description}
ro.build.date={build_date}
ro.build.date.utc={build_date_utc}
ro.build.characteristics=default

#
# FINGERPRINT
#
ro.build.fingerprint={fingerprint}
ro.build.version.fingerprint={fingerprint}
ro.bootimage.build.fingerprint={fingerprint}
ro.vendor.build.fingerprint={fingerprint}
ro.odm.build.fingerprint={fingerprint}
ro.system.build.fingerprint={fingerprint}
ro.system_ext.build.fingerprint={fingerprint}
ro.product.build.fingerprint={fingerprint}

#
# HARDWARE
#
ro.hardware={hardware}
ro.hardware.chipname={hardware}
ro.board.platform={hardware}
ro.baseband=unknown

#
# BOOTLOADER
#
ro.bootloader=unknown
ro.boot.hardware={hardware}
ro.boot.verifiedbootstate=green
ro.boot.flash.locked=1
ro.boot.veritymode=enforcing
ro.boot.vbmeta.device_state=locked

#
# EMULATOR MASKING - CRITICAL
#
ro.kernel.qemu=0
ro.kernel.android.qemud=0
ro.kernel.qemu.gles=0
ro.kernel.androidboot.hardware={hardware}
init.svc.qemu-props=stopped
init.svc.goldfish-setup=stopped
init.svc.goldfish-logcat=stopped

#
# SECURITY
#
ro.secure=1
ro.adb.secure=1
ro.debuggable=0
ro.allow.mock.location=0
persist.sys.usb.config=none
ro.oem_unlock_supported=0

#
# DALVIK
#
dalvik.vm.heapstartsize=8m
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.heapminfree=512k
dalvik.vm.heapmaxfree=8m
dalvik.vm.dex2oat-Xms=64m
dalvik.vm.dex2oat-Xmx=512m
dalvik.vm.dex2oat-threads=4
dalvik.vm.image-dex2oat-Xms=64m
dalvik.vm.image-dex2oat-Xmx=64m
dalvik.vm.image-dex2oat-threads=4
dalvik.vm.usejit=true
dalvik.vm.usejitprofiles=true
dalvik.vm.dexopt.secondary=true

#
# SYSTEM
#
ro.config.notification_sound=OnTheHunt.ogg
ro.config.alarm_alert=Alarm_Classic.ogg
persist.sys.dalvik.vm.lib.2=libart.so
ro.url.legal=http://www.google.com/intl/%s/mobile/android/basic/phone-legal.html
ro.url.legal.android_privacy=http://www.google.com/intl/%s/mobile/android/basic/privacy.html
ro.com.google.clientidbase=android-google
ro.com.google.gmsversion={android_version}_202311

#
# WIFI
#
wifi.interface=wlan0
wifi.direct.interface=p2p0

#
# GRAPHICS
#
ro.opengles.version=196610
debug.hwui.renderer=skiavk
ro.hardware.egl={hardware}
ro.hardware.vulkan={hardware}

#
# ADDITIONAL MASKING
#
gsm.version.baseband=unknown
gsm.version.ril-impl=android mediatek-ril
gsm.sim.operator.numeric=
gsm.sim.operator.alpha=
gsm.sim.operator.iso-country=
gsm.sim.state=UNKNOWN
gsm.current.phone-type=1
gsm.nitz.time=
gsm.network.type=LTE
ril.ecclist=112,911

#
# DISPLAY
#
ro.sf.lcd_density=420
persist.sys.sf.color_saturation=1.0
persist.sys.sf.native_mode=2
ro.surface_flinger.max_frame_buffer_acquired_buffers=3

# End of build.prop
"""

    return build_prop


def main():
    parser = argparse.ArgumentParser(description='Generate build.prop from device profile')
    parser.add_argument('--profile', '-p', required=True,
                        help='Path to device profile JSON')
    parser.add_argument('--output', '-o', required=True,
                        help='Output build.prop path')
    parser.add_argument('--append', action='store_true',
                        help='Append to existing file instead of overwrite')

    args = parser.parse_args()

    print(f"=== Build.prop Generator ===")

    # Load profile
    print(f"Loading profile from: {args.profile}")
    try:
        with open(args.profile, 'r', encoding='utf-8') as f:
            profile = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Profile not found: {args.profile}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in profile: {e}")
        sys.exit(1)

    # Validate required fields
    required_fields = ['brand', 'model', 'device', 'product', 'manufacturer',
                       'hardware', 'android_version', 'sdk_version', 'build_id',
                       'build_number', 'security_patch', 'fingerprint']

    missing = [f for f in required_fields if f not in profile]
    if missing:
        print(f"ERROR: Missing required fields in profile: {missing}")
        sys.exit(1)

    print(f"Device: {profile['brand']} {profile['model']}")
    print(f"Android: {profile['android_version']} (SDK {profile['sdk_version']})")

    # Generate build.prop
    print("Generating build.prop...")
    build_prop_content = generate_build_prop(profile)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)

    # Write file
    mode = 'a' if args.append else 'w'
    with open(args.output, mode, encoding='utf-8') as f:
        f.write(build_prop_content)

    print(f"Written to: {args.output}")

    # Print key properties
    print("\n=== Key Properties ===")
    print(f"ro.product.model={profile['model']}")
    print(f"ro.product.manufacturer={profile['manufacturer']}")
    print(f"ro.build.fingerprint={profile['fingerprint']}")
    print(f"ro.kernel.qemu=0")
    print(f"ro.secure=1")
    print(f"ro.debuggable=0")


if __name__ == '__main__':
    main()
