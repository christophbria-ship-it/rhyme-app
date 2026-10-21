"""Songwriting features: themed rhymes, lyrics analysis (syllables / stress / rhyme scheme) and the line helper."""
import pytest

def test_themes_loaded(engine):
    assert len(engine.themes) == 20 and engine.theme_labels["love"] == "Love & romance"
    assert all(len(v) > 300 for v in engine.themes.values())
    assert {"kiss", "heart", "romance"} <= engine.themes["love"] and {"moon", "starlight"} <= engine.themes["night"]

@pytest.mark.parametrize("word,theme,expected", [("night", "night", {"light", "bright"}), ("fire", "fire", {"desire"}),
                                                  ("feet", "love", {"sweet", "heat"})])
def test_themed_rhymes_marked_and_first(engine, word, theme, expected):
    r = engine.rhymes(word, theme=theme, limit=5000)
    on = {x["word"] for t in ("perfect", "near", "slant") for x in r[t] if x["themed"]}
    assert expected <= on and r["theme"] == theme and r["themed_total"] == len(on)
    for t in ("perfect", "near", "slant"):
        flags = [x["themed"] for x in r[t]]; assert flags == sorted(flags, reverse=True)  # on-theme first

def test_theme_only_and_off(engine):
    r = engine.rhymes("night", theme="night", theme_only=True, limit=5000)
    allx = r["perfect"] + r["near"] + r["slant"]; assert allx and all(x["themed"] for x in allx)
    plain = engine.rhymes("night", limit=5000)
    assert plain["theme"] is None and not any(x["themed"] for x in plain["perfect"]) and plain["themed_total"] == 0
    assert [x["word"] for x in plain["perfect"]] != [x["word"] for x in engine.rhymes("night", theme="night", limit=5000)["perfect"]]

def test_unknown_theme(engine):
    with pytest.raises(ValueError): engine.rhymes("cat", theme="nope")

@pytest.mark.parametrize("line,syl", [("orange silver month", 5), ("The waves were crashing at my feet", 8),
                                      ("I couldn't take it anymore", 8), ("", 0), ("Fire!", 2)])
def test_syllable_counts(engine, line, syl):
    assert engine.analyze(line)["lines"][0]["syllables"] == syl

def test_stress_pattern(engine):
    l = engine.analyze("Shall I compare thee to a summer's day")["lines"][0]
    assert l["syllables"] == 10 and l["words"][2]["stress"] == "u/" and l["words"][-1]["stress"] == "/"
    assert engine.analyze("banana")["lines"][0]["stress"] == "u/u"

@pytest.mark.parametrize("text,scheme", [
    ("I walked along the lonely shore\nThe waves were crashing at my feet\nI couldn't take it anymore\nMy heart was skipping every beat", "ABAB"),
    ("roses are red\nviolets are blue\nsugar is sweet\nand so are you", "ABCB"),
    ("the cat\nthe hat\nthe dog\nthe log", "AABB"),
    ("one two\nred shoe\n\nbig tree\nsee me", "AA AA"),          # letters restart per stanza
])
def test_rhyme_scheme(engine, text, scheme):
    assert engine.analyze(text)["scheme"] == scheme

def test_match_types(engine):
    a = engine.analyze("my love\nthe sky above\nthe month\nonce\nmy love")
    m = [l["match"] for l in a["lines"]]
    assert m == [None, "perfect", None, "near", "repeat"] and a["scheme"] == "AABBA"

def test_unknown_words_and_limits(engine):
    l = engine.analyze("glorbify the zzyzx")["lines"][0]
    assert l["words"][0]["known"] is False and l["words"][0]["syllables"] >= 3 and l["syllables"] >= 5
    with pytest.raises(ValueError): engine.analyze("x" * 10001)
    assert engine.analyze("a\n" * 1000)["total_lines"] == 400

def test_line_helper_fits_meter(engine):
    h = engine.line_help("The waves were crashing at my feet", "My heart was skipping")
    assert h["end_word"] == "feet" and h["target_syllables"] == 8 and h["needed"] == 3 and h["fits_count"]
    sug = h["suggestions"]["perfect"]; assert sug and all(x["syllables"] == 3 for x in sug)
    assert {"incomplete", "obsolete"} & {x["word"] for x in sug}

def test_line_helper_theme_and_fallback(engine):
    h = engine.line_help("The waves were crashing at my feet", "My", theme="love")
    flags = [x["themed"] for x in h["suggestions"]["perfect"]]; assert flags == sorted(flags, reverse=True)
    full = engine.line_help("I walked along the lonely shore", "I walked along the lonely shore and then")
    assert full["needed"] is None and not full["fits_count"] and full["suggestions"]["perfect"]
    assert all(any(c in x["word"] for c in "aeiouy") for t in full["suggestions"].values() for x in t)
    with pytest.raises(ValueError): engine.line_help("  ", "abc")
