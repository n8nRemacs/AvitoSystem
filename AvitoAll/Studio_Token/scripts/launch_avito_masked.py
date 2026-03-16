#!/usr/bin/env python3
"""
Launch Avito with Frida masking (Google Pixel 6)
"""
import frida
import sys
import time

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
    print("Launching Avito with Device Masking")
    print("=" * 60)

    # Connect to Frida Server via localhost
    print("\n[1/4] Connecting to Frida Server...")
    device = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
    print(f"OK Connected: {device}")

    # Spawn Avito (start app with Frida attached)
    print("\n[2/4] Spawning Avito...")
    pid = device.spawn(['com.avito.android'])
    print(f"OK Spawned with PID: {pid}")

    # Attach to spawned process
    print("\n[3/4] Attaching and injecting script...")
    session = device.attach(pid)
    script = session.create_script(script_code)
    script.on('message', on_message)
    script.load()
    print("OK Script injected successfully")

    # Resume the app (it's paused after spawn)
    print("\n[4/4] Resuming app...")
    device.resume(pid)
    print("OK Avito is running with Pixel 6 masking")

    print("\n" + "=" * 60)
    print("SUCCESS! Avito is running as Google Pixel 6")
    print("=" * 60)
    print("\nYou can now:")
    print("  1. Authorize in Avito app on emulator")
    print("  2. Enter phone number and SMS code")
    print("  3. Wait for login confirmation")
    print("\nPress Ctrl+C to stop and keep Frida attached...")
    print("(Or close this window and Avito will continue normally)")
    print("=" * 60)

    # Keep script running
    sys.stdin.read()

except KeyboardInterrupt:
    print("\n\n[*] Detaching Frida (Avito will continue running)...")
    session.detach()
    print("[*] Done!")

except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
