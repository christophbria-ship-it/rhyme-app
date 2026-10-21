import json, urllib.request, urllib.error, pytest
def get(base, path):
    try:
        with urllib.request.urlopen(base + path) as r: return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e: return e.code, e.read(), e.headers

def test_health(base_url):
    c, b, _ = get(base_url, "/api/health"); assert c == 200 and json.loads(b)["words"] > 120000
def test_rhymes(base_url):
    c, b, _ = get(base_url, "/api/rhymes?word=Silver&syllables=3&limit=10"); d = json.loads(b)
    assert c == 200 and d["word"] == "silver" and "elapsed_ms" in d
    assert all(x["syllables"] == 3 for x in d["perfect"] + d["near"] + d["slant"])
def test_suggest(base_url):
    c, b, _ = get(base_url, "/api/suggest?q=ora"); assert c == 200 and "orange" in json.loads(b)["suggestions"]
@pytest.mark.parametrize("q,code", [("/api/rhymes", 400), ("/api/rhymes?word=", 400), ("/api/rhymes?word=%3Cscript%3E", 400),
    ("/api/rhymes?word=cat&sort=bogus", 400), ("/api/rhymes?word=cat&pos=xyz", 400), ("/api/rhymes?word=cat&syllables=a", 400),
    ("/api/nope", 404), ("/../server.py", 404), ("/static/../server.py", 404)])
def test_errors(base_url, q, code):
    c, b, _ = get(base_url, q); assert c == code
def test_static(base_url):
    c, b, h = get(base_url, "/"); assert c == 200 and b"Rhymer" in b and "text/html" in h["Content-Type"]
    assert get(base_url, "/app.js")[0] == 200 and get(base_url, "/app.css")[0] == 200
def test_oov_api(base_url):
    d = json.loads(get(base_url, "/api/rhymes?word=snorkelbiscuit")[1]); assert d["known"] is False

# ---- songwriting endpoints ----
def post(base, path, body):
    import urllib.request
    req = urllib.request.Request(base + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

def test_themes_api(base_url):
    c, b, _ = get(base_url, "/api/themes"); d = json.loads(b)
    assert c == 200 and len(d["themes"]) == 20 and d["themes"][0] == {"id": "love", "label": "Love & romance", "size": d["themes"][0]["size"]}

def test_rhymes_theme_api(base_url):
    d = json.loads(get(base_url, "/api/rhymes?word=night&theme=night&theme_only=1")[1])
    assert d["theme"] == "night" and d["perfect"] and all(x["themed"] for x in d["perfect"])
    assert get(base_url, "/api/rhymes?word=night&theme=bogus")[0] == 400

def test_analyze_api(base_url):
    import urllib.parse
    d = json.loads(get(base_url, "/api/analyze?text=" + urllib.parse.quote("the cat\nthe hat"))[1]); assert d["scheme"] == "AA"
    c, d = post(base_url, "/api/analyze", json.dumps({"text": "roses are red\nviolets are blue\nsugar is sweet\nand so are you"}).encode())
    assert c == 200 and d["scheme"] == "ABCB" and d["total_lines"] == 4
    assert get(base_url, "/api/analyze")[0] == 400
    assert post(base_url, "/api/analyze", b"not json")[0] == 400 and post(base_url, "/api/analyze", b'{"text": 5}')[0] == 400
    assert post(base_url, "/api/analyze", json.dumps({"text": "x" * 10001}).encode())[0] == 400
    assert post(base_url, "/api/nope", b"{}")[0] == 404

def test_line_api(base_url):
    import urllib.parse
    d = json.loads(get(base_url, "/api/line?" + urllib.parse.urlencode({"prev": "The waves were crashing at my feet", "line": "My heart was skipping", "theme": "love"}))[1])
    assert d["needed"] == 3 and d["theme"] == "love" and all(x["syllables"] == 3 for x in d["suggestions"]["perfect"])
    assert get(base_url, "/api/line?prev=")[0] == 400 and get(base_url, "/api/line?prev=hello&theme=zz")[0] == 400

# ---- related + AI proxy ----
def test_related_api(base_url):
    d = json.loads(get(base_url, "/api/related?word=snow&limit=50")[1])
    assert d["in_vocab"] and "cold" in [x["word"] for x in d["related"]] and d["phrases"]
    assert get(base_url, "/api/related")[0] == 400 and get(base_url, "/api/related?word=%3Cx%3E")[0] == 400
    d = json.loads(get(base_url, "/api/rhymes?word=night&theme=related&theme_only=1")[1])
    assert d["perfect"] and all(x["themed"] for x in d["perfect"]) and "light" in [x["word"] for x in d["perfect"]]

def test_rank_lines_api(base_url):
    c, d = post(base_url, "/api/rank_lines", json.dumps({"line": "falling snow", "lines": ["the night is cold", "we let it go"]}).encode())
    assert c == 200 and [x["tier"] for x in d["lines"]] == ["perfect", "assonant"]
    assert post(base_url, "/api/rank_lines", json.dumps({"line": "", "lines": []}).encode())[0] == 400
    assert post(base_url, "/api/rank_lines", b"[1]")[0] == 400

def test_verify_api(base_url):
    c, d = post(base_url, "/api/verify", json.dumps({"word": "snow", "items": ["glow", "let it go", "banana"]}).encode())
    assert c == 200 and [x["text"] for x in d["items"]] == ["glow", "let it go"] and d["items"][1]["group"] == "phrase"
    assert post(base_url, "/api/verify", json.dumps({"word": "snow", "items": "x"}).encode())[0] == 400
    assert post(base_url, "/api/verify", b"nope")[0] == 400

def test_related_api_big(base_url):
    d = json.loads(get(base_url, "/api/related?word=heart")[1])
    assert len(d["related"]) >= 100 and len(d["phrases"]) >= 20 and {"perfect", "multi", "slant"} <= {x["group"] for x in d["related"]}

def test_ai_proxy(base_url, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    got = {}
    class W(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            got["path"] = self.path; got["key"] = self.headers.get("X-Rhymer-Key"); got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            b = json.dumps({"lines": ["we let it go"], "model": "mock"}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    s = ThreadingHTTPServer(("127.0.0.1", 0), W); threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.delenv("RHYMER_AI_URL", raising=False)
    assert post(base_url, "/api/ai/lines", b'{"line":"x"}')[0] == 503
    monkeypatch.setenv("RHYMER_AI_URL", f"http://127.0.0.1:{s.server_address[1]}"); monkeypatch.setenv("RHYMER_AI_KEY", "k123")
    c, d = post(base_url, "/api/ai/lines", json.dumps({"line": "falling snow", "count": 6}).encode())
    assert c == 200 and d["lines"] == ["we let it go"] and got == {"path": "/lines", "key": "k123", "body": {"line": "falling snow", "count": 6}}
    assert post(base_url, "/api/ai/lines", json.dumps({"line": "x" * 9000}).encode())[0] == 413
    c, d = post(base_url, "/api/ai/brainstorm", json.dumps({"word": "snow"}).encode())
    assert c == 200 and got["path"] == "/brainstorm" and got["body"] == {"word": "snow"}
    s.shutdown()
