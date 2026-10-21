"""One-off: build the word-association dataset (v2) for "Related to my word" rhymes.
Vectors: GloVe 6B 100d (glove-wiki-gigaword-100) concatenated with ConceptNet Numberbatch 19.08 (en, 300d), weighted
0.4/0.6, reduced with PCA to DIM dims and quantised to int8. Needs gensim + numpy + the downloads in /tmp (see README);
the output in data/assoc/ is committed, so build/CI never need the raw vectors.
  vocab.json  {"version":2,"dim","words","k_gen","q_per_shard","q_shards","groups":{V:n},"phrase_groups":{V:n}}
  g-<V>.bin   every vocab word whose rhyme part has stressed vowel V: n uint16 ids, then n*DIM int8 vectors
  q-XX.bin    per word (fixed width): DIM int8 "expanded" query vector (word + 0.5*mean of its 10 nearest
              neighbours, i.e. a 2-hop smoothed meaning) then K_GEN uint16 general neighbour ids (65535 = none)
  p-<V>.json  phrase bank entries whose rhyme part has stressed vowel V: [[text, phones, source], ...]
  p-<V>.bin   their int8 vectors (Numberbatch phrase vector when it exists, else mean of the word vectors)
Rhyme candidates are grouped by stressed vowel, so a query only needs its own group(s): every perfect, near,
slant (assonance-based) and assonant rhyme shares that vowel."""
import os, sys, json, re, pickle
import numpy as np
from gensim.models import KeyedVectors
from build_index import rhyme_tail, strip, VOWELS
ROOT = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(ROOT, "data"); OUT = os.path.join(D, "assoc")
GLOVE = os.environ.get("GLOVE", "/tmp/glove/g.model"); NBDIR = os.environ.get("NUMBERBATCH", "/tmp/nb")
TOP = int(os.environ.get("TOP", 60000)); DIM = int(os.environ.get("DIM", 64)); K_GEN = 24; Q_SHARDS = 32
info = pickle.load(open(os.path.join(D, "index.pkl"), "rb"))["info"]
sys.path.insert(0, ROOT)
from engine import STOPWORDS, _stem_clash, phrase_phones
kv = KeyedVectors.load(GLOVE)
nbw = open(os.path.join(NBDIR, "nb.words")).read().split("\n"); nbi = {w: i for i, w in enumerate(nbw)}
NB = np.load(os.path.join(NBDIR, "nb.npy"), mmap_mode="r")
words = [w for w in kv.index_to_key[:TOP] if re.fullmatch(r"[a-z]+", w) and w in info and len(w) > 1]
N = len(words); idx = {w: i for i, w in enumerate(words)}; print("vocab", N)
def unit(M):
    n = np.linalg.norm(M, axis=1, keepdims=True); return np.where(n > 0, M / np.maximum(n, 1e-9), 0).astype(np.float32)
A, B = np.sqrt(0.4), np.sqrt(0.6)
G = unit(np.stack([kv[w] for w in words]))
Nm = unit(np.stack([NB[nbi[w]] if w in nbi else np.zeros(300, np.float32) for w in words]))
C = unit(np.hstack([A * G, B * Nm]))
# general neighbours + expanded query vectors (full dims)
gen = np.full((N, K_GEN), 65535, np.uint16); Q = np.zeros_like(C)
for s in range(0, N, 2048):
    S = C[s:s + 2048] @ C.T
    for r in range(S.shape[0]): S[r, s + r] = -1
    top = np.argpartition(-S, 60, axis=1)[:, :60]
    for r in range(S.shape[0]):
        i = s + r; w = words[i]; order = top[r][np.argsort(-S[r, top[r]])]
        good = [j for j in order if not _stem_clash(w, words[j]) and words[j] not in STOPWORDS]
        gen[i, :min(K_GEN, len(good))] = good[:K_GEN]
        Q[i] = C[i] + 0.5 * C[good[:10]].mean(0) if good else C[i]
Q = unit(Q)
# PCA projection (fit on word vectors), int8 quantisation (cosine is scale-invariant per vector)
mu = C.mean(0); U, Sv, Vt = np.linalg.svd(C[::2] - mu, full_matrices=False); P = Vt[:DIM].T
print("PCA variance kept %.3f" % ((Sv[:DIM] ** 2).sum() / (Sv ** 2).sum()))
def q8(M):
    X = (M - mu) @ P; X /= np.maximum(np.abs(X).max(1, keepdims=True), 1e-9); return np.round(X * 127).astype(np.int8)
