"""One-off data prep (needs: pip install wordfreq g2p_en). Writes committed files used by build_index.py:
  data/extra_words.tsv : word \t confidence(derived|g2p) \t ARPAbet pron   (words not in CMUdict)
  data/zipf.tsv        : word \t wordfreq zipf frequency                  (all included words)
Expands the vocabulary to ~TARGET words with the most frequent wordfreq 'large' English words not in CMUdict.
Inflected forms whose base is in CMUdict get rule-derived pronunciations; the rest use the g2p_en neural model."""
import re, os, sys
from wordfreq import top_n_list, zipf_frequency
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"); TARGET = int(os.environ.get("TARGET", 250000))
cmu = {}
for line in open(os.path.join(D, "cmudict.dict"), encoding="utf-8"):
    line = line.split("#")[0].strip()
    if line:
        w, *ph = line.split(); cmu.setdefault(re.sub(r"\(\d+\)$", "", w).lower(), ph)
VOICELESS = {"P", "T", "K", "F", "TH"}; SIB = {"S", "Z", "SH", "ZH", "CH", "JH"}
def derive(w):
    """pron for an inflected form from its CMUdict base, or None."""
    def last(ph): return re.sub(r"\d", "", ph[-1])
    tries = []
    if w.endswith("ies"): tries.append((w[:-3] + "y", "S"))
    if w.endswith("es"): tries.append((w[:-2], "S"))
    if w.endswith("s") and not w.endswith("ss"): tries.append((w[:-1], "S"))
    if w.endswith("'s"): tries.append((w[:-2], "S"))
    if w.endswith("ied"): tries.append((w[:-3] + "y", "D"))
    if w.endswith("ed"): tries += [(w[:-2], "D"), (w[:-1], "D")] + ([(w[:-3], "D")] if len(w) > 4 and w[-3] == w[-4] else [])
    if w.endswith("ing"): tries += [(w[:-3], "NG"), (w[:-3] + "e", "NG")] + ([(w[:-4], "NG")] if len(w) > 5 and w[-4] == w[-5] else [])
    if w.endswith("er"): tries += [(w[:-2], "ER"), (w[:-1], "ER")] + ([(w[:-3], "ER")] if len(w) > 4 and w[-3] == w[-4] else [])
    if w.endswith("est"): tries += [(w[:-3], "EST"), (w[:-2], "EST")]
    if w.endswith("ly"): tries.append((w[:-2], "LY"))
    if w.endswith("ness"): tries.append((w[:-4], "NESS"))
    for base, suf in tries:
        ph = cmu.get(base)
        if not ph or len(base) < 2: continue
        l = last(ph)
        if suf == "S": add = ["IH0", "Z"] if l in SIB else ["S"] if l in VOICELESS else ["Z"]
        elif suf == "D": add = ["IH0", "D"] if l in {"T", "D"} else ["T"] if l in VOICELESS | {"S", "SH", "CH"} else ["D"]
        elif suf == "NG": add = ["IH0", "NG"]
        elif suf == "ER": add = ["ER0"]
        elif suf == "EST": add = ["AH0", "S", "T"]
        elif suf == "LY": add = ["L", "IY0"]
        else: add = ["N", "AH0", "S"]
        return ph + add
    return None
words = top_n_list("en", 1_000_000, wordlist="large")
ok = re.compile(r"^[a-z][a-z'\-]*[a-z]$")
new = [w for w in words if ok.match(w) and w not in cmu and not w.startswith("-") and "--" not in w]
new = new[:max(0, TARGET - len(cmu))]
from g2p_en import G2p
g2p = G2p(); out = []
for i, w in enumerate(new):
    ph = derive(w); conf = "derived"
    if not ph:
        ph = [p for p in g2p.predict(w.replace("'", "").replace("-", " ").split()[0]) if p] if " " not in w.replace("-", " ") else \
             [p for part in w.replace("'", "").split("-") for p in g2p.predict(part)]
        conf = "g2p"
    if ph: out.append(f"{w}\t{conf}\t{' '.join(ph)}")
    if i % 20000 == 0: print(i, w, file=sys.stderr, flush=True)
open(os.path.join(D, "extra_words.tsv"), "w").write("\n".join(out) + "\n")
allw = set(cmu) | {l.split("\t")[0] for l in out}
with open(os.path.join(D, "zipf.tsv"), "w") as f:
    for w in sorted(allw):
        z = zipf_frequency(w, "en", wordlist="large")
        if z > 0: f.write(f"{w}\t{z}\n")
print("cmu", len(cmu), "new", len(out), "derived", sum("\tderived\t" in l for l in out))
