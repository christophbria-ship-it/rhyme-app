"""Related rhymes (GloVe association x rhyme quality), phrases, and the AI-line post-check ranking."""
import pytest

def rel(engine, w, **kw): return engine.related(w, limit=1000, **kw)

def test_snow_related(engine):
    r = rel(engine, "snow"); words = [x["word"] for x in r["related"]]
    assert r["in_vocab"] and "cold" in words
    assert {"blow", "blows", "below", "glow", "low", "flow"} & set(words[:20]), words[:20]
    assert {"frozen", "cold", "colder"} & set(words)

def test_night_related(engine):
    words = [x["word"] for x in rel(engine, "night")["related"]]
    assert {"light", "bright", "fight", "sight"} <= set(words[:30]), words[:30]

def test_related_ranking_and_tiers(engine):
    r = rel(engine, "snow")["related"]
    sc = [x["score"] for x in r]; assert sc == sorted(sc, reverse=True)
    q = {"perfect": 1.0, "near": 0.85, "slant": 0.7, "assonant": 0.5}
    for x in r: assert abs(x["score"] - x["assoc"] * q[x["tier"]]) < 0.002 and x["tier"] in q
    assert all(x["word"] not in ("so", "though", "snows", "snowy") for x in r)
    perfect = {x["word"] for x in r if x["tier"] == "perfect"}; assert {"below", "low", "slow"} <= perfect

def test_related_phrases(engine):
    r = engine.related("snow")
    assert 3 <= len(r["phrases"]) <= 12
    ends = {x["word"] for x in rel(engine, "snow")["related"]}
    for p in r["phrases"]:
        n = len(p["text"].split()); assert 2 <= n <= 3 and p["text"].split()[-1] == p["end"] and p["end"] in ends
    sc = [p["score"] for p in r["phrases"]]; assert sc == sorted(sc, reverse=True)

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
    import os
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "assoc")
    assert sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) < 8_000_000

def test_rank_lines(engine):
    r = engine.rank_lines("walking through the falling snow", ["The city sleeps in frozen light", "Feeling the winter in my bones",
        "walking through the falling snow", "Our footprints fading as we go", "The world is hushed and white below", ""])
    tiers = [x["tier"] for x in r["lines"]]
    assert tiers == ["perfect", "perfect", "assonant", "none", "none", "repeat"], tiers
    assert r["lines"][0]["text"] == "The world is hushed and white below" and r["end"] == "snow" and r["syllables"] == 7
    assert engine.rank_lines("I love the night", ["we dance till the morning light"])["lines"][0]["tier"] == "perfect"

@pytest.mark.parametrize("args", [("", ["a"]), ("snow", "nope"), ("snow", ["x"] * 21), ("snow", ["x" * 201]), ("x" * 201, ["a"]), ("!!!", ["a"])])
def test_rank_lines_validation(engine, args):
    with pytest.raises(ValueError): engine.rank_lines(*args)
