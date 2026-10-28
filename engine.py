"""Rhyme engine: loads precomputed indices, answers queries."""
import os, pickle, re, bisect, json, struct, math, operator
from build_index import keys, strip, VOWELS, rhyme_tail, segments, cons_sim, FAM, MANNER
import functools, copy
strip = functools.lru_cache(maxsize=4096)(strip)  # hot path: phone stress-stripping (a few hundred distinct phones)
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
        return {"lines": lines, "scheme": " ".join(scheme_parts), "rhyme_density": self.rhyme_density(text[:10000]),
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
                "fits_count": fit, "end_word": p["end"], "theme": theme, "echo": self.echo(p),
                "suggestions": {t: [x for x in r[t] if re.search(r"[aeiouy]", x["word"])] for t in ("perfect", "near", "slant")}}

# ---------------- shared phonetic helpers: phrase phones, rhyme-tail tiers, multi-syllable vowel matching ----------------
STOPWORDS = set("""a an the and or but if so though although because while since until unless whether as than then that this these
those there here where when what which who whom whose why how it its i me my mine you your yours he him his she her hers we us our
ours they them their theirs one ones be am is are was were been being do does did done doing have has had having can could would
should will shall may might must go goes going gone went get gets got getting just like also very much more most some any all such
only even still well yet both each either neither every about above across after against along among around before behind beside
between beyond during into onto over through under within without upon not no nor too something nothing anything everything someone
anyone everyone thing things stuff way lot many few own same other another okay oh yeah wow ok say says said make makes made know
in on at to for from of with by near off out up down per via mph pm am km two three four five six seven eight nine ten wo ca""".split())
# monosyllabic grammar words lose their stress inside a phrase ("let it GO", "HOLD me"); particles keep it at the end ("give it UP")
FUNC = set("""a an the and or but nor of to in on at for from with by as is it its i me my you your he him his she her we us our they
them their be am are was were if so that this than then do does did not no can will would could should has have had i'm i'll i'd
it's don't can't won't ain't you're we're they're im""".split())
PARTICLES = set("up down out in on off away back over around through along apart aside by".split())
FILLER = set("though tho so too oh ooh yeah yea uh huh it that this then and but or the a an to of just anyway somehow indeed".split())
DETS = {"the", "a", "an", "my", "your", "his", "her", "our", "their", "this", "every", "each"}
TIER_Q = {"perfect": 1.0, "near": 0.85, "slant": 0.7}
ASSONANT_Q = 0.5
REDUCED = {"AH", "IH", "UH"}

def _stem_clash(w, c):
    return (len(w) >= 4 and c.startswith(w[:4])) or w.startswith(c) or (len(c) >= 4 and w.startswith(c[:4]))

def phrase_phones(toks, info, guess=None):
    """phones of a word sequence (first pronunciation of each word), grammar words destressed. None if a word is unknown
    and no `guess` function is given (guess(w) -> phone list or None)."""
    out = []
    for k, t in enumerate(toks):
        t = t.lower().strip("'")
        if not t: continue
        if t in info: ph = info[t]["prons"][0].split()
        elif guess: ph = guess(t)
        else: ph = None
        if not ph: return None
        if t in FUNC and not (k == len(toks) - 1 and t in PARTICLES): ph = [p[:-1] + "0" if p[-1] in "12" else p for p in ph]
        out.extend(ph)
    return out

def _nv(p):
    s = strip(p)
    return "@" if s in REDUCED and p[-1:] == "0" else "AA" if s == "AO" else s  # schwa-like vowels merge; cot-caught merger

def vowel_match(a, b):
    """number of trailing vowels the two phone sequences share (multi-syllable / compound rhyme length)"""
    va = [_nv(p) for p in a if strip(p) in VOWELS]; vb = [_nv(p) for p in b if strip(p) in VOWELS]
    n = 0
    while n < len(va) and n < len(vb) and va[-1 - n] == vb[-1 - n]: n += 1
    return n

