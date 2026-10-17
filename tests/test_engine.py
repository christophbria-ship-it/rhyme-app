import pytest
def words(r, tier): return {x["word"] for x in r[tier]}

def test_vocab_size(engine): assert len(engine.words) > 120000

@pytest.mark.parametrize("w,expected", [
    ("cat", {"hat", "bat", "that", "flat"}), ("light", {"night", "bright", "write", "bite"}),
    ("phlegm", {"them", "gem", "stem"}),          # uncommon spelling
    ("colonel", {"journal", "eternal", "kernel"}), # spelling unrelated to sound
    ("through", {"blue", "do", "true"}), ("tough", {"rough", "stuff", "enough"}),
    ("silver", {"quicksilver"}),                    # multi-syllable perfect
    ("nation", {"station", "creation", "relation"}),
    ("computer", {"commuter", "polluter"}),
])
def test_perfect(engine, w, expected):
    assert expected <= words(engine.rhymes(w, limit=5000), "perfect")

def test_multisyllable_score(engine):
    r = engine.rhymes("nation", limit=5000)
    m = {x["word"]: x["matched_syllables"] for x in r["perfect"]}
    assert m["station"] == 2 and m["dissipation"] >= 2
    r = engine.rhymes("combat", limit=5000)
    assert {x["word"]: x["matched_syllables"] for x in r["perfect"]}.get("wombat", 0) >= 2

@pytest.mark.parametrize("w", ["orange", "month", "purple"])
def test_famously_hard_words_get_near_or_slant(engine, w):
    r = engine.rhymes(w, limit=5000)
    assert r["known"] and len(r["near"]) + len(r["slant"]) > 0
    assert w not in words(r, "perfect") | words(r, "near") | words(r, "slant")

def test_month_near(engine): assert "once" in words(engine.rhymes("month", limit=5000), "near")
def test_orange_no_common_perfect(engine):
    assert not [x for x in engine.rhymes("orange")["perfect"] if x["freq"] >= 3]
def test_purple_near(engine): assert {"circle", "turtle"} <= words(engine.rhymes("purple", limit=5000), "near")

def test_tiers_disjoint(engine):
    r = engine.rhymes("love", limit=100000)
    p, n, s = words(r, "perfect"), words(r, "near"), words(r, "slant")
    assert not (p & n) and not (p & s) and not (n & s) and "dove" in p

def test_oov_guess(engine):
    r = engine.rhymes("glorbify")
    assert not r["known"] and r["guessed_from"] and len(r["perfect"]) > 0
    assert "identify" in words(engine.rhymes("zzentify", limit=5000), "perfect")

def test_oov_nothing(engine):
    r = engine.rhymes("q")
    assert isinstance(r["perfect"], list)

def test_case_and_whitespace(engine):
    assert engine.rhymes("  CAT ")["word"] == "cat"

@pytest.mark.parametrize("bad", ["", "123", "a b<script>", "x" * 60])
def test_invalid(engine, bad):
    with pytest.raises(ValueError): engine.rhymes(bad)

def test_filters(engine):
    r = engine.rhymes("cat", syllables=[2], pos=["n"], min_len=5, max_len=8, min_freq=2, limit=5000)
    allx = r["perfect"] + r["near"] + r["slant"]
    assert allx and all(x["syllables"] == 2 and "n" in x["pos"] and 5 <= x["len"] <= 8 and x["freq"] >= 2 for x in allx)

def test_sorts(engine):
    f = [x["freq"] for x in engine.rhymes("day", sort="freq")["perfect"]]; assert f == sorted(f, reverse=True)
    a = [x["word"] for x in engine.rhymes("day", sort="alpha")["perfect"]]; assert a == sorted(a)
    l = [x["len"] for x in engine.rhymes("day", sort="length")["perfect"]]; assert l == sorted(l)

def test_suggest(engine):
    s = engine.suggest("rhy"); assert "rhyme" in s and len(s) <= 8
    assert engine.suggest("") == [] and engine.suggest("zzzzqqq") == []

# ---- tighter slant rhymes ----
JUNK = {"the", "a", "of", "and", "to", "it", "is", "what", "have", "that", "was", "but", "just", "up", "one"}
@pytest.mark.parametrize("w", ["cat", "month", "dog", "love", "day", "go", "it", "night"])
def test_slant_no_function_word_junk(engine, w):
    s = words(engine.rhymes(w, limit=100000), "slant")
    assert not (s & (JUNK - {w})), s & JUNK

@pytest.mark.parametrize("w", ["cat", "month", "silver", "orange", "love", "dog"])
def test_slant_shares_stressed_vowel_or_consonants(engine, w):
    from build_index import rhyme_tail, strip, VOWELS
    def sv(ph): return next(strip(p) for p in rhyme_tail(ph) if strip(p) in VOWELS)
    tv = {sv(p.split()) for p in engine.info[w]["prons"]}
    r = engine.rhymes(w, limit=100000)
    for x in r["slant"]:
        assert x["score"] >= 0.6
        cv = {sv(p.split()) for p in engine.info[x["word"]]["prons"]}
        if not (tv & cv):  # consonance-only matches must keep the full consonant skeleton
            assert x["score"] == 0.6

def test_slant_examples(engine):
    assert {"bad", "camp"} & words(engine.rhymes("cat", limit=100000), "slant")
    s = words(engine.rhymes("cat", limit=100000), "slant"); assert "cash" not in s and "back" not in s
    assert {"storage", "porridge"} <= words(engine.rhymes("orange", limit=100000), "slant")
    assert {"river", "deliver"} <= words(engine.rhymes("silver", limit=100000), "slant")

def test_slant_volume_reasonable(engine):
    for w in ["cat", "month", "dog", "it"]:
        assert engine.rhymes(w, min_freq=3, limit=100000)["slant_total"] < 400

def test_slant_sorted_by_score(engine):
    sc = [x["score"] for x in engine.rhymes("silver", limit=100000)["slant"]]; assert sc == sorted(sc, reverse=True)

# ---- POS for inflected forms ----
@pytest.mark.parametrize("w,tag", [("cats", "n"), ("churches", "n"), ("studies", "n"), ("walked", "v"), ("stopped", "v"),
                                   ("running", "v"), ("happier", "adj"), ("biggest", "adj"), ("rhymes", "n")])
def test_inflected_pos(engine, w, tag): assert tag in engine.info[w]["pos"]

def test_pos_coverage(engine):
    assert sum(1 for v in engine.info.values() if v["pos"]) > 50000
