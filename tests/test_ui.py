import os, re, pytest
from playwright.sync_api import sync_playwright, expect
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
SIZES = {"mobile": (375, 812), "tablet": (768, 1024), "desktop": (1366, 900)}

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(); yield b; b.close()

@pytest.fixture(params=list(SIZES))
def page(request, browser):
    w, h = SIZES[request.param]
    ctx = browser.new_context(viewport={"width": w, "height": h}); pg = ctx.new_page()
    errors = []; pg.on("pageerror", lambda e: errors.append(e))
    pg.size_name = request.param; yield pg
    ctx.close(); assert not errors, errors

def shot(pg, name): pg.screenshot(path=os.path.join(SHOTS, f"{pg.size_name}-{name}.png"), full_page=True)

def test_results(page, base_url):
    page.goto(base_url); shot(page, "initial")
    page.fill("#q", "silver"); page.click("#go")
    expect(page.locator('.tier[data-tier="perfect"]')).to_be_visible()
    expect(page.locator(".w", has_text="quicksilver")).to_be_visible()
    assert page.locator('.group h3').count() >= 2
    w = page.evaluate("document.documentElement.scrollWidth"); assert w <= SIZES[page.size_name][0]
    shot(page, "results")

def test_autosuggest_and_keyboard(page, base_url):
    page.goto(base_url); page.type("#q", "oran", delay=30)
    expect(page.locator('#sug li[data-w="orange"]')).to_be_visible(); shot(page, "autosuggest")
    page.keyboard.press("ArrowDown"); assert page.input_value("#q").startswith("oran")
    page.locator('#sug li[data-w="orange"]').dispatch_event("mousedown")
    expect(page.locator("#status")).to_have_attribute("data-state", re.compile("done|empty"))
    assert page.input_value("#q") == "orange"

def test_filters_ui(page, base_url):
    page.goto(base_url + "/?w=cat"); expect(page.locator("#status")).to_have_attribute("data-state", "done")
    page.select_option("#syl", "1"); page.select_option("#tiers", "perfect")
    expect(page.locator(".group h3")).to_have_count(1); expect(page.locator(".group h3")).to_have_text("1 syllable")
    assert page.locator(".tier").count() == 1
    page.click(".w >> nth=0"); expect(page.locator("#status")).to_have_attribute("data-state", re.compile("done|empty"))

def test_loading_state(page, base_url):
    held = []
    page.route("**/api/rhymes*", lambda r: held.append(r))  # hold the request open
    page.goto(base_url); page.fill("#q", "orange"); page.click("#go")
    expect(page.locator("#status")).to_have_attribute("data-state", "loading")
    expect(page.locator(".skel").first).to_be_visible(); shot(page, "loading")
    page.wait_for_function("true"); assert held; held[0].continue_()
    expect(page.locator("#status")).to_have_attribute("data-state", "done", timeout=10000)

def test_empty_state(page, base_url):
    page.goto(base_url); page.fill("#maxl", "2"); page.fill("#q", "orange"); page.click("#go")
    expect(page.locator("#empty")).to_be_visible(); shot(page, "empty")

def test_error_states(page, base_url):
    page.goto(base_url); page.click("#go")
    expect(page.locator(".err")).to_contain_text("enter a word"); shot(page, "error-blank")
    page.route("**/api/rhymes*", lambda r: r.fulfill(status=500, content_type="application/json", body='{"error":"internal error"}'))
    page.fill("#q", "cat"); page.click("#go"); expect(page.locator(".err")).to_contain_text("internal error"); shot(page, "error-server")
    page.unroute("**/api/rhymes*"); page.route("**/api/rhymes*", lambda r: r.abort())
    page.fill("#q", "dog"); page.click("#go"); expect(page.locator(".err")).to_be_visible(); shot(page, "error-network")

