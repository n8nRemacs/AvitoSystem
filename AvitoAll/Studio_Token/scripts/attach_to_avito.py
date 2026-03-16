#!/usr/bin/env python3
"""
Start Avito and immediately attach Frida for device masking
"""
import frida
import subprocess
import time
import sys

# Read the Frida script
script_path = '../frida_scripts/build_mask.js'
with open(script_path, 'r', encoding='utf-8') as f:
    script_code = f.read()

def on_message(message, data):
    """Handle messages from Frida script"""
    if message['type'] == 'send':
        print(f"[Frida] {message['payload']}")
    elif message['type'] == 'error':
        print(f"[Error] {message['stack']}")

try:
    print("=" * 60)
    print("Starting Avito with Device Masking")
    print("=" * 60)

    # Step 1: Force stop Avito first
    print("\n[1/5] Stopping any running Avito...")
    subprocess.run([
        r'C:\Users\Dimon\AppData\Local\Android\Sdk\platform-tools\adb.exe',
        'shell', 'am', 'force-stop', 'com.avito.android'
    ], check=True, capture_output=True)
    time.sleep(1)
    print("OK Avito stopped")

    # Step 2: Start Avito via ADB
    print("\n[2/5] Starting Avito...")
    subprocess.Popen([
        r'C:\Users\Dimon\AppData\Local\Android\Sdk\platform-tools\adb.exe',
        'shell', 'am', 'start', '-n', 'com.avito.android/.Launcher'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("OK Avito starting...")

    # Step 3: Wait for process to appear and get PID
    print("\n[3/5] Waiting for Avito process...")
    max_attempts = 10
    pid = None
    for attempt in range(max_attempts):
        time.sleep(0.5)
        result = subprocess.run([
            r'C:\Users\Dimon\AppData\Local\Android\Sdk\platform-tools\adb.exe',
            'shell', 'pidof', 'com.avito.android'
        ], capture_output=True, text=True)

        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split()[0])
            print(f"OK Found process PID: {pid}")
            break

        if attempt == max_attempts - 1:
            print("ERROR: Avito process not found after 5 seconds")
            sys.exit(1)

    # Step 4: Connect to Frida and attach
    print("\n[4/5] Attaching Frida...")
    device = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
    session = device.attach(pid)
    script = session.create_script(script_code)
    script.on('message', on_message)
    script.load()
    print("OK Frida attached and script loaded")

    # Step 5: Keep running
    print("\n[5/5] Masking active!")
    print("\n" + "=" * 60)
    print("SUCCESS! Avito is running as Google Pixel 6")
    print("=" * 60)
    print("\nDevice properties masked:")
    print("  - Model: Pixel 6")
    print("  - Manufacturer: Google")
    print("  - Brand: google")
    print("  - Device: oriole")
    print("\nYou can now:")
    print("  1. Authorize in Avito app on emulator")
    print("  2. Enter phone number and SMS code")
    print("  3. Open 'Messages' tab after login")
    print("\nKeep this window open to maintain masking!")
    print("Press Ctrl+C to stop...")
    print("=" * 60)

    # Keep script running
    sys.stdin.read()

except KeyboardInterrupt:
    print("\n\n[*] Stopping...")
    session.detach()
    print("[*] Frida detached. Avito will continue running.")

except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