def tail_tier(qph, cph):
    """rhyme tier of candidate phones vs query phones, comparing rhyme tails (from the last stressed vowel):
    perfect / near / slant / assonant, or None when the stressed vowels differ."""
    qt, ct = rhyme_tail(qph), rhyme_tail(cph)
    if not qt or not ct or strip(qt[0]) not in VOWELS or strip(qt[0]) != strip(ct[0]): return None
    qv = [p for p in qt if strip(p) in VOWELS]; cv = [p for p in ct if strip(p) in VOWELS]
    if len(qv) != len(cv): return "assonant"
    qn, cn = [_nv(p) for p in qt], [_nv(p) for p in ct]
    if qn == cn: return "perfect"
    fam = lambda xs: [x if x in VOWELS or x == "@" else FAM.get(x, x) for x in xs]
    if fam(qn) == fam(cn): return "near"
    if [_nv(p) for p in qv] != [_nv(p) for p in cv]: return "assonant"
    return "slant" if cons_sim(segments(qt), segments(ct)) >= SLANT_MIN else "assonant"

# ---------------- related rhymes (association vectors, see build_assoc.py) ----------------
class Assoc:
    """Lazy reader for data/assoc v2 (vocab.json, g-<V>.bin vowel groups, q-XX.bin query shards, p-<V> phrase groups)."""
    def __init__(self, path=os.path.join(D, "assoc")):
        self.path = path; self._v = None; self._g = {}; self._q = {}; self._p = {}
    def available(self):
        return os.path.exists(os.path.join(self.path, "vocab.json"))
    def vocab(self):
        if self._v is None:
            v = json.load(open(os.path.join(self.path, "vocab.json")))
            self.words = v["words"]; self.index = {w: i for i, w in enumerate(self.words)}
            self.dim, self.k_gen, self.per = v["dim"], v["k_gen"], v["q_per_shard"]; self._v = v
            self.lyric = {self.words[i] for i in v.get("lyric", [])}
        return self._v
    def query(self, w):
        """(vector, norm, [general neighbour words]) or None"""
        self.vocab(); i = self.index.get(w)
        if i is None: return None
        sh, off = divmod(i, self.per)
        if sh not in self._q: self._q[sh] = open(os.path.join(self.path, f"q-{sh:02d}.bin"), "rb").read()
        rec = self.dim + 2 * self.k_gen; o = off * rec; b = self._q[sh]
        vec = struct.unpack_from(f"<{self.dim}b", b, o); gen = struct.unpack_from(f"<{self.k_gen}H", b, o + self.dim)
        return vec, math.sqrt(sum(x * x for x in vec)), [self.words[g] for g in gen if g != 65535]
    def group(self, v):
        """[(word, vector, norm)] for vowel group v"""
        if v not in self._g:
            self.vocab(); n = self._v["groups"].get(v, 0); out = []
            if n:
                b = open(os.path.join(self.path, f"g-{v}.bin"), "rb").read()
                ids = struct.unpack_from(f"<{n}H", b, 0)
                for k, i in enumerate(ids):
                    vec = struct.unpack_from(f"<{self.dim}b", b, 2 * n + k * self.dim)
                    out.append((self.words[i], vec, math.sqrt(sum(x * x for x in vec))))
            self._g[v] = out
        return self._g[v]
    def lookup(self, v, w):
        """(vector, norm) of word w inside vowel group v, or None"""
        if not hasattr(self, "_gm"): self._gm = {}
        if v not in self._gm: self._gm[v] = {c: (vec, n) for c, vec, n in self.group(v)}
        return self._gm[v].get(w)
    def phrases(self, v):
        """[(text, phones, source, vector, norm)] for vowel group v"""
        if v not in self._p:
            self.vocab(); n = self._v["phrase_groups"].get(v, 0); out = []
            if n:
                meta = json.load(open(os.path.join(self.path, f"p-{v}.json")))
                b = open(os.path.join(self.path, f"p-{v}.bin"), "rb").read()
                for k, (t, ph, src) in enumerate(meta):
                    vec = struct.unpack_from(f"<{self.dim}b", b, k * self.dim)
                    out.append((t, ph.split(), src, vec, math.sqrt(sum(x * x for x in vec))))
            self._p[v] = out
        return self._p[v]

