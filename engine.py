"""Rhyme engine: loads precomputed indices, answers queries."""
import os, pickle, re, bisect
from build_index import keys, strip, VOWELS, rhyme_tail, segments, cons_sim
SLANT_MIN = 0.6
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
WORD_RE = re.compile(r"^[a-z][a-z'.\-]{0,44}$")

class Engine:
    def __init__(self, path=os.path.join(D, "index.pkl")):
        d = pickle.load(open(path, "rb"))
        self.words, self.info, self.idx, self.suffix = d["words"], d["info"], d["idx"], d["suffix"]
        self.sorted_words = sorted(self.words)
        self._cache = {}

    @staticmethod
    def normalize(w):
        return (w or "").strip().lower()

    def pronunciations(self, w):
        """returns (list of phone lists, guessed: bool, source word)"""
        if w in self.info:
            return [p.split() for p in self.info[w]["prons"]], False, w
        for n in range(min(len(w), 6), 1, -1):  # OOV: borrow tail from longest spelling-suffix match
            src = self.suffix.get(w[-n:])
            if src: return [p.split() for p in self.info[src]["prons"]], True, src
        return [], True, None

    @staticmethod
    def matched_syllables(a, b):
        a, b = [strip(p) for p in a], [strip(p) for p in b]
        n = 0
        for x, y in zip(reversed(a), reversed(b)):
            if x != y: break
            n += x in VOWELS
        return n

    def suggest(self, q, limit=8):
        q = self.normalize(q)
        if not q: return []
        i = bisect.bisect_left(self.sorted_words, q); out = []
        while i < len(self.sorted_words) and self.sorted_words[i].startswith(q) and len(out) < 400:
            out.append(self.sorted_words[i]); i += 1
        out.sort(key=lambda w: (-self.info[w]["freq"], len(w)))
        return out[:limit]

    def _candidates(self, w):
        """unfiltered candidates per tier: list of (word, matched_syllables, slant_score). Cached."""
        hit = self._cache.get(w)
        if hit is not None: return hit
        prons, guessed, src = self.pronunciations(w)
        out = {"prons": prons, "guessed": guessed, "src": src, "perfect": [], "near": [], "slant": []}
        seen = {w}
        ks = [dict(zip(("perfect", "family", "asson", "conson"), keys(ph))) for ph in prons]
        segs = [segments(ph) for ph in prons]
        for tier, name in (("perfect", "perfect"), ("near", "family")):
            for ph, k in zip(prons, ks):
                for i in self.idx[name].get(k[name], ()):
                    c = self.words[i]
                    if c in seen: continue
                    seen.add(c)
                    m = max(self.matched_syllables(ph, q.split()) for q in self.info[c]["prons"]) if tier == "perfect" else 0
                    out[tier].append((c, m, 1.0))
        slant = {}
        for sg, k in zip(segs, ks):
            if k["asson"].startswith("u:"): continue  # no stressed vowel: assonance is meaningless
            for i in self.idx["asson"].get(k["asson"], ()):
                c = self.words[i]
                if c in seen: continue
                sc = max(cons_sim(sg, cs) for cs in self.info[c]["segs"])
                if sc >= SLANT_MIN and sc > slant.get(c, 0): slant[c] = sc
            if sum(len(x) for x in sg) >= 2:  # consonance only when there is a real consonant skeleton
                for i in self.idx["conson"].get(k["conson"], ()):
                    c = self.words[i]
                    if c not in seen and c not in slant: slant[c] = SLANT_MIN
        out["slant"] = [(c, 0, round(sc, 3)) for c, sc in slant.items()]
        if len(self._cache) > 4000: self._cache.clear()
        self._cache[w] = out
        return out

    def rhymes(self, word, syllables=None, pos=None, min_len=None, max_len=None,
               min_freq=None, sort="score", limit=200, include=("perfect", "near", "slant")):
        w = self.normalize(word)
        if not WORD_RE.match(w): raise ValueError("invalid word")
        cd = self._candidates(w)
        res = {"word": w, "known": not cd["guessed"], "guessed_from": cd["src"] if cd["guessed"] else None,
               "pronunciations": [" ".join(p) for p in cd["prons"]], "perfect": [], "near": [], "slant": []}
        pos = set(pos) if pos else None
        key = {"score": lambda x: (-x["matched_syllables"], -x["score"], -x["freq"], x["word"]),
               "freq": lambda x: (-x["freq"], x["word"]), "alpha": lambda x: x["word"],
               "length": lambda x: (x["len"], x["word"]), "syllables": lambda x: (x["syllables"], -x["freq"])}
        for tier in ("perfect", "near", "slant"):
            if tier not in include: continue
            items = []
            for c, m, sc in cd[tier]:
                inf = self.info[c]
                if syllables and inf["syl"] not in syllables: continue
                if pos and not (pos & set(inf["pos"])): continue
                if min_len and inf["len"] < min_len: continue
                if max_len and inf["len"] > max_len: continue
                if min_freq is not None and inf["freq"] < min_freq: continue
                items.append({"word": c, "syllables": inf["syl"], "freq": inf["freq"], "pos": inf["pos"],
                              "len": inf["len"], "matched_syllables": m, "score": sc})
            items.sort(key=key.get(sort, key["score"]))
            res[tier + "_total"] = len(items)
            res[tier] = items[:limit]
        return res
