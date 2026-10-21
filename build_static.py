"""Build a fully static version into site/: UI + JSON data shards + in-browser rhyme engine (api-shim.js).
Deployable to GitHub Pages; lookups run client-side, no server needed."""
import os, json, pickle, shutil
ROOT = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(ROOT, "site"); SHARDS = 8
d = pickle.load(open(os.path.join(ROOT, "data", "index.pkl"), "rb"))
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(os.path.join(OUT, "data"))
rows = [[w, d["info"][w]["syl"], d["info"][w]["freq"], ",".join(d["info"][w]["pos"]), "|".join(d["info"][w]["prons"]), {"dict": 0, "derived": 1, "g2p": 2}[d["info"][w]["conf"]]] for w in d["words"]]
n = (len(rows) + SHARDS - 1) // SHARDS
for i in range(SHARDS):
    json.dump(rows[i*n:(i+1)*n], open(os.path.join(OUT, "data", f"words-{i}.json"), "w"), separators=(",", ":"))
shutil.copy(os.path.join(ROOT, "data", "themes.json"), os.path.join(OUT, "data", "themes.json"))
# association shards (lazy-loaded by the browser only in "Related to my word" mode)
from engine import STOPWORDS
shutil.copytree(os.path.join(ROOT, "data", "assoc"), os.path.join(OUT, "data", "assoc"))
av = json.load(open(os.path.join(ROOT, "data", "assoc", "vocab.json"))); av["stopwords"] = sorted(STOPWORDS)
json.dump(av, open(os.path.join(OUT, "data", "assoc", "vocab.json"), "w"), separators=(",", ":"))
json.dump({"shards": SHARDS, "words": len(rows)}, open(os.path.join(OUT, "data", "manifest.json"), "w"))
for f in ("app.css", "app.js", "manifest.webmanifest"): shutil.copy(os.path.join(ROOT, "static", f), OUT)
shutil.copytree(os.path.join(ROOT, "static", "icons"), os.path.join(OUT, "icons"))
shutil.copy(os.path.join(ROOT, "static", "api-shim.js"), OUT)
html = open(os.path.join(ROOT, "static", "index.html")).read()
html = html.replace('<meta name="theme-color" content="#FBF7EF">', """<meta name="theme-color" content="#7A3E1D">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png"><link rel="icon" type="image/svg+xml" href="icons/icon.svg">
<link rel="apple-touch-icon" sizes="180x180" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="apple-mobile-web-app-title" content="Rhymer">
<meta name="application-name" content="Rhymer">""")
html = html.replace('<script src="/app.js"></script>', '<script src="/app.js"></script><script>if("serviceWorker" in navigator)addEventListener("load",()=>navigator.serviceWorker.register("sw.js",{scope:"./"}).then(r=>window.SW_REG=r).catch(e=>console.warn("SW failed",e)));</script>')
html = html.replace('href="/app.css"', 'href="app.css"')
# AI worker endpoint for the static site (no secrets: the worker holds the Workers AI binding)
ai_url = os.environ.get("RHYMER_AI_URL") or (open(os.path.join(ROOT, "worker", "URL")).read().strip() if os.path.exists(os.path.join(ROOT, "worker", "URL")) else "")
open(os.path.join(OUT, "config.js"), "w").write(f"window.RHYMER_AI_URL={json.dumps(ai_url.rstrip('/') + '/lines' if ai_url else '')};\n")
html = html.replace('<script src="api-shim.js"></script>', '<script src="config.js"></script><script src="api-shim.js"></script>').replace('<script src="/app.js"></script>', '<script src="config.js"></script><script src="api-shim.js"></script><script src="app.js"></script>')
open(os.path.join(OUT, "index.html"), "w").write(html)
open(os.path.join(OUT, ".nojekyll"), "w").close()
# service worker: precache list + content-hash version
import hashlib
allfiles = sorted(os.path.relpath(os.path.join(dp, f), OUT).replace(os.sep, "/") for dp, _, fs in os.walk(OUT) for f in fs if f not in (".nojekyll",))
# association shards are fetched lazily and cached at runtime by the service worker (not precached)
assets = ["./"] + [a for a in allfiles if not a.startswith("data/assoc/shard-")]
h = hashlib.sha256(b"rhymer-v4")
for a in allfiles: h.update(a.encode()); h.update(open(os.path.join(OUT, a), "rb").read())
sw = open(os.path.join(ROOT, "static", "sw.js")).read().replace("__VERSION__", h.hexdigest()[:12]).replace("__ASSETS__", json.dumps(assets))
open(os.path.join(OUT, "sw.js"), "w").write(sw)
print("sw version", h.hexdigest()[:12], "precache", len(assets), "files")
print("site built:", sum(os.path.getsize(os.path.join(OUT, "data", f)) for f in os.listdir(os.path.join(OUT, "data"))) // 1024, "KB data")
