"""Minimal MITM runner: Frida anti-detect + SSL bypass + mitmproxy.

Steps:
1. Start mitmdump on PC
2. ADB reverse proxy
3. Attach Frida to running Avito with anti-detect + SSL bypass + API sniff
4. Enable device proxy
5. Collect traffic
"""

import frida
import json
import os
import subprocess
import sys
import time
import threading

PACKAGE = "com.avito.android"
PROXY_PORT = 8082
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAFFIC_LOG = os.path.join(BASE_DIR, "traffic_log.jsonl")
FLOW_FILE = os.path.join(BASE_DIR, "avito_flows.mitm")
OUTPUT_FILE = os.path.join(BASE_DIR, "mitm_fingerprint.json")
COLLECT_SECONDS = 90

detached = threading.Event()
frida_msgs = []


def on_message(message, data):
    if message["type"] == "send":
        payload = message["payload"]
        print(f"  [frida] {payload[:150]}")
        frida_msgs.append(payload)
    elif message["type"] == "error":
        print(f"  [frida ERROR] {message.get('description', '')[:200]}", file=sys.stderr)


def on_detach(reason, crash):
    print(f"\n[!] Frida detached: {reason}")
    detached.set()


def find_mitmdump():
    import glob as _g
    hits = _g.glob(os.path.expanduser("~/AppData/Roaming/Python/*/Scripts/mitmdump.exe"))
    return hits[0] if hits else "mitmdump"


def write_addon():
    """Write mitmproxy addon for traffic logging."""
    code = f'''import json, time
LOG = r"{TRAFFIC_LOG}"
class L:
    def __init__(self):
        self.fh = open(LOG, "a", encoding="utf-8")
        self.n = 0
    def response(self, flow):
        self.n += 1
        e = {{"ts": time.time(), "method": flow.request.method,
              "url": flow.request.pretty_url, "host": flow.request.host,
              "req_headers": dict(flow.request.headers),
              "status": flow.response.status_code,
              "resp_headers": dict(flow.response.headers)}}
        if flow.request.content and len(flow.request.content) < 10000:
            try: e["req_body"] = flow.request.content.decode("utf-8", errors="replace")
            except: pass
        if flow.response.content and len(flow.response.content) < 10000:
            try: e["resp_body"] = flow.response.content.decode("utf-8", errors="replace")
            except: pass
        self.fh.write(json.dumps(e, ensure_ascii=False) + "\\n")
        self.fh.flush()
        print(f"[{{self.n}}] {{flow.request.method}} {{flow.request.pretty_url[:100]}} -> {{flow.response.status_code}}")
addons = [L()]
'''
    addon_path = os.path.join(BASE_DIR, "mitm_addon.py")
    with open(addon_path, "w", encoding="utf-8") as f:
        f.write(code)
    return addon_path