def test_theme(page, base_url):
    page.goto(base_url + "/?w=cat"); expect(page.locator("#status")).to_have_attribute("data-state", "done")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(251, 247, 239)"
    assert page.evaluate("getComputedStyle(document.querySelector('h1')).color") == "rgb(122, 62, 29)"
    assert "Fraunces" in page.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily")
    assert page.locator(".logo").is_visible()
    r = page.evaluate("getComputedStyle(document.querySelector('.w')).borderRadius"); assert float(r.rstrip("px")) >= 20
    assert page.evaluate("getComputedStyle(document.querySelector('.tier')).boxShadow") != "none"

# ---- songwriting UI ----
VERSE = "I walked along the lonely shore\nThe waves were crashing at my feet\nI couldn't take it anymore\nMy heart was skipping every beat\n\nSilver moon and orange sky\nWatch the city lights go by"

def test_tabs(page, base_url):
    page.goto(base_url)
    for t in ("line", "pad", "rhymes"):
        page.click(f"#t-{t}"); expect(page.locator(f"#tab-{t}")).to_be_visible()
        expect(page.locator(f"#t-{t}")).to_have_attribute("aria-selected", "true")
        for o in {"rhymes", "line", "pad"} - {t}: expect(page.locator(f"#tab-{o}")).to_be_hidden()
    page.goto(base_url + "/#pad"); expect(page.locator("#tab-pad")).to_be_visible()

def test_theme_toggle(page, base_url):
    page.goto(base_url + "/?w=night"); expect(page.locator("#status")).to_have_attribute("data-state", "done")
    # default: switch on, "Related to my word"
    expect(page.locator("#themeToggle")).to_be_checked(); expect(page.locator("#theme")).to_have_value("related")
    expect(page.locator("#relCard")).to_be_visible()
    page.locator(".switch").click(); expect(page.locator("#theme")).to_be_disabled(); expect(page.locator("#relCard")).to_have_count(0)
    assert page.locator(".w.on").count() == 0
    page.locator(".switch").click(); expect(page.locator("#theme")).to_be_enabled()
    page.select_option("#theme", "night"); expect(page.locator(".ontheme")).to_be_visible()
    expect(page.locator('.tier[data-tier="perfect"] .w').first).to_have_class(re.compile(r"\bon\b"))
    assert page.locator('.tier[data-tier="perfect"] .w.on[data-w="light"]').count() == 1
    page.wait_for_timeout(350); shot(page, "theme-on")
    page.check("#themeOnly"); expect(page.locator(".tier .w:not(.on)")).to_have_count(0)
    page.reload(); expect(page.locator("#themeToggle")).to_be_checked(); expect(page.locator("#theme")).to_have_value("night")
    page.locator(".switch").click(); expect(page.locator(".ontheme")).to_have_count(0)

def test_line_helper(page, base_url):
    page.goto(base_url + "/#line"); page.click("#lineGo"); expect(page.locator("#lineStatus .err")).to_be_visible()
    page.click("#lineSample"); expect(page.locator("#lineStatus")).to_have_attribute("data-state", "done")
    expect(page.locator("#lineStatus")).to_contain_text("needs 3 more syllables")
    sups = page.locator('#lineOut .tier[data-tier="perfect"] .sugw sup').all_inner_texts(); assert sups and set(sups) == {"3"}
    assert page.locator(".mrow").count() == 2 and page.locator(".mw").count() >= 10
    page.wait_for_timeout(350); shot(page, "line-helper")
    first = page.locator('#lineOut .tier[data-tier="perfect"] .sugw').first; w = first.get_attribute("data-w"); first.click()
    expect(page.locator("#curLine")).to_have_value("My heart was skipping " + w)
    expect(page.locator("#lineStatus")).to_contain_text("already as long")
    assert page.evaluate("document.documentElement.scrollWidth") <= SIZES[page.size_name][0]