C8, Q8 = q8(C), q8(Q)
def svowels(prons):
    out = []
    for p in prons:
        v = [strip(x) for x in rhyme_tail(p.split()) if strip(x) in VOWELS]
        if v and v[0] not in out: out.append(v[0])
    return out
# proper nouns (WordNet: (nearly) every sense is an instance, e.g. monroe, wright) never become rhyme candidates
from nltk.corpus import wordnet as wn
def proper(w):
    ss = wn.synsets(w)
    return bool(ss) and sum(1 for x in ss if x.instance_hypernyms()) / len(ss) >= 0.8
groups = {}
for i, w in enumerate(words):
    if proper(w): continue
    for v in svowels(info[w]["prons"]): groups.setdefault(v, []).append(i)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
for v, ids in groups.items():
    with open(os.path.join(OUT, f"g-{v}.bin"), "wb") as f:
        f.write(np.array(ids, "<u2").tobytes()); f.write(C8[ids].tobytes())
per = (N + Q_SHARDS - 1) // Q_SHARDS
for sh in range(Q_SHARDS):
    a, b = sh * per, min(N, (sh + 1) * per)
    with open(os.path.join(OUT, f"q-{sh:02d}.bin"), "wb") as f:
        for i in range(a, b): f.write(Q8[i].tobytes() + gen[i].astype("<u2").tobytes())
# phrase bank
pg = {}
for line in open(os.path.join(D, "phrases.txt")):
    text, src = line.rstrip("\n").split("\t")
    toks = text.replace("-", " ").split(); ph = phrase_phones(toks, info)
    if not ph: continue
    term = "_".join(toks)
    if term in nbi: nv = np.asarray(NB[nbi[term]], np.float32)
    else:
        cs = [Nm[idx[t]] for t in toks if t in idx and t not in STOPWORDS] or [Nm[idx[t]] for t in toks if t in idx]
        if not cs: continue
        nv = np.mean(cs, 0)
    gs = [G[idx[t]] for t in toks if t in idx and t not in STOPWORDS] or [G[idx[t]] for t in toks if t in idx]
    gv = np.mean(gs, 0) if gs else np.zeros(100, np.float32)
    vec = np.hstack([A * gv / max(np.linalg.norm(gv), 1e-9), B * nv / max(np.linalg.norm(nv), 1e-9)])
    for v in svowels([" ".join(ph)]): pg.setdefault(v, []).append((text, " ".join(ph), src, vec))
for v, items in pg.items():
    json.dump([[t, p, s] for t, p, s, _ in items], open(os.path.join(OUT, f"p-{v}.json"), "w"), separators=(",", ":"))
    open(os.path.join(OUT, f"p-{v}.bin"), "wb").write(q8(unit(np.stack([x[3] for x in items]))).tobytes())
# "lyric vocabulary" prior: words used in the lyric-style phrase bank or the mood themes get a small boost
lyric = set()
for line in open(os.path.join(D, "phrases.txt")):
    text, src = line.rstrip("\n").split("\t")
    if src in ("ai", "wikt"): lyric.update(text.replace("-", " ").split())
th = json.load(open(os.path.join(D, "themes.json")))
for t in th.values(): lyric.update(t["words"])
lyric_ids = sorted(idx[w] for w in lyric if w in idx)
json.dump({"version": 2, "dim": DIM, "lyric": lyric_ids, "k_gen": K_GEN, "q_shards": Q_SHARDS, "q_per_shard": per, "words": words,
           "groups": {v: len(ids) for v, ids in groups.items()}, "phrase_groups": {v: len(x) for v, x in pg.items()},
           "source": "GloVe 6B 100d + ConceptNet Numberbatch 19.08 (CC BY-SA 4.0); phrases: Wiktionary (CC BY-SA), ConceptNet, Workers AI"},
          open(os.path.join(OUT, "vocab.json"), "w"), separators=(",", ":"))
tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
print(f"wrote {OUT}: {tot/1e6:.2f} MB, {sum(len(x) for x in pg.values())} phrase entries")
