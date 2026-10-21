"""Rhyme engine: loads precomputed indices, answers queries."""
import os, pickle, re, bisect, json
from build_index import keys, strip, VOWELS, rhyme_tail, segments, cons_sim
SLANT_MIN = 0.6
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
WORD_RE = re.compile(r"^[a-z][a-z'.\-]{0,44}$")

class Engine:
    def __init__(self, path=os.path.join(D, "index.pkl")):
        d = pickle.load(open(path, "rb"))
        self.words, self.info, self.idx, self.suffix = d["words"], d["info"], d["idx"], d["suffix"]
        self.assonsig = d["assonsig"]
        self.sorted_words = sorted(self.words)
        self._cache = {}
        tp = os.path.join(D, "themes.json")
        t = json.load(open(tp)) if os.path.exists(tp) else {}
        self.themes = {k: set(v["words"]) for k, v in t.items()}
        self.theme_labels = {k: v["label"] for k, v in t.items()}

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
            for sig, ids in self.assonsig.get(k["asson"], {}).items():
                sc = cons_sim(sg, sig)
                if sc < SLANT_MIN: continue
                for i in ids:
                    c = self.words[i]
                    if c not in seen and sc > slant.get(c, 0): slant[c] = sc
            if sum(len(x) for x in sg) >= 2:  # consonance only when there is a real consonant skeleton
                for i in self.idx["conson"].get(k["conson"], ()):
                    c = self.words[i]
                    if c not in seen and c not in slant: slant[c] = SLANT_MIN
        out["slant"] = [(c, 0, round(sc, 3)) for c, sc in slant.items()]
        if len(self._cache) > 4000: self._cache.clear()
        self._cache[w] = out
        return out

    def rhymes(self, word, syllables=None, pos=None, min_len=None, max_len=None,
               min_freq=None, sort="score", limit=200, include=("perfect", "near", "slant"), theme=None, theme_only=False):
        w = self.normalize(word)
        if not WORD_RE.match(w): raise ValueError("invalid word")
        if theme and theme not in self.themes: raise ValueError("unknown theme")
        tset = self.themes.get(theme) if theme else None
        cd = self._candidates(w)
        res = {"word": w, "known": not cd["guessed"], "confidence": self.info[w]["conf"] if w in self.info else "guess", "guessed_from": cd["src"] if cd["guessed"] else None,
               "pronunciations": [" ".join(p) for p in cd["prons"]], "perfect": [], "near": [], "slant": []}
        pos = set(pos) if pos else None
        key = {"score": lambda x: (x["conf"] != "dict", -x["matched_syllables"], -x["score"], -x["freq"], x["word"]),
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
                              "len": inf["len"], "matched_syllables": m, "score": sc, "conf": inf["conf"],
                              "themed": bool(tset) and c in tset})
            if tset is not None and theme_only: items = [x for x in items if x["themed"]]
            items.sort(key=key.get(sort, key["score"]))
            if tset is not None: items.sort(key=lambda x: not x["themed"])  # stable: on-theme words first
            res[tier + "_total"] = len(items)
            res[tier] = items[:limit]
        res["theme"] = theme
        res["themed_total"] = sum(1 for t in ("perfect", "near", "slant") for x in res[t] if x["themed"]) if tset is not None else 0
        return res

    # ---------------- songwriting: lyrics analysis & line helper ----------------
    TOKEN = re.compile(r"[A-Za-z][A-Za-z']*(?:-[A-Za-z']+)*")

    def word_info(self, raw):
        w = raw.lower().strip("'")
        prons, guessed, src = self.pronunciations(w) if w else ([], True, None)
        ph = prons[0] if prons else []
        stress = "".join("/" if p[-1] in "12" else "u" for p in ph if strip(p) in VOWELS)
        if not ph: stress = "u" * max(1, len(re.findall(r"[aeiouy]+", w)))  # crude fallback
        return {"word": raw, "norm": w, "syllables": len(stress), "stress": stress, "known": not guessed,
                "keys": sorted({keys(p)[0] for p in prons}), "fkeys": sorted({keys(p)[1] for p in prons})}

    def analyze(self, text):
        """Per-line syllable counts, stress patterns and a rhyme scheme (letters restart at each blank-line stanza)."""
        if text is None: raise ValueError("missing text")
        if len(text) > 10000: raise ValueError("text too long")
        lines, scheme_parts, stanza = [], [], []
        groups = []  # (letter, perfect keys, family keys, end word) for the current stanza
        def letter(i): return chr(65 + i) if i < 26 else "Z"
        for raw in text.split("\n")[:400]:
            toks = self.TOKEN.findall(raw)
            if not toks:
                lines.append({"text": raw, "words": [], "syllables": 0, "end": None, "letter": None, "match": None})
                if stanza: scheme_parts.append("".join(stanza)); stanza = []; groups = []
                continue
            ws = [self.word_info(t) for t in toks]
            end = ws[-1]; pk, fk = set(end["keys"]), set(end["fkeys"])
            let = match = None
            for g in groups:
                if end["norm"] == g[3]: let, match = g[0], "repeat"; break
                if pk & g[1]: let, match = g[0], "perfect"; break
            if let is None:
                for g in groups:
                    if fk & g[2]: let, match = g[0], "near"; break
            if let is None:
                let = letter(len(groups)); groups.append((let, pk, fk, end["norm"]))
            else:
                for i, g in enumerate(groups):
                    if g[0] == let: groups[i] = (let, g[1] | pk, g[2] | fk, g[3])
            stanza.append(let)
            lines.append({"text": raw, "words": [{k: v for k, v in x.items() if k not in ("keys", "fkeys")} for x in ws],
                          "syllables": sum(x["syllables"] for x in ws), "stress": " ".join(x["stress"] for x in ws),
                          "end": end["norm"], "letter": let, "match": match})
        if stanza: scheme_parts.append("".join(stanza))
        return {"lines": lines, "scheme": " ".join(scheme_parts),
                "total_lines": sum(1 for l in lines if l["words"]), "total_syllables": sum(l["syllables"] for l in lines)}

    def line_help(self, prev, line="", theme=None, limit=40):
        """Suggest end words that rhyme with the previous line and complete `line` to the same syllable count."""
        a = self.analyze((prev or "").strip() + "\n" + (line or "").strip())
        p, l = a["lines"][0], a["lines"][1]
        if not p["words"]: raise ValueError("previous line has no words")
        needed = p["syllables"] - l["syllables"]
        base = dict(theme=theme, limit=limit, sort="score")
        r = self.rhymes(p["end"], syllables=[needed] if needed >= 1 else None, min_freq=2, **base)
        fit = needed >= 1
        if fit and not (r["perfect"] or r["near"]):  # nothing fits the count: fall back to any length
            r = self.rhymes(p["end"], min_freq=2, **base); fit = False
        return {"prev": p, "line": l, "target_syllables": p["syllables"], "needed": needed if needed >= 1 else None,
                "fits_count": fit, "end_word": p["end"], "theme": theme,
                "suggestions": {t: [x for x in r[t] if re.search(r"[aeiouy]", x["word"])] for t in ("perfect", "near", "slant")}}
