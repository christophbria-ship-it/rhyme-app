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
