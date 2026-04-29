"""Launch sniff_fingerprint.js via Frida Python API.

Supports two modes:
  --gadget   Connect to Frida Gadget (TCP port 27042, for patched APK)
  (default)  Attach to running process via USB

Collects output for ~60 seconds, then saves raw log to sniff_output.log.
"""

import frida
import subprocess
import sys
import time
import os

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "sniff_fingerprint.js")
PACKAGE = "com.avito.android"
COLLECT_SECONDS = 60
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "sniff_output.log")
GADGET_PORT = 27042

lines = []


def on_message(message, data):
    if message["type"] == "send":
        line = message["payload"]
        print(line)
        lines.append(line)
    elif message["type"] == "log":
        line = message["payload"]
        print(line)
        lines.append(line)
    elif message["type"] == "error":
        print(f"[ERROR] {message.get('description', message)}", file=sys.stderr)


def connect_gadget():
    """Connect to Frida Gadget via TCP (for patched APK)."""
    print(f"[*] Setting up ADB port forward: tcp:{GADGET_PORT} -> tcp:{GADGET_PORT}")
    subprocess.run(["adb", "forward", f"tcp:{GADGET_PORT}", f"tcp:{GADGET_PORT}"],
                    capture_output=True, timeout=5)

    print(f"[*] Connecting to Frida Gadget at 127.0.0.1:{GADGET_PORT}...")
    mgr = frida.get_device_manager()
    device = mgr.add_remote_device(f"127.0.0.1:{GADGET_PORT}")
    print(f"[*] Device: {device.name}")

    # In gadget mode, the process is called "Gadget" and is waiting
    print("[*] Attaching to Gadget process...")
    session = device.attach("Gadget")
    print("[*] Attached! App will resume after script loads.")
    return device, session


def connect_usb():
    """Attach to running Avito process via USB."""
    print("[*] Connecting to USB device...")
    device = frida.get_usb_device(timeout=10)
    print(f"[*] Device: {device.name}")

    result = subprocess.run(["adb", "shell", "pidof", PACKAGE],
                            capture_output=True, text=True, timeout=5)
    pid_str = result.stdout.strip()

    if pid_str:
        pid = int(pid_str.split()[0])
        print(f"[*] Found running {PACKAGE} at PID {pid}")
        session = device.attach(pid)
    else:
        print(f"[*] {PACKAGE} not running. Please start Avito first!")
        sys.exit(1)

    return device, session


def main():
    gadget_mode = "--gadget" in sys.argv

    if gadget_mode:
        print("[*] Mode: Frida Gadget (patched APK)")
        device, session = connect_gadget()
    else:
        print("[*] Mode: USB attach")
        device, session = connect_usb()

    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        script_code = f.read()

    # Wrap script to wait for Java VM to be available (gadget loads before JVM)
    wrapper = """
    var _attempts = 0;
    function waitForJava(callback) {
        _attempts++;
        try {
            if (typeof Java !== 'undefined' && Java.available) {
                send('[*] Java available after ' + _attempts + ' attempts');
                callback();
                return;
            }
        } catch(e) {}
        if (_attempts % 50 === 0) {
            send('[*] Waiting for Java VM... attempt ' + _attempts);
        }
        setTimeout(function() { waitForJava(callback); }, 100);
    }
    waitForJava(function() {
    """ + script_code + """
    });
    """

    script = session.create_script(wrapper, runtime="v8")
    script.on("message", on_message)
    script.load()

    print(f"[*] Script loaded! Collecting data for {COLLECT_SECONDS} seconds...")
    print("[*] Browse Avito — open messenger, chats, search, scroll around.")
    print()

    try:
        time.sleep(COLLECT_SECONDS)
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")

    print(f"\n[*] Collection done. {len(lines)} lines captured.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[*] Saved to {OUTPUT_FILE}")

    try:
        session.detach()
    except Exception:
        pass


if __name__ == "__main__":
    main()
