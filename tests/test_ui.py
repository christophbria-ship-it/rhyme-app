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
    assert page.locator(".w.on").count() == 0 and page.is_disabled("#theme")
    page.locator(".switch").click(); expect(page.locator("#theme")).to_be_enabled()
    page.select_option("#theme", "night"); expect(page.locator(".ontheme")).to_be_visible()
    expect(page.locator('.tier[data-tier="perfect"] .w').first).to_have_class(re.compile(r"\bon\b"))
    assert page.locator('.tier[data-tier="perfect"] .w.on[data-w="light"]').count() == 1
    page.wait_for_timeout(350); shot(page, "theme-on")
    page.check("#themeOnly"); expect(page.locator(".w:not(.on)")).to_have_count(0)
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
