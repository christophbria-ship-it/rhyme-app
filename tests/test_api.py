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
