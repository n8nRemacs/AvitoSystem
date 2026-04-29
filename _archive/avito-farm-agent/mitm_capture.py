"""Mitmproxy addon to capture Avito traffic for fingerprint analysis.

Usage: mitmdump -s mitm_capture.py -p 8080
"""

import json
import os
import time
from mitmproxy import http

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "mitm_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOG_FILE = os.path.join(OUTPUT_DIR, "avito_traffic.jsonl")
_counter = 0


def request(flow: http.HTTPFlow):
    """Log outgoing requests."""
    global _counter
    _counter += 1

    host = flow.request.pretty_host
    # Only log avito-related traffic
    if not any(k in host.lower() for k in ("avito", "socket.avito", "item.avito",
                                            "api.avito", "m.avito", "www.avito")):
        return

    entry = {
        "n": _counter,
        "ts": time.time(),
        "type": "request",
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": host,
        "path": flow.request.path,
        "headers": dict(flow.request.headers),
        "content_length": len(flow.request.content) if flow.request.content else 0,
    }

    # Capture body for POST/PUT (fingerprint data often in POST)
    if flow.request.content and flow.request.method in ("POST", "PUT", "PATCH"):
        try:
            body = flow.request.content.decode("utf-8", errors="replace")
            if len(body) < 50000:  # Don't log huge bodies
                entry["body"] = body
        except Exception:
            entry["body_hex"] = flow.request.content[:1000].hex()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def response(flow: http.HTTPFlow):
    """Log responses with headers (fingerprint tokens, cookies, etc.)."""
    host = flow.request.pretty_host
    if not any(k in host.lower() for k in ("avito", "socket.avito", "item.avito",
                                            "api.avito", "m.avito", "www.avito")):
        return

    entry = {
        "ts": time.time(),
        "type": "response",
        "url": flow.request.pretty_url,
        "status": flow.response.status_code,
        "headers": dict(flow.response.headers),
        "content_length": len(flow.response.content) if flow.response.content else 0,
    }

    # Capture small response bodies
    if flow.response.content and len(flow.response.content) < 50000:
        try:
            body = flow.response.content.decode("utf-8", errors="replace")
            entry["body"] = body
        except Exception:
            pass

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