def test_lyrics_pad(page, base_url):
    page.goto(base_url + "/#pad"); page.fill("#pad", VERSE)
    expect(page.locator("#scheme")).to_contain_text("ABAB AA")
    expect(page.locator("#padLines .syl")).to_have_count(6)
    assert page.locator("#padLines .syl").all_inner_texts()[:2] == ["8", "8"]
    expect(page.locator("#padStats")).to_contain_text("6 lines"); expect(page.locator("#padSaved")).to_have_text("Saved")
    page.wait_for_timeout(350); shot(page, "lyrics-pad")
    page.reload(); expect(page.locator("#pad")).to_have_value(VERSE); expect(page.locator("#scheme")).to_contain_text("ABAB AA")
    page.locator('.endw[data-w="feet"]').click(); expect(page.locator("#tab-rhymes")).to_be_visible()
    expect(page.locator("#q")).to_have_value("feet"); expect(page.locator('.w[data-w="beat"]').first).to_be_visible()
    page.goto(base_url + "/#pad"); page.once("dialog", lambda d: d.accept()); page.click("#padClear")
    expect(page.locator("#pad")).to_have_value(""); expect(page.locator("#padStats")).to_contain_text("will appear here")

def test_lyrics_pad_error(page, base_url):
    page.route("**/api/analyze", lambda r: r.fulfill(status=500, content_type="application/json", body='{"error":"internal error"}'))
    page.goto(base_url + "/#pad"); page.fill("#pad", "hello world")
    expect(page.locator("#padStats .err")).to_contain_text("internal error")


# ---- related rhymes + AI line writer (worker mocked) ----
import json as _json
AI_LINES = ["The world is hushed and white below", "I feel the bitter winter wind blow", "The city sleeps in frozen light",
            "Our footprints fading as we go", "Feeling the winter in my bones", "walking through the falling snow"]

BRAINSTORM = {"perfect": ["glow", "tableau", "zzqx"], "multi": ["let it go", "overflow"], "slant": ["cold"], "phrases": ["white glow", "below zero", "banana bread"]}

def _ai_body(route):
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(route.request.url).query).get("q")
    return _json.loads(q[0] if q else (route.request.post_data or "{}"))

def mock_ai(page, lines=AI_LINES, status=200, seen=None, bs=BRAINSTORM):
    def h(route):
        body = _ai_body(route)
        if "brainstorm" in route.request.url:
            if bs is None: return route.fulfill(status=503, content_type="application/json", body='{"error":"not configured"}')
            return route.fulfill(status=200, content_type="application/json", body=_json.dumps({**bs, "model": "@cf/meta/mock"}))
        if seen is not None: seen.append(body)
        if status != 200: return route.fulfill(status=status, content_type="application/json", body=_json.dumps({"error": "AI service error"}))
        out = [l for l in lines if l not in body.get("exclude", [])] or ["A brand new line that ends in glow"]
        route.fulfill(status=200, content_type="application/json", body=_json.dumps({"lines": out[:30], "model": "@cf/meta/mock", "ms": 5}))
    page.route("**/api/ai/**", h)

def test_related_card(page, base_url):
    mock_ai(page)
    page.goto(base_url + "/?w=snow"); expect(page.locator("#relCard")).to_be_visible()
    expect(page.locator("#relCard")).to_have_attribute("data-bs", "done")
    rel = page.locator("#relCard .w.rel").evaluate_all("e => e.map(x => x.dataset.w)")
    assert len(rel) >= 100 and "cold" in rel and {"blow", "below", "low", "glow"} & set(rel), len(rel)
    groups = page.locator("#relCard .relgroup").evaluate_all("e => e.map(x => x.dataset.group)")
    assert groups == ["perfect", "multi", "slant", "phrase"], groups
    ai = page.locator("#relCard .ai").all_inner_texts(); joined = " ".join(ai)
    assert "tableau" in joined and "banana" not in joined and "zzqx" not in joined, ai
    expect(page.locator("#relCard .bsnote")).to_contain_text("more from AI")
    expect(page.locator("#relCard .phrase").first).to_be_visible()
    page.wait_for_timeout(350); shot(page, "related")
    ph = page.locator("#relCard .phrase").first; ph.click(); expect(ph).to_have_text("Copied ✓")
    page.uncheck("#bsToggle"); expect(page.locator("#relCard")).to_have_attribute("data-bs", "off")
    assert page.evaluate("localStorage.getItem('rhymer-bs')") == "0"; expect(page.locator("#relCard .ai")).to_have_count(0)
    page.check("#bsToggle"); expect(page.locator("#relCard")).to_have_attribute("data-bs", "done")
    page.locator('#relCard .w.rel[data-w="cold"]').first.click(); expect(page.locator("#q")).to_have_value("cold")

