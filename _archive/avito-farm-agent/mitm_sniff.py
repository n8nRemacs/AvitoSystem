"""Combined MITM approach: Frida SSL pinning bypass + mitmproxy traffic capture.

Steps:
1. Start mitmdump in background (saves flows to avito_flows.mitm)
2. Set up ADB reverse proxy (device:8082 -> PC:8082)
3. Configure device WiFi proxy via iptables
4. Spawn Avito with Frida + ssl_bypass.js
5. Collect traffic for N seconds
6. Parse and analyze captured flows
"""

import frida
import json
import os
import subprocess
import sys
import signal
import time
import threading

PACKAGE = "com.avito.android"
PROXY_PORT = 8082
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SSL_BYPASS_PATH = os.path.join(BASE_DIR, "ssl_bypass.js")
SNIFF_SCRIPT_PATH = os.path.join(BASE_DIR, "quick_sniff.js")
FLOW_FILE = os.path.join(BASE_DIR, "avito_flows.mitm")
OUTPUT_FILE = os.path.join(BASE_DIR, "mitm_fingerprint.json")
ADDON_PATH = os.path.join(BASE_DIR, "mitm_addon.py")
TRAFFIC_LOG = os.path.join(BASE_DIR, "traffic_log.jsonl")
COLLECT_SECONDS = 90

detached = threading.Event()
frida_messages = []


def on_message(message, data):
    if message["type"] == "send":
        payload = message["payload"]
        print(f"  [frida] {payload[:150]}")
        frida_messages.append(payload)
    elif message["type"] == "error":
        print(f"  [frida ERROR] {message.get('description', '')[:150]}", file=sys.stderr)


def on_detach(reason, crash):
    print(f"\n[!] Frida detached: {reason}")
    if crash:
        print(f"[!] Crash: {crash}")
    detached.set()


def create_addon():
    """Create mitmproxy addon that logs all requests to JSONL."""
    addon_code = '''"""mitmproxy addon: log all HTTP(S) requests/responses to JSONL."""
import json
import time

LOG_FILE = r"''' + TRAFFIC_LOG.replace("\\", "\\\\") + '''"

class AvitoLogger:
    def __init__(self):
        self.fh = open(LOG_FILE, "a", encoding="utf-8")
        self.count = 0

    def response(self, flow):
        self.count += 1
        entry = {
            "ts": time.time(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "host": flow.request.host,
            "req_headers": dict(flow.request.headers),
            "req_body_len": len(flow.request.content) if flow.request.content else 0,
            "status": flow.response.status_code,
            "resp_headers": dict(flow.response.headers),
            "resp_body_len": len(flow.response.content) if flow.response.content else 0,
        }
        # Include small request bodies (likely JSON with fingerprint data)
        if flow.request.content and len(flow.request.content) < 10000:
            try:
                entry["req_body"] = flow.request.content.decode("utf-8", errors="replace")
            except Exception:
                pass
        # Include small response bodies
        if flow.response.content and len(flow.response.content) < 10000:
            try:
                entry["resp_body"] = flow.response.content.decode("utf-8", errors="replace")
            except Exception:
                pass

        self.fh.write(json.dumps(entry, ensure_ascii=False) + "\\n")
        self.fh.flush()

        # Print summary
        print(f"[{self.count}] {flow.request.method} {flow.request.pretty_url[:100]} -> {flow.response.status_code}")

addons = [AvitoLogger()]
'''
    with open(ADDON_PATH, "w", encoding="utf-8") as f:
        f.write(addon_code)
    print(f"[*] Addon written to {ADDON_PATH}")


