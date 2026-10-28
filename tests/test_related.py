"""Related rhymes v2 (GloVe+ConceptNet association x multi-syllable rhyme quality), phrases, brainstorm verify,
AI-line ranking, rhyme density, echo words."""
import os, pytest

def rel(engine, w, **kw): return engine.related(w, limit=1000, **kw)

def test_snow_related_plentiful(engine):
    r = engine.related("snow"); words = [x["word"] for x in r["related"]]; phrases = [p["text"] for p in r["phrases"]]
    assert r["in_vocab"] and len(words) >= 100, len(words)                       # spec: >= 40; target 100-300
    assert len(words) + len(phrases) >= 150
    hits = {"cold", "glow", "below", "frozen", "let it go"} & (set(words) | set(phrases))
    assert len(hits) >= 4, hits
    assert {"blow", "below", "glow", "low", "flow"} & set(words[:20]), words[:20]
    assert any(p.endswith(("go", "glow", "flow", "blow", "ago")) and len(p.split()) >= 3 for p in phrases), phrases[:20]

@pytest.mark.parametrize("w,must", [("night", {"light", "bright", "fight", "sight"}), ("heart", {"apart", "start", "part"}), ("love", {"above"}), ("rain", {"pain"})])
def test_common_words_plentiful(engine, w, must):
    r = engine.related(w); words = [x["word"] for x in r["related"]]
    assert len(words) >= 100 and len(r["phrases"]) >= 20, (len(words), len(r["phrases"]))
    assert must <= set(words[:60]), words[:60]

def test_groups_and_fields(engine):
    r = engine.related("snow")
    g = {x["group"] for x in r["related"]}; assert g <= {"perfect", "multi", "slant"} and len(g) == 3
    assert set(r["groups"]) >= {"perfect", "multi", "slant"}
    multi = [x for x in r["related"] if x["group"] == "multi"]; assert multi and all(x["syllables"] >= 2 for x in multi)
    for x in r["related"]:
        assert x["tier"] in ("perfect", "near", "slant", "assonant") and 0 < x["score"] and x["matched"] >= 0
        if x["group"] == "perfect": assert x["tier"] in ("perfect", "near")
    sc = [x["score"] for x in r["related"]]; assert sc == sorted(sc, reverse=True)
    assert all(x["word"] not in ("so", "though", "snows", "snowy", "thereof") for x in r["related"])
    perfect = {x["word"] for x in r["related"] if x["tier"] == "perfect"}; assert {"below", "low", "slow"} <= perfect

def test_multisyllable_matches(engine):
    r = rel(engine, "frozen"); words = {x["word"]: x for x in r["related"]}
    assert "chosen" in words and words["chosen"]["tier"] == "perfect" and words["chosen"]["matched"] >= 2

def test_related_phrases(engine):
    r = engine.related("snow")
    assert 20 <= len(r["phrases"]) <= 80
    for p in r["phrases"]:
        assert 2 <= len(p["text"].replace("-", " ").split()) <= 6 and p["tier"] in ("perfect", "near", "slant", "assonant")
    sc = [p["score"] for p in r["phrases"]]; assert sc == sorted(sc, reverse=True)
    ends = {}
    for p in r["phrases"]: ends[p["text"].split()[-1]] = ends.get(p["text"].split()[-1], 0) + 1
    assert max(ends.values()) <= 4

def test_related_oov_and_errors(engine):
    r = engine.related("glorbify"); assert not r["in_vocab"] and r["related"] == [] and r["phrases"] == []
    with pytest.raises(ValueError): engine.related("<b>")

def test_related_theme_mode(engine):
    r = engine.rhymes("snow", theme="related", limit=5000)
    on = {x["word"] for x in r["perfect"] if x["themed"]}; assert {"below", "low", "slow"} <= on
    flags = [x["themed"] for x in r["perfect"]]; assert flags == sorted(flags, reverse=True)
    only = engine.rhymes("snow", theme="related", theme_only=True, limit=5000)
    assert only["perfect"] and all(x["themed"] for x in only["perfect"]) and len(only["perfect"]) < len(r["perfect"])

def test_related_min_freq(engine):
    r = engine.related("night", min_freq=4.5)
    assert r["related"] and all(x["freq"] >= 4.5 for x in r["related"])

def test_assoc_data_size():
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "assoc")
    files = os.listdir(d); assert sum(os.path.getsize(os.path.join(d, f)) for f in files) < 16_000_000
    assert max(os.path.getsize(os.path.join(d, f)) for f in files) < 2_500_000   # lazy-loaded per stressed vowel

def test_verify_brainstorm(engine):
    v = engine.verify("snow", ["glow", "let it go", "below zero", "white glow", "cold", "banana", "snow", "<b>", "overflow"])
    by = {x["text"]: x for x in v["items"]}
    assert by["glow"]["group"] == "perfect" and by["let it go"]["group"] == "phrase" and by["let it go"]["tier"] == "perfect"
    assert by["overflow"]["group"] == "multi" and by["white glow"]["tier"] == "perfect"
    assert "banana" not in by and "snow" not in by and "<b>" not in by and "cold" in by and by["cold"]["tier"] in ("slant", "assonant")
    with pytest.raises(ValueError): engine.verify("snow", "nope")
    with pytest.raises(ValueError): engine.verify("snow", ["x"] * 201)