def build_frida_script():
    """Load and concatenate all JS scripts."""
    scripts = []
    for name in ["anti_detect.js", "ssl_bypass.js", "quick_sniff.js"]:
        path = os.path.join(BASE_DIR, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                scripts.append(f"// === {name} ===\n" + f.read())
    return "\n\n".join(scripts)


def main():
    # Check device
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
    if "device" not in r.stdout.split("\n", 1)[-1]:
        print("[-] No device connected"); sys.exit(1)

    # Clean old logs
    for f in [TRAFFIC_LOG, FLOW_FILE]:
        if os.path.exists(f):
            os.remove(f)

    # Start mitmdump
    addon_path = write_addon()
    mitm_exe = find_mitmdump()
    print(f"[*] Starting mitmdump ({mitm_exe})...")
    mitm_proc = subprocess.Popen(
        [mitm_exe, "--mode", "regular", "-p", str(PROXY_PORT),
         "--set", "ssl_insecure=true", "-s", addon_path, "-w", FLOW_FILE],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(4)
    if mitm_proc.poll() is not None:
        print(f"[-] mitmdump died: {mitm_proc.stdout.read()[:500]}")
        sys.exit(1)
    print(f"[*] mitmdump running (PID {mitm_proc.pid})")

    # ADB reverse
    subprocess.run(["adb", "reverse", f"tcp:{PROXY_PORT}", f"tcp:{PROXY_PORT}"],
                    capture_output=True, timeout=5)

    try:
        # Connect Frida
        print("[*] Connecting Frida...")
        device = frida.get_usb_device(timeout=10)
        print(f"[*] Device: {device.name}")

        # Check if Avito running, if not launch it
        r = subprocess.run(["adb", "shell", "pidof", PACKAGE],
                            capture_output=True, text=True, timeout=5)
        if not r.stdout.strip():
            print("[*] Launching Avito...")
            subprocess.run(["adb", "shell", "monkey", "-p", PACKAGE,
                            "-c", "android.intent.category.LAUNCHER", "1"],
                            capture_output=True, timeout=10)
            time.sleep(6)
            r = subprocess.run(["adb", "shell", "pidof", PACKAGE],
                                capture_output=True, text=True, timeout=5)

        pid = int(r.stdout.strip().split()[0])
        print(f"[*] Avito PID: {pid}")

        # Attach and load scripts
        print("[*] Attaching Frida...")
        session = device.attach(pid)
        session.on("detached", on_detach)

        script_code = build_frida_script()
        print(f"[*] Loading scripts ({len(script_code)} bytes)...")
        script = session.create_script(script_code, runtime="v8")
        script.on("message", on_message)
        script.load()
        print("[*] Frida scripts loaded!")

        # Enable proxy AFTER hooks are in place
        time.sleep(2)
        print("[*] Enabling proxy...")
        subprocess.run(["adb", "shell", "su", "-c",
                        f"settings put global http_proxy 127.0.0.1:{PROXY_PORT}"],
                        capture_output=True, timeout=5)

        # Collect
        print(f"\n[*] Collecting for {COLLECT_SECONDS}s... Browse Avito!\n")
        for i in range(COLLECT_SECONDS):
            if detached.is_set():
                print(f"\n[!] Frida ended after {i}s")
                break
            time.sleep(1)
            if (i + 1) % 15 == 0:
                count = 0
                if os.path.exists(TRAFFIC_LOG):
                    with open(TRAFFIC_LOG, "r") as f:
                        count = sum(1 for _ in f)
                print(f"  [{i+1}s] {count} requests, {COLLECT_SECONDS-i-1}s left")

        try:
            session.detach()
        except Exception:
            pass

    finally:
        # Cleanup
        print("[*] Cleaning up...")
        subprocess.run(["adb", "shell", "su", "-c", "settings put global http_proxy :0"],
                        capture_output=True, timeout=5)
        mitm_proc.terminate()
        try:
            mitm_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mitm_proc.kill()

    # Analyze
    analyze()


def analyze():
    if not os.path.exists(TRAFFIC_LOG):
        print("[-] No traffic captured"); return

    entries = []
    with open(TRAFFIC_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    print(f"\n{'='*70}")
    print(f"CAPTURED: {len(entries)} requests")
    print(f"{'='*70}")

    hosts = sorted(set(e.get("host", "") for e in entries))
    print(f"\nHosts ({len(hosts)}):")
    for h in hosts[:30]:
        cnt = sum(1 for e in entries if e.get("host") == h)
        print(f"  {h} ({cnt} requests)")

    # Extract fingerprint headers
    fp_kw = ["device", "fingerprint", "x-app", "x-client", "x-mob", "user-agent",
             "x-platform", "x-install", "x-session", "x-source", "x-request"]
    fp_headers = {}
    for e in entries:
        for k, v in e.get("req_headers", {}).items():
            if any(kw in k.lower() for kw in fp_kw):
                fp_headers.setdefault(k, set()).add(str(v)[:200])

    if fp_headers:
        print(f"\nFingerprint headers ({len(fp_headers)}):")
        for k in sorted(fp_headers):
            for v in list(fp_headers[k])[:2]:
                print(f"  {k}: {v[:100]}")

    # Save
    report = {
        "total": len(entries),
        "hosts": hosts,
        "fp_headers": {k: list(v) for k, v in fp_headers.items()},
        "sample_requests": entries[:20],
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[*] Report: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
