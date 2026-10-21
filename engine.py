"""Rhyme engine: loads precomputed indices, answers queries."""
import os, pickle, re, bisect, json, struct
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
        if theme and theme != "related" and theme not in self.themes: raise ValueError("unknown theme")
        tset = (self.related_set(w) if theme == "related" else self.themes.get(theme)) if theme else None
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

# ---------------- related rhymes (word association from GloVe, see build_assoc.py) ----------------
STOPWORDS = set("""a an the and or but if so though although because while since until unless whether as than then that this these
those there here where when what which who whom whose why how it its i me my mine you your yours he him his she her hers we us our
ours they them their theirs one ones be am is are was were been being do does did done doing have has had having can could would
should will shall may might must go goes going gone went get gets got getting just like also very much more most some any all such
only even still well yet both each either neither every about above across after against along among around before behind beside
between beyond during into onto over through under within without upon not no nor too something nothing anything everything someone
anyone everyone thing things stuff way lot many few own same other another okay oh yeah wow ok say says said make makes made know
in on at to for from of with by near off out up down per via mph pm am km two three four five six seven eight nine ten wo ca""".split())
TIER_Q = {"perfect": 1.0, "near": 0.85, "slant": 0.7}
ASSONANT_Q = 0.5

def _stem_clash(w, c):
    return (len(w) >= 4 and c.startswith(w[:4])) or w.startswith(c) or (len(c) >= 4 and w.startswith(c[:4]))

class Assoc:
    """Lazy reader for data/assoc (vocab.json + fixed-width binary shards)."""
    def __init__(self, path=os.path.join(D, "assoc")):
        self.path = path; self._v = None; self._shards = {}
    def _vocab(self):
        if self._v is None:
            v = json.load(open(os.path.join(self.path, "vocab.json")))
            self._v = v; self.words = v["words"]; self.index = {w: i for i, w in enumerate(self.words)}
            self.k1, self.k2, self.per = v["k_rhyme"], v["k_gen"], v["per_shard"]; self.rec = self.k1 * 3 + self.k2 * 2
        return self._v
    def available(self):
        return os.path.exists(os.path.join(self.path, "vocab.json"))
    def neighbours(self, w):
        """([(word, sim), ...] rhyme-eligible neighbours, [word, ...] general neighbours) or None if not in vocab."""
        self._vocab(); i = self.index.get(w)
        if i is None: return None
        sh, off = divmod(i, self.per)
        if sh not in self._shards:
            self._shards[sh] = open(os.path.join(self.path, f"shard-{sh:02d}.bin"), "rb").read()
        b = self._shards[sh]; o = off * self.rec
        ids = struct.unpack_from(f"<{self.k1}H", b, o); sims = b[o + self.k1 * 2:o + self.k1 * 3]
        gen = struct.unpack_from(f"<{self.k2}H", b, o + self.k1 * 3)
        return ([(self.words[c], s / 255) for c, s in zip(ids, sims) if c != 65535], [self.words[c] for c in gen if c != 65535])

