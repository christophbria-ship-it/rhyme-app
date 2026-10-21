"""Stdlib HTTP server for the rhyme app. Usage: python server.py [port]"""
import json, os, sys, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from engine import Engine
ROOT = os.path.dirname(os.path.abspath(__file__))
ENGINE = Engine()
SORTS = {"score", "freq", "alpha", "length", "syllables"}
POS = {"n", "v", "adj", "adv"}

def ints(v):
    return [int(x) for x in v.split(",") if x.strip()] if v else None

class Server(ThreadingHTTPServer):
    request_queue_size = 256
    daemon_threads = True

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        """POST /api/analyze with JSON {"text": ...} for long lyrics."""
        try:
            if urlparse(self.path).path != "/api/analyze": return self.send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length", 0))
            if n > 100000: return self.send(413, {"error": "body too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict) or not isinstance(body.get("text"), str): return self.send(400, {"error": "missing 'text'"})
            return self.send(200, ENGINE.analyze(body["text"]))
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception:
            self.send(500, {"error": "internal error"})
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        try:
            if u.path == "/api/health":
                return self.send(200, {"ok": True, "words": len(ENGINE.words)})
            if u.path == "/api/suggest":
                return self.send(200, {"suggestions": ENGINE.suggest(q.get("q", ""), int(q.get("limit", 8)))})
            if u.path == "/api/rhymes":
                if not q.get("word", "").strip(): return self.send(400, {"error": "missing 'word' parameter"})
                sort = q.get("sort", "score")
                if sort not in SORTS: return self.send(400, {"error": "invalid sort"})
                pos = q.get("pos", "").split(",") if q.get("pos") else None
                if pos and not set(pos) <= POS: return self.send(400, {"error": "invalid pos"})
                t = time.perf_counter()
                r = ENGINE.rhymes(q["word"], syllables=ints(q.get("syllables")), pos=pos,
                                  min_len=int(q["min_len"]) if q.get("min_len") else None,
                                  max_len=int(q["max_len"]) if q.get("max_len") else None,
                                  min_freq=float(q["min_freq"]) if q.get("min_freq") else None,
                                  sort=sort, limit=min(int(q.get("limit", 300)), 5000),
                                  theme=q.get("theme") or None, theme_only=q.get("theme_only") in ("1", "true"))
                r["elapsed_ms"] = round((time.perf_counter() - t) * 1000, 2)
                return self.send(200, r)
            if u.path == "/api/themes":
                return self.send(200, {"themes": [{"id": k, "label": v, "size": len(ENGINE.themes[k])} for k, v in ENGINE.theme_labels.items()]})
            if u.path == "/api/analyze":
                if "text" not in q: return self.send(400, {"error": "missing 'text' parameter"})
                return self.send(200, ENGINE.analyze(q["text"]))
            if u.path == "/api/line":
                if not q.get("prev", "").strip(): return self.send(400, {"error": "missing 'prev' parameter"})
                return self.send(200, ENGINE.line_help(q["prev"], q.get("line", ""), theme=q.get("theme") or None,
                                                       limit=min(int(q.get("limit", 40)), 500)))
            if u.path.startswith("/api/"): return self.send(404, {"error": "not found"})
            path = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            f = os.path.normpath(os.path.join(ROOT, "static", path))
            if not f.startswith(os.path.join(ROOT, "static")) or not os.path.isfile(f):
                return self.send(404, b"not found", "text/plain")
            ct = {"html": "text/html", "js": "application/javascript", "css": "text/css"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
            self.send(200, open(f, "rb").read(), ct + "; charset=utf-8")
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": "internal error"})

def serve(port=8765, workers=None):
    """Pre-fork: bind once, fork N worker processes (copy-on-write index) that all accept on the socket."""
    import socket, signal
    workers = workers or int(os.environ.get("WORKERS", min(4, os.cpu_count() or 1)))
    s = Server(("0.0.0.0", port), H)
    print(f"listening on :{port} with {workers} workers", flush=True)
    if workers <= 1: return s.serve_forever()
    import gc; gc.freeze()  # keep index pages shared after fork
    kids = []
    for _ in range(workers):
        pid = os.fork()
        if pid == 0:
            try: s.serve_forever()
            finally: os._exit(0)
        kids.append(pid)
    def stop(*_):
        for k in kids:
            try: os.kill(k, signal.SIGTERM)
            except ProcessLookupError: pass
        os._exit(0)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    for k in kids: os.waitpid(k, 0)

if __name__ == "__main__": serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
