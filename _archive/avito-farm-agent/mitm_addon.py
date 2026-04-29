import json, time
LOG = r"C:\Users\EloNout\Проекты\AvitoSystem\avito-farm-agent\traffic_log.jsonl"
class L:
    def __init__(self):
        self.fh = open(LOG, "a", encoding="utf-8")
        self.n = 0
    def response(self, flow):
        self.n += 1
        e = {"ts": time.time(), "method": flow.request.method,
              "url": flow.request.pretty_url, "host": flow.request.host,
              "req_headers": dict(flow.request.headers),
              "status": flow.response.status_code,
              "resp_headers": dict(flow.response.headers)}
        if flow.request.content and len(flow.request.content) < 10000:
            try: e["req_body"] = flow.request.content.decode("utf-8", errors="replace")
            except: pass
        if flow.response.content and len(flow.response.content) < 10000:
            try: e["resp_body"] = flow.response.content.decode("utf-8", errors="replace")
            except: pass
        self.fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        self.fh.flush()
        print(f"[{self.n}] {flow.request.method} {flow.request.pretty_url[:100]} -> {flow.response.status_code}")
addons = [L()]