def coda_sim(a, b):
    """0..1 similarity of two consonant codas (lists of phones): greedy best matches, identical 1 / family .6 / manner .4"""
    if not a and not b: return 1.0
    if not a or not b: return 0.3
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    pool = list(long_); tot = 0.0
    for x in short:
        best, bi = 0.0, -1
        for k, y in enumerate(pool):
            s = 1.0 if x == y else 0.6 if FAM.get(x) == FAM.get(y) else 0.4 if MANNER.get(x) == MANNER.get(y) else 0.0
            if s > best: best, bi = s, k
        if bi >= 0: pool.pop(bi)
        tot += best
    return tot / len(long_)

def _coda(ph):
    t = [strip(p) for p in rhyme_tail(ph)]
    return t[1:] if len(t) > 0 and t[0] in VOWELS and not any(x in VOWELS for x in t[1:]) else None

def _cos(a, na, b, nb):
    return sum(map(operator.mul, a, b)) / (na * nb) if na and nb else 0.0

A_MIN, A_MIN_RHYME, P_MIN = 0.12, 0.05, 0.2         # association floors for words / phrases (cosine in the reduced space)
SRC_W = {"ai": 1.0, "wikt": 0.9, "cn": 0.5, "combo": 0.8}
LYRIC_BOOST = 1.35
# pure grammar words never make useful related rhymes (but verbs like go / know / say do)
REL_STOP = FUNC | set("""these those there here where when what which who whom whose why how mine yours hers ours theirs one ones been
being doing having shall may might must also very much more most some any all such only even still both each either neither every
about after against among during into onto over through under nor too something nothing anything everything someone anyone everyone okay oh yeah wow ok per via mph pm km wo ca
though although because while since until unless whether thereof whereof hereof ceo cfo cto joe mike bordeaux""".split())
GROUP_ORDER = ("perfect", "multi", "slant")

def _svowels_ph(prons):
    out = []
    for p in prons:
        v = [strip(x) for x in rhyme_tail(p) if strip(x) in VOWELS]
        if v and v[0] not in out: out.append(v[0])
    return out

