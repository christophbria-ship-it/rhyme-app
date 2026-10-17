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
