"""One-off: build data/phrases.txt, the phrase bank for multi-word / compound rhymes.
Sources, cached in /tmp:
  - Wiktionary categories: English idioms, phrasal verbs, similes and proverbs (CC BY-SA), from /tmp/wikt/*.json
  - ConceptNet Numberbatch 19.08 multi-word terms whose words are all common (CC BY-SA), from /tmp/nb/nb.words
  - ~2.4k lyric-style phrases generated once with Workers AI (mistral-small-3.1-24b), from /tmp/aiphr.json
Keeps 2-6 word phrases made only of known words, without placeholders, and not ending in a bare function word."""
import json, os, pickle, re
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
info = pickle.load(open(os.path.join(D, "index.pkl"), "rb"))["info"]
BAD_END = set("a an the of to and or but for with at by from as than that my your his her our their its is are was were be "
              "into onto upon very".split())
PLACEHOLDER = re.compile(r"\b(one's|someone|someone's|something|oneself|somebody|sb|sth|etc)\b")
def clean(s):
    s = s.lower().replace("’", "'").replace("‘", "'").strip()
    s = re.sub(r"[^a-z' \-]", " ", s); s = re.sub(r"\s+", " ", s).strip()
    return s
def ok(s, maxw=6):
    if not s or PLACEHOLDER.search(s): return False
    t = s.replace("-", " ").split()
    if not (2 <= len(t) <= maxw): return False
    if t[-1] in BAD_END or t[-1] not in info or info[t[-1]]["freq"] < 2.5: return False
    return all(x.strip("'") in info for x in t)
out = {}
def add(s, src):
    s = clean(s)
    if ok(s) and s not in out: out[s] = src
ai = json.load(open("/tmp/aiphr.json"))
for arr in ai.values():
    for s in arr: add(s, "ai")
for c in ["English_idioms", "English_similes", "English_proverbs", "English_phrasal_verbs"]:
    for s in json.load(open(f"/tmp/wikt/{c}.json")): add(s, "wikt")
for w in open("/tmp/nb/nb.words").read().split("\n"):
    if "_" not in w: continue
    t = w.split("_")
    p0 = info.get(t[0], {}).get("pos", [])
    if len(t) == 2 and ("v" in p0 or "adj" in p0) and all(re.fullmatch(r"[a-z]+", x) and x in info and len(x) > 1 and info[x]["freq"] >= 4.7 for x in t): add(" ".join(t), "cn")
with open(os.path.join(D, "phrases.txt"), "w") as f:
    for s, src in sorted(out.items()): f.write(f"{s}\t{src}\n")
from collections import Counter
print(len(out), Counter(out.values()))