def _related(self, word, limit=300, min_freq=None, phrases=80):
    w = self.normalize(word)
    if not WORD_RE.match(w): raise ValueError("invalid word")
    if not hasattr(self, "assoc"): self.assoc = Assoc()
    A = self.assoc
    q = A.query(w) if A.available() else None
    res = {"word": w, "in_vocab": q is not None, "related": [], "phrases": [], "related_total": 0, "phrase_total": 0,
           "groups": {g: 0 for g in GROUP_ORDER}}
    if q is None: return res
    qv, qn_, gen = q
    cd = self._candidates(w)
    tier_of = {}
    for t in ("slant", "near", "perfect"):
        for c, m, _ in cd[t]: tier_of[c] = (t, m)
    qph = cd["prons"][0] if cd["prons"] else []
    qtail_v = sum(1 for p in rhyme_tail(qph) if strip(p) in VOWELS) if qph else 1
    qcoda = _coda(qph) if qph else None
    items, seen = [], {w}
    for v in _svowels_ph(cd["prons"]):
        for c, vec, n in A.group(v):
            if c in seen or _stem_clash(w, c) or c in REL_STOP or c not in self.info: continue
            seen.add(c); inf = self.info[c]
            if not inf["pos"] and c not in A.lyric: continue  # mostly names / foreign words
            if min_freq is not None and inf["freq"] < min_freq: continue
            a = _cos(qv, qn_, vec, n)
            t, m = tier_of.get(c, ("assonant", 0))
            if a < (A_MIN_RHYME if t in ("perfect", "near") else A_MIN): continue
            vm = max(vowel_match(qph, p.split()) for p in self.info[c]["prons"][:2]) if qph else 0
            ml = max(m, vm)
            qual = TIER_Q.get(t, ASSONANT_Q)
            if t == "assonant":
                if qtail_v >= 2 and vm >= qtail_v: qual = 0.65  # whole vowel run matches: frozen ~ golden
                ctail = min(sum(1 for x in rhyme_tail(p.split()) if strip(x) in VOWELS) for p in inf["prons"][:2])
                for _ in range(max(0, ctail - qtail_v)): qual *= 0.7  # trailing extra syllables weaken assonance: snow ~ cold > overcast
                if qcoda is not None:  # one-syllable rhyme part: how close are the final consonants? heart ~ dark > shock > cause
                    cc = [x for x in (_coda(p.split()) for p in inf["prons"][:2]) if x is not None]
                    if cc: qual *= 0.2 + 0.8 * max(coda_sim(qcoda, x) for x in cc)
            if ml >= 2: qual *= 1.0 + 0.15 * (ml - 1)
            if c in A.lyric: qual *= LYRIC_BOOST
            elif inf["freq"] < 3.5: qual *= 0.8
            sc = a * qual
            if sc < 0.07: continue
            if (qtail_v >= 2 and ml >= 2) or (qtail_v == 1 and t in ("perfect", "near") and inf["syl"] >= 2): g = "multi"
            elif t in ("perfect", "near"): g = "perfect"
            else: g = "slant"
            items.append({"word": c, "assoc": round(a, 3), "tier": t, "group": g, "matched": ml, "score": round(sc, 4), "_s": sc,
                          "syllables": inf["syl"], "freq": inf["freq"], "pos": inf["pos"], "conf": inf["conf"]})
    items.sort(key=lambda x: (-x["_s"], x["word"]))
    # phrases: phrase bank entries whose rhyme part rhymes with the word, ranked by association x rhyme x source
    out, pseen = [], set()
    for v in _svowels_ph(cd["prons"]):
        for text, ph, src, vec, n in A.phrases(v):
            if text in pseen or src == "cn": continue  # ConceptNet phrases were mostly junk ("cardiac part")
            toks = text.split()
            parts = text.replace("-", " ").split()
            if any(x == w or _stem_clash(w, x) for x in parts): continue  # "quick-fire" repeats, doesn't rhyme
            if any(len(x) == 1 and x not in ("a", "i") for x in parts): continue  # "e-thumb"
            t = tail_tier(qph, ph) if qph else None
            if t is None: continue
            vm = vowel_match(qph, ph)
            if t == "assonant" and vm < 2: continue
            a = _cos(qv, qn_, vec, n)
            if a < P_MIN: continue
            sc = a * TIER_Q.get(t, ASSONANT_Q) * SRC_W.get(src, 0.7) * (1.0 + 0.15 * max(0, vm - qtail_v))
            if src == "wikt" and len(parts) == 2: sc *= 0.6  # two-word dictionary compounds ("side part") are rarely lyrical
            pseen.add(text)
            out.append({"text": text, "end": toks[-1], "tier": t, "source": src, "score": round(sc, 4), "_s": sc})
    out.sort(key=lambda x: (-x["_s"], x["text"]))
    per_end, kept = {}, []
    for x in out:  # variety: at most 4 phrases per ending word
        if per_end.get(x["end"], 0) < 4: kept.append(x); per_end[x["end"]] = per_end.get(x["end"], 0) + 1
    out = kept
    for x in items + out: x.pop("_s", None)
    res["related_total"] = len(items); res["related"] = items[:limit]
    res["phrase_total"] = len(out); res["phrases"] = out[:phrases]
    for x in items: res["groups"][x["group"]] += 1
    return res

def _related_set(self, w):
    r = _related(self, w, limit=100000, phrases=0)
    s = {x["word"] for x in r["related"]}
    q = self.assoc.query(w) if r["in_vocab"] else None
    if q: s.update(c for c in q[2] if not _stem_clash(w, c))
    return s

_REL_CACHE = {}
def _related_cached(self, word, *a, **kw):
    key = (word, a, tuple(sorted(kw.items())))
    hit = _REL_CACHE.get(key)
    if hit is None:
        hit = _related(self, word, *a, **kw)
        if len(_REL_CACHE) >= 256: _REL_CACHE.pop(next(iter(_REL_CACHE)))
        _REL_CACHE[key] = hit
    return copy.deepcopy(hit)
