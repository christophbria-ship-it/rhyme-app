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
        js = pg.evaluate("async w => (await (await fetch('api/rhymes?limit=5000&word='+encodeURIComponent(w))).json())", w)
        py = engine.rhymes(w, limit=5000)
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

# ---- PWA ----
def test_manifest_valid(browser, site_url):
    pg = browser.new_page(); pg.goto(site_url)
    href = pg.evaluate("document.querySelector('link[rel=manifest]').href")
    assert href == site_url + "manifest.webmanifest"
    m = pg.evaluate("async h => { const r = await fetch(h); return {ct: r.headers.get('content-type'), j: await r.json()} }", href)
    j = m["j"]
    assert j["name"] == "Rhymer" and j["short_name"] and j["display"] == "standalone"
    assert j["background_color"].upper() == "#FBF7EF" and j["theme_color"].upper() == "#7A3E1D"
    assert j["start_url"] == "./" and j["scope"] == "./"
    sizes = {(i["sizes"], i["purpose"]) for i in j["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes
    for i in j["icons"]:  # every icon loads, is a PNG of the declared size
        dim = pg.evaluate("""async src => { const r = await fetch(new URL(src, document.querySelector('link[rel=manifest]').href));
            const img = await createImageBitmap(await r.blob()); return [r.status, r.headers.get('content-type'), img.width, img.height] }""", i["src"])
        w, h = map(int, i["sizes"].split("x")); assert dim == [200, "image/png", w, h], (i, dim)
    apple = pg.evaluate("""async () => { const l = document.querySelector('link[rel=apple-touch-icon]'); const r = await fetch(l.href);
        const img = await createImageBitmap(await r.blob()); return [r.status, img.width] }""")
    assert apple == [200, 180]
    for name, val in [("apple-mobile-web-app-capable", "yes"), ("apple-mobile-web-app-title", "Rhymer"), ("theme-color", "#7A3E1D")]:
        assert pg.evaluate(f"document.querySelector('meta[name=\"{name}\"]').content") == val
    pg.close()

def test_service_worker_offline(browser, site_url):
    ctx = browser.new_context(); pg = ctx.new_page(); pg.goto(site_url)
    scope = pg.evaluate("navigator.serviceWorker.ready.then(r => r.scope)"); assert scope == site_url
    pg.reload(); pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    keys = pg.evaluate("caches.keys()"); assert len([k for k in keys if k.startswith("rhymer-") and k != "rhymer-fonts"]) == 1
    version = open(os.path.join(ROOT, "site", "sw.js")).read().split('const VERSION = "')[1].split('"')[0]
    assert "rhymer-" + version in keys and len(version) == 12
    cached = pg.evaluate("caches.open('rhymer-' + arguments[0]).then(c => c.keys()).then(ks => ks.map(r => r.url))".replace("arguments[0]", repr(version)))
    assert any(u.endswith("data/words-7.json") for u in cached) and any(u.endswith("icons/icon-512.png") for u in cached)
    ctx.set_offline(True)
    pg.goto(site_url + "?w=silver")
    expect(pg.locator("#status")).to_have_attribute("data-state", "done", timeout=30000)
    expect(pg.locator('.w[data-w="quicksilver"]')).to_be_visible()
    ctx.close()

def test_service_worker_version_changes_with_content():
    import hashlib
    sw = open(os.path.join(ROOT, "site", "sw.js")).read()
    assert "__VERSION__" not in sw and "__ASSETS__" not in sw and '"./"' in sw and "words-0.json" in sw

def test_service_worker_update_replaces_old_cache(browser, site_url):
    path = os.path.join(ROOT, "site", "sw.js"); orig = open(path).read()
    old = orig.split('const VERSION = "')[1].split('"')[0]
    ctx = browser.new_context(); pg = ctx.new_page(); pg.goto(site_url)
    pg.evaluate("navigator.serviceWorker.ready"); pg.reload(); pg.wait_for_function("navigator.serviceWorker.controller !== null")
    try:
        open(path, "w").write(orig.replace(old, "test-update1"))
        pg.evaluate("navigator.serviceWorker.getRegistration().then(r => r.update())")
        pg.wait_for_function("caches.keys().then(k => window._k = k), (window._k||[]).includes('rhymer-test-update1') && !(window._k||[]).includes('rhymer-%s')" % old, timeout=20000, polling=300)
    finally:
        open(path, "w").write(orig); ctx.close()

def test_songwriting_parity(browser, site_url, engine):
    pg = browser.new_page(); pg.goto(site_url); pg.evaluate("window.RHYME_READY")
    texts = ["I walked along the lonely shore\nThe waves were crashing at my feet\nI couldn't take it anymore\nMy heart was skipping every beat",
             "my love\nthe sky above\nthe month\nonce\nmy love", "one two\nred shoe\n\nbig tree\nsee me", "glorbify the zzyzx!!\n\n\n", "", "Rock'n'roll — well-known don't"]
    for t in texts:
        js = pg.evaluate("async t => (await (await fetch('api/analyze', {method:'POST', body: JSON.stringify({text:t})})).json())", t)
        assert js == engine.analyze(t), t
    for prev, line, theme in [("The waves were crashing at my feet", "My heart was skipping", "love"), ("I walked along the lonely shore", "", None),
                              ("Silver moon and orange sky", "Watch the city lights go", "night")]:
        js = pg.evaluate("async a => (await (await fetch('api/line?' + new URLSearchParams(a))).json())",
                         {k: v for k, v in {"prev": prev, "line": line, "theme": theme or "", "limit": "40"}.items()})
        assert js == engine.line_help(prev, line, theme=theme, limit=40), prev
    js = pg.evaluate("async () => (await (await fetch('api/rhymes?word=night&theme=night&limit=5000')).json())")
    py = engine.rhymes("night", theme="night", limit=5000)
    for t in ("perfect", "near", "slant"): assert [(x["word"], x["themed"]) for x in js[t]] == [(x["word"], x["themed"]) for x in py[t]]
    assert js["themed_total"] == py["themed_total"]
    th = pg.evaluate("async () => (await (await fetch('api/themes')).json()).themes")
    assert [t["id"] for t in th] == list(engine.theme_labels) and all(t["size"] == len(engine.themes[t["id"]]) for t in th)
    for q, code in [("api/analyze", 400), ("api/line?prev=", 400), ("api/rhymes?word=cat&theme=zz", 400)]:
        assert pg.evaluate("async q => (await fetch(q)).status", q) == code
    pg.close()

def test_static_songwriting_ui_offline(browser, site_url):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page(); pg.goto(site_url)
    pg.evaluate("navigator.serviceWorker.ready"); pg.reload(); pg.wait_for_function("navigator.serviceWorker.controller !== null")
    pg.wait_for_timeout(1500); ctx.set_offline(True)
    pg.goto(site_url + "#pad"); pg.fill("#pad", "the cat\nthe hat"); expect(pg.locator("#scheme")).to_contain_text("AA", timeout=30000)
    pg.goto(site_url + "#line"); pg.click("#lineSample"); expect(pg.locator("#lineStatus")).to_contain_text("needs 3 more syllables", timeout=30000)
    ctx.close()
