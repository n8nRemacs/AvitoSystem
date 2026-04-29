"""Quick runtime sniff - spawn Avito with Frida hooks pre-installed.

Uses spawn mode to inject hooks BEFORE anti-Frida detection initializes.
Collects fingerprint API calls for 60 seconds, saves to JSON.
"""

import frida
import json
import os
import sys
import time
import threading

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "quick_sniff.js")
PACKAGE = "com.avito.android"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "runtime_fingerprint.json")

lines = []
results = {}
detached_event = threading.Event()


def on_message(message, data):
    if message["type"] == "send":
        payload = message["payload"]
        print(payload[:200])
        lines.append(payload)

        # Parse structured results
        if payload.startswith("{"):
            try:
                entry = json.loads(payload)
                cat = entry.get("cat", "unknown")
                method = entry.get("method", "unknown")
                value = entry.get("value", "")
                if cat not in results:
                    results[cat] = {}
                results[cat][method] = value
            except json.JSONDecodeError:
                pass
        elif payload.startswith("[RESULTS]") or payload.startswith("[RESULTS_30S]"):
            try:
                data_str = payload.split("] ", 1)[1]
                merged = json.loads(data_str)
                for cat, methods in merged.items():
                    if cat not in results:
                        results[cat] = {}
                    results[cat].update(methods)
            except Exception:
                pass
    elif message["type"] == "error":
        print(f"[ERROR] {message.get('description', message)}", file=sys.stderr)


def save_results():
    """Save whatever we have so far."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[*] Done. {len(lines)} messages, {len(results)} categories.")
    print(f"[*] Results saved to {OUTPUT_FILE}")

    print("\n" + "=" * 70)
    print("RUNTIME FINGERPRINT RESULTS")
    print("=" * 70)
    for cat in sorted(results.keys()):
        methods = results[cat]
        print(f"\n[{cat}]")
        for method, value in sorted(methods.items()):
            print(f"  {method} = {str(value)[:100]}")


def main():
    print("[*] Connecting to USB device...")
    device = frida.get_usb_device(timeout=10)
    print(f"[*] Device: {device.name}")

    print(f"[*] Spawning {PACKAGE} (hooks install before app init)...")
    try:
        pid = device.spawn([PACKAGE])
    except Exception as e:
        print(f"[-] Spawn failed: {e}")
        sys.exit(1)
    print(f"[*] Spawned PID: {pid}")

    print("[*] Attaching to spawned process...")
    session = device.attach(pid)

    def on_detach(reason, crash):
        print(f"\n[!] Detached: {reason}")
        if crash:
            print(f"[!] Crash: {crash}")
        detached_event.set()

    session.on("detached", on_detach)

    print("[*] Loading script...")
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        script_code = f.read()

    script = session.create_script(script_code, runtime="v8")
    script.on("message", on_message)
    script.load()

    print("[*] Script loaded! Resuming app...")
    device.resume(pid)

    print("[*] Collecting for 60 seconds... Browse around in Avito!\n")

    try:
        # Wait up to 60s, but stop early if detached
        for i in range(60):
            if detached_event.is_set():
                print(f"\n[!] Session ended after {i}s")
                break
            time.sleep(1)
            # Save intermediate results every 15s
            if (i + 1) % 15 == 0:
                save_results()
                print(f"\n[*] ... {60 - i - 1}s remaining ...\n")
    except KeyboardInterrupt:
        print("\n[*] Interrupted")

    save_results()

    try:
        session.detach()
    except Exception:
        pass


if __name__ == "__main__":
    main()