def start_mitmdump():
    """Start mitmdump in background."""
    # Clean previous logs
    for f in [TRAFFIC_LOG, FLOW_FILE]:
        if os.path.exists(f):
            os.remove(f)

    # Find mitmdump executable
    import glob as _glob
    candidates = _glob.glob(os.path.expanduser("~/AppData/Roaming/Python/*/Scripts/mitmdump.exe"))
    mitmdump_exe = candidates[0] if candidates else "mitmdump"

    cmd = [
        mitmdump_exe,
        "--mode", "regular",
        "--listen-port", str(PROXY_PORT),
        "--set", "ssl_insecure=true",
        "-s", ADDON_PATH,
        "-w", FLOW_FILE,
    ]
    print(f"[*] Starting mitmdump: {mitmdump_exe}")
    print(f"[*] Command: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait for startup
    time.sleep(5)
    if proc.poll() is not None:
        out = proc.stdout.read()
        print(f"[-] mitmdump failed to start:\n{out}")
        return None
    print(f"[*] mitmdump running (PID {proc.pid})")
    return proc


def setup_device_proxy():
    """Configure device to route traffic through mitmproxy via iptables."""
    print("[*] Setting up device proxy...")

    # ADB reverse: device port -> PC port
    subprocess.run(["adb", "reverse", f"tcp:{PROXY_PORT}", f"tcp:{PROXY_PORT}"],
                    capture_output=True, timeout=5)
    print(f"  adb reverse tcp:{PROXY_PORT} -> tcp:{PROXY_PORT}")

    # Use iptables to redirect HTTP(S) traffic to mitmproxy (transparent-ish)
    # First remove old rules
    cmds = [
        # Remove old iptables rules (ignore errors)
        f"iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination 127.0.0.1:{PROXY_PORT} 2>/dev/null; true",
        f"iptables -t nat -D OUTPUT -p tcp --dport 80 -j DNAT --to-destination 127.0.0.1:{PROXY_PORT} 2>/dev/null; true",
        # Set global proxy (for apps that respect it)
        f"settings put global http_proxy 127.0.0.1:{PROXY_PORT}",
    ]
    for cmd in cmds:
        subprocess.run(["adb", "shell", "su", "-c", cmd],
                        capture_output=True, timeout=5)
        print(f"  {cmd[:80]}")

    print("[*] Device proxy configured")


def clear_device_proxy():
    """Remove proxy settings from device."""
    print("[*] Clearing device proxy...")
    cmds = [
        "settings put global http_proxy :0",
    ]
    for cmd in cmds:
        subprocess.run(["adb", "shell", "su", "-c", cmd],
                        capture_output=True, timeout=5)


def attach_avito_with_bypass(device):
    """Attach to running Avito and load SSL bypass + sniff scripts."""
    # Get Avito PID
    result = subprocess.run(["adb", "shell", "pidof", PACKAGE],
                            capture_output=True, text=True, timeout=5)
    pid_str = result.stdout.strip()
    if not pid_str:
        # Launch Avito and wait for it
        print(f"[*] Launching {PACKAGE}...")
        subprocess.run(["adb", "shell", "monkey", "-p", PACKAGE,
                        "-c", "android.intent.category.LAUNCHER", "1"],
                        capture_output=True, timeout=10)
        time.sleep(5)
        result = subprocess.run(["adb", "shell", "pidof", PACKAGE],
                                capture_output=True, text=True, timeout=5)
        pid_str = result.stdout.strip()
        if not pid_str:
            raise RuntimeError("Avito failed to start")

    pid = int(pid_str.split()[0])
    print(f"[*] Avito PID: {pid}")

    print(f"[*] Attaching to PID {pid}...")
    session = device.attach(pid)
    session.on("detached", on_detach)

    # Load BOTH scripts as a single combined script (faster, single attach)
    print("[*] Loading combined SSL bypass + API sniff script...")
    with open(SSL_BYPASS_PATH, "r", encoding="utf-8") as f:
        ssl_code = f.read()
    with open(SNIFF_SCRIPT_PATH, "r", encoding="utf-8") as f:
        sniff_code = f.read()

    # Combine scripts — both use Java.perform, merge them
    combined = ssl_code + "\n\n// === API Sniff hooks ===\n\n" + sniff_code
    script = session.create_script(combined, runtime="v8")
    script.on("message", on_message)
    script.load()

    print("[*] Scripts loaded!")
    return session, pid


def analyze_traffic():
    """Parse traffic log and extract fingerprint-related data."""
    if not os.path.exists(TRAFFIC_LOG):
        print("[-] No traffic log found")
        return

    entries = []
    with open(TRAFFIC_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    print(f"\n[*] Captured {len(entries)} HTTP(S) requests")

    # Extract fingerprint-relevant info
    fp_headers = {}
    fp_urls = []
    fp_bodies = []

    fp_header_keys = [
        "x-device", "x-fingerprint", "x-app", "x-client", "x-mob",
        "user-agent", "x-request-id", "x-session", "x-install",
        "authorization", "x-platform", "x-source",
    ]

    for entry in entries:
        url = entry.get("url", "")
        headers = entry.get("req_headers", {})
        body = entry.get("req_body", "")

        # Collect fingerprint-related headers
        for hk, hv in headers.items():
            if any(fp in hk.lower() for fp in fp_header_keys):
                if hk not in fp_headers:
                    fp_headers[hk] = set()
                fp_headers[hk].add(str(hv)[:200])

        # URLs with fingerprint/device/tracking keywords
        url_lower = url.lower()
        if any(kw in url_lower for kw in ["device", "fingerprint", "track", "analytics",
                                            "install", "identify", "register", "config"]):
            fp_urls.append({"url": url, "method": entry.get("method")})

        # Request bodies with fingerprint data
        if body:
            body_lower = body.lower()
            if any(kw in body_lower for kw in ["device_id", "fingerprint", "android_id",
                                                 "advertising_id", "gaid", "model",
                                                 "manufacturer", "imei"]):
                fp_bodies.append({
                    "url": url,
                    "body_preview": body[:500],
                })

    report = {
        "total_requests": len(entries),
        "unique_hosts": list(set(e.get("host", "") for e in entries)),
        "fingerprint_headers": {k: list(v) for k, v in fp_headers.items()},
        "fingerprint_urls": fp_urls[:50],
        "fingerprint_bodies": fp_bodies[:20],
        "all_request_headers_sample": {},
    }

    # Sample first Avito API request headers
    for entry in entries:
        if "avito" in entry.get("host", "").lower():
            report["all_request_headers_sample"] = entry.get("req_headers", {})
            report["sample_url"] = entry.get("url", "")
            break

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'=' * 70}")
    print("MITM FINGERPRINT ANALYSIS")
    print(f"{'=' * 70}")
    print(f"\nTotal requests captured: {len(entries)}")
    print(f"Unique hosts: {len(report['unique_hosts'])}")
    for host in sorted(report["unique_hosts"])[:20]:
        print(f"  - {host}")

    if fp_headers:
        print(f"\nFingerprint-related headers ({len(fp_headers)}):")
        for hk, vals in sorted(fp_headers.items()):
            for v in list(vals)[:2]:
                print(f"  {hk}: {v[:100]}")

    if fp_urls:
        print(f"\nFingerprint-related URLs ({len(fp_urls)}):")
        for u in fp_urls[:10]:
            print(f"  {u['method']} {u['url'][:100]}")

    if fp_bodies:
        print(f"\nRequest bodies with fingerprint data ({len(fp_bodies)}):")
        for b in fp_bodies[:5]:
            print(f"  URL: {b['url'][:80]}")
            print(f"  Body: {b['body_preview'][:200]}")

    print(f"\n[*] Full report: {OUTPUT_FILE}")


def main():
    # Check ADB
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
    if "device" not in result.stdout.split("\n", 1)[-1]:
        print("[-] No ADB device connected!")
        sys.exit(1)

    # Step 1: Create addon and start mitmdump
    create_addon()
    mitm_proc = start_mitmdump()
    if not mitm_proc:
        sys.exit(1)

    try:
        # Step 2: Setup ADB reverse (but NOT proxy yet — let app start first)
        subprocess.run(["adb", "reverse", f"tcp:{PROXY_PORT}", f"tcp:{PROXY_PORT}"],
                        capture_output=True, timeout=5)
        print(f"[*] ADB reverse tcp:{PROXY_PORT} -> tcp:{PROXY_PORT}")

        # Step 3: Connect Frida and spawn Avito (no proxy interference)
        print("[*] Connecting to USB device...")
        device = frida.get_usb_device(timeout=10)
        print(f"[*] Device: {device.name}")

        # Kill existing Avito
        subprocess.run(["adb", "shell", "am", "force-stop", PACKAGE],
                        capture_output=True, timeout=5)
        time.sleep(1)

        session, pid = attach_avito_with_bypass(device)

        # Step 3b: NOW enable proxy (after app launched + hooks loaded)
        print("[*] Enabling device proxy (post-launch)...")
        subprocess.run(["adb", "shell", "su", "-c",
                        f"settings put global http_proxy 127.0.0.1:{PROXY_PORT}"],
                        capture_output=True, timeout=5)
        print(f"[*] Global proxy set to 127.0.0.1:{PROXY_PORT}")

        # Step 4: Collect
        print(f"\n[*] Collecting traffic for {COLLECT_SECONDS} seconds...")
        print("[*] Browse around in Avito to generate traffic!\n")

        for i in range(COLLECT_SECONDS):
            if detached.is_set():
                print(f"\n[!] Frida session ended after {i}s")
                break
            time.sleep(1)
            if (i + 1) % 15 == 0:
                # Check traffic count
                count = 0
                if os.path.exists(TRAFFIC_LOG):
                    with open(TRAFFIC_LOG, "r") as f:
                        count = sum(1 for _ in f)
                print(f"  [{i+1}s] {count} requests captured, {COLLECT_SECONDS - i - 1}s remaining...")

        # Detach Frida
        try:
            session.detach()
        except Exception:
            pass

    finally:
        # Cleanup
        clear_device_proxy()
        if mitm_proc:
            print("[*] Stopping mitmdump...")
            mitm_proc.terminate()
            try:
                mitm_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mitm_proc.kill()

    # Step 5: Analyze
    analyze_traffic()


if __name__ == "__main__":
    main()
