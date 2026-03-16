#!/usr/bin/env python3
"""
Simple script to test Frida connection to Android device
"""
import frida
import sys

try:
    print("=" * 50)
    print("Testing Frida Connection")
    print("=" * 50)

    # List all available devices
    print("\n[1/4] Listing all Frida devices...")
    device_manager = frida.get_device_manager()
    devices = device_manager.enumerate_devices()

    print(f"Found {len(devices)} device(s):")
    for dev in devices:
        print(f"  - {dev.name} (ID: {dev.id}, Type: {dev.type})")

    # Try to get device (USB first, then socket/remote)
    print("\n[2/4] Connecting to device...")
    device = None
    try:
        device = frida.get_usb_device(timeout=3)
        print(f"OK Connected to USB device: {device.name}")
    except:
        print("  No USB device, trying remote/socket devices...")
        # Try socket device (might be forwarded Android)
        socket_devices = [d for d in devices if d.type in ('remote', 'tether')]
        if socket_devices:
            device = socket_devices[0]
            print(f"OK Connected to: {device.name} (Type: {device.type})")
        elif devices:
            # Skip local system, it's not what we want
            non_local = [d for d in devices if d.type != 'local']
            if non_local:
                device = non_local[0]
            else:
                device = devices[0]
            print(f"OK Connected to: {device.name} (Type: {device.type})")

    # List processes
    print(f"\n[3/4] Listing processes on {device.name}...")
    processes = device.enumerate_processes()
    print(f"OK Found {len(processes)} processes")

    # Show first 10 processes
    print("\n[4/4] Sample processes:")
    for proc in processes[:10]:
        print(f"  PID {proc.pid:5d}: {proc.name}")

    # Check for Avito
    avito_procs = [p for p in processes if 'avito' in p.name.lower()]
    if avito_procs:
        print(f"\nOK Avito app found:")
        for proc in avito_procs:
            print(f"  PID {proc.pid}: {proc.name}")
    else:
        print("\nWARNING: Avito app NOT running (install and launch it first)")

    print("\n" + "=" * 50)
    print("SUCCESS: Frida connection working!")
    print("=" * 50)
    sys.exit(0)

except frida.TimedOutError:
    print("\nERROR: Could not find USB device")
    print("  Make sure:")
    print("  1. Emulator is running")
    print("  2. Frida Server is running on emulator")
    print("  3. ADB is connected (adb devices)")
    sys.exit(1)

except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