Engine.related = _related_cached
Engine.related_set = _related_set

# ---------------- verify AI brainstorm items against the rhyme engine ----------------
def _verify(self, word, items):
    w = self.normalize(word)
    if not WORD_RE.match(w): raise ValueError("invalid word")
    if not isinstance(items, list) or len(items) > 200 or not all(isinstance(x, str) and 0 < len(x) <= 60 for x in items): raise ValueError("invalid items")
    cd = self._candidates(w); qph = cd["prons"][0] if cd["prons"] else []
    tier_of = {}
    for t in ("slant", "near", "perfect"):
        for c, m, _ in cd[t]: tier_of[c] = t
    qtail_v = sum(1 for p in rhyme_tail(qph) if strip(p) in VOWELS) if qph else 1
    guess = lambda t: (self.pronunciations(t)[0] or [None])[0]
    out, seen = [], set()
    for raw in items:
        text = re.sub(r"\s+", " ", re.sub(r"[^a-z' \-]", " ", raw.lower())).strip()
        toks = text.replace("-", " ").split()
        if not toks or text in seen or toks[-1] == w: continue
        seen.add(text)
        if len(toks) == 1 and toks[0] in tier_of: t = tier_of[toks[0]]
        else:
            ph = phrase_phones(toks, self.info, guess)
            t = tail_tier(qph, ph) if ph and qph else None
        if t is None: continue
        ph = phrase_phones(toks, self.info, guess) or []
        vm = vowel_match(qph, ph) if qph else 0
        if t == "assonant" and vm < 2 and len(toks) > 1: continue
        syl = sum(1 for p in ph if strip(p) in VOWELS)
        if len(toks) > 1: g = "phrase"
        elif (qtail_v >= 2 and vm >= 2) or (qtail_v == 1 and t in ("perfect", "near") and syl >= 2): g = "multi"
        elif t in ("perfect", "near"): g = "perfect"
        else: g = "slant"
        out.append({"text": text, "tier": t, "group": g, "matched": vm, "syllables": syl})
    return {"word": w, "items": out}

Engine.verify = _verify

# ---------------- AI line post-check: score candidate lines like a songwriter would ----------------
RANK_ORDER = {"perfect": 0, "near": 1, "slant": 2, "assonant": 3, "none": 4, "repeat": 5}
TIER_BASE = {"perfect": 55, "near": 47, "slant": 38, "assonant": 26, "none": 0, "repeat": 4}
CLICHES = ["deep inside", "end of time", "set me free", "heart of stone", "fire in my soul", "like the rain", "shining star",
           "never let you go", "break my heart", "burning bright", "dark of night", "dreams come true", "all night long",
           "by my side", "touch the sky", "light the way", "heart and soul", "shattered dreams", "lost in your eyes",
           "whispers in the wind", "dance in the rain", "stars above", "fly so high", "cold as ice", "white as snow",
           "winter wonderland", "feel so alive", "forever and always", "rise above", "spread my wings", "against the odds",
           "tear me apart", "take my breath away", "heart beats", "in the moonlight", "come what may"]

def _stressed_vowels(self, w):
    prons, _, _ = self.pronunciations(w)
    out = set()
    for p in prons:
        v = [strip(x) for x in rhyme_tail(p) if strip(x) in VOWELS]
        if v: out.add(v[0])
    return out

def _line_phones(self, toks):
    guess = lambda t: (self.pronunciations(t)[0] or [None])[0]
    return phrase_phones(toks[-4:], self.info, guess) or []

def _internal(self, toks):
    """internal rhyme pairs among the line's content words (same rhyme key, different words)"""
    ks = {}
    for t in toks:
        t = t.lower().strip("'")
        if t in STOPWORDS or len(t) < 2: continue
        wi = self.word_info(t)
        for k in wi["keys"][:1]: ks.setdefault(k.replace("AO", "AA"), set()).add(t)
    return sum(len(v) - 1 for v in ks.values() if len(v) > 1)

