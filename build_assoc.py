"""One-off: build the word-association dataset from GloVe 6B 100d (needs gensim + numpy + the fse/glove-wiki-gigaword-100
KeyedVectors files). Writes compact, lazily-loaded shards to data/assoc/ (committed; build/CI does not need GloVe):
  vocab.json      {"words": [...], "k_rhyme": K1, "k_gen": K2, "shards": S, "per_shard": P}
  shard-XX.bin    per word, fixed width: K1 uint16 "rhyme-neighbour" ids (same stressed vowel, i.e. rhyme-eligible),
                  K1 uint8 cosine*255 for them, then K2 uint16 general neighbour ids (65535 = empty)
Rhyme neighbours are the most similar words *within the group of words sharing the stressed vowel of the rhyme part*,
so association can be combined with rhyme quality later; general neighbours feed phrase building."""
import os, sys, json, re, pickle, struct
import numpy as np
from gensim.models import KeyedVectors
from build_index import rhyme_tail, strip, VOWELS
ROOT = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(ROOT, "data"); OUT = os.path.join(D, "assoc")
GLOVE = os.environ.get("GLOVE", "/tmp/glove/g.model"); TOP = int(os.environ.get("TOP", 60000))
K1, K2, SHARDS = 36, 20, 16
info = pickle.load(open(os.path.join(D, "index.pkl"), "rb"))["info"]
kv = KeyedVectors.load(GLOVE)
words = [w for w in kv.index_to_key[:TOP] if re.fullmatch(r"[a-z]+", w) and w in info and len(w) > 1]
print("vocab", len(words))
idx = {w: i for i, w in enumerate(words)}
M = np.stack([kv[w] for w in words]).astype(np.float32); M /= np.linalg.norm(M, axis=1, keepdims=True)
def svowels(w):
    out = set()
    for p in info[w]["prons"]:
        t = rhyme_tail(p.split())
        v = [strip(x) for x in t if strip(x) in VOWELS]
        if v: out.add(v[0])
    return out
groups = {}
for i, w in enumerate(words):
    for v in svowels(w): groups.setdefault(v, []).append(i)
N = len(words); rn = np.full((N, K1), 65535, np.uint16); rs = np.zeros((N, K1), np.uint8); gn = np.full((N, K2), 65535, np.uint16)
best = {}
for v, ids in groups.items():
    ids = np.array(ids); G = M[ids]
    for s in range(0, len(ids), 2048):
        S = G[s:s + 2048] @ G.T
        for r, row in enumerate(S):
            me = ids[s + r]; row[s + r] = -1
            top = np.argpartition(-row, min(K1 * 4, len(row) - 1))[:K1 * 4]
            for j in top:
                c = ids[j]; sim = float(row[j])
                if sim > 0: best.setdefault(me, {}); best[me][c] = max(best[me].get(c, 0), sim)
from engine import Engine, TIER_Q, ASSONANT_Q, STOPWORDS, _stem_clash
eng = Engine()
for me, d in best.items():
    w = words[me]
    cd = eng._candidates(w); tq = {}
    for t in ("slant", "near", "perfect"):
        for c, _, _ in cd[t]: tq[c] = TIER_Q[t]
    # keep the neighbours with the best association x rhyme quality (store the raw similarity)
    items = [(c, s) for c, s in d.items() if not _stem_clash(w, words[c]) and words[c] not in STOPWORDS]
    items.sort(key=lambda x: (-x[1] * tq.get(words[x[0]], ASSONANT_Q), words[x[0]]))
    for k, (c, s) in enumerate(items[:K1]): rn[me, k] = c; rs[me, k] = min(255, int(round(s * 255)))
for s in range(0, N, 4096):
    S = M[s:s + 4096] @ M.T
    for r in range(S.shape[0]): S[r, s + r] = -1
    top = np.argpartition(-S, K2, axis=1)[:, :K2]
    for r in range(S.shape[0]):
        order = top[r][np.argsort(-S[r, top[r]])]; gn[s + r, :] = order
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
per = (N + SHARDS - 1) // SHARDS
for sh in range(SHARDS):
    a, b = sh * per, min(N, (sh + 1) * per)
    with open(os.path.join(OUT, f"shard-{sh:02d}.bin"), "wb") as f:
        for i in range(a, b): f.write(rn[i].astype("<u2").tobytes() + rs[i].tobytes() + gn[i].astype("<u2").tobytes())
json.dump({"words": words, "k_rhyme": K1, "k_gen": K2, "shards": SHARDS, "per_shard": per, "source": "GloVe 6B 100d (glove-wiki-gigaword-100)"},
          open(os.path.join(OUT, "vocab.json"), "w"), separators=(",", ":"))
tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
print(f"wrote {OUT}: {tot/1e6:.2f} MB")
for w in ("snow", "night"):
    i = idx[w]; print(w, [words[c] for c in rn[i] if c != 65535][:20], "| gen:", [words[c] for c in gn[i]][:10])
