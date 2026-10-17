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
json.dump({"shards": SHARDS, "words": len(rows)}, open(os.path.join(OUT, "data", "manifest.json"), "w"))
for f in ("app.css", "app.js"): shutil.copy(os.path.join(ROOT, "static", f), OUT)
shutil.copy(os.path.join(ROOT, "static", "api-shim.js"), OUT)
html = open(os.path.join(ROOT, "static", "index.html")).read()
html = html.replace('href="/app.css"', 'href="app.css"').replace('<script src="/app.js"></script>', '<script src="api-shim.js"></script><script src="app.js"></script>')
open(os.path.join(OUT, "index.html"), "w").write(html)
open(os.path.join(OUT, ".nojekyll"), "w").close()
print("site built:", sum(os.path.getsize(os.path.join(OUT, "data", f)) for f in os.listdir(os.path.join(OUT, "data"))) // 1024, "KB data")
