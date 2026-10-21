"""Opt-in live check of the deployed AI line writer (uses real Workers AI quota; responses are edge-cached 7 days).
    .venv/bin/python tests/live_quality.py ["line"] ...
Mirrors the app: hints from the local engine -> worker GET ?q= -> rank_lines -> best 8.
Pass = >= 6 of the 8 have a true rhyme on the stressed vowel (perfect/near) and are within +-2 syllables."""
import json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import Engine
URL = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "worker", "URL")).read().strip().rstrip("/")
ORIGIN = "https://christophbria-ship-it.github.io"

def body_for(e, line, mood="any"):
    h = e.line_help(line, "", limit=40); end = h["end_word"]
    rel = [x for x in e.related(end, limit=120, phrases=0)["related"] if x["group"] != "slant" and x["freq"] >= 3.8 and x["pos"] and x["word"].isalpha() and len(x["word"]) >= 3]
    H = []
    def add(w, cap=10):
        if len(H) < cap and w not in H and w != end: H.append(w)
    for x in [x for x in rel if x["tier"] == "perfect"][:7]: add(x["word"])
    for x in sorted([x for x in h["suggestions"]["perfect"] if x["freq"] >= 4.2 and x["pos"] and x["word"].isalpha() and len(x["word"]) >= 3], key=lambda x: -x["freq"])[:12]: add(x["word"], 8)
    for x in rel: add(x["word"])
    rel = H
    rhythm = " ".join("-".join("DUM" if c == "/" else "da" for c in w["stress"]) for w in h["prev"]["words"])
    b = {"line": line, "mood": mood, "count": 24, "syllables": h["target_syllables"], "end_word": end, "rhymes": rel, "rhythm": rhythm}
    if h.get("echo") and h["echo"]["words"]: b["echo"] = {"word": h["echo"]["word"], "words": h["echo"]["words"][:12]}
    return b

def run(e, line):
    b = body_for(e, line); q = json.dumps(b, separators=(",", ":"))
    req = urllib.request.Request(URL + "/lines?v=6e&q=" + urllib.parse.quote(q), headers={"Origin": ORIGIN, "User-Agent": "rhymer-live-test"})
    with urllib.request.urlopen(req, timeout=90) as r: d = json.load(r); cache = r.headers.get("cf-cache-status")
    sense = d.get("sense") if isinstance(d.get("sense"), list) and len(d["sense"]) == len(d["lines"]) else None
    ranked = e.rank_lines(line, d["lines"][:40], sense=sense[:40] if sense else None)["lines"]
    best = [x for x in ranked if x["tier"] != "none" and x["score"] >= 35][:8]
    good = [x for x in best if x["tier"] in ("perfect", "near") and abs(x["syllable_diff"]) <= 2]
    return d, cache, ranked, best, good

if __name__ == "__main__":
    e = Engine(); lines = sys.argv[1:] or ["walking through the falling snow"]; ok = True
    for line in lines:
        d, cache, ranked, best, good = run(e, line)
        print(f"\n{line!r}: model={d.get('model')} candidates={len(d['lines'])} cache={cache} cached={d.get('cached', False)}")
        for x in best: print(f"  {x['score']:3d} {x['tier']:8s} syl={x['syllables']:2d} multi={x['multi']} int={x['internal']} sense={x['sense']}  {x['text']}")
        print(f"  -> {len(good)}/{len(best)} true stressed-vowel rhymes within +-2 syllables")
        ok &= len(best) == 8 and len(good) >= 6
    sys.exit(0 if ok else 1)
