"""One-off: build songwriting theme word sets from full WordNet 3.0 -> data/themes.json (committed).
Needs nltk and the full WordNet files (data.* included): WN_DIR=/path/to/wordnet python build_themes.py
For each preset theme, seed words are expanded through WordNet: synonyms, hyponyms (2 levels), hypernyms,
similar-to/also-see, meronyms/holonyms, derivational forms, topic-domain members and common gloss words;
then inflected forms present in the vocabulary are added. Only words in the Rhymer vocabulary are kept."""
import os, re, json, collections
from nltk.corpus.reader.wordnet import WordNetCorpusReader
ROOT = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(ROOT, "data")
wn = WordNetCorpusReader(os.environ.get("WN_DIR", os.path.expanduser("~/nltk_data/corpora/wordnet")), None)
THEMES = {
    "love": ("Love & romance", "love romance kiss heart desire passion darling embrace sweetheart adore lover honey baby forever tender "
             "devotion yearn crush flame affection beloved cherish true bliss delight sweet charm beauty bride wedding ring rose "
             "together hold touch soulmate valentine smile glow dear divine angel paradise heaven moonlight candlelight"),
    "heartbreak": ("Heartbreak", "heartbreak sorrow grief tear loneliness regret goodbye pain cry lonely broken ache weep mourn sad "
                   "blue empty cold apart gone lost alone farewell betray lie leave tears scar wound shatter fade apart despair "
                   "miss misery hurt bitter cruel rain night"),
    "night": ("Night & dreams", "night darkness moon star midnight dream sleep shadow dusk twilight moonlight starlight light bright "
              "glow candle lantern owl insomnia nightmare lullaby slumber black velvet silence quiet stars sky dawn evening late "
              "neon blackout fright sight"),
    "ocean": ("Ocean & sea", "ocean sea wave tide shore ship sail beach harbor sailor salt sand coast island deep blue anchor storm "
              "mermaid whale dolphin reef foam spray surf current drift boat captain lighthouse pier dock bay gull sea-breeze breeze"),
    "nature": ("Nature", "nature forest tree flower mountain river garden meadow leaf grass bloom seed root branch valley hill "
               "stone moss fern lake stream spring field wild green earth sky bird bee rose pine oak willow sunrise"),
    "weather": ("Weather & sky", "weather rain storm thunder snow wind sun cloud sky lightning hail fog mist breeze frost ice "
                "rainbow drizzle downpour hurricane tornado gale sunshine heat cold winter summer autumn season gray grey"),
    "city": ("City life", "city street building traffic neon subway downtown skyline tower bridge avenue alley block crowd siren "
             "concrete taxi cab bus train station lights rooftop corner sidewalk billboard apartment urban night club"),
    "party": ("Party & dance", "party dance celebration drink club festival dancer music beat bass floor groove wine champagne toast "
              "cheers lights night crowd jump bounce shake spin dj tonight weekend fun wild loud"),
    "money": ("Money & hustle", "money wealth gold cash rich bank price diamond hustle dollar coin fortune treasure jewel pearl "
              "deal profit paid pay bill check spend luxury fame empire crown throne grind boss million"),
    "fire": ("Fire & heat", "fire flame burn heat smoke ash spark blaze ember inferno wildfire torch candle glow fever hot "
             "sun light desire passion ignite match fuel kindle scorch sear melt"),
    "journey": ("Journey & road", "journey road travel path highway train wander voyage drive ride mile map compass horizon "
                "destination trail track bus plane flight station ticket suitcase home away gone far road-trip miles"),
    "war": ("Conflict & war", "war battle fight soldier weapon enemy victory struggle army sword gun bullet blood fire shield "
            "armor siege conquer defeat attack defend hero rebel revolution peace flag march"),
    "faith": ("Faith & spirit", "faith god prayer heaven soul angel church grace hope spirit holy bless pray hymn choir light "
              "glory savior sin redemption believe miracle cross altar divine eternal"),
    "time": ("Time & memory", "time clock hour moment memory past future age remember yesterday tomorrow forever never minute "
             "year season history nostalgia old young youth childhood photograph fade dream"),
    "home": ("Home & family", "home house family mother father child brother sister mom dad baby kitchen porch door window "
             "roof yard town hometown hearth bed table love kin"),
    "food": ("Food & taste", "food meal bread fruit cook taste sweet dinner sugar honey spice salt wine cake pie feast kitchen "
             "apple cherry peach lemon chocolate coffee tea breakfast"),
    "animals": ("Animals", "animal bird dog cat horse wolf fish lion tiger bear eagle crow dove snake fox deer owl bee butterfly"),
    "body": ("Body", "body hand eye blood bone skin face lip heart breath hair mouth tongue finger arm leg knee chest spine soul"),
    "music": ("Music", "music song sing melody rhythm guitar drum singer chord verse chorus beat bass piano note tune harmony "
              "rhyme rap record radio stage band microphone mic hook lyric"),
    "freedom": ("Freedom & escape", "freedom liberty escape fly wild free wing sky bird road run break chain cage open horizon "
                "rebel ride wind away soar flight"),
}
STOP = set("a an the of to in on at by for with from and or but is are was be been as that this it its which who whom whose "
           "what when where how than then into onto over under up down out off not no any some all each every other such "
           "one two used usually especially something someone person thing things very more most".split())