def _rank_lines(self, line, lines, keep=8, sense=None):
    if not isinstance(line, str) or not line.strip(): raise ValueError("missing line")
    if sense is not None and not (isinstance(sense, list) and len(sense) == len(lines) and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 10 for x in sense)):
        raise ValueError("invalid sense")
    if not isinstance(lines, list) or len(lines) > 40 or not all(isinstance(x, str) and len(x) <= 200 for x in lines): raise ValueError("invalid lines")
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
    stoks = self.TOKEN.findall(line); sph = _line_phones(self, stoks)
    if not hasattr(self, "assoc"): self.assoc = Assoc()
    qa = self.assoc.query(end) if self.assoc.available() and WORD_RE.match(end) else None
    evs = _svowels_ph(self.pronunciations(end)[0]) if qa else []
    tail_v = sum(1 for p in rhyme_tail(self.pronunciations(end)[0][0]) if strip(p) in VOWELS) if self.pronunciations(end)[0] else 1
    out = []
    for i, text in enumerate(lines):
        a = self.analyze(text.strip())["lines"][0] if text.strip() else {"words": []}
        if not a["words"]:
            out.append({"text": text, "end": None, "tier": "none", "syllables": 0, "syllable_diff": src["syllables"], "multi": 0,
                        "internal": 0, "filler": False, "cliche": False, "assoc": None, "sense": None, "score": 0, "_i": i}); continue
        e = a["end"]
        if e == end: t = "repeat"
        elif e in tiers: t = tiers[e]
        elif set(self.word_info(e)["keys"]) & set(ew["keys"]): t = "perfect"
        elif sv & _stressed_vowels(self, e): t = "assonant"
        else: t = "none"
        toks = self.TOKEN.findall(text)
        filler = e in FILLER and end not in FILLER
        vm = vowel_match(sph, _line_phones(self, toks)) if t in ("perfect", "near", "slant", "assonant") else 0
        multi = max(0, vm - tail_v)
        # parroting the input's lead-in word ("falling snow" -> "falling dough") is a template swap, not a multi rhyme
        parrot = len(toks) >= 2 and len(stoks) >= 2 and toks[-2].lower() == stoks[-2].lower() and t != "repeat"
        if parrot: multi = 0
        internal = _internal(self, toks[:-1] + [e])
        sd = abs(a["syllables"] - src["syllables"])
        low = " " + " ".join(x.lower() for x in toks) + " "
        cliche = any(" " + c + " " in low for c in CLICHES)
        sc = TIER_BASE[t] * (0.35 if filler else 1.0)
        if t not in ("none", "repeat") and not filler: sc += min(20, 10 * multi)
        sc += min(12, 4 * internal)
        sc += {0: 13, 1: 10, 2: 4}.get(sd, -8 * (sd - 2))
        if cliche: sc -= 15
        if parrot: sc -= 10
        if len(toks) >= 2 and toks[-2].lower() in DETS and e in self.info and self.info[e]["pos"] and "n" not in self.info[e]["pos"]: sc -= 20  # "to the succumb"
        if not filler and e in STOPWORDS and e not in PARTICLES and end not in STOPWORDS: sc -= 15  # dangling "from"/"them"/"some"
        if len(toks) < 3: sc -= 10
        ef = self.info[e]["freq"] if e in self.info else 0
        if t not in ("none", "repeat"): sc -= 12 if ef < 3.0 else 6 if ef < 3.5 else 0  # forced, obscure rhyme words
        coh = None
        if qa and t in ("perfect", "near", "slant", "assonant"):
            for v in evs:
                hit = self.assoc.lookup(v, e)
                if hit: coh = _cos(qa[0], qa[1], hit[0], hit[1]); break
            if coh is not None: sc += 6 if coh >= 0.3 else 3 if coh >= 0.18 else -6 if coh < 0.06 else 0  # does the rhyme word belong?
        sc += max(0, 6 - i // 4)  # the model lists its best ideas first
        sn = None
        if sense is not None and t not in ("none", "repeat"):
            sn = round(sense[i]); sc += max(-30, min(20, (sn - 6) * 5))
            if sn <= 3: sc -= 15  # editor pass rated it nonsense / forced
        out.append({"text": text.strip(), "end": e, "tier": t, "syllables": a["syllables"], "syllable_diff": sd, "multi": multi,
                    "internal": internal, "filler": filler, "cliche": cliche, "assoc": round(coh, 3) if coh is not None else None, "sense": sn,
                    "score": max(0, min(100, round(sc))), "_i": i})
    # variety: penalise reused end words and near-duplicate lines (bag of content words)
    out.sort(key=lambda x: (-x["score"], x["_i"]))
    ends, bags = {}, []
    for x in out:
        if x["end"] is None: continue
        bag = {t.lower() for t in self.TOKEN.findall(x["text"]) if t.lower() not in STOPWORDS}
        pen = 0
        if ends.get(x["end"], 0): pen += 15 * ends[x["end"]]
        if any(bag and len(bag & b) / len(bag | b) >= 0.6 for b in bags): pen += 25
        x["score"] = max(0, x["score"] - pen); ends[x["end"]] = ends.get(x["end"], 0) + 1; bags.append(bag)
    out.sort(key=lambda x: (-x["score"], RANK_ORDER[x["tier"]], x["syllable_diff"], x["_i"]))
    for k, x in enumerate(out):
        x["keep"] = k < keep and x["score"] >= 40 and x["tier"] != "none"; x.pop("_i")
    return {"line": line.strip(), "end": end, "syllables": src["syllables"], "lines": out}

Engine.rank_lines = _rank_lines

# ---------------- rhyme density (Malmi et al. 2016: mean longest vowel-sequence match per word vs the previous 15 words) ----------------
def rhyme_density(self, text):
    seq, ends = [], []  # vowel stream (stress-less) and, per word, (index of its last vowel, word)
    for raw in self.TOKEN.findall(text or ""):
        w = raw.lower().strip("'"); prons = self.pronunciations(w)[0]
        vs = [strip(p).replace("AO", "AA") for p in prons[0] if strip(p) in VOWELS] if prons else []
        if not vs: continue
        seq.extend(vs); ends.append((len(seq) - 1, w))
    if len(ends) < 2: return 0.0
    tot = 0
    for k in range(1, len(ends)):
        pi, wi = ends[k]; best = 0
        for j in range(max(0, k - 15), k):
            pj, wj = ends[j]
            if wj == wi: continue
            n = 0
            while pj - n >= 0 and pi - n > pj and seq[pi - n] == seq[pj - n]: n += 1
            best = max(best, n)
        tot += best
    return round(tot / (len(ends) - 1), 3)

Engine.rhyme_density = rhyme_density

# ---------------- vowel "echo" words for multi-syllable rhymes: same vowels from the stressed syllable on ----------------
def _echo(self, pline, limit=12):
    """For the word before the line's end word (e.g. "falling" in "...the falling snow"): common words with the same
    stressed-vowel pattern (calling, crawling, stalling) - building blocks for multi-syllable and internal rhymes."""
    ws = pline["words"] if pline else []
    if len(ws) < 2: return None
    w = ws[-2]["norm"]
    if w in STOPWORDS or w not in self.info: return None
    best = {}
    for p in self.info[w]["prons"][:1]:
        ph = p.split(); k = keys(ph)[2]; sg = segments(ph)
        if k.startswith("u:"): continue
        ks = {k, " ".join("AO" if x == "AA" else x for x in k.split()), " ".join("AA" if x == "AO" else x for x in k.split())}
        for kk in sorted(ks):
            for sig, ids in self.assonsig.get(kk, {}).items():
                sc = cons_sim(sg, sig)
                if sc < 0.5: continue
                for i in ids:
                    c = self.words[i]; inf = self.info[c]
                    if c == w or c in STOPWORDS or inf["freq"] < 3.5 or not inf["pos"] or "'" in c or _stem_clash(w, c): continue
                    if sc > best.get(c, 0): best[c] = sc
    out = [(-round(sc, 3), -self.info[c]["freq"], c) for c, sc in best.items()]
    out.sort()
    return {"word": w, "words": [c for _, _, c in out[:limit]]} if out else None

Engine.echo = _echo
