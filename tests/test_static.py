"""Static (GitHub Pages) build: served under a sub-path, engine runs in-browser. Checks parity with the Python engine."""
import os, re, json, subprocess, sys, tempfile, threading, functools, pytest
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright, expect
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); SHOTS = os.path.join(ROOT, "screenshots")
SIZES = {"mobile": (375, 812), "tablet": (768, 1024), "desktop": (1366, 900)}

@pytest.fixture(scope="module")
def site_url():
    subprocess.run([sys.executable, os.path.join(ROOT, "build_static.py")], check=True, capture_output=True)
    tmp = tempfile.mkdtemp(); os.symlink(os.path.join(ROOT, "site"), os.path.join(tmp, "rhyme-app"))
    class Q(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    s = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=tmp))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/rhyme-app/"; s.shutdown()

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(); yield b; b.close()

def test_parity_with_python_engine(browser, site_url, engine):
    pg = browser.new_page(); pg.goto(site_url); pg.evaluate("window.RHYME_READY")
    cases = ["cat", "orange", "silver", "month", "purple", "colonel", "phlegm", "love", "it", "glorbify", "nation", "day",
             "Computer", "dog", "rhythm", "x", "don't", "well-known"]
    for w in cases:
        js = pg.evaluate("async w => (await (await fetch('api/rhymes?limit=2000&word='+encodeURIComponent(w))).json())", w)
        py = engine.rhymes(w, limit=2000)
        for t in ("perfect", "near", "slant"):
            assert [x["word"] for x in js[t]] == [x["word"] for x in py[t]], (w, t)
            assert [x["score"] for x in js[t]] == [x["score"] for x in py[t]] and [x["matched_syllables"] for x in js[t]] == [x["matched_syllables"] for x in py[t]]
        assert js["guessed_from"] == py["guessed_from"]
    for q in ["rhy", "ora", "zzzq"]:
        js = pg.evaluate("async q => (await (await fetch('api/suggest?q='+q)).json()).suggestions", q)
        assert js == engine.suggest(q)
    for bad in ["", "%3Cb%3E", "cat&sort=nope", "cat&pos=zz", "cat&syllables=a"]:
        st = pg.evaluate("async q => (await fetch('api/rhymes?word='+q)).status", bad); assert st == 400, bad
    pg.close()

@pytest.mark.parametrize("size", list(SIZES))
def test_static_ui(browser, site_url, size):
    w, h = SIZES[size]; ctx = browser.new_context(viewport={"width": w, "height": h}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(e))
    held = []; pg.route("**/data/words-*.json", lambda r: held.append(r))
    pg.goto(site_url); pg.fill("#q", "orange"); pg.click("#go")
    expect(pg.locator("#status")).to_have_attribute("data-state", "loading")
    pg.screenshot(path=os.path.join(SHOTS, f"static-{size}-loading.png"), full_page=True)
    for r in held: r.continue_()
    pg.unroute("**/data/words-*.json")
    expect(pg.locator("#status")).to_have_attribute("data-state", "done", timeout=20000)
    expect(pg.locator('.tier[data-tier="slant"] .w[data-w="porridge"]')).to_be_visible()
    pg.screenshot(path=os.path.join(SHOTS, f"static-{size}-results.png"), full_page=True)
    pg.fill("#maxl", "2"); pg.locator("#maxl").dispatch_event("change"); expect(pg.locator("#empty")).to_be_visible()
    pg.fill("#maxl", ""); pg.fill("#q", ""); pg.click("#go"); expect(pg.locator(".err")).to_be_visible()
    assert pg.evaluate("document.documentElement.scrollWidth") <= w
    ctx.close(); assert not errs, errs

def test_static_data_failure_shows_error(browser, site_url):
    pg = browser.new_page(); pg.route("**/data/words-2.json", lambda r: r.abort())
    pg.goto(site_url); pg.fill("#q", "cat"); pg.click("#go")
    expect(pg.locator(".err")).to_be_visible(); pg.screenshot(path=os.path.join(SHOTS, "static-error-data.png")); pg.close()