def test_rank_lines(engine):
    r = engine.rank_lines("walking through the falling snow", ["The city sleeps in frozen light", "Feeling the winter in my bones",
        "walking through the falling snow", "Our footprints fading as we go", "The world is hushed and white below", "",
        "I miss you so though", "calling through the crawling snow"])
    by = {x["text"]: x for x in r["lines"]}
    assert by["The world is hushed and white below"]["tier"] == "perfect" and by["walking through the falling snow"]["tier"] == "repeat"
    assert by["I miss you so though"]["filler"] and by["I miss you so though"]["score"] < 40
    assert by["The city sleeps in frozen light"]["tier"] == "none" and not by["The city sleeps in frozen light"]["keep"]
    assert r["end"] == "snow" and r["syllables"] == 7
    sc = [x["score"] for x in r["lines"]]; assert sc == sorted(sc, reverse=True) and all(0 <= s <= 100 for s in sc)
    assert r["lines"][0]["tier"] == "perfect" and r["lines"][0]["keep"]
    assert engine.rank_lines("I love the night", ["we dance till the morning light"])["lines"][0]["tier"] == "perfect"

def test_rank_multi_and_internal_beats_plain(engine):
    r = engine.rank_lines("walking through the falling snow", ["the river by the road below", "the stars are calling, crawling slow"])
    a, b = sorted(r["lines"], key=lambda x: x["text"])
    assert b["text"].startswith("the stars") and b["internal"] >= 1 and b["score"] > a["score"]
    c = engine.rank_lines("my heart is frozen", ["the path I've chosen", "we drank a soda"])["lines"]
    assert c[0]["text"].startswith("the path") and c[0]["tier"] == "perfect"

@pytest.mark.parametrize("args", [("", ["a"]), ("snow", "nope"), ("snow", ["x"] * 41), ("snow", ["x" * 201]), ("x" * 201, ["a"]), ("!!!", ["a"])])
def test_rank_lines_validation(engine, args):
    with pytest.raises(ValueError): engine.rank_lines(*args)

def test_rhyme_density(engine):
    plain = engine.analyze("I went to the store today\nthe weather was fine and warm\nwe ate some bread for lunch")["rhyme_density"]
    dense = engine.analyze("I'm falling, calling, crawling through the night\nstalling, sprawling, balling with the light")["rhyme_density"]
    assert 0 <= plain < dense and dense > 1.0, (plain, dense)
    assert engine.analyze("")["rhyme_density"] == 0

def test_echo_words(engine):
    e = engine.line_help("walking through the falling snow", "")["echo"]
    assert e["word"] == "falling" and {"calling", "crawling"} <= set(e["words"])

def test_rank_parrot_penalty(engine):
    r = {x["text"]: x for x in engine.rank_lines("walking through the falling snow", ["hours pass by like falling dough", "hours pass by like drifting dough"])["lines"]}
    assert r["hours pass by like falling dough"]["multi"] == 0 and r["hours pass by like falling dough"]["score"] < r["hours pass by like drifting dough"]["score"]

def test_rank_sense_and_grammar(engine):
    line = "my heart is beating like a drum"
    c = ["got my fingers snapping to the succumb", "till the feeling in my chest goes numb", "the crowd is cheering waiting for some"]
    r = {x["text"]: x for x in engine.rank_lines(line, c, sense=[9, 9, 9])["lines"]}
    assert r[c[1]]["score"] > r[c[0]]["score"] and r[c[1]]["score"] > r[c[2]]["score"]   # "the succumb" (verb after "the"), dangling "some"
    hi = engine.rank_lines(line, c, sense=[10, 10, 10])["lines"]; lo = engine.rank_lines(line, c, sense=[0, 0, 0])["lines"]
    assert all(a["score"] > b["score"] for a, b in zip(sorted(hi, key=lambda x: x["text"]), sorted(lo, key=lambda x: x["text"])))
    assert {x["sense"] for x in hi} == {10}
    for bad in ([1, 2], [11, 0, 0], ["a", 1, 1], [True, 1, 1]):
        with pytest.raises(ValueError): engine.rank_lines(line, c, sense=bad)

def test_rank_sense_nonsense_penalty(engine):
    lines = ["my fingers tapping out a nervous gum", "till the feeling in my chest goes numb"]
    r = {x["text"]: x for x in engine.rank_lines("my heart is beating like a drum", lines, sense=[2, 8])["lines"]}
    r6 = {x["text"]: x for x in engine.rank_lines("my heart is beating like a drum", lines, sense=[6, 8])["lines"]}
    assert r[lines[0]]["sense"] == 2 and r6[lines[0]]["score"] - r[lines[0]]["score"] >= 35 and r[lines[1]]["score"] > r[lines[0]]["score"]