def _related(self, word, limit=40, min_freq=None, phrases=12):
    w = self.normalize(word)
    if not WORD_RE.match(w): raise ValueError("invalid word")
    if not hasattr(self, "assoc"): self.assoc = Assoc()
    nb = self.assoc.neighbours(w) if self.assoc.available() else None
    res = {"word": w, "in_vocab": nb is not None, "related": [], "phrases": [], "related_total": 0}
    if nb is None: return res
    rl, gl = nb
    cd = self._candidates(w)
    tier_of = {}
    for t in ("slant", "near", "perfect"):
        for c, _, _ in cd[t]: tier_of[c] = t
    cand = {}
    for c, sim in rl:
        if c == w or _stem_clash(w, c) or c not in self.info or c in STOPWORDS: continue
        t = tier_of.get(c, "assonant"); cand[c] = (sim, t)
    for r, c in enumerate(gl):
        if c in cand or c == w or _stem_clash(w, c) or c not in tier_of or c in STOPWORDS: continue
        cand[c] = (0.6 - 0.01 * r, tier_of[c])
    items = []
    for c, (sim, t) in cand.items():
        inf = self.info[c]
        if min_freq is not None and inf["freq"] < min_freq: continue
        sc = sim * TIER_Q.get(t, ASSONANT_Q)
        items.append({"word": c, "assoc": round(sim, 3), "tier": t, "score": round(sc, 4), "_s": sc, "syllables": inf["syl"],
                      "freq": inf["freq"], "pos": inf["pos"], "conf": inf["conf"]})
    items.sort(key=lambda x: (-x["_s"], x["word"]))
    # phrases: "<associated word> <rhyming ending>" from simple part-of-speech templates
    pool = [(c, sim) for c, sim in rl if c != w and not _stem_clash(w, c) and c in self.info and c not in STOPWORDS] + \
           [(c, 0.6 - 0.01 * r) for r, c in enumerate(gl) if c != w and not _stem_clash(w, c) and c in self.info and c not in STOPWORDS]
    used, out = {}, []
    for e in items[:16]:
        ep = e["pos"]; best = None
        kind = "adj" if "adj" in ep else "adv" if "adv" in ep else "n" if "n" in ep else "v" if "v" in ep else None
        if kind is None: continue
        for c, a in pool:
            if c == e["word"] or used.get(c, 0) >= 2 or _stem_clash(e["word"], c): continue
            pp = self.info[c]["pos"]
            verbish = c.endswith("ing") or ("v" in pp and (c.endswith("s") or c.endswith("ed")))
            if kind in ("adj", "adv") and verbish: text, wgt = f"{c} {e['word']}", 1.0
            elif kind == "n" and "adj" in pp and not verbish: text, wgt = f"the {c} {e['word']}", 1.0
            elif kind == "v" and "n" in pp and "v" not in pp: text, wgt = f"{c} {e['word']}", 1.0
            else: continue
            if best is None or a * wgt > best[1]: best = (text, a * wgt, c)
        if best:
            used[best[2]] = used.get(best[2], 0) + 1
            out.append({"text": best[0], "end": e["word"], "tier": e["tier"], "_s": e["_s"] * best[1], "score": round(e["_s"] * best[1], 4)})
    out.sort(key=lambda x: (-x["_s"], x["text"]))
    for x in items + out: x.pop("_s", None)
    res["related_total"] = len(items); res["related"] = items[:limit]; res["phrases"] = out[:phrases]
    return res

def _related_set(self, w):
    r = _related(self, w, limit=100000, phrases=0)
    s = {x["word"] for x in r["related"]}
    nb = self.assoc.neighbours(w) if r["in_vocab"] else None
    if nb: s.update(c for c in nb[1] if not _stem_clash(w, c))
    return s

Engine.related = _related
Engine.related_set = _related_set

# ---------------- AI line post-check: rank candidate lines by how well they rhyme with the input ----------------
RANK_ORDER = {"perfect": 0, "near": 1, "slant": 2, "assonant": 3, "none": 4, "repeat": 5}

def _stressed_vowels(self, w):
    prons, _, _ = self.pronunciations(w)
    out = set()
    for p in prons:
        v = [strip(x) for x in rhyme_tail(p) if strip(x) in VOWELS]
        if v: out.add(v[0])
    return out

def _rank_lines(self, line, lines):
    if not isinstance(line, str) or not line.strip(): raise ValueError("missing line")
    if not isinstance(lines, list) or len(lines) > 20 or not all(isinstance(x, str) and len(x) <= 200 for x in lines): raise ValueError("invalid lines")
    if len(line) > 200: raise ValueError("line too long")
    src = self.analyze(line.strip())["lines"][0]
    if not src["words"]: raise ValueError("line has no words")
    end = src["end"]; ew = self.word_info(end)
    tiers = {}
    if WORD_RE.match(end):
        cd = self._candidates(end)
        for t in ("slant", "near", "perfect"):
            for c, _, _ in cd[t]: tiers[c] = t
    sv = _stressed_vowels(self, end)
    out = []
    for i, text in enumerate(lines):
        a = self.analyze(text.strip())["lines"][0] if text.strip() else {"words": []}
        if not a["words"]:
            out.append({"text": text, "end": None, "tier": "none", "syllables": 0, "syllable_diff": src["syllables"], "_i": i}); continue
        e = a["end"]
        if e == end: t = "repeat"
        elif e in tiers: t = tiers[e]
        elif set(self.word_info(e)["keys"]) & set(ew["keys"]): t = "perfect"
        elif sv & _stressed_vowels(self, e): t = "assonant"
        else: t = "none"
        out.append({"text": text.strip(), "end": e, "tier": t, "syllables": a["syllables"], "syllable_diff": abs(a["syllables"] - src["syllables"]), "_i": i})
    out.sort(key=lambda x: (RANK_ORDER[x["tier"]], x["syllable_diff"], x["_i"]))
    for x in out: x.pop("_i")
    return {"line": line.strip(), "end": end, "syllables": src["syllables"], "lines": out}

Engine.rank_lines = _rank_lines