vocab, zipf = set(), {}
for line in open(os.path.join(D, "cmudict.dict"), encoding="utf-8"):
    w = line.split()[0] if line.strip() else ""
    if w: vocab.add(re.sub(r"\(\d+\)$", "", w).lower())
for line in open(os.path.join(D, "extra_words.tsv"), encoding="utf-8"): vocab.add(line.split("\t")[0])
for line in open(os.path.join(D, "zipf.tsv"), encoding="utf-8"):
    w, z = line.rstrip("\n").split("\t"); zipf[w] = float(z)
def lemmas(s): return [l.name().lower() for l in s.lemmas() if "_" not in l.name()]
def expand(seeds):
    score = collections.Counter()
    for seed in seeds.split():
        score[seed] += 10
        syns = []
        for pos, k in (("n", 2), ("v", 1), ("a", 1)):
            syns += wn.synsets(seed, pos)[:k]
        for s in syns:
            for l in lemmas(s): score[l] += 5
            for l in s.lemmas():
                for d in l.derivationally_related_forms():
                    if "_" not in d.name(): score[d.name().lower()] += 3
            rel = set(s.similar_tos()) | set(s.also_sees()) | set(s.part_meronyms()) | set(s.member_meronyms()) \
                | set(s.substance_meronyms()) | set(s.part_holonyms()) | set(s.member_holonyms()) | set(s.in_topic_domains()) | set(s.entailments())
            hypo = list(s.hyponyms())
            if len(hypo) <= 40:
                for h in hypo:
                    rel.add(h)
                    if len(h.hyponyms()) <= 25: rel.update(h.hyponyms())
            for r in rel:
                for l in lemmas(r): score[l] += 2
            for g in re.findall(r"[a-z]+", s.definition().lower()):
                if g not in STOP and 3.5 <= zipf.get(g, 0) < 5.3: score[g] += 1
    return score
def inflect(words):
    out = set(words)
    for w in vocab:
        if w in out or zipf.get(w, 0) < 2: continue
        for suf, rep in (("s", ""), ("es", ""), ("ies", "y"), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("er", ""), ("est", ""), ("ly", ""), ("y", "")):
            if w.endswith(suf):
                b = w[:-len(suf)] + rep
                if b in words or (len(b) > 2 and b[-1] == b[-2] and b[:-1] in words): out.add(w); break
    return out
out = {}
for tid, (label, seeds) in THEMES.items():
    sc = expand(seeds)
    # very common words only count when they are a direct synonym of a seed sense (avoids "make", "move", "get")
    words = {w for w, s in sc.items() if w in vocab and len(w) > 1 and (s >= 5 if zipf.get(w, 0) >= 5.3 else s >= 2)}
    words = inflect(words)
    ranked = sorted(words, key=lambda w: (-(sc.get(w, 0) >= 5), -zipf.get(w, 0), w))[:4000]
    out[tid] = {"label": label, "seeds": seeds.split(), "words": sorted(ranked)}
    print(f"{tid:10s} {len(out[tid]['words']):5d}  e.g. {', '.join(ranked[:12])}")
json.dump(out, open(os.path.join(D, "themes.json"), "w"), separators=(",", ":"))
print("wrote data/themes.json", os.path.getsize(os.path.join(D, "themes.json")) // 1024, "KB")
