"""Render the Rhymer app icons (copper on cream) from SVG with headless Chromium -> static/icons/."""
import os
from playwright.sync_api import sync_playwright
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "icons")
def svg(maskable, scale=None):
    # maskable: full-bleed background, artwork inside the 80% safe zone
    s = scale or (0.62 if maskable else 0.8)
    rx = 0 if maskable else 112
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs><radialGradient id="g" cx="50%" cy="30%" r="75%"><stop offset="0" stop-color="#FFFBF3"/><stop offset="1" stop-color="#F3E6D2"/></radialGradient>
<linearGradient id="c" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#C8834A"/><stop offset=".5" stop-color="#B87333"/><stop offset="1" stop-color="#8E4E22"/></linearGradient></defs>
<rect width="512" height="512" rx="{rx}" fill="url(#g)"/>
<g transform="translate(256 256) scale({s}) translate(-256 -256)">
<circle cx="256" cy="256" r="200" fill="none" stroke="url(#c)" stroke-width="18"/>
<circle cx="256" cy="256" r="172" fill="none" stroke="#B87333" stroke-opacity=".35" stroke-width="4"/>
<text x="256" y="330" text-anchor="middle" font-family="Fraunces, Georgia, 'Times New Roman', serif" font-weight="700" font-size="230" fill="#7A3E1D">R</text>
<path d="M150 372 q53 -26 106 0 t106 0" fill="none" stroke="url(#c)" stroke-width="12" stroke-linecap="round"/>
</g></svg>'''
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, size, mask in [("icon-192.png", 192, False), ("icon-512.png", 512, False), ("icon-maskable-512.png", 512, True),
                             ("icon-maskable-192.png", 192, True), ("apple-touch-icon.png", 180, "apple")]:
        pg = b.new_page(viewport={"width": size, "height": size})
        pg.set_content(f'<html><head><link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700&display=block" rel="stylesheet"></head>'
                       f'<body style="margin:0;background:transparent">{svg(bool(mask), 0.8 if mask == "apple" else None).replace("<svg ", f"<svg width={size} height={size} ", 1)}</body></html>')
        pg.wait_for_timeout(1500)
        pg.screenshot(path=os.path.join(OUT, name), omit_background=not mask, clip={"x": 0, "y": 0, "width": size, "height": size}); pg.close()
    open(os.path.join(OUT, "icon.svg"), "w").write(svg(False))
    b.close()
print("icons written to", OUT)