def test_related_brainstorm_unavailable(page, base_url):
    mock_ai(page, bs=None)
    page.goto(base_url + "/?w=night"); expect(page.locator("#relCard")).to_have_attribute("data-bs", "error")
    assert page.locator("#relCard .w.rel").count() >= 100

def test_ai_line_writer(page, base_url):
    seen = []; mock_ai(page, seen=seen)
    page.goto(base_url + "/#line"); page.click("#aiGo"); expect(page.locator("#aiLine .err")).to_contain_text("Write a lyric line")
    page.fill("#prevLine", "walking through the falling snow"); page.select_option("#aiLine .aimood", "love"); page.click("#aiGo")
    expect(page.locator("#aiLine")).to_have_attribute("data-state", "done")
    tiers = [t.lower() for t in page.locator("#aiLine .ail .tb:not(.tx)").all_inner_texts()]
    assert tiers[:3] == ["perfect"] * 3 and "repeat" not in tiers and "none" not in tiers, tiers
    scores = [int(t) for t in page.locator("#aiLine .ail .sc").all_inner_texts()]; assert scores == sorted(scores, reverse=True) and scores[0] >= 60
    texts = page.locator("#aiLine .ail .txt").all_inner_texts(); assert "walking through the falling snow" not in texts and "The city sleeps in frozen light" not in texts
    b = seen[0]; assert b["line"] == "walking through the falling snow" and b["mood"] == "love" and b["end_word"] == "snow" and b["count"] == 24
    assert b["syllables"] == 7 and "glow" in b["rhymes"] and "exclude" not in b and "calling" in b["echo"]["words"] and "DUM" in b["rhythm"]
    expect(page.locator("#aiLine .aistatus")).to_contain_text("AI candidates")
    page.wait_for_timeout(350); shot(page, "ai-lines")
    page.locator("#aiLine .cp").first.click(); expect(page.locator("#aiLine .cp").first).to_have_text("Copied ✓")
    n = page.locator("#aiLine .ail").count()
    page.click("#aiLine .aimore"); expect(page.locator("#aiLine .ail")).to_have_count(n + 1)
    assert len(seen) == 2 and len(seen[1]["exclude"]) == 6 and seen[1]["seed"] == 1

def test_ai_fallback(page, base_url):
    mock_ai(page, status=502)
    page.goto(base_url + "/#line"); page.fill("#prevLine", "walking through the falling snow"); page.click("#aiGo")
    expect(page.locator("#aiLine")).to_have_attribute("data-state", "fallback")
    expect(page.locator("#aiLine .note")).to_contain_text("AI unavailable"); expect(page.locator("#aiLine .fbw").first).to_be_visible()
    page.wait_for_timeout(300); shot(page, "ai-fallback")
    page.unroute("**/api/ai/**"); page.context.set_offline(True)
    page.click("#aiGo"); expect(page.locator("#aiLine .note")).to_contain_text("offline"); page.context.set_offline(False)

def test_ai_lyrics_pad(page, base_url):
    seen = []; mock_ai(page, seen=seen)
    page.goto(base_url + "/#pad"); page.fill("#pad", "Cold wind across the frozen lake\nwalking through the falling snow"); page.click("#padAI")
    expect(page.locator("#aiPad")).to_have_attribute("data-state", "done")
    assert seen[0]["line"] == "walking through the falling snow" and seen[0]["context"] == "Cold wind across the frozen lake"
    page.locator("#aiPad .ins").first.click()
    expect(page.locator("#pad")).to_have_value("Cold wind across the frozen lake\nwalking through the falling snow\nThe world is hushed and white below")
    expect(page.locator("#scheme")).to_contain_text("ABB"); expect(page.locator("#density")).to_contain_text("Rhyme density")
    page.wait_for_timeout(300); shot(page, "ai-pad")
